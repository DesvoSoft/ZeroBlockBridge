"""Mods, plugins and modpacks: Modrinth search/install/update and the
server's content files. Every method blocks (network or disk): call it
off the UI thread."""

import os
import threading
from typing import Callable, Optional

from app.services import mod_content, mod_icons, mod_install_tracker
from app.services.mod_content import (  # noqa: F401  (re-exported for UIs)
    DeleteResult, ModDownloadError, NoCompatibleVersionError, UnsafePathError,
    filter_updates_for_selection, snapshot_then_apply,
)
from app.services.modrinth import (  # noqa: F401  (re-exported for UIs)
    MOD_LOADERS, PLUGIN_LOADERS, ModrinthClient, ModrinthException, loader_display,
)
from app.services.mrpack_installer import MrpackCompatibilityError  # noqa: F401  (re-exported)


class ModsApi:
    def __init__(self, client_factory: Callable = ModrinthClient,
                 create_snapshot: Optional[Callable] = None):
        self._client_factory = client_factory
        self._client = None
        self._client_lock = threading.Lock()
        self._create_snapshot = create_snapshot

    @property
    def client(self):
        with self._client_lock:
            if self._client is None:
                self._client = self._client_factory()
            return self._client

    # -- Modrinth --------------------------------------------------------
    def search(self, query: str, **filters) -> dict:
        return self.client.search(query, **filters)

    def get_versions(self, slug: str, mc_version: Optional[str] = None, loader: Optional[str] = None) -> list:
        return self.client.get_versions(slug, mc_version=mc_version, loader=loader)

    def required_dependencies(self, version: dict, mc_version: str, loader: str, installed_slugs) -> dict:
        return self.client.get_required_dependencies(version, mc_version, loader, installed_slugs)

    def check_updates(self, server_name: str, mc_version: str, loader: str) -> list:
        return self.client.check_updates(server_name, mc_version, loader)

    def fetch_icon(self, icon_url: str):
        """PIL image (cached on disk) or None; raises on network errors."""
        return mod_icons.fetch_icon(icon_url, self.client.session)

    @staticmethod
    def cached_icon(icon_url: str):
        return mod_icons.cached_icon(icon_url)

    # -- installs --------------------------------------------------------
    def install_version(self, version: dict, server_name: str, loader: str, slug: str,
                        progress: Optional[Callable[[float], None]] = None) -> Optional[str]:
        return mod_content.install_version(self.client, version, server_name, loader, slug, progress)

    def install_latest(self, slug: str, server_name: str, mc_version: str, loader: str) -> Optional[str]:
        return mod_content.install_latest(self.client, slug, server_name, mc_version, loader)

    def install_modpack(self, version: dict, server_name: str,
                        on_download: Optional[Callable[[float], None]] = None,
                        on_status: Optional[Callable[[str], None]] = None) -> dict:
        return mod_content.install_modpack(self.client, version, server_name, on_download, on_status)

    def apply_updates(self, server_name: str, loader: str, updates: list,
                      on_update: Optional[Callable[[dict], None]] = None) -> tuple:
        """Pre-update snapshot, then each update. Returns (snapshot_error,
        updated, failed); nothing is touched when the snapshot fails."""
        def apply_one(update):
            if on_update:
                on_update(update)
            return self.client.apply_update(update, server_name, loader)
        return snapshot_then_apply(self._create_snapshot, server_name, updates, apply_one)

    # -- the server's files ------------------------------------------------
    @staticmethod
    def installed_files(server_name: str) -> list[str]:
        return mod_content.installed_jar_files(server_name)

    @staticmethod
    def installed_slugs(server_name: str) -> set:
        return mod_install_tracker.get_installed_slugs(server_name)

    @staticmethod
    def installed_filename(server_name: str, slug: str) -> str:
        return mod_install_tracker.get_installed_filename(server_name, slug)

    @staticmethod
    def uninstall(server_name: str, slug: str) -> Optional[str]:
        return mod_content.uninstall(server_name, slug)

    @staticmethod
    def delete_file(server_name: str, path: str) -> Optional[str]:
        """Delete one mod/plugin file. Returns the Modrinth slug it was
        installed as (now forgotten), or None. Raises OSError/UnsafePathError."""
        fname = os.path.basename(path)
        slug = next((s for s in mod_install_tracker.get_installed_slugs(server_name)
                     if mod_install_tracker.get_installed_filename(server_name, s) == fname), None)
        mod_content.delete_content_file(server_name, path)
        return slug

    @staticmethod
    def delete_files(server_name: str, paths) -> DeleteResult:
        return mod_content.delete_content_files(server_name, paths)
