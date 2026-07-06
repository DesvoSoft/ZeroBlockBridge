import json
import logging
import os

from app.core.constants import SERVERS_DIR

logger = logging.getLogger(__name__)


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
    path = _file_path(server_name, filename)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(entries, f, indent=2)


def add_entry(server_name: str, filename: str, entry: dict) -> None:
    entries = load_json_list(server_name, filename)
    name = entry.get("name")
    entries = [e for e in entries if e.get("name") != name]
    entries.append(entry)
    save_json_list(server_name, filename, entries)


def remove_entry(server_name: str, filename: str, name: str) -> None:
    entries = load_json_list(server_name, filename)
    entries = [e for e in entries if e.get("name") != name]
    save_json_list(server_name, filename, entries)
