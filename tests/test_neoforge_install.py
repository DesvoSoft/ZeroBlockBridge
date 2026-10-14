"""NeoForge server creation: versions, installer URL, installer run,
provisioning dispatch, launch resolution, wizard engine rules."""
import json
import os
from contextlib import ExitStack
from unittest.mock import MagicMock, patch

import pytest

from app.core import logic, neoforge, version_manager
from app.core.version_manager import VersionManager

BUILDS = ["20.2.93", "20.4.251", "21.1.258", "21.1.259", "21.6.20-beta", "26.3.0.76", "26.3.0.77"]


@pytest.fixture
def vm():
    VersionManager._instance = None
    yield VersionManager()
    VersionManager._instance = None


# ----------------------------------------------------------------------
# Version manager
# ----------------------------------------------------------------------
def test_fetch_neoforge_lists_supported_mc_versions(vm):
    resp = MagicMock()
    resp.json.return_value = {"versions": BUILDS}
    with patch.object(version_manager.requests, "get", return_value=resp) as get:
        assert vm._fetch_neoforge(timeout=3) == ["26.3", "1.21.6", "1.21.1", "1.20.4", "1.20.2"]
    assert get.call_args.args[0] == neoforge.VERSIONS_API


def test_installer_url_picks_newest_stable_build(vm):
    with patch.object(VersionManager, "_fetch_neoforge_builds", return_value=BUILDS):
        assert vm.get_download_url("NeoForge", "1.21.1") == neoforge.installer_url("21.1.259")
        assert vm.get_download_url("NeoForge", "1.21.6") == neoforge.installer_url("21.6.20-beta")
        assert vm.get_download_url("NeoForge", "1.19.2") is None


def test_pinned_build_skips_the_network(vm):
    with patch.object(VersionManager, "_fetch_neoforge_builds", side_effect=AssertionError("no fetch")):
        assert vm.get_download_url("NeoForge", "1.21.1", "21.1.77") == neoforge.installer_url("21.1.77")


def test_network_failure_returns_none(vm):
    with patch.object(VersionManager, "_fetch_neoforge_builds", side_effect=OSError("offline")):
        assert vm.get_download_url("NeoForge", "1.21.1") is None


def test_neoforge_is_fetched_with_the_other_engines(vm):
    with patch.object(VersionManager, "_fetch_vanilla", return_value=["26.3"]), \
            patch.object(VersionManager, "_fetch_fabric", return_value=["26.3"]), \
            patch.object(VersionManager, "_fetch_forge", return_value=["26.3"]), \
            patch.object(VersionManager, "_fetch_paper", return_value=["26.3"]), \
            patch.object(VersionManager, "_fetch_purpur", return_value=["26.3"]), \
            patch.object(VersionManager, "_fetch_neoforge", return_value=["26.3", "1.21.1"]):
        assert vm._fetch_all_versions(timeout=1)["NeoForge"] == ["26.3", "1.21.1"]


def test_cache_without_neoforge_gets_defaults_and_refreshes(vm):
    old = {"last_updated": "2026-10-14T00:00:00", "Vanilla": ["26.3"], "Forge": ["26.3"]}
    filled = vm._with_all_engines(old)
    assert filled["NeoForge"] == vm._get_default_cache()["NeoForge"]
    assert filled["last_updated"] is None  # background refresh fetches the real list
    full = vm._get_default_cache()
    assert vm._with_all_engines(full) is full


@pytest.mark.parametrize("versions, ok", [
    (["1.21.4"], True), (["26.3"], True), (["26.3-rc-3", "26.2"], True), ([], True),
    (["0.15.7"], False),   # cached Fabric loader builds
    (["47.2.0"], False),   # cached Forge builds
])
def test_mc_version_list_detection(versions, ok):
    assert version_manager._looks_like_mc_versions(versions) is ok


def test_26x_cache_is_not_treated_as_stale(vm, tmp_path):
    """Regression: startswith("1.") flagged every 26.x list as stale and
    forced a synchronous network refresh on each launch."""
    cache = {"last_updated": "2999-01-01T00:00:00", "Vanilla": ["26.3"], "Fabric": ["26.3"],
             "Forge": ["26.3", "1.21.1"], "Paper": ["26.3", "26.3-rc-3"], "Purpur": ["26.3"],
             "NeoForge": ["26.3"]}
    path = tmp_path / "versions_cache.json"
    path.write_text(json.dumps(cache), encoding="utf-8")
    with patch.object(version_manager, "VERSIONS_CACHE_FILE", str(path)), \
            patch.object(VersionManager, "_fetch_defaults_sync", side_effect=AssertionError("forced refresh")):
        assert vm._load_cache()["Paper"] == ["26.3", "26.3-rc-3"]


