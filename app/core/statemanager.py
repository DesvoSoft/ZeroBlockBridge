import threading
import time

from app.core.app_config import AppConfig


class TunnelStatusDebouncer:
    """Debounces tunnel status updates to avoid redundant UI refreshes."""

    def __init__(self, debounce_ms: int = AppConfig.DEBOUNCE_MS):
        self._last_status: str = None
        self._last_time: float = 0
        self._debounce_ms = debounce_ms
        self._lock = threading.Lock()

    def schedule_update(self, new_status: dict) -> bool:
        now = time.time() * 1000
        new_val = new_status.get("status")
        with self._lock:
            if now - self._last_time < self._debounce_ms:
                return False
            if new_val == self._last_status:
                return False
            self._last_status = new_val
            self._last_time = now
        return True

    def current_status(self) -> dict:
        with self._lock:
            return {"status": self._last_status} if self._last_status else None


_default_debouncer = TunnelStatusDebouncer()


def schedule_update(new_status: dict) -> bool:
    return _default_debouncer.schedule_update(new_status)


def current_status() -> dict:
    return _default_debouncer.current_status()
