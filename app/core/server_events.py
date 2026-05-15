import logging
from dataclasses import dataclass
from typing import Any, Callable, Dict, List
import threading

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
    
    # New Events for ARCH-02 / Core decoupling
    CONSOLE_LINE = "console_line"
    TUNNEL_CONSOLE_LINE = "tunnel_console_line"
    NOTIFICATION = "notification"
    REQUEST_RESTART = "request_restart"
    TUNNEL_STATUS = "tunnel_status"


@dataclass
class EventPayload:
    event_type: str
    data: Any = None


class EventBus:
    """Robust pub/sub event bus for ZBB."""
    
    def __init__(self):
        self._listeners: Dict[str, List[Callable]] = {}
        self._lock = threading.RLock()

    def subscribe(self, event_type: str, callback: Callable):
        """Register a callback for an event type."""
        with self._lock:
            if event_type not in self._listeners:
                self._listeners[event_type] = []
            if callback not in self._listeners[event_type]:
                self._listeners[event_type].append(callback)

    def unsubscribe(self, event_type: str, callback: Callable):
        """Remove a callback from an event type."""
        with self._lock:
            if event_type in self._listeners:
                if callback in self._listeners[event_type]:
                    self._listeners[event_type].remove(callback)

    def emit(self, event_type: str, data: Any = None):
        """Trigger an event synchronously."""
        # logger.debug(f"[EventBus] Emit: {event_type}") # Optional: trace events
        with self._lock:
            callbacks = self._listeners.get(event_type, []).copy()
        
        for callback in callbacks:
            try:
                callback(data)
            except Exception as e:
                logger.error(f"[EventBus] Error in callback for {event_type}: {e}", exc_info=True)

# Alias for backwards compatibility during transition
ServerEventEmitter = EventBus
