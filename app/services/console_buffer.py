import threading
from collections import deque
from typing import List


class CircularBuffer:
    def __init__(self, max_size: int = 1000):
        self.max_size = max_size
        self._buffer: deque = deque(maxlen=max_size)
        # append() and list(deque) race: iterating a deque while another
        # thread mutates it raises RuntimeError. Reads happen at crash time
        # (CrashReporter) exactly when the reader thread is flushing lines.
        self._lock = threading.Lock()

    def append(self, line: str):
        with self._lock:
            self._buffer.append(line)

    def read_all(self) -> List[str]:
        with self._lock:
            return list(self._buffer)

    def read_last_n(self, n: int) -> List[str]:
        with self._lock:
            return list(self._buffer)[-n:] if n > 0 else []

    def clear(self):
        with self._lock:
            self._buffer.clear()
