"""Tracks which Modrinth slugs are installed per server.

Jar filenames don't reliably map back to Modrinth project slugs, so this
records the mapping at install time instead of trying to infer it later.
"""
import json
import logging
import os
from pathlib import Path

from app.core.constants import SERVERS_DIR

logger = logging.getLogger(__name__)

_METADATA_FILENAME = "installed_mods.json"


def _metadata_path(server_name: str) -> Path:
    return Path(SERVERS_DIR) / server_name / _METADATA_FILENAME


def record_install(server_name: str, slug: str, filename: str) -> None:
    if not slug:
        return
    path = _metadata_path(server_name)
    data = _read(path)
    data[slug] = filename
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
    except OSError as exc:
        logger.warning("Failed to record install metadata for %s: %s", slug, exc)


def get_installed_slugs(server_name: str) -> set:
    return set(_read(_metadata_path(server_name)).keys())


def get_installed_filename(server_name: str, slug: str) -> str:
    return _read(_metadata_path(server_name)).get(slug, "")


def remove_install(server_name: str, slug: str) -> None:
    path = _metadata_path(server_name)
    data = _read(path)
    if slug not in data:
        return
    del data[slug]
    try:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
    except OSError as exc:
        logger.warning("Failed to remove install metadata for %s: %s", slug, exc)


def _read(path: Path) -> dict:
    if not path.exists():
        return {}
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except (OSError, json.JSONDecodeError) as exc:
        logger.warning("Failed to read install metadata at %s: %s", path, exc)
        return {}
