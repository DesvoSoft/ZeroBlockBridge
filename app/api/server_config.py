"""One server's configuration: server.properties, worlds, RAM, icon, launch
settings, scheduled restarts and modpack import. Everything blocks on disk."""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Callable, Optional

from app.core import logic
from app.core.constants import SERVERS_DIR
from app.services import server_properties
from app.services.mrpack_installer import install_mrpack
from app.services.server_paths import check_server_name


@dataclass(frozen=True)
class LaunchSettings:
    java_path: str               # "auto" or a java executable
    use_aikars: bool
    jvm_custom_flags: str


class ServerConfigApi:
    # -- metadata ----------------------------------------------------------
    @staticmethod
    def meta(name: str) -> dict:
        """The server's metadata.json (type, version, ram...), {} when missing."""
        return logic.get_server_meta(check_server_name(name)) or {}

    # -- server.properties ---------------------------------------------------
    @staticmethod
    def properties(name: str) -> dict:
        return server_properties.load_server_properties(check_server_name(name))

    @staticmethod
    def save_properties(name: str, values: dict) -> None:
        """Merge ``values`` into server.properties (other keys are kept)."""
        server_properties.save_server_properties(check_server_name(name), new_properties=values)

    @staticmethod
    def worlds(name: str) -> list:
        """World folders of the server (for the level-name picker)."""
        return server_properties.list_worlds(check_server_name(name))

    # -- resources -----------------------------------------------------------
    @staticmethod
    def ram_mb(name: str) -> int:
        return logic.get_server_ram(check_server_name(name))

    @staticmethod
    def set_ram_mb(name: str, ram_mb: int) -> None:
        logic.set_server_ram(check_server_name(name), ram_mb)

    @staticmethod
    def set_icon(name: str, image_path: str) -> bool:
        """Scale ``image_path`` to 64x64 server-icon.png. False on a bad image."""
        return bool(logic.save_server_icon(check_server_name(name), image_path))

    # -- launch ----------------------------------------------------------------
    def launch_settings(self, name: str) -> LaunchSettings:
        meta = self.meta(name)
        return LaunchSettings(meta.get("java_path", "auto"), meta.get("use_aikars", True),
                              meta.get("jvm_custom_flags", ""))

    @staticmethod
    def save_launch_settings(name: str, settings: LaunchSettings) -> bool:
        """False (nothing written) when the server has no metadata.json yet."""
        if not os.path.exists(os.path.join(str(SERVERS_DIR), check_server_name(name), "metadata.json")):
            return False
        return bool(logic.update_server_meta(name, {
            "java_path": settings.java_path,
            "use_aikars": settings.use_aikars,
            "jvm_custom_flags": settings.jvm_custom_flags.strip(),
        }))

    # -- scheduled restarts ------------------------------------------------------
    @staticmethod
    def restart_schedule(name: str) -> Optional[dict]:
        """None when off, else {"type": "interval"|"time", "interval_hours" |
        "restart_time", "backup_on_restart", ...}."""
        return logic.Scheduler(check_server_name(name)).get_schedule()

    @staticmethod
    def set_restart_schedule(name: str, enabled: bool, interval_hours: Optional[int] = None,
                             restart_time: Optional[str] = None, backup_on_restart: bool = False) -> None:
        logic.Scheduler(check_server_name(name)).set_restart_schedule(
            enabled, interval_hours=interval_hours, restart_time=restart_time,
            backup_on_restart=backup_on_restart)

    # -- content ---------------------------------------------------------------
    def import_modpack(self, name: str, mrpack_path: str,
                       on_status: Optional[Callable[[str], None]] = None) -> dict:
        """Install a local .mrpack into the server. Returns the summary
        (installed, skipped_client, failed); raises MrpackCompatibilityError."""
        meta = self.meta(name)
        return install_mrpack(mrpack_path=mrpack_path, server_name=name, progress_callback=on_status,
                              server_type=meta.get("type"), mc_version=meta.get("version"))
