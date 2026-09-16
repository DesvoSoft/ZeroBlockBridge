"""Tracks which Modrinth slugs are installed per server.

Jar filenames don't reliably map back to Modrinth project slugs, so this
records the mapping at install time instead of trying to infer it later.
"""
import json
import logging
import threading
from pathlib import Path

from app.core.constants import SERVERS_DIR, atomic_write_json

logger = logging.getLogger(__name__)

_METADATA_FILENAME = "installed_mods.json"

# Per-server lock: record_install/remove_install's read-modify-write span
# must be atomic, or two near-simultaneous calls for the same server (e.g.
# a batch install submitting several mods to the icon/install executor at
# once) can race and drop one entry.
_locks: dict[str, threading.Lock] = {}
_locks_guard = threading.Lock()


def _lock_for(server_name: str) -> threading.Lock:
    with _locks_guard:
        lock = _locks.get(server_name)
        if lock is None:
            lock = threading.Lock()
            _locks[server_name] = lock
        return lock


def _metadata_path(server_name: str) -> Path:
    return Path(SERVERS_DIR) / server_name / _METADATA_FILENAME


def record_install(server_name: str, slug: str, filename: str) -> None:
    if not slug:
        return
    with _lock_for(server_name):
        path = _metadata_path(server_name)
        data = _read(path)
        data[slug] = filename
        try:
            atomic_write_json(path, data, indent=2)
        except OSError as exc:
            logger.warning("Failed to record install metadata for %s: %s", slug, exc)


def get_installed_slugs(server_name: str) -> set:
    return set(_read(_metadata_path(server_name)).keys())


def get_installed_filename(server_name: str, slug: str) -> str:
    return _read(_metadata_path(server_name)).get(slug, "")


def remove_install(server_name: str, slug: str) -> None:
    with _lock_for(server_name):
        path = _metadata_path(server_name)
        data = _read(path)
        if slug not in data:
            return
        del data[slug]
        try:
            atomic_write_json(path, data, indent=2)
        except OSError as exc:
            logger.warning("Failed to remove install metadata for %s: %s", slug, exc)


def remove_install_by_filename(server_name: str, filename: str) -> None:
    data = _read(_metadata_path(server_name))
    slug = next((s for s, f in data.items() if f == filename), None)
    if slug is None:
        return
    remove_install(server_name, slug)


def _read(path: Path) -> dict:
    if not path.exists():
        return {}
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except (OSError, json.JSONDecodeError) as exc:
        logger.warning("Failed to read install metadata at %s: %s", path, exc)
        return {}
