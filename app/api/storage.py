"""Folders: where things live and opening them in the system file manager."""

from __future__ import annotations

import logging
import os
import subprocess
import sys
from pathlib import Path
from typing import Callable, Optional

from app.core.constants import BASE_DIR, LOGS_DIR, SERVERS_DIR
from app.services.server_paths import check_server_name

logger = logging.getLogger(__name__)


def open_in_file_manager(path, *, create: bool = False, platform: Optional[str] = None,
                         run: Callable = subprocess.run) -> bool:
    """Show ``path`` in Explorer / Finder / the desktop's file manager.

    Returns False when the folder doesn't exist (and ``create`` is off) or
    the file manager couldn't be launched; the caller tells the user.
    """
    path = Path(path)
    if create:
        try:
            path.mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            logger.warning("Could not create %s: %s", path, exc)
            return False
    if not path.exists():
        return False
    platform = platform or sys.platform
    command = "explorer" if platform == "win32" else "open" if platform == "darwin" else "xdg-open"
    try:
        run([command, str(path)], check=False)
    except OSError as exc:
        logger.warning("Failed to open %s with %s: %s", path, command, exc)
        return False
    return True


class StorageApi:
    @property
    def data_dir(self) -> Path:
        return Path(BASE_DIR)

    @property
    def servers_dir(self) -> Path:
        return Path(SERVERS_DIR)

    @property
    def logs_dir(self) -> Path:
        return Path(LOGS_DIR)

    def server_dir(self, server_name: str, subpath: str = "") -> Path:
        path = Path(SERVERS_DIR) / check_server_name(server_name)
        return path / subpath if subpath else path

    def ensure_servers_dir(self) -> Path:
        os.makedirs(SERVERS_DIR, exist_ok=True)
        return Path(SERVERS_DIR)

    def open_folder(self, path, create: bool = False) -> bool:
        return open_in_file_manager(path, create=create)