# ----------------------------------------------------------------------
# Installer run
# ----------------------------------------------------------------------
def test_install_neoforge_runs_the_installer_and_reports_modern_layout(tmp_path):
    (tmp_path / "run.bat").write_text("@java @user_jvm_args.txt @libraries/...")
    cancel = MagicMock()
    with patch.object(logic, "_run_installer", return_value=str(tmp_path)) as run:
        result = logic.install_neoforge("srv", "1.21.1", None, java_bin="/jdk/java",
                                        loader_version="21.1.77", cancel_event=cancel)
    assert result == "NEOFORGE_MODERN"
    args, kwargs = run.call_args
    assert args[:5] == ("srv", "NeoForge", "1.21.1", "neoforge-installer.jar", ["--installServer"])
    assert kwargs == {"java_bin": "/jdk/java", "loader_version": "21.1.77", "cancel_event": cancel}


@pytest.mark.parametrize("installed", [None, "empty"])
def test_install_neoforge_failure(tmp_path, installed):
    with patch.object(logic, "_run_installer", return_value=None if installed is None else str(tmp_path)):
        assert logic.install_neoforge("srv", "1.21.1") is None


# ----------------------------------------------------------------------
# Provisioning
# ----------------------------------------------------------------------
def test_provisioning_uses_the_neoforge_installer_with_pinned_build(tmp_path):
    from tests.test_provisioning import _Env, fake_download_installer
    with ExitStack() as stack:
        env = _Env(tmp_path, stack)
        calls = []
        fake = fake_download_installer(env, b"jar")

        def install(name, version, progress_cb, java_bin="java", loader_version=None):
            calls.append((version, loader_version, java_bin))
            return fake(name, version, progress_cb, java_bin)
        neo = stack.enter_context(patch("app.core.logic.install_neoforge", side_effect=install))
        result = env.run(type="NeoForge", version="1.21.1", loader_version="21.1.77", modpack_loader="NeoForge")
    assert result.ok
    neo.assert_called_once()
    env.install_forge.assert_not_called()
    assert calls == [("1.21.1", "21.1.77", "/jdk/bin/java")]


def test_neoforge_counts_as_an_installer_engine():
    from app.core.provisioning import INSTALLER_ENGINES, INSTALLER_FUNCTIONS
    assert "NeoForge" in INSTALLER_ENGINES
    assert all(hasattr(logic, fn) for fn in INSTALLER_FUNCTIONS.values())


# ----------------------------------------------------------------------
# Launch: run.bat + libraries/net/neoforged/neoforge/<build>/win_args.txt
# ----------------------------------------------------------------------
def _neoforge_layout(root):
    import sys
    args_name = "win_args.txt" if sys.platform == "win32" else "unix_args.txt"
    lib = root / "libraries" / "net" / "neoforged" / "neoforge" / "21.1.77"
    lib.mkdir(parents=True)
    boot = root / "libraries" / "cpw" / "mods" / "bootstraplauncher" / "2.0.2"
    boot.mkdir(parents=True)
    import zipfile
    with zipfile.ZipFile(boot / "bootstraplauncher-2.0.2.jar", "w") as zf:
        zf.writestr("META-INF/MANIFEST.MF", "Manifest-Version: 1.0\n" + "x" * 2048)
    (lib / args_name).write_text(
        "-p libraries/cpw/mods/bootstraplauncher/2.0.2/bootstraplauncher-2.0.2.jar "
        "--add-modules ALL-MODULE-PATH -DlibraryDirectory=libraries cpw.mods.bootstraplauncher.BootstrapLauncher "
        "--launchTarget neoforgeserver --fml.neoForgeVersion 21.1.77 --fml.mcVersion 1.21.1",
        encoding="utf-8")
    (root / "run.bat").write_text("java @user_jvm_args.txt @libraries/net/neoforged/neoforge/21.1.77/win_args.txt %*")
    (root / "user_jvm_args.txt").write_text("# Xmx")
    return os.path.relpath(lib / args_name, root)


def test_launch_target_uses_the_neoforge_args_file(tmp_path):
    rel_args = _neoforge_layout(tmp_path)
    runner = logic.ServerRunner("srv", "2048M", MagicMock())
    assert runner._resolve_launch_target(str(tmp_path)) == ("server.jar", rel_args)
    with patch.object(logic, "probe_java", return_value=None), \
            patch.object(logic, "get_server_meta", return_value={}):
        cmd = runner._build_command("server.jar", rel_args)
    assert cmd[-2:] == [f"@{rel_args}", "nogui"] and "-jar" not in cmd


def test_normalize_finds_the_neoforge_entry_jar(tmp_path):
    _neoforge_layout(tmp_path)
    assert logic.normalize_server_jar(str(tmp_path)) is True
    assert (tmp_path / "server.jar").exists()


# ----------------------------------------------------------------------
# Wizard
# ----------------------------------------------------------------------
def test_modpacks_accept_neoforge_servers():
    from app.ui.server_wizard import MODDED_ENGINES, modpack_step_error
    assert "NeoForge" in MODDED_ENGINES
    data = {"modpack_path": "p.mrpack", "type": "NeoForge", "version": "1.21.1",
            "modpack_loader": "NeoForge", "modpack_mc": "1.21.1"}
    assert modpack_step_error(data) is None
    assert "Fabric, Forge or NeoForge" in modpack_step_error(dict(data, type="Paper"))
