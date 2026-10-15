"""Folders: where things live and opening them in the system file manager."""

from __future__ import annotations

import logging
import os
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Optional

from app.core import bootstrap, installer
from app.core.constants import BASE_DIR, JDK_CACHE_DIR, LOGS_DIR, SERVERS_DIR, VERSIONS_CACHE_FILE
from app.services.disk_usage import dir_size
from app.services.disk_usage import format_size  # noqa: F401  (re-exported for UIs)
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


@dataclass(frozen=True)
class InstallInfo:
    """How this copy runs: portable, installed (where) or neither."""
    exe: Path
    portable: bool
    installed_at: Optional[str]

    @property
    def shortcut_target(self) -> Path:
        return Path(self.installed_at) if self.installed_at else self.exe


class StorageApi:
    def __init__(self, manager=None):
        self._manager = manager

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

    @staticmethod
    def usage() -> list:
        """(category key, size in bytes) for Settings -> Storage. Blocking
        (walks the data folder). Keys: servers, backups, java, crash_reports,
        logs, versions_cache."""
        servers_dir = Path(SERVERS_DIR)
        crash_total = 0
        if servers_dir.exists():
            for folder in servers_dir.iterdir():
                crash_total += dir_size(folder / "crash_reports")
        versions_size = VERSIONS_CACHE_FILE.stat().st_size if VERSIONS_CACHE_FILE.exists() else 0
        return [
            ("servers", dir_size(servers_dir)),
            ("backups", dir_size(Path(BASE_DIR) / "backups")),
            ("java", dir_size(JDK_CACHE_DIR)),
            ("crash_reports", crash_total),
            ("logs", dir_size(LOGS_DIR)),
            ("versions_cache", versions_size),
        ]

    def purge_crash_reports(self) -> int:
        """Delete every server's crash reports; returns how many folders had some."""
        return self._manager.purge_crash_reports()

    @staticmethod
    def install_info(exe=None) -> InstallInfo:
        exe = Path(exe or sys.executable).resolve()
        marker = bootstrap.read_marker()
        installed = marker.get("exe_path") if marker.get("mode") == bootstrap.MODE_INSTALLED else None
        return InstallInfo(exe, (exe.parent / bootstrap.PORTABLE_FLAG).exists(), installed)

    @staticmethod
    def add_shortcuts(target: Path, start_menu: bool = False, desktop: bool = False) -> list:
        """Start menu / Desktop shortcuts to ``target``; returns failure messages."""
        return installer.add_shortcuts(target, start_menu=start_menu, desktop=desktop)
