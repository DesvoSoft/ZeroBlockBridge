import os
import shutil


def pytest_sessionfinish(session):
    cache_dir = os.path.join(os.path.dirname(__file__), "..", ".pytest_cache")
    if os.path.isdir(cache_dir):
        shutil.rmtree(cache_dir, ignore_errors=True)
    zbb_cache = os.path.join(os.path.dirname(__file__), "..", "app", "bin", ".zbb_cache")
    if os.path.isdir(zbb_cache):
        shutil.rmtree(zbb_cache, ignore_errors=True)


class FakeRunner:
    def __init__(self):
        self.started = False
        self.stopped = False
        self.running = False

    def start(self):
        self.started = True
        self.running = True

    def stop(self):
        self.stopped = True
        self.running = False


class FakeEmitter:
    def __init__(self):
        self.events = []
        self._listeners = {}

    def subscribe(self, event, callback):
        if event not in self._listeners:
            self._listeners[event] = []
        self._listeners[event].append(callback)

    def unsubscribe(self, event, callback):
        if event in self._listeners and callback in self._listeners[event]:
            self._listeners[event].remove(callback)

    def emit(self, event, data=None):
        self.events.append((event, data))
        for cb in self._listeners.get(event, []):
            try:
                cb(data)
            except Exception:
                pass
