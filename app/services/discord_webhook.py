import logging
import queue
import threading
import time
from datetime import datetime, timezone
from typing import Callable, Optional

import requests

from app.core.server_events import EventBus, ServerEvent

logger = logging.getLogger(__name__)

_RATE_LIMIT_SECONDS = 2
_POST_TIMEOUT = 10
_MAX_429_WAIT = 30
_PLAYER_FLUSH_DELAY = 3.0

# Internal queue sentinel for the coalesced player join/leave message.
_PLAYERS_FLUSH = "_players_flush"

_EVENT_LABELS = {
    ServerEvent.CRASHED: ("Server Crashed", 0xFF0000),
    ServerEvent.READY: ("Server Ready", 0x57F287),
    ServerEvent.STOPPED: ("Server Stopped", 0x99AAB5),
    ServerEvent.RESTARTED: ("Server Restarted", 0xF1C40F),
    ServerEvent.ZOMBIE_DETECTED: ("Server Unresponsive", 0xE74C3C),
    ServerEvent.LAG_SPIKE: ("Lag Detected", 0xE67E22),
    ServerEvent.TUNNEL_STATUS: ("Tunnel Online", 0x9B59B6),
    ServerEvent.PLAYER_LIST: ("Players", 0x3498DB),
    ServerEvent.BACKUP_COMPLETED: ("Backup Completed", 0x3498DB),
    ServerEvent.BACKUP_FAILED: ("Backup Failed", 0xE67E22),
}

# Settings key (webhook_events dict) -> ServerEvent
SETTING_EVENT_KEYS = {
    "crashed": ServerEvent.CRASHED,
    "ready": ServerEvent.READY,
    "stopped": ServerEvent.STOPPED,
    "restarted": ServerEvent.RESTARTED,
    "zombie_detected": ServerEvent.ZOMBIE_DETECTED,
    "lag_spike": ServerEvent.LAG_SPIKE,
    "tunnel_online": ServerEvent.TUNNEL_STATUS,
    "player_joins": ServerEvent.PLAYER_LIST,
    "backup_completed": ServerEvent.BACKUP_COMPLETED,
    "backup_failed": ServerEvent.BACKUP_FAILED,
}

# The original four stay opt-out (existing users keep their behavior);
# the newer, chattier events are opt-in.
DEFAULT_EVENT_PREFS = {
    "crashed": True,
    "ready": True,
    "backup_completed": True,
    "backup_failed": True,
    "stopped": False,
    "restarted": False,
    "zombie_detected": False,
    "lag_spike": False,
    "tunnel_online": False,
    "player_joins": False,
}


def _fmt_duration(seconds: float) -> str:
    seconds = int(seconds)
    h, rem = divmod(seconds, 3600)
    m, s = divmod(rem, 60)
    if h:
        return f"{h}h {m}m"
    if m:
        return f"{m}m {s}s"
    return f"{s}s"


