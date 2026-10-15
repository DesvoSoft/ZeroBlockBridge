import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from app.core import bootstrap, i18n, installer
from app.core.app_config import AppConfig
from app.core.bootstrap import MODE_INSTALLED, MODE_MANUAL, PORTABLE_FLAG, SetupResult
from app.core.fs_links import create_junction, is_link, link_target

REAL_PLATFORM = sys.platform


class _Calls:
    def __init__(self):
        self.setup = []
        self.already = []
        self.launched = []
        self.setup_result = None
        self.already_result = "run"


@pytest.fixture(autouse=True)
def env(tmp_path, monkeypatch):
    """Sandbox the marker file location so tests never touch the real
    %LOCALAPPDATA%\\ZeroBlockBridge, never leak ZBB_DATA_DIR into other
    tests, and never open a real dialog or launch a real process."""
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "AppData"))
    monkeypatch.delenv("ZBB_DATA_DIR", raising=False)
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "platform", "win32")

    calls = _Calls()

    def _ask_setup(exe, data_dir):
        calls.setup.append((exe, data_dir))
        return calls.setup_result

    def _ask_already(exe, installed, installed_version):
        calls.already.append((exe, installed, installed_version))
        return calls.already_result

    monkeypatch.setattr("app.ui.first_run_dialog.ask_setup", _ask_setup)
    monkeypatch.setattr("app.ui.first_run_dialog.ask_already_installed", _ask_already)
    monkeypatch.setattr(installer, "launch", calls.launched.append)
    monkeypatch.setattr(installer, "register_uninstall", lambda exe, version: None)
    return calls


def _marker_file(tmp_path):
    return tmp_path / "AppData" / "ZeroBlockBridge" / "install.json"


def _write_marker(tmp_path, data):
    marker = _marker_file(tmp_path)
    marker.parent.mkdir(parents=True, exist_ok=True)
    marker.write_text(json.dumps(data), encoding="utf-8")


def _read_marker(tmp_path):
    return json.loads(_marker_file(tmp_path).read_text(encoding="utf-8"))


def _run_exe(monkeypatch, exe: Path):
    exe.parent.mkdir(parents=True, exist_ok=True)
    exe.write_bytes(b"exe")
    monkeypatch.setattr(sys, "executable", str(exe), raising=False)
    return exe


def _zbb_folder(folder: Path) -> Path:
    """Make `folder` look like ZBB data (as a real session leaves it)."""
    (folder / "config").mkdir(parents=True, exist_ok=True)
    (folder / "config" / "zbb_settings.json").write_text("{}", encoding="utf-8")
    return folder


def _server(folder: Path) -> Path:
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "server.properties").write_text("motd=x", encoding="utf-8")
    return folder


# ----------------------------------------------------------------------
# Data dir resolution
# ----------------------------------------------------------------------
def test_dev_mode_returns_repo_root_without_marker_or_env(monkeypatch, tmp_path, env):
    monkeypatch.setattr(sys, "frozen", False, raising=False)

    result = bootstrap.resolve_data_dir()

    assert result == Path(bootstrap.__file__).resolve().parent.parent.parent
    assert "ZBB_DATA_DIR" not in os.environ
    assert not _marker_file(tmp_path).exists()
    assert env.setup == []


def test_portable_flag_uses_exe_dir_without_dialog(monkeypatch, tmp_path, env):
    exe = _run_exe(monkeypatch, tmp_path / "usb" / "ZeroBlockBridge.exe")
    (exe.parent / PORTABLE_FLAG).write_text("x", encoding="utf-8")
    _write_marker(tmp_path, {"data_dir": str(tmp_path / "elsewhere"), "mode": MODE_MANUAL})

    assert bootstrap.resolve_data_dir() == exe.parent
    assert os.environ["ZBB_DATA_DIR"] == str(exe.parent)
    assert env.setup == [] and env.already == []


def test_manual_marker_is_used_silently(monkeypatch, tmp_path, env):
    _run_exe(monkeypatch, tmp_path / "Downloads" / "ZeroBlockBridge.exe")
    data = tmp_path / "data"
    _write_marker(tmp_path, {"data_dir": str(data), "mode": MODE_MANUAL})

    assert bootstrap.resolve_data_dir() == data
    assert os.environ["ZBB_DATA_DIR"] == str(data)
    assert env.setup == [] and env.already == []


