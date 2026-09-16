"""Player skin heads (face avatars) from mc-heads.net, cached on disk.

Only meaningful for real Java accounts (online-mode UUIDs): offline-mode and
Bedrock UUIDs have no skin on Mojang's side, so callers show an initial tile
instead of asking for those.
"""

import logging
import os
import time
from pathlib import Path
from typing import Optional

import requests

from app.core.constants import BASE_DIR
from app.services.http_download import stream_to_file

logger = logging.getLogger(__name__)

HEAD_URL = "https://mc-heads.net/avatar/{uuid}/{size}"
HEAD_CACHE_DIR = BASE_DIR / ".zbb_cache" / "player_heads"
# Skins change rarely; refresh a few times a week at most.
MAX_AGE_SECONDS = 3 * 24 * 3600
_TIMEOUT = 8


def head_cache_path(player_uuid: str, size: int) -> Path:
    return HEAD_CACHE_DIR / f"{player_uuid.replace('-', '').lower()}_{size}.png"


def fetch_head(player_uuid: str, size: int = 64) -> Optional[Path]:
    """Path to a PNG head for this UUID, downloading it when missing or stale.

    Blocking — call from a worker. On a network error an older cached copy is
    still returned; None when there's nothing to show.
    """
    if not player_uuid:
        return None
    path = head_cache_path(player_uuid, size)
    try:
        if path.exists() and time.time() - path.stat().st_mtime < MAX_AGE_SECONDS:
            return path
    except OSError:
        pass
    tmp = path.with_suffix(".part")
    try:
        HEAD_CACHE_DIR.mkdir(parents=True, exist_ok=True)
        stream_to_file(HEAD_URL.format(uuid=player_uuid.replace("-", ""), size=size), tmp, timeout=_TIMEOUT)
        os.replace(tmp, path)
        return path
    except (requests.RequestException, OSError) as exc:
        logger.debug("Head download failed for %s: %s", player_uuid, exc)
        try:
            tmp.unlink(missing_ok=True)
        except OSError:
            pass
        return path if path.exists() else None
