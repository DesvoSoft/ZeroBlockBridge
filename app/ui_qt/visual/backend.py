"""One presentation backend for both variants: a QObject over ``app.api``
with Qt properties, signals and slots (what QML binds to, and what the
Widgets variant connects to), plus a capped console list model."""

from __future__ import annotations

import concurrent.futures
import time
from typing import Any, Callable

from PySide6.QtCore import (
    Property, QAbstractListModel, QModelIndex, QObject, Qt, QTimer, Signal, Slot,
)

from app.core.i18n import _
from app.ui.formatting import engine_name, format_duration, format_memory

MAX_LINES = 1000
FLUSH_MS = 50
EV = {"starting": "starting", "ready": "ready", "stopped": "stopped",
      "players": "player_count", "line": "console_line"}


class ConsoleModel(QAbstractListModel):
    """Console lines for a QML ListView: appended in batches, capped."""
    LineRole = Qt.ItemDataRole.UserRole + 1

    def __init__(self, parent=None):
        super().__init__(parent)
        self._lines: list[str] = []

    def rowCount(self, parent=QModelIndex()):  # noqa: N802 - Qt API
        return 0 if parent.isValid() else len(self._lines)

    def data(self, index, role=Qt.ItemDataRole.DisplayRole):
        if not index.isValid():
            return None
        if role in (Qt.ItemDataRole.DisplayRole, self.LineRole):
            return self._lines[index.row()]
        return None

    def roleNames(self):  # noqa: N802 - Qt API
        return {self.LineRole: b"line"}

    def append(self, lines: list[str]) -> None:
        lines = lines[-MAX_LINES:]
        overflow = len(self._lines) + len(lines) - MAX_LINES
        if overflow > 0:
            self.beginRemoveRows(QModelIndex(), 0, overflow - 1)
            del self._lines[:overflow]
            self.endRemoveRows()
        first = len(self._lines)
        self.beginInsertRows(QModelIndex(), first, first + len(lines) - 1)
        self._lines.extend(lines)
        self.endInsertRows()

    def clear(self) -> None:
        self.beginResetModel()
        self._lines.clear()
        self.endResetModel()