def test_running_the_installed_exe_needs_no_dialog(monkeypatch, tmp_path, env):
    exe = _run_exe(monkeypatch, tmp_path / "Programs" / "ZeroBlockBridge.exe")
    data = tmp_path / "data"
    _write_marker(tmp_path, {"data_dir": str(data), "mode": MODE_INSTALLED,
                             "exe_path": str(exe), "version": AppConfig.APP_VERSION})

    assert bootstrap.resolve_data_dir() == data
    assert env.setup == [] and env.already == []


def test_installed_exe_updated_in_place_refreshes_recorded_version(monkeypatch, tmp_path, env):
    exe = _run_exe(monkeypatch, tmp_path / "Programs" / "ZeroBlockBridge.exe")
    data = tmp_path / "data"
    _write_marker(tmp_path, {"data_dir": str(data), "mode": MODE_INSTALLED,
                             "exe_path": str(exe), "version": "0.0.1"})

    bootstrap.resolve_data_dir()

    assert _read_marker(tmp_path)["version"] == AppConfig.APP_VERSION


def _installed_and_download(monkeypatch, tmp_path):
    installed = tmp_path / "Programs" / "ZeroBlockBridge.exe"
    installed.parent.mkdir(parents=True)
    installed.write_bytes(b"old")
    download = _run_exe(monkeypatch, tmp_path / "Downloads" / "ZeroBlockBridge.exe")
    data = tmp_path / "data"
    _write_marker(tmp_path, {"data_dir": str(data), "mode": MODE_INSTALLED,
                             "exe_path": str(installed), "version": "0.0.1"})
    return installed, download, data


def test_second_copy_asks_and_can_run_anyway(monkeypatch, tmp_path, env):
    installed, download, data = _installed_and_download(monkeypatch, tmp_path)
    env.already_result = "run"

    assert bootstrap.resolve_data_dir() == data
    assert env.already == [(download, installed, "0.0.1")]
    assert env.launched == []


def test_second_copy_open_hands_over_to_installed_app(monkeypatch, tmp_path, env):
    installed, _, _ = _installed_and_download(monkeypatch, tmp_path)
    env.already_result = "open"

    with pytest.raises(SystemExit):
        bootstrap.resolve_data_dir()
    assert env.launched == [installed]
    assert _read_marker(tmp_path)["version"] == "0.0.1"


def test_second_copy_update_records_version_and_opens_installed(monkeypatch, tmp_path, env):
    installed, _, _ = _installed_and_download(monkeypatch, tmp_path)
    env.already_result = "updated"

    with pytest.raises(SystemExit):
        bootstrap.resolve_data_dir()
    assert env.launched == [installed]
    assert _read_marker(tmp_path)["version"] == AppConfig.APP_VERSION


def test_second_copy_dialog_closed_quits(monkeypatch, tmp_path, env):
    _installed_and_download(monkeypatch, tmp_path)
    env.already_result = "cancel"

    with pytest.raises(SystemExit):
        bootstrap.resolve_data_dir()
    assert env.launched == []


def test_marker_from_older_build_offers_install_keeping_data(monkeypatch, tmp_path, env):
    exe = _run_exe(monkeypatch, tmp_path / "Downloads" / "ZeroBlockBridge.exe")
    data = tmp_path / "data"
    _write_marker(tmp_path, {"data_dir": str(data)})
    env.setup_result = SetupResult(MODE_MANUAL, data)

    assert bootstrap.resolve_data_dir() == data
    assert env.setup == [(exe, data)]
    assert _read_marker(tmp_path) == {"data_dir": str(data), "mode": MODE_MANUAL, "language": "en"}


def test_install_offer_closed_runs_and_asks_again_later(monkeypatch, tmp_path, env):
    _run_exe(monkeypatch, tmp_path / "Downloads" / "ZeroBlockBridge.exe")
    data = tmp_path / "data"
    _write_marker(tmp_path, {"data_dir": str(data)})
    env.setup_result = None

    assert bootstrap.resolve_data_dir() == data
    assert _read_marker(tmp_path) == {"data_dir": str(data)}


