import json
import sys
from pathlib import Path

import pytest

from app.core import bootstrap


@pytest.fixture(autouse=True)
def _isolated_appdata(tmp_path, monkeypatch):
    """Sandbox the marker file location so tests never touch the real
    %LOCALAPPDATA%\\ZeroBlockBridge, and never leak ZBB_DATA_DIR into
    other tests."""
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "AppData"))
    monkeypatch.delenv("ZBB_DATA_DIR", raising=False)
    return tmp_path


def _marker_file(tmp_path):
    return tmp_path / "AppData" / "ZeroBlockBridge" / "install.json"


def test_dev_mode_returns_repo_root_without_marker_or_env(monkeypatch, tmp_path):
    monkeypatch.setattr(sys, "frozen", False, raising=False)

    result = bootstrap.resolve_data_dir()

    expected = Path(bootstrap.__file__).resolve().parent.parent.parent
    assert result == expected
    assert "ZBB_DATA_DIR" not in __import__("os").environ
    assert not _marker_file(tmp_path).exists()


def test_frozen_with_valid_marker_returns_it_without_dialog(monkeypatch, tmp_path):
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "executable", str(tmp_path / "exe" / "ZeroBlockBridge.exe"), raising=False)
    data_dir = tmp_path / "chosen_data"
    data_dir.mkdir()
    marker = _marker_file(tmp_path)
    marker.parent.mkdir(parents=True)
    marker.write_text(json.dumps({"data_dir": str(data_dir)}), encoding="utf-8")

    def _fail_if_called(exe_dir):
        raise AssertionError("dialog must not be shown when a valid marker exists")

    monkeypatch.setattr("app.ui.first_run_dialog.ask_data_dir", _fail_if_called, raising=False)

    result = bootstrap.resolve_data_dir()

    assert result == data_dir
    import os
    assert os.environ["ZBB_DATA_DIR"] == str(data_dir)


def test_frozen_no_marker_but_existing_servers_dir_adopts_silently(monkeypatch, tmp_path):
    exe_dir = tmp_path / "exe"
    (exe_dir / "servers").mkdir(parents=True)
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "executable", str(exe_dir / "ZeroBlockBridge.exe"), raising=False)

    def _fail_if_called(exe_dir):
        raise AssertionError("dialog must not be shown for a pre-existing install")

    monkeypatch.setattr("app.ui.first_run_dialog.ask_data_dir", _fail_if_called, raising=False)

    result = bootstrap.resolve_data_dir()

    assert result == exe_dir
    marker = json.loads(_marker_file(tmp_path).read_text(encoding="utf-8"))
    assert marker["data_dir"] == str(exe_dir)


def test_frozen_fresh_install_shows_dialog_and_persists_choice(monkeypatch, tmp_path):
    exe_dir = tmp_path / "exe"
    exe_dir.mkdir()
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "executable", str(exe_dir / "ZeroBlockBridge.exe"), raising=False)

    chosen = tmp_path / "user_chosen"
    calls = []

    def _fake_ask(passed_exe_dir):
        calls.append(passed_exe_dir)
        chosen.mkdir()
        return chosen

    monkeypatch.setattr("app.ui.first_run_dialog.ask_data_dir", _fake_ask, raising=False)

    result = bootstrap.resolve_data_dir()

    assert result == chosen
    assert calls == [exe_dir]
    marker = json.loads(_marker_file(tmp_path).read_text(encoding="utf-8"))
    assert marker["data_dir"] == str(chosen)


def test_frozen_marker_pointing_to_unwritable_dir_falls_back(monkeypatch, tmp_path):
    exe_dir = tmp_path / "exe"
    exe_dir.mkdir()
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "executable", str(exe_dir / "ZeroBlockBridge.exe"), raising=False)

    stale = tmp_path / "stale_dir"
    marker = _marker_file(tmp_path)
    marker.parent.mkdir(parents=True)
    marker.write_text(json.dumps({"data_dir": str(stale)}), encoding="utf-8")

    monkeypatch.setattr(bootstrap, "is_writable_dir", lambda p: p != stale)

    fresh = tmp_path / "fresh_choice"

    def _fake_ask(passed_exe_dir):
        fresh.mkdir()
        return fresh

    monkeypatch.setattr("app.ui.first_run_dialog.ask_data_dir", _fake_ask, raising=False)

    result = bootstrap.resolve_data_dir()

    assert result == fresh


def test_is_writable_dir_true_for_new_and_existing_dir(tmp_path):
    target = tmp_path / "new_subdir"
    assert bootstrap.is_writable_dir(target) is True
    assert target.exists()
    assert bootstrap.is_writable_dir(target) is True
