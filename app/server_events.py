class ServerEvent:
    STARTING = "starting"
    READY = "ready"
    STOPPED = "stopped"
    ERROR = "error"

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
        """Trigger event."""
        if event in self._listeners:
            for callback in self._listeners[event]:
                try:
                    # Inspect callback to see if it accepts arguments?
                    # Simpler: just pass data if provided, or rely on callback signature matching.
                    # For safety, let's try-except or assume consistent usage.
                    # If data is None, call without args (or with None if callback expects it?)
                    # Let's assume callbacks take 0 or 1 arg.
                    
                    import inspect
                    sig = inspect.signature(callback)
                    if len(sig.parameters) > 0:
                        callback(data)
                    else:
                        callback()
                        
                except Exception as e:
                    print(f"[Error] Event callback failed for {event}: {e}")
