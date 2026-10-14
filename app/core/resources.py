"""Location of read-only bundled files (assets/), importable before the data
directory is resolved -- unlike `app.core.constants.ASSETS_DIR`."""

import sys
from pathlib import Path


def resource_dir() -> Path:
    if getattr(sys, "frozen", False):
        # PyInstaller onefile extracts `datas` to _MEIPASS, not next to the exe.
        return Path(getattr(sys, "_MEIPASS", Path(sys.executable).resolve().parent))
    return Path(__file__).resolve().parent.parent.parent


def assets_dir() -> Path:
    return resource_dir() / "assets"
