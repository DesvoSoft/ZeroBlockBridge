"""Main window of the Qt slice: server list, live status header, console,
tray and the close-to-tray choice."""

from __future__ import annotations

import concurrent.futures
import logging
import threading
import time
from typing import Any, Callable

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QAction, QIcon, QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QApplication, QCheckBox, QDialog, QFrame, QHBoxLayout, QLabel, QLineEdit,
    QListWidget, QMainWindow, QMenu, QPushButton, QSystemTrayIcon, QVBoxLayout,
    QWidget,
)

from app.core.i18n import _
from app.core.resources import assets_dir
from app.ui.formatting import engine_name, format_duration, format_memory
from app.ui_qt.console import ConsoleView
from app.ui_qt.wizard import EngineVersionDialog

logger = logging.getLogger(__name__)

CLOSE_ASK, CLOSE_TRAY, CLOSE_EXIT = "ask", "tray", "exit"
STATUS_TICK_MS = 1000
MEMORY_EVERY_TICKS = 3
SHUTDOWN_DEADLINE_S = 8.0
COMMAND_HISTORY_MAX = 50

# ServerEvent names (plain strings; the enum lives in the core).
EV_STARTING, EV_READY, EV_STOPPED = "starting", "ready", "stopped"
EV_PLAYER_COUNT, EV_CONSOLE_LINE = "player_count", "console_line"


class CloseChoiceDialog(QDialog):
    """Minimize to tray or exit; same strings as the CustomTkinter dialog."""

    def __init__(self, parent, running: list):
        super().__init__(parent)
        self.choice = None
        self.setWindowTitle(_("Close ZeroBlockBridge"))
        lay = QVBoxLayout(self)
        lay.setContentsMargins(20, 18, 20, 18)
        lay.setSpacing(12)
        lay.addWidget(QLabel(_("Close ZeroBlockBridge?"), objectName="heading"))
        text = _("Keep ZeroBlockBridge running in the system tray, or exit it completely?")
        if running:
            text += "\n\n" + _("Exiting will stop: {items}.").format(items=", ".join(running))
        body = QLabel(text, wordWrap=True)
        body.setMinimumWidth(380)
        lay.addWidget(body)
        self.remember = QCheckBox(_("Don't ask again (change it in Settings > General)"))
        lay.addWidget(self.remember)
        row = QHBoxLayout()
        row.addStretch(1)
        btn_exit = QPushButton(_("Exit"))
        btn_tray = QPushButton(_("Minimize to tray"), objectName="primary")
        btn_exit.clicked.connect(lambda: self._pick(CLOSE_EXIT))
        btn_tray.clicked.connect(lambda: self._pick(CLOSE_TRAY))
        row.addWidget(btn_exit)
        row.addWidget(btn_tray)
        lay.addLayout(row)
        btn_tray.setDefault(True)
        btn_tray.setFocus()

    def _pick(self, choice: str) -> None:
        self.choice = choice
        self.accept()


