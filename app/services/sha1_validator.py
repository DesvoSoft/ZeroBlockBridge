"""
PROV-04 — SHA1 Download Validation Pipeline.

Provides checksum verification for all server jar downloads with
automatic retry on mismatch. Integrates with the download pipeline
in app/logic.py.
"""

import logging
import os
import time
from typing import Callable, Optional

import requests

from app.services.http_download import stream_to_file

logger = logging.getLogger(__name__)

MAX_RETRIES = 3
RETRY_DELAY = 2  # seconds between retries


def _safe_remove(path: str) -> None:
    """Best-effort cleanup of a partial/corrupt download — a locked file
    (e.g. antivirus scanning it) must not crash the caller, which is
    supposed to always return a tuple, never raise."""
    try:
        os.remove(path)
    except OSError as exc:
        logger.warning("Could not remove %s: %s", path, exc)


def _publish(part_path: str, dest_path: str) -> None:
    from app.core.atomic_io import replace_with_retry
    replace_with_retry(part_path, dest_path)


def download_with_verification(
    url: str,
    dest_path: str,
    expected_sha1: Optional[str] = None,
    progress_callback: Optional[Callable] = None,
    max_retries: int = MAX_RETRIES,
) -> tuple:
    """
    Download a file with SHA1 verification and automatic retry.

    Bytes go to `<dest>.part` and only replace `dest_path` once complete and
    verified: a download interrupted by the app closing (or a crash) never
    leaves a truncated jar where the server would load it.

    Args:
        url: Download URL.
        dest_path: Destination file path.
        expected_sha1: Expected SHA1 hash (None = skip verification).
        progress_callback: Optional fn(float) for progress 0.0–1.0.
        max_retries: Maximum download attempts on checksum failure.

    Returns:
        (success: bool, file_path: str | None, error: str | None)
    """
    part_path = f"{dest_path}.part"
    for attempt in range(1, max_retries + 1):
        try:
            try:
                actual = stream_to_file(url, part_path, timeout=60, progress_callback=progress_callback)
            except PermissionError as exc:
                _safe_remove(part_path)
                return False, None, (
                    f"Permission denied writing to {dest_path}. Close any program "
                    f"using this file (e.g. antivirus scan) or check folder permissions: {exc}"
                )
            except OSError as exc:
                _safe_remove(part_path)
                return False, None, f"Failed to write {dest_path}: {exc}"

            if progress_callback:
                progress_callback(1.0)

            # SHA1 verification
            if expected_sha1 and actual != expected_sha1.lower():
                logger.warning(
                    "SHA1 mismatch (attempt %d/%d) for %s: expected=%s, actual=%s",
                    attempt, max_retries, os.path.basename(dest_path),
                    expected_sha1, actual,
                )
                _safe_remove(part_path)
                if attempt < max_retries:
                    time.sleep(RETRY_DELAY)
                    continue
                return False, None, (
                    f"Download corruption persisted after {max_retries} attempts. "
                    f"Expected SHA1: {expected_sha1}, got: {actual}"
                )
            if expected_sha1:
                logger.info("SHA1 verified: %s (attempt %d)", os.path.basename(dest_path), attempt)
            else:
                logger.warning(
                    "SHA1 not provided for %s — skipping verification",
                    os.path.basename(dest_path),
                )
            try:
                _publish(part_path, dest_path)
            except OSError as exc:
                _safe_remove(part_path)
                return False, None, f"Failed to write {dest_path}: {exc}"
            return True, dest_path, None

        except requests.RequestException as exc:
            logger.error("Download failed (attempt %d/%d): %s", attempt, max_retries, exc)
            if os.path.exists(part_path):
                _safe_remove(part_path)
            if attempt < max_retries:
                time.sleep(RETRY_DELAY)
            else:
                return False, None, f"Download failed after {max_retries} attempts: {exc}"

    return False, None, "Download failed: unknown error"