class MainBackend(QObject):
    changed = Signal()            # header / buttons
    serversChanged = Signal()
    selectedChanged = Signal()
    loadingChanged = Signal()
    linesAppended = Signal(list)  # one batch of console lines
    consoleCleared = Signal()

    def __init__(self, api, dispatcher, parent=None):
        super().__init__(parent)
        self.api = api
        self._dispatch = dispatcher
        self._executor = concurrent.futures.ThreadPoolExecutor(max_workers=4, thread_name_prefix="qt-visual")
        self._servers: list[str] = []
        self._selected = ""
        self._engine = ""
        self._loading = False
        self._phase = "offline"
        self._since = 0.0
        self._players = 0
        self._max_players: int | None = None
        self._ram = ""
        self._pending: list[str] = []
        self.console = ConsoleModel(self)
        self._flush = QTimer(self, interval=FLUSH_MS, singleShot=True)
        self._flush.timeout.connect(self._flush_lines)
        self._tick = QTimer(self, interval=1000)
        self._tick.timeout.connect(self._on_tick)
        self._tick.start()
        self._subs = [
            api.events.subscribe(EV["line"], self._on_line),
            api.events.subscribe(EV["starting"], lambda _d: self._set_phase("starting")),
            api.events.subscribe(EV["ready"], lambda _d: self._set_phase("running")),
            api.events.subscribe(EV["stopped"], lambda _d: self._set_phase("offline")),
            api.events.subscribe(EV["players"], self._on_players),
        ]

    def run_async(self, fn: Callable[[], Any], on_done: Callable[[Any], None]) -> None:
        def job():
            try:
                result = fn()
            except Exception as exc:  # noqa: BLE001 - shown as "no data"
                result = exc
            self._dispatch(lambda: on_done(result))
        self._executor.submit(job)

    # -- properties (QML binds to these) -------------------------------------
    def _get_servers(self): return self._servers
    def _get_selected(self): return self._selected
    def _get_engine(self): return self._engine
    def _get_loading(self): return self._loading
    def _get_phase(self): return self._phase if self._viewing_running() else "offline"

    def _get_status(self) -> str:
        phase = self._get_phase()
        if phase == "offline":
            return _("Offline")
        elapsed = format_duration(time.monotonic() - self._since)
        template = _("Starting… {elapsed}") if phase == "starting" else _("Running · {elapsed}")
        return template.format(elapsed=elapsed)

    def _get_ram(self): return self._ram if self._get_phase() != "offline" else ""

    def _get_players(self) -> str:
        if self._get_phase() != "running":
            return ""
        cap = f" / {self._max_players}" if self._max_players else ""
        return _("Players: {count}").format(count=f"{self._players}{cap}")

    def _get_start_label(self): return _("Stop") if self._get_phase() != "offline" else _("Start")

    def _get_can_start(self) -> bool:
        return bool(self._selected) and not (self.api.servers.is_running() and not self._viewing_running())

    servers = Property(list, _get_servers, notify=serversChanged)
    selected = Property(str, _get_selected, notify=selectedChanged)
    engineText = Property(str, _get_engine, notify=changed)
    loading = Property(bool, _get_loading, notify=loadingChanged)
    phase = Property(str, _get_phase, notify=changed)
    statusText = Property(str, _get_status, notify=changed)
    ramText = Property(str, _get_ram, notify=changed)
    playersText = Property(str, _get_players, notify=changed)
    startLabel = Property(str, _get_start_label, notify=changed)
    canStart = Property(bool, _get_can_start, notify=changed)

    # Translated labels QML needs (it has no access to gettext).
    @Slot(str, result=str)
    def tr(self, text: str) -> str:
        return _(text)

    # -- slots ---------------------------------------------------------------
    @Slot()
    def refresh(self) -> None:
        def shown(servers):
            self._servers = sorted(servers, key=str.lower) if isinstance(servers, list) else []
            self.serversChanged.emit()
            last = self.api.settings.get("last_server")
            if not self._selected and self._servers:
                self.select(last if last in self._servers else self._servers[0])
        self.run_async(self.api.servers.list, shown)

    @Slot(str)
    def select(self, name: str) -> None:
        if not name or name == self._selected:
            return
        self._selected = name
        self._engine = ""
        self._set_loading(True)
        self.selectedChanged.emit()
        if self.api.servers.select(name):
            self.api.settings.set("last_server", name)

        def shown(info):
            if self._selected != name:
                return
            if not isinstance(info, Exception):
                self._max_players = info.max_players
                self._engine = f"{engine_name(info.engine)} {info.mc_version or ''}".strip()
            self._set_loading(False)
            self.changed.emit()
        self.run_async(lambda: self.api.servers.info(name), shown)
        self.changed.emit()

    @Slot()
    def startStop(self) -> None:  # noqa: N802 - QML name
        if self._viewing_running():
            self.run_async(self.api.servers.stop, lambda _r: self._set_phase("offline"))
        elif self._selected:
            name = self._selected
            self.run_async(lambda: self.api.servers.start(name), lambda _r: self.changed.emit())

    @Slot(str, result=bool)
    def sendCommand(self, text: str) -> bool:  # noqa: N802 - QML name
        text = text.strip()
        if not text:
            return False
        if not self.api.console.send(text):
            self._on_line("[UI] " + _("The server is not running."))
            return False
        return True

    # -- events --------------------------------------------------------------
    def _viewing_running(self) -> bool:
        running = self.api.servers.running_server()
        return running is not None and running == self._selected

    def _set_loading(self, value: bool) -> None:
        if self._loading != value:
            self._loading = value
            self.loadingChanged.emit()

    def _set_phase(self, phase: str) -> None:
        self._phase = phase
        self._since = time.monotonic()
        if phase == "offline":
            self._players, self._ram = 0, ""
        self.changed.emit()

    def _on_players(self, count) -> None:
        self._players = int(count or 0)
        self.changed.emit()

    def _on_tick(self) -> None:
        if self._get_phase() == "offline":
            return
        self.changed.emit()
        if int(time.monotonic() - self._since) % 3 == 0:
            def shown(sample):
                if not isinstance(sample, Exception) and sample.used_bytes:
                    self._ram = format_memory(sample.used_bytes)
                    self.changed.emit()
            self.run_async(self.api.servers.memory, shown)

    def _on_line(self, line) -> None:
        if isinstance(line, str):
            self._pending.append(line.rstrip("\n"))
            if not self._flush.isActive():
                self._flush.start()

    def _flush_lines(self) -> None:
        batch, self._pending = self._pending, []
        if batch:
            self.console.append(batch)
            self.linesAppended.emit(batch)

    def shutdown(self) -> None:
        for sub in self._subs:
            sub.cancel()
        self._executor.shutdown(wait=False, cancel_futures=True)

    # -- demo (bench and screenshots only: no server is started) -------------
    def demo_running(self, ram_bytes: int = int(2.4 * 2**30), players: int = 3) -> None:
        name = self._selected
        self.api.servers.running_server = lambda: name
        self.api.servers.is_running = lambda: True
        self._set_phase("running")
        self._since -= 4980
        self._players, self._ram = players, format_memory(ram_bytes)
        self.changed.emit()
