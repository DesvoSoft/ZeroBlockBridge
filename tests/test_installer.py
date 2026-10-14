import os
import subprocess
import sys
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from app.core import fs_links, installer, resources

windows_only = pytest.mark.skipif(sys.platform != "win32", reason="Windows registry/shell")


@pytest.fixture(autouse=True)
def _appdata(tmp_path, monkeypatch):
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "Local"))
    return tmp_path


# ----------------------------------------------------------------------
# Paths
# ----------------------------------------------------------------------
def test_default_dirs_follow_localappdata(tmp_path):
    assert installer.default_install_dir() == tmp_path / "Local" / "Programs" / "ZeroBlockBridge"
    assert installer.standard_data_dir() == tmp_path / "Local" / "ZeroBlockBridge"


def test_standard_data_dir_without_localappdata_uses_home(monkeypatch, tmp_path):
    monkeypatch.delenv("LOCALAPPDATA")
    monkeypatch.setattr(Path, "home", lambda: tmp_path / "home")
    assert installer.standard_data_dir() == tmp_path / "home" / "ZeroBlockBridge"


def test_same_path_through_a_link_and_for_missing_files(tmp_path):
    real = tmp_path / "real"
    real.mkdir()
    fs_links.create_junction(str(real), str(tmp_path / "link"))
    assert installer.same_path(tmp_path / "link", real)
    assert installer.same_path(tmp_path / "nope" / "a.exe", tmp_path / "nope" / "." / "a.exe")
    assert not installer.same_path(tmp_path / "a", tmp_path / "b")


# ----------------------------------------------------------------------
# Uninstall data removal (review finding: rmtree of a user-chosen folder)
# ----------------------------------------------------------------------
def test_remove_data_dir_keeps_the_users_own_files(tmp_path):
    documents = tmp_path / "Documents"
    for name in ("servers/srv", "backups/srv", "config", "bin", "logs", ".zbb_cache/jdks"):
        (documents / name).mkdir(parents=True)
    (documents / "config" / "zbb_settings.json").write_text("{}")
    (documents / "Thesis.docx").write_text("precious")
    (documents / "Photos").mkdir()

    installer.remove_data_dir(documents)

    assert (documents / "Thesis.docx").read_text() == "precious"
    assert (documents / "Photos").is_dir()
    for name in installer.ZBB_DATA_ENTRIES:
        assert not (documents / name).exists(), name


def test_remove_data_dir_never_follows_server_links(tmp_path):
    external = tmp_path / "Minecraft Servers" / "OneBlock"
    external.mkdir(parents=True)
    (external / "level.dat").write_text("world")
    data = tmp_path / "data"
    (data / "servers").mkdir(parents=True)
    fs_links.create_junction(str(external), str(data / "servers" / "OneBlock"))

    installer.remove_data_dir(data)

    assert (external / "level.dat").read_text() == "world"
    assert not data.exists()  # only ZBB content inside: folder removed too


# ----------------------------------------------------------------------
# Delayed exe removal (review finding: fired while the exe was still open)
# ----------------------------------------------------------------------
def test_removal_command_retries_until_the_install_folder_is_gone(tmp_path):
    exe = installer.default_install_dir() / installer.EXE_NAME
    cmd = installer.removal_command(exe)
    assert f'rmdir /s /q "{exe.parent}"' in cmd
    assert "for /l %i in (1,1,30)" in cmd
    assert f'if not exist "{exe.parent}" exit /b 0' in cmd


def test_removal_command_outside_install_folder_only_deletes_the_exe(tmp_path):
    exe = tmp_path / "elsewhere" / installer.EXE_NAME
    cmd = installer.removal_command(exe)
    assert f'del /f /q "{exe}"' in cmd and "rmdir" not in cmd


def test_schedule_removal_spawns_detached_cmd(monkeypatch, tmp_path):
    popen = MagicMock()
    monkeypatch.setattr(subprocess, "Popen", popen)
    exe = tmp_path / "a" / installer.EXE_NAME
    installer.schedule_removal(exe)
    args, kwargs = popen.call_args
    assert args[0] == installer.removal_command(exe)
    assert kwargs["cwd"] == str(exe.parent.parent)  # never inside the folder it deletes


