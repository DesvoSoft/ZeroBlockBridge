"""Resolves where ZBB stores its data (servers/config/backups/bin/.zbb_cache).

Must run -- and must finish running -- before `app.core.constants` is
imported anywhere in the process. That module fixes `BASE_DIR` (and every
path derived from it) at import time, and 25+ other modules bind those
constants at module load, so there is no later point at which the choice
can still be applied.
"""

import json
import logging
import os
import sys
from pathlib import Path

logger = logging.getLogger(__name__)

MARKER_FILENAME = "install.json"


def _marker_path() -> Path:
    local_appdata = os.environ.get("LOCALAPPDATA")
    if local_appdata:
        base = Path(local_appdata) / "ZeroBlockBridge"
    else:
        base = Path.home() / ".zeroblockbridge"
    return base / MARKER_FILENAME


def _read_marker(marker_path: Path) -> Path | None:
    try:
        with open(marker_path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, ValueError) as e:
        logger.debug("No usable data dir marker at %s: %s", marker_path, e)
        return None
    data_dir = data.get("data_dir")
    return Path(data_dir) if data_dir else None


def _write_marker(marker_path: Path, data_dir: Path) -> None:
    marker_path.parent.mkdir(parents=True, exist_ok=True)
    with open(marker_path, "w", encoding="utf-8") as f:
        json.dump({"data_dir": str(data_dir)}, f, indent=4)


def is_writable_dir(path: Path) -> bool:
    """Best-effort check that `path` exists (creating it if needed) and
    can actually be written to -- catches Program Files-style installs
    without admin rights."""
    try:
        path.mkdir(parents=True, exist_ok=True)
        probe = path / ".zbb_write_test"
        probe.write_text("ok", encoding="utf-8")
        probe.unlink()
        return True
    except OSError as e:
        logger.debug("Data dir %s not writable: %s", path, e)
        return False


def resolve_data_dir() -> Path:
    """Return the directory ZBB should use for servers/config/etc.,
    setting ZBB_DATA_DIR so `app.core.constants` picks it up."""
    if not getattr(sys, "frozen", False):
        # Dev mode: unchanged behavior (repo root), no marker/dialog.
        return Path(__file__).resolve().parent.parent.parent

    marker_path = _marker_path()
    data_dir = _read_marker(marker_path)
    if data_dir is not None and is_writable_dir(data_dir):
        os.environ["ZBB_DATA_DIR"] = str(data_dir)
        return data_dir

    exe_dir = Path(sys.executable).resolve().parent
    if (exe_dir / "servers").exists() or (exe_dir / "config").exists():
        # Pre-dates this feature: it already writes next to the exe.
        # Silently adopt that location -- no dialog, no disruption.
        data_dir = exe_dir
    else:
        from app.ui.first_run_dialog import ask_data_dir
        data_dir = ask_data_dir(exe_dir)

    _write_marker(marker_path, data_dir)
    os.environ["ZBB_DATA_DIR"] = str(data_dir)
    return data_dir