class MainWindow(QMainWindow):
    def __init__(self, api, dispatcher):
        super().__init__()
        self.api = api
        self._dispatch = dispatcher
        self._executor = concurrent.futures.ThreadPoolExecutor(max_workers=6, thread_name_prefix="qt-ui")
        self._exiting = False
        self._tray: QSystemTrayIcon | None = None
        self._tray_notified = False
        self._viewed: str | None = None
        self._phase: str | None = None       # "starting" / "running" / None
        self._phase_since = 0.0
        self._ticks = 0
        self._players = 0
        self._max_players: int | None = None
        self._history: list[str] = []
        self._history_pos = 0

        self.setWindowTitle("ZeroBlockBridge")
        self.setWindowIcon(QIcon(str(assets_dir() / "logo.png")))
        self.resize(1100, 720)
        self._build()

        self._subs = [
            api.events.subscribe(EV_CONSOLE_LINE, self._on_console_line),
            api.events.subscribe(EV_STARTING, lambda _d: self._enter_phase("starting")),
            api.events.subscribe(EV_READY, lambda _d: self._enter_phase("running")),
            api.events.subscribe(EV_STOPPED, lambda _d: self._enter_phase(None)),
            api.events.subscribe(EV_PLAYER_COUNT, self._on_player_count),
        ]
        self._tick = QTimer(self, interval=STATUS_TICK_MS)
        self._tick.timeout.connect(self._on_tick)
        self._tick.start()
        self.load_servers()

    # -- helpers -----------------------------------------------------------
    def run_async(self, fn: Callable[[], Any], on_done: Callable[[Any], None] | None = None) -> None:
        """Run ``fn`` on a worker; ``on_done(result)`` back on the GUI thread."""
        def job():
            try:
                result = fn()
            except Exception as exc:  # noqa: BLE001 - logged; the UI keeps going
                logger.exception("UI worker failed")
                result = exc
            if on_done is not None:
                self._dispatch(lambda: on_done(result))
        try:
            self._executor.submit(job)
        except RuntimeError:  # executor shut down while exiting
            pass

    # -- layout ------------------------------------------------------------
    def _build(self) -> None:
        root = QWidget(objectName="root")
        self.setCentralWidget(root)
        outer = QHBoxLayout(root)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        sidebar = QWidget(objectName="sidebar")
        sidebar.setFixedWidth(240)
        sl = QVBoxLayout(sidebar)
        sl.setContentsMargins(10, 16, 10, 12)
        brand = QLabel("ZeroBlockBridge", objectName="heading")
        sl.addWidget(brand)
        sl.addWidget(QLabel(_("Servers"), objectName="muted"))
        self.server_list = QListWidget()
        self.server_list.currentTextChanged.connect(self._on_select)
        sl.addWidget(self.server_list, 1)
        self.empty_label = QLabel(_("No servers yet."), objectName="muted")
        self.empty_label.hide()
        sl.addWidget(self.empty_label)
        btn_new = QPushButton(_("New server…"), objectName="primary")
        btn_new.clicked.connect(self.open_wizard)
        sl.addWidget(btn_new)
        outer.addWidget(sidebar)

        main = QWidget()
        ml = QVBoxLayout(main)
        ml.setContentsMargins(20, 16, 20, 16)
        ml.setSpacing(12)

        header = QFrame(objectName="card")
        hl = QHBoxLayout(header)
        hl.setContentsMargins(16, 12, 16, 12)
        titles = QVBoxLayout()
        self.lbl_name = QLabel(_("Select a server"), objectName="title")
        self.lbl_engine = QLabel("", objectName="muted")
        titles.addWidget(self.lbl_name)
        titles.addWidget(self.lbl_engine)
        hl.addLayout(titles, 1)
        self.lbl_status = QLabel(objectName="status")
        self.lbl_ram = QLabel("", objectName="badge")
        self.lbl_players = QLabel("", objectName="badge")
        for w in (self.lbl_status, self.lbl_ram, self.lbl_players):
            hl.addWidget(w, 0, Qt.AlignmentFlag.AlignVCenter)
        self.btn_start = QPushButton(_("Start"), objectName="primary")
        self.btn_start.setMinimumWidth(110)
        self.btn_start.clicked.connect(self._start_or_stop)
        hl.addWidget(self.btn_start)
        ml.addWidget(header)

        self.console = ConsoleView()
        ml.addWidget(self.console, 1)
        row = QHBoxLayout()
        self.cmd = QLineEdit(placeholderText=_("Type a command (e.g. say hello)…"))
        self.cmd.returnPressed.connect(self._send_command)
        self.btn_send = QPushButton(_("Send"))
        self.btn_send.clicked.connect(self._send_command)
        row.addWidget(self.cmd, 1)
        row.addWidget(self.btn_send)
        ml.addLayout(row)
        QShortcut(QKeySequence(Qt.Key.Key_Up), self.cmd, lambda: self._recall(-1))
        QShortcut(QKeySequence(Qt.Key.Key_Down), self.cmd, lambda: self._recall(1))
        outer.addWidget(main, 1)
        self._render_status()

    # -- servers -----------------------------------------------------------
    def load_servers(self) -> None:
        self.run_async(self.api.servers.list, self._render_servers)

    def _render_servers(self, servers) -> None:
        if isinstance(servers, Exception):
            servers = []
        self.server_list.clear()
        self.server_list.addItems(sorted(servers, key=str.lower))
        self.empty_label.setVisible(not servers)
        last = self.api.settings.get("last_server")
        matches = self.server_list.findItems(last, Qt.MatchFlag.MatchExactly) if last else []
        if matches:
            self.server_list.setCurrentItem(matches[0])
        elif servers:
            self.server_list.setCurrentRow(0)

    def _on_select(self, name: str) -> None:
        if not name:
            return
        self._viewed = name
        self.lbl_name.setText(name)
        self.lbl_engine.setText("")
        if self.api.servers.select(name):
            self.api.settings.set("last_server", name)

        def shown(info):
            if isinstance(info, Exception) or self._viewed != name:
                return
            self._max_players = info.max_players
            self.lbl_engine.setText(f"{engine_name(info.engine)} {info.mc_version or ''}".strip())
            self._render_status()
        self.run_async(lambda: self.api.servers.info(name), shown)
        self._render_status()

    # -- status ------------------------------------------------------------
    def _viewing_running(self) -> bool:
        running = self.api.servers.running_server()
        return running is not None and running == self._viewed

    def _enter_phase(self, phase: str | None) -> None:
        self._phase = phase
        self._phase_since = time.monotonic()
        if phase is None:
            self._players = 0
            self.lbl_ram.setText("")
        self._render_status()

    def _on_player_count(self, count) -> None:
        self._players = int(count or 0)
        self._render_status()

    def _render_status(self) -> None:
        viewing_running = self._phase is not None and self._viewing_running()
        if viewing_running:
            elapsed = format_duration(time.monotonic() - self._phase_since)
            if self._phase == "starting":
                text = _("Starting… {elapsed}").format(elapsed=elapsed)
            else:
                text = _("Running · {elapsed}").format(elapsed=elapsed)
            phase = self._phase
        else:
            text, phase = _("Offline"), "offline"
        self.lbl_status.setText("● " + text)
        if self.lbl_status.property("phase") != phase:
            self.lbl_status.setProperty("phase", phase)
            self.lbl_status.style().unpolish(self.lbl_status)
            self.lbl_status.style().polish(self.lbl_status)

        cap = f" / {self._max_players}" if self._max_players else ""
        self.lbl_players.setText(_("Players: {count}").format(count=f"{self._players}{cap}"))
        self.lbl_players.setVisible(viewing_running and self._phase == "running")
        self.lbl_ram.setVisible(viewing_running and bool(self.lbl_ram.text()))

        other_running = self.api.servers.is_running() and not self._viewing_running()
        if viewing_running:
            self.btn_start.setText(_("Stop"))
            self.btn_start.setObjectName("danger")
        else:
            self.btn_start.setText(_("Start"))
            self.btn_start.setObjectName("primary")
        self.btn_start.style().unpolish(self.btn_start)
        self.btn_start.style().polish(self.btn_start)
        self.btn_start.setEnabled(self._viewed is not None and not other_running)
        self.cmd.setEnabled(viewing_running)
        self.btn_send.setEnabled(viewing_running)
        if self._tray is not None:
            self._tray.setToolTip("ZeroBlockBridge - " + text if viewing_running else "ZeroBlockBridge")

    def _on_tick(self) -> None:
        if self._phase is None or not self._viewing_running():
            return
        self._ticks += 1
        self._render_status()
        if self._ticks % MEMORY_EVERY_TICKS == 0:
            def shown(sample):
                if isinstance(sample, Exception) or self._phase is None:
                    return
                self.lbl_ram.setText(format_memory(sample.used_bytes) if sample.used_bytes else "")
                self.lbl_ram.setVisible(bool(sample.used_bytes))
            self.run_async(self.api.servers.memory, shown)

    def _start_or_stop(self) -> None:
        if self._viewing_running():
            self.btn_start.setEnabled(False)
            self.run_async(self.api.servers.stop, lambda _r: self._enter_phase(None))
        elif self._viewed:
            self.btn_start.setEnabled(False)
            name = self._viewed
            self.run_async(lambda: self.api.servers.start(name), lambda _r: self._render_status())

    # -- console -----------------------------------------------------------
    def _on_console_line(self, line) -> None:
        if isinstance(line, str):
            self.console.log(line)

    def _send_command(self) -> None:
        cmd = self.cmd.text().strip()
        if not cmd:
            return
        if not self.api.console.send(cmd):
            self.console.log("[UI] " + _("The server is not running."))
            return
        self._history = (self._history + [cmd])[-COMMAND_HISTORY_MAX:]
        self._history_pos = len(self._history)
        self.cmd.clear()

    def _recall(self, step: int) -> None:
        if not self._history:
            return
        self._history_pos = max(0, min(len(self._history), self._history_pos + step))
        self.cmd.setText(self._history[self._history_pos] if self._history_pos < len(self._history) else "")

    # -- wizard ------------------------------------------------------------
    def open_wizard(self) -> EngineVersionDialog:
        dialog = EngineVersionDialog(self.api, self.run_async, self)
        dialog.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
        dialog.open()
        return dialog

    # -- close / tray ------------------------------------------------------
    def _running_summary(self) -> list:
        running = []
        if self.api.servers.is_running():
            running.append(_("the server '{name}'").format(name=self.api.servers.active))
        if self.api.tunnel.is_running:
            running.append(_("the Playit tunnel"))
        if self.api.servers.creations():
            running.append(_("the server being created"))
        return running

    def closeEvent(self, event) -> None:
        if self._exiting:
            event.accept()
            return
        event.ignore()
        tray_ok = QSystemTrayIcon.isSystemTrayAvailable()
        setting = self.api.settings.get("close_action", CLOSE_ASK)
        action = CLOSE_EXIT if not tray_ok else (setting if setting in (CLOSE_ASK, CLOSE_TRAY, CLOSE_EXIT) else CLOSE_ASK)
        if action == CLOSE_ASK:
            dialog = CloseChoiceDialog(self, self._running_summary())
            if dialog.exec() != QDialog.DialogCode.Accepted or dialog.choice is None:
                return
            if dialog.remember.isChecked():
                self.api.settings.set("close_action", dialog.choice)
            action = dialog.choice
        if action == CLOSE_TRAY:
            self.hide_to_tray()
        else:
            self.exit_app()

    def _ensure_tray(self) -> QSystemTrayIcon:
        if self._tray is None:
            tray = QSystemTrayIcon(self.windowIcon(), self)
            menu = QMenu(self)
            act_open = QAction(_("Open ZeroBlockBridge"), menu)
            act_open.triggered.connect(self.show_from_tray)
            menu.addAction(act_open)
            menu.setDefaultAction(act_open)
            menu.addSeparator()
            act_exit = QAction(_("Exit"), menu)
            act_exit.triggered.connect(self.exit_app)
            menu.addAction(act_exit)
            tray.setContextMenu(menu)
            tray.activated.connect(lambda reason: reason == QSystemTrayIcon.ActivationReason.Trigger
                                   and self.show_from_tray())
            self._tray = tray
            self._render_status()
        return self._tray

    def hide_to_tray(self) -> None:
        tray = self._ensure_tray()
        tray.show()
        self.hide()
        if not self._tray_notified:
            self._tray_notified = True
            tray.showMessage("ZeroBlockBridge", _("ZeroBlockBridge is still running here. "
                                                  "Right-click the icon to open or exit."))

    def show_from_tray(self) -> None:
        if self._tray is not None:
            self._tray.hide()
        self.showNormal()
        self.raise_()
        self.activateWindow()

    def exit_app(self) -> None:
        if self._exiting:
            return
        self._exiting = True
        if self._tray is not None:
            self._tray.hide()
        self._tick.stop()
        for sub in self._subs:
            sub.cancel()
        self.api.tasks.cancel_all()
        self.api.settings.save()
        self._executor.shutdown(wait=False, cancel_futures=True)
        self.hide()
        # api.shutdown() blocks (graceful server stop): off the GUI thread,
        # with a deadline so a stuck stop can't keep the process alive.
        done = threading.Event()

        def shutdown():
            try:
                self.api.shutdown()
            finally:
                done.set()
        threading.Thread(target=shutdown, name="qt-shutdown", daemon=True).start()
        deadline = time.monotonic() + SHUTDOWN_DEADLINE_S

        def poll():
            if done.is_set() or time.monotonic() > deadline:
                QApplication.instance().quit()
            else:
                QTimer.singleShot(100, poll)
        poll()
