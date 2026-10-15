"""The smaller areas of the API: console, tunnel, players, backups, Java, settings."""

import logging
from dataclasses import dataclass
from typing import Any, Optional

from app.services.java_detector import JavaDetector
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


class BackupsApi:
    def __init__(self, manager):
        self._manager = manager

    def create_snapshot(self, server_name: str) -> tuple:
        """Pre-update snapshot: (path, None) or (None, error). Blocking."""
        return self._manager.create_pre_update_snapshot(server_name)

    def delete(self, server_name: str, backup_path: str) -> tuple:
        return self._manager.delete_backup(server_name, backup_path)


@dataclass(frozen=True)
class JavaSummary:
    major: int
    source: str              # "PORTABLE", "PATH", "REGISTRY", ...
    version_string: str

    @property
    def portable(self) -> bool:
        return self.source == "PORTABLE"


class JavaApi:
    def __init__(self, detector_factory=JavaDetector):
        self._detector_factory = detector_factory

    def best(self) -> Optional[JavaSummary]:
        """The preferred Java found on this machine, or None. Blocking."""
        installations = self._detector_factory().detect_all()
        if not installations:
            return None
        best = installations[0]
        return JavaSummary(best.major, best.source, best.version_string)


class SettingsApi:
    """App-wide settings (config/zbb_settings.json)."""

    def __init__(self, settings: Optional[SettingsManager] = None):
        self._settings = settings

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
