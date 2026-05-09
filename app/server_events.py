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

class ServerEventEmitter:
    """Observable pattern for server state changes."""
    def __init__(self):
        self._listeners = {}

    def on(self, event, callback):
        """Register callback for event."""
        if event not in self._listeners:
            self._listeners[event] = []
        self._listeners[event].append(callback)

    def emit(self, event, data=None):
        """Trigger event. All callbacks receive data (may be None)."""
        if event in self._listeners:
            for callback in self._listeners[event]:
                try:
                    callback(data)
                except Exception as e:
                    print(f"[Error] Event callback failed for {event}: {e}")
