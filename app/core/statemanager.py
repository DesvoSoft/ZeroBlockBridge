import time

_last_status: str = None
_last_time: float = 0
_debounce_ms: int = 200


def schedule_update(new_status: dict) -> bool:
    now = time.time() * 1000
    new_val = new_status.get("status")
    if now - _last_time < _debounce_ms:
        return False
    if new_val == _last_status:
        return False
    globals()["_last_status"] = new_val
    globals()["_last_time"] = now
    return True


def current_status() -> dict:
    return {"status": _last_status} if _last_status else None