# ----------------------------------------------------------------------
# Shortcuts
# ----------------------------------------------------------------------
def test_create_shortcut_passes_paths_through_env(monkeypatch, tmp_path):
    lnk = tmp_path / "menu" / "ZeroBlockBridge.lnk"
    seen = {}

    def fake_run(cmd, env, **kwargs):
        seen.update(cmd=cmd, env=env)
        lnk.write_bytes(b"lnk")
        return subprocess.CompletedProcess(cmd, 0, "", "")
    monkeypatch.setattr(subprocess, "run", fake_run)

    target = tmp_path / "Programs" / "ZeroBlockBridge.exe"
    installer.create_shortcut(target, lnk)

    assert seen["cmd"][0] == "powershell.exe"
    assert seen["env"]["ZBB_LNK"] == str(lnk)
    assert seen["env"]["ZBB_TARGET"] == str(target)
    assert str(target) not in " ".join(seen["cmd"])  # never interpolated into the script


def test_create_shortcut_failure_raises(monkeypatch, tmp_path):
    monkeypatch.setattr(subprocess, "run",
                        lambda cmd, **kw: subprocess.CompletedProcess(cmd, 1, "", "denied"))
    with pytest.raises(OSError, match="denied"):
        installer.create_shortcut(tmp_path / "x.exe", tmp_path / "x.lnk")


def test_add_shortcuts_reports_failures_without_raising(monkeypatch, tmp_path):
    monkeypatch.setattr(installer, "start_menu_shortcut_path", lambda: tmp_path / "menu.lnk")
    monkeypatch.setattr(installer, "desktop_shortcut_path", lambda: None)

    def boom(target, lnk):
        raise OSError("nope")
    monkeypatch.setattr(installer, "create_shortcut", boom)

    failures = installer.add_shortcuts(tmp_path / "x.exe", start_menu=True, desktop=True)
    assert failures == ["Start menu: nope", "Desktop: folder not found"]


def test_remove_shortcuts_deletes_both(monkeypatch, tmp_path):
    menu, desk = tmp_path / "m.lnk", tmp_path / "d.lnk"
    menu.write_text("x")
    monkeypatch.setattr(installer, "start_menu_shortcut_path", lambda: menu)
    monkeypatch.setattr(installer, "desktop_shortcut_path", lambda: desk)  # already gone
    installer.remove_shortcuts()
    assert not menu.exists()


@windows_only
def test_shell_folders_resolve():
    assert installer.start_menu_shortcut_path().name == installer.SHORTCUT_NAME
    assert installer.desktop_shortcut_path().parent.is_dir()


# ----------------------------------------------------------------------
# Install / update
# ----------------------------------------------------------------------
@pytest.fixture
def quiet_shell(monkeypatch):
    calls = {"shortcuts": [], "registered": []}
    monkeypatch.setattr(installer, "add_shortcuts",
                        lambda target, start_menu, desktop: calls["shortcuts"].append((target, start_menu, desktop))
                        or [])
    monkeypatch.setattr(installer, "register_uninstall",
                        lambda exe, version: calls["registered"].append((exe, version)))
    return calls


def test_install_copies_exe_and_registers(tmp_path, quiet_shell):
    src = tmp_path / "Downloads" / "ZeroBlockBridge.exe"
    src.parent.mkdir()
    src.write_bytes(b"v2")

    dest, failures = installer.install(src, "2.3.0", start_menu=True, desktop=False)

    assert dest == installer.default_install_dir() / installer.EXE_NAME
    assert dest.read_bytes() == b"v2" and failures == []
    assert quiet_shell["shortcuts"] == [(dest, True, False)]
    assert quiet_shell["registered"] == [(dest, "2.3.0")]


def test_install_from_the_installed_copy_does_not_copy(monkeypatch, tmp_path, quiet_shell):
    dest = installer.default_install_dir() / installer.EXE_NAME
    dest.parent.mkdir(parents=True)
    dest.write_bytes(b"same")
    monkeypatch.setattr(installer, "copy_exe", lambda *a: pytest.fail("must not copy onto itself"))

    assert installer.install(dest, "2.3.0")[0] == dest


def test_install_reports_registry_failure(monkeypatch, tmp_path, quiet_shell):
    src = tmp_path / "ZeroBlockBridge.exe"
    src.write_bytes(b"x")

    def fail(exe, version):
        raise OSError("registry locked")
    monkeypatch.setattr(installer, "register_uninstall", fail)
    _, failures = installer.install(src, "2.3.0")
    assert failures == ["Apps list entry: registry locked"]


