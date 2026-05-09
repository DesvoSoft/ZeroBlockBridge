import threading
from typing import List, Optional

class CircularBuffer:
    """
    A thread-safe circular buffer for storing console lines.
    Ensures O(1) append operations and O(n) read operations, 
    preventing infinite memory growth.
    """
    def __init__(self, max_size: int = 1000):
        self.max_size = max_size
        self._buffer: List[str] = []
        self._lock = threading.RLock()

    def append(self, line: str):
        """Append a line to the buffer. O(1) amortized, dropping oldest if full."""
        with self._lock:
            self._buffer.append(line)
            if len(self._buffer) > self.max_size:
                # We pop from the beginning. In a Python list, pop(0) is O(n).
                # To make append truly O(1), we could use collections.deque,
                # but for 1000 elements, pop(0) or slicing is fast enough.
                # However, for strict O(1), let's use deque or just a slice when reading.
                # Since we want to support line indexing and slicing easily, we'll use a list and slice.
                # Actually, dropping 100 lines at once is more efficient. Let's drop 10% to amortize O(n).
                drop_count = max(1, self.max_size // 10)
                self._buffer = self._buffer[drop_count:]

    def read_all(self) -> List[str]:
        """Read all lines currently in the buffer."""
        with self._lock:
            return list(self._buffer)

    def read_last_n(self, n: int) -> List[str]:
        """Read the last N lines from the buffer."""
        with self._lock:
            return self._buffer[-n:] if n > 0 else []

    def get_lines_since(self, index: int) -> List[str]:
        """
        Read lines appended after a given abstract index.
        Note: Since we drop from the front, absolute indexing is complex.
        For UI lazy rendering, it's easier to just read the whole buffer
        when restoring, or use a batch mechanism.
        """
        pass

    def clear(self):
        """Clear the buffer."""
        with self._lock:
            self._buffer.clear()
