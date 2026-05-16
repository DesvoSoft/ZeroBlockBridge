from collections import deque
from typing import List


class CircularBuffer:
    def __init__(self, max_size: int = 1000):
        self.max_size = max_size
        self._buffer: deque = deque(maxlen=max_size)

    def append(self, line: str):
        self._buffer.append(line)

    def read_all(self) -> List[str]:
        return list(self._buffer)

    def read_last_n(self, n: int) -> List[str]:
        return list(self._buffer)[-n:] if n > 0 else []

    def clear(self):
        self._buffer.clear()
