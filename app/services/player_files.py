import json
import logging
import os
import threading

from app.core.constants import SERVERS_DIR, atomic_write_json

logger = logging.getLogger(__name__)

# Per-(server, filename) lock so add_entry/remove_entry's read-modify-write
# span is atomic — without it, two near-simultaneous calls for the same file
# (e.g. rapid clicks before the UI re-renders) can race: both read the same
# starting list, both write back, and the second write silently drops the
# first call's change.
_locks: dict[tuple[str, str], threading.Lock] = {}
_locks_guard = threading.Lock()


def _lock_for(server_name: str, filename: str) -> threading.Lock:
    key = (server_name, filename)
    with _locks_guard:
        lock = _locks.get(key)
        if lock is None:
            lock = threading.Lock()
            _locks[key] = lock
        return lock


def _file_path(server_name: str, filename: str) -> str:
    return os.path.join(SERVERS_DIR, server_name, filename)


def load_json_list(server_name: str, filename: str) -> list[dict]:
    path = _file_path(server_name, filename)
    if not os.path.exists(path):
        return []
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except (json.JSONDecodeError, OSError) as exc:
        logger.warning("Failed to read %s for %s: %s", filename, server_name, exc)
        return []
    if not isinstance(data, list):
        return []
    return data


def save_json_list(server_name: str, filename: str, entries: list[dict]) -> None:
    atomic_write_json(_file_path(server_name, filename), entries, indent=2)


def add_entry(server_name: str, filename: str, entry: dict) -> None:
    with _lock_for(server_name, filename):
        entries = load_json_list(server_name, filename)
        name = entry.get("name")
        entries = [e for e in entries if e.get("name") != name]
        entries.append(entry)
        save_json_list(server_name, filename, entries)


def remove_entry(server_name: str, filename: str, name: str) -> None:
    with _lock_for(server_name, filename):
        entries = load_json_list(server_name, filename)
        entries = [e for e in entries if e.get("name") != name]
        save_json_list(server_name, filename, entries)