def test_deleted_install_offers_setup_again(monkeypatch, tmp_path, env):
    exe = _run_exe(monkeypatch, tmp_path / "Downloads" / "ZeroBlockBridge.exe")
    data = tmp_path / "data"
    _write_marker(tmp_path, {"data_dir": str(data), "mode": MODE_INSTALLED,
                             "exe_path": str(tmp_path / "gone" / "ZeroBlockBridge.exe")})
    env.setup_result = SetupResult(MODE_MANUAL, data)

    bootstrap.resolve_data_dir()

    assert env.setup == [(exe, data)]


def test_no_marker_but_existing_servers_dir_adopts_as_portable(monkeypatch, tmp_path, env):
    exe = _run_exe(monkeypatch, tmp_path / "exe" / "ZeroBlockBridge.exe")
    _zbb_folder(exe.parent)
    (exe.parent / "servers").mkdir()

    assert bootstrap.resolve_data_dir() == exe.parent
    assert (exe.parent / PORTABLE_FLAG).exists()
    assert env.setup == []
    assert not _marker_file(tmp_path).exists()


def test_fresh_portable_choice_writes_flag_not_marker(monkeypatch, tmp_path, env):
    exe = _run_exe(monkeypatch, tmp_path / "usb" / "ZeroBlockBridge.exe")
    env.setup_result = SetupResult("portable", exe.parent)

    assert bootstrap.resolve_data_dir() == exe.parent
    assert env.setup == [(exe, None)]
    assert (exe.parent / PORTABLE_FLAG).exists()
    assert not _marker_file(tmp_path).exists()


def test_fresh_install_records_install_and_opens_installed_copy(monkeypatch, tmp_path, env):
    _run_exe(monkeypatch, tmp_path / "Downloads" / "ZeroBlockBridge.exe")
    data = tmp_path / "data"
    installed = tmp_path / "Programs" / "ZeroBlockBridge.exe"
    env.setup_result = SetupResult(MODE_INSTALLED, data, installed)

    with pytest.raises(SystemExit):
        bootstrap.resolve_data_dir()

    assert _read_marker(tmp_path) == {"data_dir": str(data), "mode": MODE_INSTALLED,
                                      "exe_path": str(installed), "version": AppConfig.APP_VERSION, "language": "en"}
    assert env.launched == [installed]


def test_fresh_setup_closed_quits_without_marker(monkeypatch, tmp_path, env):
    _run_exe(monkeypatch, tmp_path / "Downloads" / "ZeroBlockBridge.exe")
    env.setup_result = None

    with pytest.raises(SystemExit):
        bootstrap.resolve_data_dir()
    assert not _marker_file(tmp_path).exists()


def test_marker_pointing_to_unwritable_dir_falls_back_to_setup(monkeypatch, tmp_path, env):
    exe = _run_exe(monkeypatch, tmp_path / "Downloads" / "ZeroBlockBridge.exe")
    stale = tmp_path / "stale_dir"
    _write_marker(tmp_path, {"data_dir": str(stale), "mode": MODE_MANUAL})
    monkeypatch.setattr(bootstrap, "is_writable_dir", lambda p: p != stale)
    fresh = tmp_path / "fresh_choice"
    env.setup_result = SetupResult(MODE_MANUAL, fresh)

    assert bootstrap.resolve_data_dir() == fresh
    assert env.setup == [(exe, None)]


def test_is_writable_dir_true_for_new_and_existing_dir(tmp_path):
    target = tmp_path / "new_subdir"
    assert bootstrap.is_writable_dir(target) is True
    assert target.exists()
    assert bootstrap.is_writable_dir(target) is True


