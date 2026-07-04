"""
PROV-04 — SHA1 Download Validation Pipeline.

Provides checksum verification for all server jar downloads with
automatic retry on mismatch. Integrates with the download pipeline
in app/logic.py.
"""

import hashlib
import logging
import os
import time
from typing import Callable, Optional

import requests

logger = logging.getLogger(__name__)

MAX_RETRIES = 3
RETRY_DELAY = 2  # seconds between retries





def download_with_verification(
    url: str,
    dest_path: str,
    expected_sha1: Optional[str] = None,
    progress_callback: Optional[Callable] = None,
    max_retries: int = MAX_RETRIES,
) -> tuple:
    """
    Download a file with SHA1 verification and automatic retry.

    Args:
        url: Download URL.
        dest_path: Destination file path.
        expected_sha1: Expected SHA1 hash (None = skip verification).
        progress_callback: Optional fn(float) for progress 0.0–1.0.
        max_retries: Maximum download attempts on checksum failure.

    Returns:
        (success: bool, file_path: str | None, error: str | None)
    """
    for attempt in range(1, max_retries + 1):
        try:
            resp = requests.get(url, stream=True, timeout=60)
            resp.raise_for_status()

            total = int(resp.headers.get("content-length", 0))
            downloaded = 0
            sha1 = hashlib.sha1()

            try:
                with open(dest_path, "wb") as f:
                    for chunk in resp.iter_content(chunk_size=8192):
                        if chunk:
                            f.write(chunk)
                            sha1.update(chunk)
                            downloaded += len(chunk)
                            if progress_callback and total > 0:
                                progress_callback(downloaded / total)
            except PermissionError as exc:
                return False, None, (
                    f"Permission denied writing to {dest_path}. Close any program "
                    f"using this file (e.g. antivirus scan) or check folder permissions: {exc}"
                )
            except OSError as exc:
                return False, None, f"Failed to write {dest_path}: {exc}"

            if progress_callback:
                progress_callback(1.0)

            # SHA1 verification
            if expected_sha1:
                actual = sha1.hexdigest()
                if actual != expected_sha1.lower():
                    logger.warning(
                        "SHA1 mismatch (attempt %d/%d) for %s: expected=%s, actual=%s",
                        attempt, max_retries, os.path.basename(dest_path),
                        expected_sha1, actual,
                    )
                    if attempt < max_retries:
                        os.remove(dest_path)
                        time.sleep(RETRY_DELAY)
                        continue
                    else:
                        os.remove(dest_path)
                        return False, None, (
                            f"Download corruption persisted after {max_retries} attempts. "
                            f"Expected SHA1: {expected_sha1}, got: {actual}"
                        )
                else:
                    logger.info("SHA1 verified: %s (attempt %d)", os.path.basename(dest_path), attempt)
            else:
                logger.warning(
                    "SHA1 not provided for %s — skipping verification",
                    os.path.basename(dest_path),
                )

            return True, dest_path, None

        except requests.RequestException as exc:
            logger.error("Download failed (attempt %d/%d): %s", attempt, max_retries, exc)
            if os.path.exists(dest_path):
                os.remove(dest_path)
            if attempt < max_retries:
                time.sleep(RETRY_DELAY)
            else:
                return False, None, f"Download failed after {max_retries} attempts: {exc}"

    return False, None, "Download failed: unknown error"
