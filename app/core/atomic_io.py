"""Crash-safe file writes (temp file + os.replace).

Dependency-free so `app.core.bootstrap` can use it before the data dir is
resolved; `app.core.constants` re-exports both helpers for everything else.
"""

import json
import os
import tempfile
import time

# Windows refuses os.replace while any other handle has the target open
# (antivirus, OneDrive sync, a backup zipping the folder): retry briefly.
_REPLACE_ATTEMPTS = 6
_REPLACE_BACKOFF_S = 0.05


def replace_with_retry(src: str, dst: str) -> None:
    for attempt in range(_REPLACE_ATTEMPTS):
        try:
            os.replace(src, dst)
            return
        except PermissionError:
            if attempt == _REPLACE_ATTEMPTS - 1:
                raise
            time.sleep(_REPLACE_BACKOFF_S * (attempt + 1))


def atomic_write_text(path, write_fn, *, suffix: str = "") -> None:
    """Write to `path` via temp-file + os.replace, calling `write_fn(file_obj)`
    to produce the content.

    A crash or power loss mid-write with a plain open(path, "w") leaves a
    truncated/corrupt file behind — this can't, since the swap only happens
    once the temp file is fully written and closed. Mirrors the pattern
    java_installer.py/playit_manager.py already use for binary downloads.
    """
    path = str(path)
    dir_name = os.path.dirname(path) or "."
    os.makedirs(dir_name, exist_ok=True)
    fd, tmp_path = tempfile.mkstemp(dir=dir_name, prefix=".tmp_", suffix=suffix)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            write_fn(f)
        replace_with_retry(tmp_path, path)
    except BaseException:
        try:
            os.remove(tmp_path)
        except OSError:
            pass
        raise


def atomic_write_json(path, data, *, indent: int = 4) -> None:
    """Write JSON to `path` atomically — see atomic_write_text."""
    atomic_write_text(path, lambda f: json.dump(data, f, indent=indent), suffix=".json")