# ----------------------------------------------------------------------
# Stray data left next to the exe (the "server disappeared" bug)
# ----------------------------------------------------------------------
def test_rescue_moves_servers_backups_and_missing_config(tmp_path):
    exe_dir, data = tmp_path / "Downloads", tmp_path / "data"
    _server(exe_dir / "servers" / "OneBlock")
    (exe_dir / "servers" / "OneBlock" / "server.jar").write_text("jar")
    (exe_dir / "backups" / "OneBlock").mkdir(parents=True)
    (exe_dir / "config").mkdir()
    for name in ("playit.toml", ".zbb.lock", "versions_cache.json", "zbb_settings.json"):
        (exe_dir / "config" / name).write_text(f"old {name}")
    (data / "config").mkdir(parents=True)
    (data / "config" / "zbb_settings.json").write_text("newer settings")

    moved = bootstrap.rescue_stray_data(exe_dir, data)

    assert (data / "servers" / "OneBlock" / "server.jar").read_text() == "jar"
    assert (data / "backups" / "OneBlock").is_dir()
    assert (data / "config" / "playit.toml").read_text() == "old playit.toml"
    assert (data / "config" / "zbb_settings.json").read_text() == "newer settings"
    assert not (data / "config" / ".zbb.lock").exists()
    assert not (exe_dir / "servers").exists()
    assert "servers/OneBlock" in moved and "config/playit.toml" in moved


def test_rescue_never_overwrites_an_existing_server(tmp_path):
    exe_dir, data = _zbb_folder(tmp_path / "Downloads"), tmp_path / "data"
    _server(exe_dir / "servers" / "srv")
    (exe_dir / "servers" / "srv" / "a.txt").write_text("stray")
    (data / "servers" / "srv").mkdir(parents=True)
    (data / "servers" / "srv" / "a.txt").write_text("real")

    assert "servers/srv" not in bootstrap.rescue_stray_data(exe_dir, data)
    assert (data / "servers" / "srv" / "a.txt").read_text() == "real"
    assert (exe_dir / "servers" / "srv" / "a.txt").read_text() == "stray"


def test_rescue_relinks_custom_location_servers_without_touching_them(monkeypatch, tmp_path):
    monkeypatch.setattr(sys, "platform", REAL_PLATFORM)  # real junction/symlink
    exe_dir, data = _zbb_folder(tmp_path / "Downloads"), tmp_path / "data"
    custom = tmp_path / "Minecraft Servers" / "OneBlock"
    custom.mkdir(parents=True)
    (custom / "level.txt").write_text("keep me")
    (exe_dir / "servers").mkdir(parents=True)
    create_junction(str(custom), str(exe_dir / "servers" / "OneBlock"))

    bootstrap.rescue_stray_data(exe_dir, data)

    moved = data / "servers" / "OneBlock"
    assert is_link(moved)
    assert os.path.normcase(link_target(moved)) == os.path.normcase(str(custom))
    assert (moved / "level.txt").read_text() == "keep me"
    assert (custom / "level.txt").exists()
    assert not os.path.lexists(exe_dir / "servers" / "OneBlock")


def test_rescue_is_a_noop_when_data_lives_next_to_exe(tmp_path):
    (tmp_path / "servers" / "srv").mkdir(parents=True)
    assert bootstrap.rescue_stray_data(tmp_path, tmp_path) == []
    assert (tmp_path / "servers" / "srv").is_dir()


def test_stray_data_is_rescued_on_startup(monkeypatch, tmp_path, env):
    exe = _run_exe(monkeypatch, tmp_path / "Downloads" / "ZeroBlockBridge.exe")
    _zbb_folder(exe.parent)
    _server(exe.parent / "servers" / "OneBlock")
    data = tmp_path / "data"
    _write_marker(tmp_path, {"data_dir": str(data), "mode": MODE_MANUAL})

    bootstrap.resolve_data_dir()

    assert (data / "servers" / "OneBlock").is_dir()


# ----------------------------------------------------------------------
# Import isolation: the root cause of the bug
# ----------------------------------------------------------------------
def test_setup_dialogs_never_import_constants():
    """Showing any setup dialog must not import app.core.constants: that
    pins BASE_DIR before the user's choice is applied, so the first session
    wrote servers next to the exe and they vanished on the next launch."""
    root = Path(bootstrap.__file__).resolve().parent.parent.parent
    code = (
        "import sys\n"
        "import app.core.bootstrap, app.core.installer, app.core.i18n, app.ui.first_run_dialog\n"
        "app.core.i18n.set_language('es')\n"
        "app.core.bootstrap.use_stored_language({})\n"
        "from app.ui import win_effects\n"
        "class W:\n"
        "    def iconbitmap(self, path): pass\n"
        "win_effects._apply_app_icon(W())\n"
        "assert 'app.core.constants' not in sys.modules, 'constants imported'\n"
    )
    result = subprocess.run([sys.executable, "-c", code], cwd=root, capture_output=True, text=True)
    assert result.returncode == 0, result.stderr


