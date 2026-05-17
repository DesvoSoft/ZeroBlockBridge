import threading
import time

_last_status: str = None
_last_time: float = 0
_debounce_ms: int = 200
_lock = threading.Lock()


def schedule_update(new_status: dict) -> bool:
    global _last_status, _last_time
    now = time.time() * 1000
    new_val = new_status.get("status")
    with _lock:
        if now - _last_time < _debounce_ms:
            return False
        if new_val == _last_status:
            return False
        _last_status = new_val
        _last_time = now
    return True


def current_status() -> dict:
    with _lock:
        return {"status": _last_status} if _last_status else None
