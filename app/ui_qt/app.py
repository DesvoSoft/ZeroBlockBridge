"""Entry point of the Qt UI (``py app/launcher.py --ui=qt``)."""

from __future__ import annotations

import logging
import signal
import sys

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication, QMessageBox

from app.core.app_config import AppConfig
from app.core.i18n import _

logger = logging.getLogger(__name__)


def _arg(name: str) -> str | None:
    prefix = f"--{name}="
    return next((a[len(prefix):] for a in sys.argv if a.startswith(prefix)), None)


def create_window(app: QApplication):
    """The API with a Qt dispatcher, the theme, and the main window (also
    used by tools/qt_spike_bench.py)."""
    from app.api import AppApi
    from app.ui_qt import theme
    from app.ui_qt.dispatcher import QtDispatcher
    from app.ui_qt.main_window import MainWindow

    dispatcher = QtDispatcher(app)
    api = AppApi(dispatcher=dispatcher)
    theme.apply(app, _arg("theme") or api.settings.get("theme", "Dark"))
    return MainWindow(api, dispatcher)


def main() -> None:
    # Startup glue (logging, language, single instance) runs before any
    # window or API exists, so -- as in app/ui/main.py -- it talks to the core.
    from app.core.bootstrap import keep_language, startup_language
    from app.core.constants import BASE_DIR, CONFIG_DIR, LOGS_DIR
    from app.core.i18n import set_language
    from app.core.logging_setup import configure_logging
    from app.core.single_instance import SingleInstanceLock
    from app.services.settings_manager import SettingsManager

    log_path = configure_logging(LOGS_DIR)
    logger.info("ZeroBlockBridge %s starting, Qt UI (log file: %s)", AppConfig.APP_VERSION, log_path)
    settings = SettingsManager()
    language = startup_language(settings, BASE_DIR)
    if _arg("lang"):  # spike: try a language for one run without saving it
        language = set_language(_arg("lang"))

    app = QApplication(sys.argv)
    app.setApplicationName("ZeroBlockBridge")
    app.setQuitOnLastWindowClosed(False)  # the tray keeps the app alive

    lock = SingleInstanceLock(CONFIG_DIR / ".zbb.lock")
    if not lock.try_acquire():
        QMessageBox.warning(None, "Zero Block Bridge", _(
            "ZeroBlockBridge is already running.\n\n"
            "If you don't see its window, look for its icon in the system tray "
            "(next to the clock) and choose Open."))
        sys.exit(1)
    if not _arg("lang"):
        keep_language(settings, language)
    if not settings.get("eula_accepted", False):
        # Spike scope: the EULA dialog is not ported yet.
        QMessageBox.information(None, "Zero Block Bridge", _(
            "Accept the Minecraft EULA in the regular window first (start without --ui=qt)."))
        lock.release()
        sys.exit(0)

    variant = _arg("variant")
    if variant in ("widgets", "qml"):
        # Visual-ceiling spike: the main screen only (docs/QT-SPIKE.md).
        from app.ui_qt.visual.launch import create
        window, backend = create(app, variant, _arg("theme") or settings.get("theme", "Dark"))
        app.setQuitOnLastWindowClosed(True)
        app.aboutToQuit.connect(backend.shutdown)
        window.show()
        backend.api.start_background_services()
        code = app.exec()
        backend.api.shutdown()
        lock.release()
        sys.exit(code)
    window = create_window(app)
    window.show()
    window.api.start_background_services()

    signal.signal(signal.SIGINT, lambda *_a: window.exit_app())
    # Let Python see Ctrl+C: the Qt loop holds the GIL-free C++ side otherwise.
    keepalive = QTimer(interval=250)
    keepalive.timeout.connect(lambda: None)
    keepalive.start()
    code = app.exec()
    lock.release()
    sys.exit(code)