def test_is_newer_compares_versions():
    from app.ui.first_run_dialog import is_newer
    assert is_newer("2.3.0", "2.2.0")
    assert is_newer("2.10.0", "2.9.0")
    assert not is_newer("2.2.0", "2.2.0")
    assert not is_newer("2.1.0", "2.2.0")
    assert is_newer("2.2.0", None)


# ----------------------------------------------------------------------
# Review regressions: never move or adopt folders that aren't ZBB's
# ----------------------------------------------------------------------
def test_rescue_ignores_folders_that_are_not_zbb_data(tmp_path):
    """Downloads/Desktop often already have their own config/ or backups/."""
    exe_dir, data = tmp_path / "Downloads", tmp_path / "data"
    (exe_dir / "config").mkdir(parents=True)
    (exe_dir / "config" / "settings.ini").write_text("not ours")
    (exe_dir / "backups" / "photos").mkdir(parents=True)

    assert bootstrap.rescue_stray_data(exe_dir, data) == []
    assert (exe_dir / "config" / "settings.ini").exists()
    assert (exe_dir / "backups" / "photos").is_dir()
    assert not data.exists()


def test_rescue_only_moves_server_looking_entries(tmp_path):
    exe_dir, data = _zbb_folder(tmp_path / "Downloads"), tmp_path / "data"
    _server(exe_dir / "servers" / "real")
    (exe_dir / "servers" / "notes").mkdir(parents=True)

    moved = bootstrap.rescue_stray_data(exe_dir, data)

    assert "servers/real" in moved
    assert (exe_dir / "servers" / "notes").is_dir()
    assert not (data / "servers" / "notes").exists()


def test_rescue_skips_folder_used_by_a_running_instance(monkeypatch, tmp_path):
    exe_dir, data = _zbb_folder(tmp_path / "Downloads"), tmp_path / "data"
    _server(exe_dir / "servers" / "srv")
    monkeypatch.setattr(bootstrap, "_in_use", lambda folder: True)

    assert bootstrap.rescue_stray_data(exe_dir, data) == []
    assert (exe_dir / "servers" / "srv").is_dir()


def test_in_use_ignores_own_dead_and_garbage_pids(tmp_path):
    lock = _zbb_folder(tmp_path) / "config" / ".zbb.lock"
    for content in (str(os.getpid()), "999999999", "garbage"):
        lock.write_text(content)
        assert bootstrap._in_use(tmp_path) is False, content


def test_in_use_detects_a_live_zbb_process(monkeypatch, tmp_path):
    lock = _zbb_folder(tmp_path) / "config" / ".zbb.lock"
    lock.write_text("4242")

    class _Proc:
        def __init__(self, pid):
            self.pid = pid

        def name(self):
            return "ZeroBlockBridge.exe"
    monkeypatch.setattr("psutil.Process", _Proc)
    assert bootstrap._in_use(tmp_path) is True


def test_second_legacy_portable_copy_stays_separate(monkeypatch, tmp_path, env):
    """v2.2.0 wrote the marker pointing at the first portable copy's folder;
    a second portable copy must not have its servers moved into it."""
    copy_a = _zbb_folder(tmp_path / "CopyA")
    (copy_a / "ZeroBlockBridge.exe").write_bytes(b"exe")
    _write_marker(tmp_path, {"data_dir": str(copy_a)})
    exe_b = _run_exe(monkeypatch, tmp_path / "CopyB" / "ZeroBlockBridge.exe")
    _zbb_folder(exe_b.parent)
    _server(exe_b.parent / "servers" / "b-server")

    assert bootstrap.resolve_data_dir() == exe_b.parent
    assert (exe_b.parent / "servers" / "b-server").is_dir()
    assert not (copy_a / "servers").exists()
    assert (exe_b.parent / PORTABLE_FLAG).exists()
    assert env.setup == []


