"""Modrinth project icons: download, scale to a thumbnail, cache on disk.

Returns PIL images; wrapping them for a toolkit (CTkImage, QPixmap) and any
in-memory cache of those wrappers belongs to the UI.
"""

from __future__ import annotations

import hashlib
import io
import logging
from pathlib import Path
from typing import Optional

from PIL import Image

from app.core.constants import BASE_DIR

logger = logging.getLogger(__name__)

ICON_SIZE = 48
ICON_TIMEOUT = 8


def icon_cache_dir() -> Path:
    return BASE_DIR / ".zbb_cache" / "modrinth_icons"


def icon_disk_path(icon_url: str) -> Path:
    return icon_cache_dir() / (hashlib.md5(icon_url.encode()).hexdigest() + ".png")


def cached_icon(icon_url: str) -> Optional[Image.Image]:
    """The icon from the disk cache, or None when missing/unreadable."""
    disk_path = icon_disk_path(icon_url)
    if not disk_path.exists():
        return None
    try:
        img = Image.open(disk_path)
        img.load()
    except OSError as exc:
        logger.debug("Unreadable cached icon %s: %s", disk_path, exc)
        return None
    return img


def fetch_icon(icon_url: str, session) -> Optional[Image.Image]:
    """Cached icon, else download it with ``session`` (a requests.Session),
    scale it to ICON_SIZE and cache it. None for non-http(s) URLs. Network
    and decode errors propagate to the caller."""
    if not icon_url.startswith(("https://", "http://")):
        return None
    img = cached_icon(icon_url)
    if img is not None:
        return img
    resp = session.get(icon_url, timeout=ICON_TIMEOUT)
    resp.raise_for_status()
    img = Image.open(io.BytesIO(resp.content)).resize((ICON_SIZE, ICON_SIZE), Image.LANCZOS)
    try:
        icon_cache_dir().mkdir(parents=True, exist_ok=True)
        img.save(icon_disk_path(icon_url))
    except OSError as exc:
        logger.debug("Icon disk cache write failed: %s", exc)
    return img
