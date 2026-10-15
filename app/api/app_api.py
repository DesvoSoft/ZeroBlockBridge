"""AppApi: the one object a UI talks to.

Inputs and outputs are plain Python (str, dict, dataclasses, PIL images);
nothing here imports a GUI toolkit. A UI creates one AppApi, sets the event
dispatcher for its main loop, and calls the areas below.
"""

from __future__ import annotations

import concurrent.futures
import logging
from typing import Optional

from app.api.areas import BackupsApi, ConsoleApi, JavaApi, SettingsApi, TunnelApi
from app.api.creation import CreationApi
from app.api.events import Dispatcher, EventHub, direct
from app.api.mods import ModsApi
from app.api.players import PlayersApi
from app.api.server_config import ServerConfigApi
from app.api.servers import ServersApi
from app.api.storage import StorageApi
from app.api.tasks import TaskRunner
from app.core.server_events import EventBus

logger = logging.getLogger(__name__)


class AppApi:
    def __init__(self, bus: Optional[EventBus] = None, manager=None,
                 executor: Optional[concurrent.futures.Executor] = None,
                 dispatcher: Dispatcher = direct, mods: Optional[ModsApi] = None,
                 java: Optional[JavaApi] = None, settings: Optional[SettingsApi] = None):
        self.bus = bus or EventBus()
        if manager is None:
            # Imported here: ZBBManager wires every service at construction,
            # which tests of the API alone don't need.
            from app.core.core import ZBBManager
            manager = ZBBManager(self.bus)
        self._manager = manager
        self._executor = executor or concurrent.futures.ThreadPoolExecutor(
            max_workers=4, thread_name_prefix="api-task")
        self.events = EventHub(self.bus, dispatcher)
        self.tasks = TaskRunner(self._executor, lambda: self.events.dispatcher)

        self.servers = ServersApi(manager, self.bus, self.tasks)
        self.console = ConsoleApi(manager)
        self.tunnel = TunnelApi(manager)
        self.backups = BackupsApi(manager)
        self.players = PlayersApi(manager.players)
        self.mods = mods or ModsApi(create_snapshot=self.backups.create_snapshot)
        self.java = java or JavaApi(manager=manager)
        self.settings = settings or SettingsApi(manager=manager)
        self.storage = StorageApi(manager)
        self.config = ServerConfigApi()
        self.creation = CreationApi(lambda: self.events.dispatcher)

    def set_dispatcher(self, dispatcher: Dispatcher) -> None:
        """Where event handlers, task progress and completion run from now on."""
        self.events.set_dispatcher(dispatcher)

    def start_background_services(self) -> None:
        """Tick loop, version pre-warm, tunnel auto-start (once, at startup)."""
        self._manager.bootstrap()

    def shutdown(self) -> None:
        """Stop servers, tunnel and monitors; then kill any child process that
        survived the graceful stop. Blocking (seconds): call off the UI thread."""
        self.tasks.cancel_all()
        self.events.close()
        self._manager.shutdown()
        self._kill_orphan_processes()

    def _kill_orphan_processes(self) -> None:
        # Last resort during exit: a failure here is unactionable (the Job
        # Object reaps survivors when the app dies), so it is only logged.
        for owner in (getattr(self._manager, "server_runner", None),
                      getattr(self._manager, "playit_manager", None)):
            proc = getattr(owner, "process", None) if owner else None
            if proc is None or proc.poll() is not None:
                continue
            try:
                proc.kill()
                proc.wait(timeout=2)
            except Exception as exc:  # noqa: BLE001 - see the comment above
                logger.debug("Orphan process kill failed: %s", exc)