def test_unrelated_config_folder_next_to_download_still_shows_setup(monkeypatch, tmp_path, env):
    exe = _run_exe(monkeypatch, tmp_path / "Downloads" / "ZeroBlockBridge.exe")
    (exe.parent / "config").mkdir()
    env.setup_result = SetupResult("portable", exe.parent)

    bootstrap.resolve_data_dir()

    assert env.setup == [(exe, None)]


def test_installed_exe_behind_a_junction_still_matches(monkeypatch, tmp_path, env):
    """%LOCALAPPDATA% relocated with a junction: the running exe and the
    recorded path are spelled differently but are the same file."""
    monkeypatch.setattr(sys, "platform", REAL_PLATFORM)
    real = tmp_path / "D" / "Programs"
    real.mkdir(parents=True)
    create_junction(str(real), str(tmp_path / "Programs"))
    monkeypatch.setattr(sys, "platform", "win32")
    _run_exe(monkeypatch, real / "ZeroBlockBridge.exe")
    data = tmp_path / "data"
    _write_marker(tmp_path, {"data_dir": str(data), "mode": MODE_INSTALLED,
                             "exe_path": str(tmp_path / "Programs" / "ZeroBlockBridge.exe"),
                             "version": AppConfig.APP_VERSION})

    assert bootstrap.resolve_data_dir() == data
    assert env.already == []


def test_marker_written_with_a_bom_is_still_read(tmp_path):
    """Windows tools (PowerShell 5's Set-Content -Encoding utf8, older
    Notepad) prepend a BOM; json.load then failed and the installed app
    was treated as a first run, offering to install again."""
    marker = tmp_path / "install.json"
    marker.write_bytes(b"\xef\xbb\xbf" + json.dumps({"mode": "installed", "version": "2.1.0"}).encode())
    assert bootstrap.read_marker(marker) == {"mode": "installed", "version": "2.1.0"}


# ----------------------------------------------------------------------
# Language: picked at setup, stored in the marker / portable settings
# ----------------------------------------------------------------------
LOCALES = Path(__file__).resolve().parent.parent / "assets" / "locales"


class _Settings:
    """SettingsManager stand-in (get/set)."""
    def __init__(self, **values):
        self.values = dict(values)

    def get(self, key, default=None):
        return self.values.get(key, default)

    def set(self, key, value):
        self.values[key] = value


@pytest.fixture
def os_language(monkeypatch):
    """Pin the OS language instead of reading the test machine's, and find
    the real catalogs although sys.frozen is faked."""
    monkeypatch.setattr(i18n, "locale_dir", lambda: LOCALES)

    def _set(code):
        monkeypatch.setattr(i18n, "system_language", lambda: code)
    _set("en")
    return _set


def test_setup_result_defaults_to_english():
    assert SetupResult(MODE_MANUAL, Path("x")).language == "en"


def test_chosen_language_is_written_to_the_marker(monkeypatch, tmp_path, env):
    _run_exe(monkeypatch, tmp_path / "Downloads" / "ZeroBlockBridge.exe")
    data = tmp_path / "data"
    env.setup_result = SetupResult(MODE_MANUAL, data, language="es")

    bootstrap.resolve_data_dir()

    assert _read_marker(tmp_path)["language"] == "es"


def test_portable_choice_stores_language_in_its_settings(monkeypatch, tmp_path, env):
    exe = _run_exe(monkeypatch, tmp_path / "usb" / "ZeroBlockBridge.exe")
    env.setup_result = SetupResult("portable", exe.parent, language="es")

    bootstrap.resolve_data_dir()

    settings = json.loads((exe.parent / "config" / "zbb_settings.json").read_text(encoding="utf-8"))
    assert settings == {"language": "es"}
    assert not _marker_file(tmp_path).exists()


