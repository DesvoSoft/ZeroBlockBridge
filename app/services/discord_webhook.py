import logging
import queue
import threading
import time
from typing import Callable, Optional

import requests

from app.core.server_events import EventBus, ServerEvent

logger = logging.getLogger(__name__)

_RATE_LIMIT_SECONDS = 2
_POST_TIMEOUT = 10

_EVENT_LABELS = {
    ServerEvent.CRASHED: ("Server Crashed", 0xFF0000),
    ServerEvent.READY: ("Server Ready", 0x57F287),
    ServerEvent.BACKUP_COMPLETED: ("Backup Completed", 0x3498DB),
    ServerEvent.BACKUP_FAILED: ("Backup Failed", 0xE67E22),
}


class DiscordWebhookService:
    def __init__(self, webhook_url: str, events: EventBus,
                 server_name_getter: Optional[Callable[[], str]] = None):
        self._url = webhook_url
        self._events = events
        # Getter, not a snapshot: the active server can change after the
        # service is created (it lives for the whole app session).
        self._get_server = server_name_getter or (lambda: "")
        self._queue: queue.Queue = queue.Queue()
        self._stop = threading.Event()
        self._worker = threading.Thread(target=self._run, daemon=True, name="DiscordWebhook")
        self._worker.start()

        self._subscriptions = []
        for event in _EVENT_LABELS:
            handler = (lambda data, e=event: self._enqueue(e, data))
            events.subscribe(event, handler)
            self._subscriptions.append((event, handler))

    def _enqueue(self, event_type: str, data) -> None:
        self._queue.put((event_type, data))

    def _run(self) -> None:
        while not self._stop.is_set():
            try:
                event_type, data = self._queue.get(timeout=1)
            except queue.Empty:
                continue
            self._post(event_type, data)
            time.sleep(_RATE_LIMIT_SECONDS)

    def _post(self, event_type: str, data) -> None:
        label, color = _EVENT_LABELS.get(event_type, ("Event", 0x99AAB5))
        description = self._format_description(event_type, data)
        payload = {
            "embeds": [{
                "title": label,
                "description": description,
                "color": color,
            }]
        }
        server_name = self._get_server()
        if server_name:
            payload["embeds"][0]["footer"] = {"text": server_name}
        try:
            resp = requests.post(self._url, json=payload, timeout=_POST_TIMEOUT)
            if resp.status_code not in (200, 204):
                logger.warning("Discord webhook returned %s", resp.status_code)
        except Exception as e:
            logger.warning("Discord webhook post failed: %s", e)

    def _format_description(self, event_type: str, data) -> str:
        if event_type == ServerEvent.CRASHED and isinstance(data, dict):
            reason = data.get("reason", "unknown")
            attempt = data.get("retry", 0)
            return f"Reason: `{reason}` — Retry attempt {attempt}"
        if event_type == ServerEvent.BACKUP_COMPLETED and isinstance(data, dict):
            path = data.get("path", "")
            return f"Backup saved: `{path}`" if path else "Backup completed successfully."
        if event_type == ServerEvent.BACKUP_FAILED and isinstance(data, dict):
            return f"Error: {data.get('error', 'unknown')}"
        return ""

    def stop(self) -> None:
        self._stop.set()
        # Unsubscribe, otherwise the dead service keeps enqueueing into a
        # queue nobody drains (and a re-created service would double-post).
        for event, handler in self._subscriptions:
            self._events.unsubscribe(event, handler)
        self._subscriptions.clear()

    @staticmethod
    def send_test(webhook_url: str) -> tuple[bool, str]:
        """Post a test embed synchronously. Returns (ok, error_detail)."""
        payload = {
            "embeds": [{
                "title": "ZeroBlockBridge",
                "description": "Webhook test successful. Notifications will appear here.",
                "color": 0x57F287,
            }]
        }
        try:
            resp = requests.post(webhook_url, json=payload, timeout=_POST_TIMEOUT)
            if resp.status_code in (200, 204):
                return True, ""
            return False, f"Discord returned HTTP {resp.status_code}"
        except requests.RequestException as e:
            return False, str(e)
