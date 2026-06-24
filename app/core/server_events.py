import logging
import threading
from typing import Any, Callable

logger = logging.getLogger(__name__)


class ServerEvent:
    STARTING = "starting"
    READY = "ready"
    STOPPED = "stopped"
    PLAYER_COUNT = "player_count"
    PLAYER_LIST = "player_list"
    CRASHED = "crashed"
    RESTARTED = "restarted"          # emitted by watchdog; available for future UI subscribers
    ZOMBIE_DETECTED = "zombie_detected"
    LAG_SPIKE = "lag_spike"
    CONSOLE_LINE = "console_line"
    TUNNEL_CONSOLE_LINE = "tunnel_console_line"
    NOTIFICATION = "notification"
    REQUEST_RESTART = "request_restart"
    TUNNEL_STATUS = "tunnel_status"
    BACKUP_COMPLETED = "backup_completed"  # emitted by BackupOrchestrator; available for future UI subscribers
    BACKUP_FAILED = "backup_failed"        # emitted by BackupOrchestrator; available for future UI subscribers


class EventBus:
    def __init__(self):
        self._listeners: Dict[str, List[Callable]] = {}
        self._lock = threading.RLock()

    def subscribe(self, event_type: str, callback: Callable):
        with self._lock:
            if event_type not in self._listeners:
                self._listeners[event_type] = []
            if callback not in self._listeners[event_type]:
                self._listeners[event_type].append(callback)

    def unsubscribe(self, event_type: str, callback: Callable):
        with self._lock:
            if event_type in self._listeners:
                if callback in self._listeners[event_type]:
                    self._listeners[event_type].remove(callback)

    def emit(self, event_type: str, data: Any = None):
        with self._lock:
            callbacks = self._listeners.get(event_type, []).copy()
        for callback in callbacks:
            try:
                callback(data)
            except Exception as e:
                logger.error("[EventBus] Error in callback for %s: %s", event_type, e, exc_info=True)