def test_portable_language_keeps_existing_settings(tmp_path):
    exe = tmp_path / "usb" / "ZeroBlockBridge.exe"
    _zbb_folder(exe.parent)
    (exe.parent / "config" / "zbb_settings.json").write_text('{"theme": "Light"}', encoding="utf-8")

    bootstrap._apply_setup(SetupResult("portable", exe.parent, language="es"), exe, {}, _marker_file(tmp_path))

    settings = json.loads((exe.parent / "config" / "zbb_settings.json").read_text(encoding="utf-8"))
    assert settings == {"theme": "Light", "language": "es"}


def test_portable_language_never_overwrites_unreadable_settings(tmp_path):
    exe = tmp_path / "usb" / "ZeroBlockBridge.exe"
    _zbb_folder(exe.parent)
    settings_file = exe.parent / "config" / "zbb_settings.json"
    settings_file.write_text("{broken", encoding="utf-8")

    bootstrap._apply_setup(SetupResult("portable", exe.parent, language="es"), exe, {}, _marker_file(tmp_path))

    assert settings_file.read_text(encoding="utf-8") == "{broken"


def test_stored_language_prefers_the_marker(tmp_path):
    data = _zbb_folder(tmp_path / "data")
    (data / "config" / "zbb_settings.json").write_text('{"language": "en"}', encoding="utf-8")

    assert bootstrap.stored_language({"data_dir": str(data), "language": "es"}) == "es"


def test_stored_language_falls_back_to_the_data_folder_settings(tmp_path):
    data = _zbb_folder(tmp_path / "data")
    # A BOM, as a settings file edited with a Windows tool may have.
    (data / "config" / "zbb_settings.json").write_text('﻿{"language": "es"}', encoding="utf-8")

    assert bootstrap.stored_language({"data_dir": str(data), "language": "xx"}) == "es"


def test_stored_language_none_when_nothing_is_saved(tmp_path):
    assert bootstrap.stored_language({}) is None
    assert bootstrap.stored_language({"data_dir": str(tmp_path / "missing")}) is None
    data = _zbb_folder(tmp_path / "data")
    (data / "config" / "zbb_settings.json").write_text("[1, 2]", encoding="utf-8")
    assert bootstrap.stored_language({"data_dir": str(data)}) is None


def test_use_stored_language_falls_back_to_the_os(os_language):
    os_language("es")
    assert bootstrap.use_stored_language({}) == "es"
    assert i18n.get_language() == "es"
    assert bootstrap.use_stored_language({"language": "en"}) == "en"


def test_pre_app_dialogs_open_in_the_stored_language(monkeypatch, tmp_path, env, os_language):
    """The update/already-installed dialog reads the marker's language."""
    installed = _run_exe(monkeypatch, tmp_path / "Programs" / "ZeroBlockBridge.exe")
    _run_exe(monkeypatch, tmp_path / "Downloads" / "ZeroBlockBridge.exe")
    _write_marker(tmp_path, {"data_dir": str(tmp_path / "data"), "mode": MODE_INSTALLED, "language": "es",
                             "exe_path": str(installed), "version": "1.0.0"})
    seen = []
    monkeypatch.setattr("app.ui.first_run_dialog.ask_already_installed",
                        lambda *a: seen.append(i18n.get_language()) or "run")

    bootstrap.resolve_data_dir()

    assert seen == ["es"]


def test_first_run_dialog_opens_in_the_os_language(monkeypatch, tmp_path, env, os_language):
    _run_exe(monkeypatch, tmp_path / "Downloads" / "ZeroBlockBridge.exe")
    os_language("es")
    seen = []
    monkeypatch.setattr("app.ui.first_run_dialog.ask_setup", lambda *a, **k: seen.append(i18n.get_language()))

    with pytest.raises(SystemExit):  # closed without choosing
        bootstrap.resolve_data_dir()

    assert seen == ["es"]


def _start(settings, data_dir, tmp_path):
    """What main() does: pick the language, then (after the lock) keep it."""
    language = bootstrap.startup_language(settings, data_dir, _marker_file(tmp_path))
    bootstrap.keep_language(settings, language)
    return language


def test_startup_language_keeps_the_saved_setting(tmp_path, os_language):
    settings = _Settings(language="es")
    _write_marker(tmp_path, {"data_dir": str(tmp_path / "data"), "language": "en"})

    assert _start(settings, tmp_path / "data", tmp_path) == "es"
    assert settings.values == {"language": "es"}


