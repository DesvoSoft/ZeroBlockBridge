"""Per-server player history: first/last seen and total playtime.

Stored as servers/<name>/zbb_player_history.json:
    {"Steve": {"first_seen": iso, "last_seen": iso, "playtime_seconds": int}}

PlayerHistoryTracker listens to PLAYER_LIST snapshots (joins and leaves are
the diff between consecutive snapshots) and closes every open session when
the server stops, so playtime survives crashes and "stop" without a logged
"left the game" line.
"""

import datetime
import json
import logging
import os
import threading
from typing import Callable, Optional

from app.core.constants import SERVERS_DIR, atomic_write_json
from app.core.server_events import ServerEvent

logger = logging.getLogger(__name__)

HISTORY_FILE = "zbb_player_history.json"


def _iso(ts: datetime.datetime) -> str:
    return ts.replace(microsecond=0).isoformat()


def history_path(server_name: str) -> str:
    return os.path.join(SERVERS_DIR, server_name, HISTORY_FILE)


def load_history(server_name: str) -> dict:
    path = history_path(server_name)
    if not os.path.exists(path):
        return {}
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, json.JSONDecodeError) as exc:
        logger.warning("Failed to read player history for %s: %s", server_name, exc)
        return {}
    return data if isinstance(data, dict) else {}


class PlayerHistory:
    """Session bookkeeping for one server; not thread-safe on its own
    (the tracker serializes access)."""

    def __init__(self, server_name: str):
        self.server_name = server_name
        self.records = load_history(server_name)
        self._open: dict[str, datetime.datetime] = {}

    def join(self, name: str, now: datetime.datetime) -> None:
        record = self.records.setdefault(name, {"first_seen": _iso(now), "playtime_seconds": 0})
        record["last_seen"] = _iso(now)
        self._open.setdefault(name, now)

    def leave(self, name: str, now: datetime.datetime) -> None:
        started = self._open.pop(name, None)
        record = self.records.get(name)
        if record is None:
            return
        record["last_seen"] = _iso(now)
        if started is not None:
            record["playtime_seconds"] = int(record.get("playtime_seconds", 0) + (now - started).total_seconds())

    def leave_all(self, now: datetime.datetime) -> None:
        for name in list(self._open):
            self.leave(name, now)

    def save(self) -> None:
        try:
            atomic_write_json(history_path(self.server_name), self.records, indent=2)
        except OSError as exc:
            logger.warning("Failed to save player history for %s: %s", self.server_name, exc)


class PlayerHistoryTracker:
    def __init__(self, event_bus, get_server_name: Callable[[], Optional[str]],
                 clock: Callable[[], datetime.datetime] = datetime.datetime.now):
        # Init all state before subscribing (events may arrive immediately).
        self._events = event_bus
        self._get_server_name = get_server_name
        self._clock = clock
        self._lock = threading.Lock()
        self._history: Optional[PlayerHistory] = None
        self._online: set[str] = set()
        event_bus.subscribe(ServerEvent.PLAYER_LIST, self._on_player_list)
        event_bus.subscribe(ServerEvent.STOPPED, self._on_stopped)

    def stop(self) -> None:
        self._events.unsubscribe(ServerEvent.PLAYER_LIST, self._on_player_list)
        self._events.unsubscribe(ServerEvent.STOPPED, self._on_stopped)
        self._on_stopped()

    def _history_for_current(self) -> Optional[PlayerHistory]:
        server = self._get_server_name()
        if not server:
            return None
        if self._history is None or self._history.server_name != server:
            self._history = PlayerHistory(server)
            self._online = set()
        return self._history

    def _on_player_list(self, players) -> None:
        with self._lock:
            history = self._history_for_current()
            if history is None:
                return
            now = self._clock()
            current = set(players or [])
            for name in current - self._online:
                history.join(name, now)
            for name in self._online - current:
                history.leave(name, now)
            self._online = current
            history.save()

    def _on_stopped(self, _data=None) -> None:
        with self._lock:
            if self._history is None or not self._online:
                self._online = set()
                return
            self._history.leave_all(self._clock())
            self._online = set()
            self._history.save()
