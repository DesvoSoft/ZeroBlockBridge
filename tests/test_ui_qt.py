"""Roadmap 8c Qt spike: app/ui_qt stays on the API seam, and its dispatcher
runs callbacks on the GUI thread. The dispatcher tests need PySide6
(requirements-qt.txt) and are skipped without it."""

import threading
from pathlib import Path

import pytest

from tests import test_api_facade as facade

ROOT = Path(__file__).resolve().parent.parent
QT_MODULES = sorted(p.name for p in (ROOT / "app" / "ui_qt").glob("*.py"))
# Pure presentation helpers shared with the CustomTkinter UI (no toolkit import).
ALLOWED_UI = {"app.ui.formatting"}


@pytest.mark.parametrize("module", QT_MODULES)
def test_qt_ui_reaches_the_core_only_through_the_api(module):
    """Same rule as the CustomTkinter screens; app.py's main() (startup glue
    before any window or API exists) is the documented exception."""
    names = facade._screen_imports(ROOT / "app" / "ui_qt" / module)
    leaks = {n for n in names if n.startswith(("app.core", "app.services"))
             and not any(n == a or n.startswith(a + ".") for a in facade.TestBoundaries.ALLOWED_CORE)
             and n != "app.core"}
    assert not leaks, f"{module} imports {sorted(leaks)}"
    ui = {n for n in names if n.startswith("app.ui.") and not n.startswith("app.ui_qt")
          and not any(n == a or n.startswith(a + ".") for a in ALLOWED_UI)}
    assert not ui, f"{module} imports CustomTkinter screens {sorted(ui)}"
    assert not names & {"tkinter", "customtkinter", "pystray", "subprocess", "shutil", "requests", "psutil"}


def test_api_never_imports_the_qt_ui():
    for path in (ROOT / "app" / "api").glob("*.py"):
        assert "ui_qt" not in path.read_text(encoding="utf-8"), path.name


class TestQtDispatcher:
    @pytest.fixture
    def app(self):
        QtWidgets = pytest.importorskip("PySide6.QtWidgets")
        return QtWidgets.QApplication.instance() or QtWidgets.QApplication([])

    def _drain(self, app, until, timeout=2.0):
        import time
        end = time.monotonic() + timeout
        while not until() and time.monotonic() < end:
            app.processEvents()
        return until()

    def test_runs_on_the_gui_thread_when_called_from_a_worker(self, app):
        from app.ui_qt.dispatcher import QtDispatcher
        dispatch = QtDispatcher()
        seen = []
        worker = threading.Thread(target=lambda: dispatch(lambda: seen.append(threading.current_thread())))
        worker.start()
        worker.join()
        assert self._drain(app, lambda: seen)
        assert seen == [threading.main_thread()]

    def test_is_deferred_and_ordered_on_the_gui_thread(self, app):
        from app.ui_qt.dispatcher import QtDispatcher
        dispatch = QtDispatcher()
        seen = []
        for i in range(5):
            dispatch(lambda i=i: seen.append(i))
        assert seen == []  # like Tk's after(0): never inline
        assert self._drain(app, lambda: len(seen) == 5)
        assert seen == [0, 1, 2, 3, 4]

    def test_a_failing_callback_does_not_stop_the_next(self, app):
        from app.ui_qt.dispatcher import QtDispatcher
        dispatch = QtDispatcher()
        seen = []
        dispatch(lambda: 1 / 0)
        dispatch(lambda: seen.append("ok"))
        assert self._drain(app, lambda: seen)

    def test_cancelled_subscription_drops_queued_calls(self, app):
        from app.api.events import EventHub
        from app.core.server_events import EventBus
        from app.ui_qt.dispatcher import QtDispatcher
        bus = EventBus()
        hub = EventHub(bus, QtDispatcher())
        seen = []
        sub = hub.subscribe("console_line", seen.append)
        bus.emit("console_line", "a")
        sub.cancel()
        app.processEvents()
        assert seen == []