class DiscordWebhookService:
    def __init__(self, webhook_url: str, events: EventBus,
                 server_name_getter: Optional[Callable[[], str]] = None,
                 enabled_events: Optional[set] = None,
                 username: str = "", avatar_url: str = "",
                 crash_mention_role: str = ""):
        self._url = webhook_url
        self._events = events
        # Getter, not a snapshot: the active server can change after the
        # service is created (it lives for the whole app session).
        self._get_server = server_name_getter or (lambda: "")
        self._username = username.strip()
        self._avatar_url = avatar_url.strip()
        self._crash_mention_role = crash_mention_role.strip()

        # Player join/leave coalescing state (guarded by _players_lock).
        self._players_lock = threading.Lock()
        self._prev_players: set = set()
        self._pending_joins: set = set()
        self._pending_leaves: set = set()
        self._last_count = 0
        self._flush_timer: Optional[threading.Timer] = None

        # Tunnel dedupe: only post when the public address actually changes.
        self._last_tunnel_addr: Optional[str] = None

        # None = all supported events (backwards compatible)
        if enabled_events is None:
            enabled_events = set(_EVENT_LABELS)
        self._enabled = {e for e in enabled_events if e in _EVENT_LABELS}
        self._queue: queue.Queue = queue.Queue()
        self._stop = threading.Event()
        self._worker = threading.Thread(target=self._run, daemon=True, name="DiscordWebhook")
        self._worker.start()

        self._subscriptions = []
        for event in self._enabled:
            if event == ServerEvent.PLAYER_LIST:
                handler = self._on_player_list
            else:
                handler = (lambda data, e=event: self._handle_event(e, data))
            events.subscribe(event, handler)
            self._subscriptions.append((event, handler))
        if ServerEvent.PLAYER_LIST in self._enabled:
            # Internal reset (never posts): a stopped server has no players,
            # even if no "left the game" lines were logged before exit.
            events.subscribe(ServerEvent.STOPPED, self._reset_players)
            self._subscriptions.append((ServerEvent.STOPPED, self._reset_players))

    # ------------------------------------------------------------------
    # Event intake (EventBus thread)
    # ------------------------------------------------------------------
    def _handle_event(self, event_type: str, data) -> None:
        if event_type == ServerEvent.STOPPED:
            # Only announce clean shutdowns; crash exits are covered by
            # the CRASHED event (avoids a double post per crash).
            if isinstance(data, dict) and data.get("exit_code") not in (0, None):
                return
        elif event_type == ServerEvent.TUNNEL_STATUS:
            if not isinstance(data, dict):
                return
            addr = data.get("dns") or data.get("ip")
            if data.get("status") != "Online" or not addr:
                self._last_tunnel_addr = None
                return
            if addr == self._last_tunnel_addr:
                return
            self._last_tunnel_addr = addr
        self._enqueue(event_type, data)

    def _enqueue(self, event_type: str, data) -> None:
        self._queue.put((event_type, data))

    # ------------------------------------------------------------------
    # Player join/leave coalescing
    # ------------------------------------------------------------------
    def _on_player_list(self, snapshot) -> None:
        names = set(snapshot) if isinstance(snapshot, (list, set, tuple)) else set()
        with self._players_lock:
            joined = names - self._prev_players
            left = self._prev_players - names
            self._prev_players = names
            self._last_count = len(names)
            # A player who joins and leaves inside the window (either order)
            # cancels out to no announcement.
            for p in joined:
                if p in self._pending_leaves:
                    self._pending_leaves.discard(p)
                else:
                    self._pending_joins.add(p)
            for p in left:
                if p in self._pending_joins:
                    self._pending_joins.discard(p)
                else:
                    self._pending_leaves.add(p)
            if self._flush_timer is None and (self._pending_joins or self._pending_leaves):
                self._flush_timer = threading.Timer(_PLAYER_FLUSH_DELAY, self._flush_players)
                self._flush_timer.daemon = True
                self._flush_timer.start()

    def _flush_players(self) -> None:
        with self._players_lock:
            joins = sorted(self._pending_joins)
            leaves = sorted(self._pending_leaves)
            count = self._last_count
            self._pending_joins = set()
            self._pending_leaves = set()
            self._flush_timer = None
        if self._stop.is_set() or (not joins and not leaves):
            return
        parts = []
        if joins:
            parts.append("Joined: " + ", ".join(f"**{p}**" for p in joins))
        if leaves:
            parts.append("Left: " + ", ".join(f"**{p}**" for p in leaves))
        parts.append(f"Online now: **{count}**")
        self._enqueue(_PLAYERS_FLUSH, "\n".join(parts))

    def _reset_players(self, _data=None) -> None:
        with self._players_lock:
            self._prev_players = set()
            self._pending_joins = set()
            self._pending_leaves = set()
            self._last_count = 0

    # ------------------------------------------------------------------
    # Worker / posting
    # ------------------------------------------------------------------
    def _run(self) -> None:
        while not self._stop.is_set():
            try:
                event_type, data = self._queue.get(timeout=1)
            except queue.Empty:
                continue
            self._post(event_type, data)
            time.sleep(_RATE_LIMIT_SECONDS)

    def _post(self, event_type: str, data) -> None:
        if event_type == _PLAYERS_FLUSH:
            label, color = _EVENT_LABELS[ServerEvent.PLAYER_LIST]
            description = data
        else:
            label, color = _EVENT_LABELS.get(event_type, ("Event", 0x99AAB5))
            description = self._format_description(event_type, data)
        embed = {
            "title": label,
            "description": description,
            "color": color,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
        server_name = self._get_server()
        if server_name:
            embed["footer"] = {"text": server_name}
        payload = {"embeds": [embed]}
        if self._username:
            payload["username"] = self._username
        if self._avatar_url:
            payload["avatar_url"] = self._avatar_url
        if event_type == ServerEvent.CRASHED and self._crash_mention_role:
            payload["content"] = f"<@&{self._crash_mention_role}>"
            payload["allowed_mentions"] = {"roles": [self._crash_mention_role]}
        self._post_payload(payload)

    def _post_payload(self, payload: dict) -> None:
        for attempt in (0, 1):
            try:
                resp = requests.post(self._url, json=payload, timeout=_POST_TIMEOUT)
            except Exception as e:
                logger.warning("Discord webhook post failed: %s", e)
                return
            if resp.status_code == 429 and attempt == 0:
                retry_after = float(_RATE_LIMIT_SECONDS)
                try:
                    retry_after = float(resp.headers.get("Retry-After")
                                        or resp.json().get("retry_after", retry_after))
                except (TypeError, ValueError, requests.exceptions.JSONDecodeError):
                    pass
                logger.info("Discord rate limited, retrying in %.1fs", retry_after)
                time.sleep(min(retry_after, _MAX_429_WAIT))
                continue
            if resp.status_code not in (200, 204):
                logger.warning("Discord webhook returned %s", resp.status_code)
            return

    def _format_description(self, event_type: str, data) -> str:
        if event_type == ServerEvent.CRASHED and isinstance(data, dict):
            reason = data.get("reason", "unknown")
            attempt = data.get("retry", 0)
            return f"Reason: `{reason}` — Retry attempt {attempt}"
        if event_type == ServerEvent.STOPPED and isinstance(data, dict):
            uptime = data.get("uptime")
            if uptime:
                return f"Clean shutdown after {_fmt_duration(uptime)}."
            return "Server stopped."
        if event_type == ServerEvent.RESTARTED and isinstance(data, dict):
            attempt = data.get("retry", 0)
            context = data.get("context", "crash")
            return f"Automatic restart (attempt {attempt}, cause: {context})."
        if event_type == ServerEvent.ZOMBIE_DETECTED and isinstance(data, dict):
            silence = int(data.get("silence_seconds", 0))
            return f"No console output for {silence}s. Watchdog is restarting the server."
        if event_type == ServerEvent.LAG_SPIKE and isinstance(data, dict):
            count = data.get("count", 0)
            window_min = int(data.get("window_seconds", 300) // 60)
            return f"{count} TPS warnings in the last {window_min} min. Server may be lagging."
        if event_type == ServerEvent.TUNNEL_STATUS and isinstance(data, dict):
            addr = data.get("dns") or data.get("ip") or ""
            return f"Server address: `{addr}`"
        if event_type == ServerEvent.BACKUP_COMPLETED and isinstance(data, dict):
            path = data.get("path", "")
            return f"Backup saved: `{path}`" if path else "Backup completed successfully."
        if event_type == ServerEvent.BACKUP_FAILED and isinstance(data, dict):
            return f"Error: {data.get('error', 'unknown')}"
        return ""

    def stop(self) -> None:
        self._stop.set()
        with self._players_lock:
            if self._flush_timer is not None:
                self._flush_timer.cancel()
                self._flush_timer = None
        # Unsubscribe, otherwise the dead service keeps enqueueing into a
        # queue nobody drains (and a re-created service would double-post).
        for event, handler in self._subscriptions:
            self._events.unsubscribe(event, handler)
        self._subscriptions.clear()

    @staticmethod
    def send_test(webhook_url: str, username: str = "", avatar_url: str = "") -> tuple[bool, str]:
        """Post a test embed synchronously. Returns (ok, error_detail)."""
        payload = {
            "embeds": [{
                "title": "ZeroBlockBridge",
                "description": "Webhook test successful. Notifications will appear here.",
                "color": 0x57F287,
            }]
        }
        if username.strip():
            payload["username"] = username.strip()
        if avatar_url.strip():
            payload["avatar_url"] = avatar_url.strip()
        try:
            resp = requests.post(webhook_url, json=payload, timeout=_POST_TIMEOUT)
            if resp.status_code in (200, 204):
                return True, ""
            return False, f"Discord returned HTTP {resp.status_code}"
        except requests.RequestException as e:
            return False, str(e)
