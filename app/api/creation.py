"""What the server-creation wizard needs before it hands its config to
``servers.create``: versions, templates, defaults, imported content checks."""

from __future__ import annotations

import threading
from typing import Callable, Optional

import psutil

from app.api.events import Dispatcher
from app.core.constants import SERVERS_DIR
from app.core.version_manager import VersionManager
from app.services import content_import, template_manager
from app.services.content_import import (  # noqa: F401  (re-exported for UIs)
    ContentImportError, ModpackInfo, WorldInfo,
)
from app.services.scaffolder import PROPERTY_DEFAULTS


class VersionsListener:
    """``cancel()`` stops further "versions refreshed" calls, also one the
    dispatcher has queued but not run yet."""

    def __init__(self, versions: VersionManager, callback: Callable[[], None], dispatcher: Dispatcher):
        self._versions = versions
        self._callback = callback
        self._dispatcher = dispatcher
        self._lock = threading.Lock()
        self._active = True
        versions.add_callback(self._notify)

    @property
    def active(self) -> bool:
        with self._lock:
            return self._active

    def _notify(self) -> None:
        if self.active:
            self._dispatcher(self._run)

    def _run(self) -> None:
        if self.active:
            self._callback()

    def cancel(self) -> None:
        with self._lock:
            self._active = False
        self._versions.remove_callback(self._notify)


class CreationApi:
    def __init__(self, dispatcher_source: Callable[[], Dispatcher],
                 versions_factory: Callable[[], VersionManager] = VersionManager):
        self._dispatcher_source = dispatcher_source
        self._versions_factory = versions_factory

    # -- versions ------------------------------------------------------------
    def versions(self, engine: str) -> list:
        """Known versions of an engine (cached; a stale cache refreshes in
        the background and ``on_versions_refreshed`` fires). May block on the
        first call (cache load)."""
        return self._versions_factory().get_versions(engine)

    def refresh_versions(self) -> None:
        """Fetch every engine's version list now. Blocking (network)."""
        self._versions_factory().refresh_versions()

    def on_versions_refreshed(self, callback: Callable[[], None]) -> VersionsListener:
        """``callback()`` through the dispatcher after each refresh."""
        return VersionsListener(self._versions_factory(), callback, self._dispatcher_source())

    # -- defaults --------------------------------------------------------------
    @staticmethod
    def property_defaults() -> dict:
        """Wizard defaults for server.properties-backed fields."""
        return dict(PROPERTY_DEFAULTS)

    @staticmethod
    def default_location() -> str:
        return str(SERVERS_DIR)

    @staticmethod
    def system_ram_mb() -> float:
        return psutil.virtual_memory().total / (1024 * 1024)

    # -- templates ---------------------------------------------------------------
    @staticmethod
    def templates() -> list:
        """Dicts with at least "name"."""
        return template_manager.list_templates()

    @staticmethod
    def load_template(name: str) -> Optional[dict]:
        return template_manager.load_template(name)

    @staticmethod
    def normalize_template_name(raw: str) -> Optional[str]:
        """A safe file name for the template, or None when it can't be one."""
        return template_manager.normalize_template_name(raw)

    @staticmethod
    def template_exists(name: str) -> bool:
        return template_manager.template_exists(name)

    @staticmethod
    def save_template(name: str, wizard_data: dict) -> None:
        template_manager.save_template(name, wizard_data)

    # -- imported content ----------------------------------------------------------
    @staticmethod
    def inspect_modpack(path: str) -> ModpackInfo:
        """Raises ContentImportError with a message for the user."""
        return content_import.inspect_modpack(path)

    @staticmethod
    def inspect_world(path: str) -> WorldInfo:
        """Raises ContentImportError with a message for the user."""
        return content_import.inspect_world(path)

    @staticmethod
    def world_version_check(world: WorldInfo, server_version: Optional[str]):
        """None, or ("error" | "warning" | "info", message)."""
        return content_import.world_version_check(world, server_version)