def test_first_launch_copies_the_setup_language_into_settings(tmp_path, os_language):
    data = tmp_path / "data"
    data.mkdir()
    _write_marker(tmp_path, {"data_dir": str(data), "language": "es"})
    settings = _Settings()

    assert _start(settings, data, tmp_path) == "es"
    assert settings.values == {"language": "es"}
    assert i18n.get_language() == "es"


def test_startup_language_never_writes_settings(tmp_path, os_language):
    """A second instance exits right after this (single-instance lock): it
    must not schedule a write of its stale copy of the settings."""
    settings = _Settings()

    assert bootstrap.startup_language(settings, tmp_path / "data", _marker_file(tmp_path)) == "en"
    assert settings.values == {}


def test_first_launch_ignores_another_folders_marker(tmp_path, os_language):
    """A portable copy must not take the installed copy's language."""
    _write_marker(tmp_path, {"data_dir": str(tmp_path / "installed-data"), "language": "es"})
    settings = _Settings(language="xx")

    assert _start(settings, tmp_path / "usb", tmp_path) == "en"
    assert settings.values == {"language": "en"}


def test_first_launch_without_marker_uses_the_os_language(tmp_path, os_language):
    os_language("es")
    settings = _Settings()

    assert _start(settings, tmp_path / "data", tmp_path) == "es"
    assert settings.values == {"language": "es"}


def test_install_offer_updates_the_language_in_existing_settings(monkeypatch, tmp_path, env):
    """The main app reads its settings first: an install offer answered in
    Spanish must not leave them saying English."""
    _run_exe(monkeypatch, tmp_path / "Downloads" / "ZeroBlockBridge.exe")
    data = _zbb_folder(tmp_path / "data")
    (data / "config" / "zbb_settings.json").write_text('{"language": "en", "theme": "Light"}', encoding="utf-8")
    _write_marker(tmp_path, {"data_dir": str(data)})
    env.setup_result = SetupResult(MODE_MANUAL, data, language="es")

    bootstrap.resolve_data_dir()

    settings = json.loads((data / "config" / "zbb_settings.json").read_text(encoding="utf-8"))
    assert settings == {"language": "es", "theme": "Light"}


def test_fresh_setup_creates_no_settings_file_in_the_data_folder(monkeypatch, tmp_path, env):
    _run_exe(monkeypatch, tmp_path / "Downloads" / "ZeroBlockBridge.exe")
    data = tmp_path / "data"
    env.setup_result = SetupResult(MODE_MANUAL, data, language="es")

    bootstrap.resolve_data_dir()

    assert not (data / "config" / "zbb_settings.json").exists()


def test_remember_language_updates_this_folders_marker(tmp_path):
    data = tmp_path / "data"
    data.mkdir()
    _write_marker(tmp_path, {"data_dir": str(data), "mode": MODE_MANUAL, "language": "en"})

    bootstrap.remember_language("es", data, _marker_file(tmp_path))

    assert _read_marker(tmp_path) == {"data_dir": str(data), "mode": MODE_MANUAL, "language": "es"}


def test_remember_language_leaves_other_markers_alone(tmp_path):
    _write_marker(tmp_path, {"data_dir": str(tmp_path / "installed-data"), "language": "en"})

    bootstrap.remember_language("es", tmp_path / "usb", _marker_file(tmp_path))
    assert _read_marker(tmp_path)["language"] == "en"

    _marker_file(tmp_path).unlink()
    bootstrap.remember_language("es", tmp_path / "usb", _marker_file(tmp_path))
    assert not _marker_file(tmp_path).exists()


def test_remember_language_survives_a_locked_marker(monkeypatch, tmp_path, caplog):
    """Runs in a Tk callback: a marker held open by OneDrive/antivirus must
    not raise there."""
    data = tmp_path / "data"
    data.mkdir()
    _write_marker(tmp_path, {"data_dir": str(data), "language": "en"})

    def _locked(*_args):
        raise PermissionError("in use")
    monkeypatch.setattr(bootstrap, "write_marker", _locked)

    bootstrap.remember_language("es", data, _marker_file(tmp_path))

    assert "Could not save the language" in caplog.text
