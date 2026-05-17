class FakeRunner:
    def __init__(self):
        self.started = False
        self.running = False

    def start(self):
        self.started = True
        self.running = True


class FakeEmitter:
    def __init__(self):
        self.events = []
        self._listeners = {}

    def subscribe(self, event, callback):
        if event not in self._listeners:
            self._listeners[event] = []
        self._listeners[event].append(callback)

    def emit(self, event, data=None):
        self.events.append((event, data))
        for cb in self._listeners.get(event, []):
            try:
                cb(data)
            except Exception:
                pass
