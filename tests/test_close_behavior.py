"""Window close: tray vs exit choice, and exit really ending the process."""
import subprocess
import sys
import time
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from app.ui import tray
from app.ui.tray import CLOSE_ASK, CLOSE_EXIT, CLOSE_TRAY, resolve_close_action

ROOT = Path(__file__).resolve().parent.parent


@pytest.mark.parametrize("setting, tray_ok, expected", [
    ("ask", True, CLOSE_ASK),
    ("tray", True, CLOSE_TRAY),
    ("exit", True, CLOSE_EXIT),
    (None, True, CLOSE_ASK),            # never chosen
    ("bogus", True, CLOSE_ASK),         # hand-edited settings file
    ("tray", False, CLOSE_EXIT),        # no tray: X must exit, never hide
    ("ask", False, CLOSE_EXIT),
])
def test_resolve_close_action(setting, tray_ok, expected):
    assert resolve_close_action(setting, tray_ok) == expected


def test_no_tray_on_linux(monkeypatch):
    monkeypatch.setattr(sys, "platform", "linux")
    assert tray.tray_supported() is False


def test_tray_supported_needs_pystray(monkeypatch):
    monkeypatch.setattr(sys, "platform", "win32")
    monkeypatch.setitem(sys.modules, "pystray", None)  # import fails
    assert tray.tray_supported() is False


def test_close_message_names_what_exit_stops():
    from app.ui.close_dialog import close_message
    assert "Exiting will stop" not in close_message([])
    msg = close_message(["the server 'OneBlock'", "the Playit tunnel"])
    assert "the server 'OneBlock', the Playit tunnel." in msg


def test_tray_actions_run_on_the_tk_thread():
    app = MagicMock()
    icon = tray.TrayIcon(app, on_open=lambda: None, on_exit=lambda: None)
    action = MagicMock()
    icon._marshal(action)()
    app.after.assert_called_once_with(0, action)
    action.assert_not_called()  # pystray's thread never touches Tk directly


def test_tray_action_after_tk_is_gone_is_dropped():
    app = MagicMock()
    app.after.side_effect = RuntimeError("main thread is not in main loop")
    tray.TrayIcon(app, lambda: None, lambda: None)._marshal(lambda: None)()  # no raise


def test_close_action_defaults_to_ask():
    from app.services.settings_manager import SettingsManager
    assert SettingsManager()._get_defaults()["close_action"] == "ask"


def test_exit_does_not_wait_for_stuck_background_work():
    """Regression: a task still running (jar download, Forge install,
    backup) kept a windowless process alive until it finished."""
    code = (
        "import threading, time\n"
        "from app.ui.main import finish_exit\n"
        "threading.Thread(target=time.sleep, args=(60,), daemon=False).start()\n"
        "finish_exit(grace=0.5)\n"
        "print('not reached')\n"
    )
    start = time.monotonic()
    result = subprocess.run([sys.executable, "-c", code], cwd=ROOT, capture_output=True, text=True, timeout=60)
    assert time.monotonic() - start < 20, "process waited for the stuck thread"
    assert result.returncode == 0
    assert "not reached" not in result.stdout


def test_exit_without_leftover_work_returns_normally():
    code = (
        "from app.ui.main import finish_exit\n"
        "finish_exit(grace=0.5)\n"
        "print('returned')\n"
    )
    result = subprocess.run([sys.executable, "-c", code], cwd=ROOT, capture_output=True, text=True, timeout=60)
    assert result.returncode == 0 and "returned" in result.stdout


def test_assets_never_resolve_under_a_relocated_data_dir(tmp_path):
    """Found while testing the tray: with ZBB_DATA_DIR set (and not frozen),
    ASSETS_DIR pointed into the data folder, so the tray icon image (and
    the window icon) couldn't be found."""
    import os
    code = "from app.core.constants import ASSETS_DIR; print(ASSETS_DIR)"
    env = dict(os.environ, ZBB_DATA_DIR=str(tmp_path))
    out = subprocess.run([sys.executable, "-c", code], cwd=ROOT, env=env,
                         capture_output=True, text=True, timeout=60).stdout.strip()
    assert Path(out) == ROOT / "assets"
    assert (Path(out) / "logo.png").exists()
