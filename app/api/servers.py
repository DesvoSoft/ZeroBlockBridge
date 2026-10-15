"""Servers: list, inspect, create, start/stop, delete, import/export."""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from typing import Callable, Optional

from app.api.tasks import Task, TaskRunner
from app.core import logic
from app.core.constants import SERVERS_DIR
from app.core.provisioning import ProvisionResult
from app.core.server_events import ServerEvent
from app.services import migration
from app.services.migration import MigrationError  # noqa: F401  (re-exported for UIs)
from app.services.modrinth import loader_for_server_type
from app.services.server_paths import check_server_name, is_valid_server_name
from app.services.server_properties import load_server_properties

logger = logging.getLogger(__name__)

CREATE_TASK = "create_server"


class ServerRunningError(RuntimeError):
    """The action needs the server stopped."""


class NoServerJarError(ValueError):
    """The folder chosen for import has no .jar to run."""


@dataclass(frozen=True)
class ServerInfo:
    name: str
    engine: Optional[str]          # metadata "type": Vanilla, Fabric, Paper... (None: unknown)
    mc_version: Optional[str]      # None when the metadata has none
    loader: Optional[str]          # Modrinth loader, None for vanilla
    max_players: Optional[int]

    @property
    def mod_context(self) -> tuple:
        """(name, mc_version, loader), what the Mods tab works with."""
        return self.name, self.mc_version if self.mc_version is not None else "1.20.1", self.loader


@dataclass(frozen=True)
class MemorySample:
    used_bytes: Optional[int]      # None while nothing runs
    limit_mb: Optional[int]        # the server's RAM allocation


class ServersApi:
    def __init__(self, manager, events, tasks: TaskRunner):
        self._manager = manager
        self._events = events
        self._tasks = tasks

    # -- queries ---------------------------------------------------------
    def list(self) -> list[str]:
        """Server folder names (creates the servers folder on first use)."""
        os.makedirs(SERVERS_DIR, exist_ok=True)
        return [d for d in os.listdir(SERVERS_DIR) if os.path.isdir(os.path.join(SERVERS_DIR, d))]

    @staticmethod
    def valid_name(name: str) -> bool:
        """Whether ``name`` can be a server folder (ask before create/import)."""
        return is_valid_server_name(name)

    def exists(self, name: str) -> bool:
        return os.path.isdir(os.path.join(SERVERS_DIR, check_server_name(name)))

    def info(self, name: str) -> ServerInfo:
        meta = logic.get_server_meta(check_server_name(name)) or {}
        engine = meta.get("type")
        try:
            max_players = int(load_server_properties(name).get("max-players", 20))
        except (TypeError, ValueError):
            max_players = None
        return ServerInfo(name=name, engine=engine, mc_version=meta.get("version"),
                          loader=loader_for_server_type(meta.get("type", "Vanilla")), max_players=max_players)

    def is_running(self) -> bool:
        return self._manager.is_running()

    @property
    def active(self) -> Optional[str]:
        """The server the core acts on: the running one, or the last selected
        while nothing runs."""
        return self._manager.current_server

    def running_server(self) -> Optional[str]:
        return self._manager.current_server if self._manager.is_running() else None

    def memory(self) -> MemorySample:
        used = self._manager.server_memory_usage()
        server = self._manager.current_server
        return MemorySample(used, logic.get_server_ram(server) if server else None)

    # -- commands --------------------------------------------------------
    def select(self, name: str) -> bool:
        """Make ``name`` the active server, unless another one runs."""
        if self._manager.is_running():
            return False
        self._manager.select_server(check_server_name(name))
        return True

    def start(self, name: Optional[str] = None) -> bool:
        """Start ``name`` (default: the active server). Blocking; call off the
        UI thread. False when a server already runs."""
        if self._manager.is_running():
            return False
        if name and self._manager.current_server != name:
            self._manager.select_server(check_server_name(name))
        return bool(self._manager.start_server())

    def stop(self) -> None:
        """Blocking (graceful wait, then kill): call off the UI thread."""
        self._manager.stop_server()

    def delete(self, name: str) -> None:
        """Delete a server folder (only the link for an imported server)."""
        check_server_name(name)
        if self._manager.is_running() and self._manager.current_server == name:
            raise ServerRunningError(name)
        logic.delete_server(name)
        if self._manager.current_server == name:
            self._manager.current_server = None

    def export(self, name: str, dest_path: str,
               progress: Optional[Callable[[str], None]] = None) -> str:
        """Write a .zbbpack; ``progress(text)`` per archived file. Blocking."""
        return migration.export_server(check_server_name(name), dest_path, progress_callback=progress)

    def import_pack(self, src_path: str, name: str) -> dict:
        return migration.import_server(src_path, check_server_name(name))

    def import_folder(self, folder: str) -> bool:
        """Link an existing server folder. Raises NoServerJarError when it has
        no .jar, ServerExistsError when the name is taken."""
        if not any(f.endswith(".jar") for f in os.listdir(folder)):
            raise NoServerJarError(folder)
        return bool(self._manager.load_server_manually(folder))

    def update_meta(self, name: str, updates: dict) -> bool:
        return logic.update_server_meta(check_server_name(name), updates)

    def request_mod_install(self, name: str, mod_ids: list) -> None:
        """Ask the core to fetch missing mods after a dependency crash."""
        self._events.emit(ServerEvent.REQUEST_MOD_INSTALL, {
            "missing_mod_ids": list(mod_ids), "server_name": name})

    def create(self, config: dict) -> Task:
        """Provision a server from wizard config. Progress: ``(fraction, text)``;
        result: a ProvisionResult. Cancelling rolls the attempt back."""
        def job(task: Task):
            try:
                return self._manager.provision_server(config, task.report, task.cancel_event)
            except Exception as exc:
                # The UI waits on a result to close its progress dialog.
                logger.exception("Provisioning %s crashed", config.get("name"))
                return ProvisionResult(ok=False, name=config.get("name", ""), error=str(exc))
        return self._tasks.start(CREATE_TASK, job)

    def creations(self) -> list[Task]:
        return self._tasks.active(CREATE_TASK)
