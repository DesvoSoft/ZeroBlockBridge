"""The smaller areas of the API: console, tunnel, backups, Java, settings."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional

from app.core.bootstrap import remember_language
from app.core.constants import BASE_DIR
from app.core import statemanager
from app.core.logic import BackupScheduler
from app.core.playit_manager import TunnelStatus, tunnel_status_label  # noqa: F401  (re-exported for UIs)
from app.services.backup_manager import BackupManager
from app.services.discord_webhook import (  # noqa: F401  (re-exported for UIs)
    DEFAULT_EVENT_PREFS, TEMPLATE_PLACEHOLDERS, DiscordWebhookService,
)
from app.services.java_detector import JavaDetector, get_required_java
from app.services.java_detector import dropdown_labels  # noqa: F401  (re-exported for UIs)
from app.services.sanitizer import ALLOWLISTED_COMMANDS  # noqa: F401  (re-exported for UIs)
from app.services.server_paths import check_server_name
from app.services.settings_manager import SettingsManager

logger = logging.getLogger(__name__)


class ConsoleApi:
    def __init__(self, manager):
        self._manager = manager

    def send(self, command: str) -> bool:
        """Send a console command to the running server. False when none runs.
        The safety check (and the blocked-command notice) is in the core."""
        if not command or not self._manager.is_running():
            return False
        self._manager.send_command(command)
        return True


class TunnelApi:
    def __init__(self, manager):
        self._manager = manager

    def start(self) -> None:
        self._manager.start_tunnel()

    def stop(self) -> None:
        self._manager.stop_tunnel()

    def reset(self, mode: str = "soft") -> None:
        """Delete the tunnels, keep the agent linked ("soft"). Blocking."""
        self._manager.reset_tunnel(mode=mode)

    def link(self, setup_code: str) -> bool:
        """Link the Playit agent with a setup code. Blocking."""
        return bool(self._manager.link_playit_manually(setup_code))

    @property
    def is_linked(self) -> bool:
        playit = getattr(self._manager, "playit_manager", None)
        return bool(playit is not None and playit.is_linked)

    @property
    def is_running(self) -> bool:
        playit = getattr(self._manager, "playit_manager", None)
        return bool(playit is not None and getattr(playit, "running", False))

    @staticmethod
    def status_changed(status: dict) -> bool:
        """Debounce for TUNNEL_STATUS events: False for a repeat of the shown
        status or one that arrives within the debounce window."""
        return statemanager.schedule_update(status)


class BackupsApi:
    """Backups of one server (``backups/<name>/*.zip``). Everything blocks."""

    def __init__(self, manager, manager_factory=BackupManager, scheduler_factory=BackupScheduler):
        self._manager = manager
        self._backups = manager_factory
        self._scheduler = scheduler_factory

    def list(self, server_name: str) -> list:
        """Dicts: path, date, size, reason ("manual" / "auto" / "pre_update"), newest first."""
        return self._backups(check_server_name(server_name)).list_backups()

    def create(self, server_name: str) -> tuple:
        """Manual backup: (path, None), (path, warning) or (None, error)."""
        return self._backups(check_server_name(server_name)).create_backup()

    def restore(self, server_name: str, backup_path: str) -> bool:
        return bool(self._backups(check_server_name(server_name)).restore_backup(backup_path))

    def folder(self, server_name: str) -> Path:
        """The server's backup folder (created if missing)."""
        return Path(self._backups(check_server_name(server_name)).backup_dir)

    def create_snapshot(self, server_name: str) -> tuple:
        """Pre-update snapshot: (path, None) or (None, error)."""
        return self._manager.create_pre_update_snapshot(server_name)

    def delete(self, server_name: str, backup_path: str) -> tuple:
        """Refuses anything but a .zip directly in that server's backup folder."""
        return self._manager.delete_backup(server_name, backup_path)

    def auto_config(self, server_name: str) -> dict:
        """{"enabled", "interval_hours", "retention_count", ...}"""
        return self._scheduler(check_server_name(server_name)).get_config()

    def set_auto_config(self, server_name: str, enabled: bool, interval_hours: int, retention_count: int) -> None:
        self._scheduler(check_server_name(server_name)).set_config(
            enabled, interval_hours=interval_hours, retention_count=retention_count)

    def seconds_until_auto(self, server_name: str) -> Optional[float]:
        """None when auto-backups are off, 0.0 when one is due."""
        return self._scheduler(check_server_name(server_name)).seconds_until_next()


@dataclass(frozen=True)
class JavaSummary:
    major: int
    source: str              # "PORTABLE", "PATH", "REGISTRY", ...
    version_string: str

    @property
    def portable(self) -> bool:
        return self.source == "PORTABLE"


class JavaApi:
    def __init__(self, detector_factory=JavaDetector, manager=None):
        self._detector_factory = detector_factory
        self._manager = manager

    def installations(self, force_refresh: bool = False) -> list:
        """JavaInstallation dataclasses (path, major, label, source...), best
        first. Blocking: scans the registry and the disk."""
        return self._detector_factory().detect_all(force_refresh=force_refresh)

    def best(self) -> Optional[JavaSummary]:
        """The preferred Java found on this machine, or None. Blocking."""
        installations = self.installations()
        if not installations:
            return None
        best = installations[0]
        return JavaSummary(best.major, best.source, best.version_string)

    @staticmethod
    def required(mc_version: str) -> int:
        """Java major version a Minecraft version needs."""
        return get_required_java(mc_version)

    # -- runtimes ZBB downloaded (.zbb_cache/jdks) -------------------------
    def managed(self) -> list:
        """Dicts: version, size_bytes."""
        return self._manager.list_managed_jdks()

    def purge(self, version: int) -> bool:
        """False while a server runs."""
        return bool(self._manager.purge_jdk(version))

    def purge_unused(self) -> bool:
        return bool(self._manager.purge_unused_jdks())


class SettingsApi:
    """App-wide settings (config/zbb_settings.json)."""

    def __init__(self, settings: Optional[SettingsManager] = None, manager=None):
        self._settings = settings
        self._manager = manager

    @property
    def _store(self) -> SettingsManager:
        return self._settings or SettingsManager()

    def get(self, key: str, default: Any = None) -> Any:
        return self._store.get(key, default)

    def set(self, key: str, value: Any) -> None:
        self._store.set(key, value)

    def save(self) -> None:
        """Write pending changes now (they are otherwise debounced)."""
        self._store.save()

    def set_language(self, code: str) -> None:
        """Language for the next start: saved here and, when it belongs to this
        data folder, in the install marker the pre-app dialogs read."""
        self._store.set("language", code)
        remember_language(code, BASE_DIR)

    def reload_notifications(self) -> None:
        """Apply saved Discord webhook settings to the running app."""
        self._manager.reload_discord_webhook()

    @staticmethod
    def send_test_notification(url: str, username: str = "", avatar_url: str = "") -> tuple:
        """(ok, error). Blocking network call."""
        return DiscordWebhookService.send_test(url, username=username, avatar_url=avatar_url)