def test_copy_exe_cleans_temp_when_replace_fails(monkeypatch, tmp_path):
    src, dest = tmp_path / "src.exe", tmp_path / "inst" / "ZeroBlockBridge.exe"
    src.write_bytes(b"new")

    def locked(a, b):
        raise PermissionError("in use")
    monkeypatch.setattr(os, "replace", locked)
    with pytest.raises(PermissionError):
        installer.copy_exe(src, dest)
    assert list(dest.parent.iterdir()) == []


def test_update_replaces_and_refreshes_entry(tmp_path, quiet_shell):
    src, dest = tmp_path / "new.exe", tmp_path / "inst" / "ZeroBlockBridge.exe"
    src.write_bytes(b"new")
    dest.parent.mkdir()
    dest.write_bytes(b"old")

    installer.update(src, dest, "2.4.0")

    assert dest.read_bytes() == b"new"
    assert quiet_shell["registered"] == [(dest, "2.4.0")]


@windows_only
def test_register_and_unregister_uninstall_entry(monkeypatch, tmp_path):
    import winreg
    monkeypatch.setattr(installer, "UNINSTALL_KEY", r"Software\ZBBTestUninstallEntry")
    exe = tmp_path / "ZeroBlockBridge.exe"
    exe.write_bytes(b"x" * 4096)
    try:
        installer.register_uninstall(exe, "9.9.9")
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, installer.UNINSTALL_KEY) as key:
            assert winreg.QueryValueEx(key, "UninstallString")[0] == f'"{exe}" --uninstall'
            assert winreg.QueryValueEx(key, "DisplayVersion")[0] == "9.9.9"
            assert winreg.QueryValueEx(key, "EstimatedSize")[0] == 4
    finally:
        installer.unregister_uninstall()
    with pytest.raises(FileNotFoundError):
        winreg.OpenKey(winreg.HKEY_CURRENT_USER, installer.UNINSTALL_KEY)
    installer.unregister_uninstall()  # already gone: no error


def test_launch_resets_pyinstaller_env(monkeypatch, tmp_path):
    popen = MagicMock()
    monkeypatch.setattr(subprocess, "Popen", popen)
    monkeypatch.setenv("_MEIPASS2", "C:/tmp/_MEI123")
    monkeypatch.setenv("_PYI_APPLICATION_HOME_DIR", "C:/tmp/_MEI123")

    installer.launch(tmp_path / "ZeroBlockBridge.exe")

    env = popen.call_args.kwargs["env"]
    assert env["PYINSTALLER_RESET_ENVIRONMENT"] == "1"
    assert "_MEIPASS2" not in env and "_PYI_APPLICATION_HOME_DIR" not in env


# ----------------------------------------------------------------------
# Uninstall target (review finding: --uninstall from another copy)
# ----------------------------------------------------------------------
def test_uninstall_targets_the_recorded_install(tmp_path):
    from app.ui.first_run_dialog import uninstall_target
    running = tmp_path / "Downloads" / "ZeroBlockBridge.exe"
    installed = tmp_path / "Programs" / "ZeroBlockBridge.exe"
    assert uninstall_target(running, {"mode": "installed", "exe_path": str(installed)}) == installed
    assert uninstall_target(running, {"mode": "manual"}) == running


# ----------------------------------------------------------------------
# fs_links / resources
# ----------------------------------------------------------------------
def test_link_helpers(tmp_path):
    real = tmp_path / "real"
    real.mkdir()
    link = tmp_path / "link"
    fs_links.create_junction(str(real), str(link))
    assert fs_links.is_link(link) and not fs_links.is_link(real)
    assert not fs_links.is_link(tmp_path / "missing")
    assert os.path.normcase(fs_links.link_target(link)) == os.path.normcase(str(real))
    fs_links.remove_link(link)
    assert not os.path.lexists(link) and real.is_dir()


def test_link_target_strips_windows_prefixes(monkeypatch):
    monkeypatch.setattr(os, "readlink", lambda p: "\\\\?\\C:\\Servers\\x")
    assert fs_links.link_target("x") == "C:\\Servers\\x"
    monkeypatch.setattr(os, "readlink", lambda p: "\\??\\D:\\y")
    assert fs_links.link_target("x") == "D:\\y"


def test_resources_dir_frozen_and_source(monkeypatch, tmp_path):
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "_MEIPASS", str(tmp_path / "mei"), raising=False)
    assert resources.assets_dir() == tmp_path / "mei" / "assets"
    monkeypatch.setattr(sys, "frozen", False, raising=False)
    assert (resources.assets_dir() / "logo.ico").exists()
