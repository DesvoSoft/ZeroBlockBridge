"""Shared streaming download primitive.

Every downloader (server jars, installers, JDK archives, the Playit agent)
used its own requests.get/iter_content loop with different chunk sizes,
timeouts and no guaranteed response close. Retry and verification policy
stay with each caller; this module only moves bytes to disk correctly.
"""

import hashlib
import logging
from typing import Callable, Optional

import requests

from app.core.app_config import AppConfig

logger = logging.getLogger(__name__)

USER_AGENT = AppConfig.USER_AGENT
CHUNK_SIZE = 64 * 1024


def stream_to_file(
    url: str,
    dest_path,
    *,
    timeout: float,
    progress_callback: Optional[Callable[[float], None]] = None,
    chunk_size: int = CHUNK_SIZE,
) -> str:
    """Stream `url` into `dest_path` and return the SHA1 hex digest of the
    bytes written.

    `progress_callback(fraction)` is called per chunk when the server sends
    Content-Length. Raises requests.RequestException for HTTP/network errors
    (including non-2xx status) and OSError when the file cannot be written;
    the response is always closed.
    """
    resp = requests.get(url, stream=True, timeout=timeout, headers={"User-Agent": USER_AGENT})
    try:
        resp.raise_for_status()
        try:
            total = int(resp.headers.get("content-length") or 0)
        except (TypeError, ValueError):
            total = 0
        sha1 = hashlib.sha1()
        written = 0
        with open(dest_path, "wb") as f:
            for chunk in resp.iter_content(chunk_size=chunk_size):
                if not chunk:
                    continue
                f.write(chunk)
                sha1.update(chunk)
                written += len(chunk)
                if progress_callback and total > 0:
                    progress_callback(min(written / total, 1.0))
        return sha1.hexdigest()
    finally:
        resp.close()
