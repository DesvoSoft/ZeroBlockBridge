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


def _stream_part(url: str, part_path: str, dest_path: str, progress_callback) -> tuple:
    """(sha1 hex, None) or (None, error message). Raises RequestException."""
    try:
        return stream_to_file(url, part_path, timeout=60, progress_callback=progress_callback), None
    except PermissionError as exc:
        _safe_remove(part_path)
        return None, (
            f"Permission denied writing to {dest_path}. Close any program "
            f"using this file (e.g. antivirus scan) or check folder permissions: {exc}"
        )
    except OSError as exc:
        _safe_remove(part_path)
        return None, f"Failed to write {dest_path}: {exc}"


def _checksum_ok(actual: str, expected_sha1: Optional[str], dest_path: str, attempt: int, max_retries: int) -> bool:
    name = os.path.basename(dest_path)
    if not expected_sha1:
        logger.warning("SHA1 not provided for %s — skipping verification", name)
        return True
    if actual != expected_sha1.lower():
        logger.warning("SHA1 mismatch (attempt %d/%d) for %s: expected=%s, actual=%s",
                       attempt, max_retries, name, expected_sha1, actual)
        return False
    logger.info("SHA1 verified: %s (attempt %d)", name, attempt)
    return True


def _publish(part_path: str, dest_path: str) -> tuple:
    """Move the verified download into place; the download result tuple."""
    from app.core.atomic_io import replace_with_retry
    try:
        replace_with_retry(part_path, dest_path)
    except OSError as exc:
        _safe_remove(part_path)
        return False, None, f"Failed to write {dest_path}: {exc}"
    return True, dest_path, None


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
            actual, error = _stream_part(url, part_path, dest_path, progress_callback)
            if error:
                return False, None, error
            if progress_callback:
                progress_callback(1.0)
            if _checksum_ok(actual, expected_sha1, dest_path, attempt, max_retries):
                return _publish(part_path, dest_path)
            _safe_remove(part_path)
            if attempt == max_retries:
                return False, None, (
                    f"Download corruption persisted after {max_retries} attempts. "
                    f"Expected SHA1: {expected_sha1}, got: {actual}"
                )
            time.sleep(RETRY_DELAY)
        except requests.RequestException as exc:
            logger.error("Download failed (attempt %d/%d): %s", attempt, max_retries, exc)
            if os.path.exists(part_path):
                _safe_remove(part_path)
            if attempt == max_retries:
                return False, None, f"Download failed after {max_retries} attempts: {exc}"
            time.sleep(RETRY_DELAY)

    return False, None, "Download failed: unknown error"
