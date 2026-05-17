import logging
from typing import Any, Callable, Dict, List

logger = logging.getLogger(__name__)


class ServerEvent:
    STARTING = "starting"
    READY = "ready"
    STOPPED = "stopped"
    ERROR = "error"
    PLAYER_COUNT = "player_count"
    CRASHED = "crashed"
    RESTARTED = "restarted"
    ZOMBIE_DETECTED = "zombie_detected"
    LAG_SPIKE = "lag_spike"
    CONSOLE_LINE = "console_line"
    TUNNEL_CONSOLE_LINE = "tunnel_console_line"
    NOTIFICATION = "notification"
    REQUEST_RESTART = "request_restart"
    TUNNEL_STATUS = "tunnel_status"
    BACKUP_COMPLETED = "backup_completed"
    BACKUP_FAILED = "backup_failed"


class EventBus:
    def __init__(self):
        self._listeners: Dict[str, List[Callable]] = {}

    def subscribe(self, event_type: str, callback: Callable):
        if event_type not in self._listeners:
            self._listeners[event_type] = []
        if callback not in self._listeners[event_type]:
            self._listeners[event_type].append(callback)

    def unsubscribe(self, event_type: str, callback: Callable):
        if event_type in self._listeners:
            if callback in self._listeners[event_type]:
                self._listeners[event_type].remove(callback)

    def emit(self, event_type: str, data: Any = None):
        callbacks = self._listeners.get(event_type, []).copy()
        for callback in callbacks:
            try:
                callback(data)
            except Exception as e:
                logger.error(f"[EventBus] Error in callback for {event_type}: {e}", exc_info=True)
