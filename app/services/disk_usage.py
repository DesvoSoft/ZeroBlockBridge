"""Disk usage helpers for the Storage/Java settings tabs.

Synchronous walkers -- callers run them in daemon threads (JDK caches and
server dirs can hold tens of thousands of files).
"""
import logging
from pathlib import Path

logger = logging.getLogger(__name__)


def dir_size(path: Path) -> int:
    """Total size in bytes of every file under `path` (0 if missing)."""
    if not path.exists():
        return 0
    total = 0
    try:
        for entry in path.rglob("*"):
            try:
                if entry.is_file():
                    total += entry.stat().st_size
            except OSError:
                continue
    except OSError as exc:
        logger.debug("dir_size walk failed for %s: %s", path, exc)
    return total


def format_size(num_bytes: int) -> str:
    """Human-readable size: 1234 -> '1.2 KB', 0 -> '0 B'."""
    size = float(num_bytes)
    for unit in ("B", "KB", "MB", "GB"):
        if size < 1024 or unit == "GB":
            if unit == "B":
                return f"{int(size)} {unit}"
            return f"{size:.1f} {unit}"
        size /= 1024
    return f"{size:.1f} GB"
