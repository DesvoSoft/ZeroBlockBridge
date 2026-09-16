"""Tests for app/core/provisioning.py (server creation pipeline)."""

import os
from contextlib import ExitStack
from unittest.mock import MagicMock, patch

import pytest

from app.core.provisioning import ServerProvisioner, resolve_required_java


class TestResolveRequiredJava:
    def test_bytecode_newer_than_map_wins(self):
        assert resolve_required_java(21, 17) == 21

    def test_forge_java8_shim_does_not_downgrade(self):
        assert resolve_required_java(8, 17) == 17

    def test_no_bytecode_result_uses_map(self):
        assert resolve_required_java(None, 21) == 21


class _Env:
    """Wires a ServerProvisioner to a temp servers dir with every external
    step patched, recording console lines and progress values."""

    def __init__(self, tmp_path, stack: ExitStack, *, jar_bytes=b"jar", download_ok=True,
                 bytecode_java=17, version_map_java=17, java_cached=True):
        self.servers_dir = tmp_path / "servers"
        self.servers_dir.mkdir()
        self.lines = []
        self.progress = []
        self.tunnels = []
        self.jdk = MagicMock()
        self.jdk.get_java_path.return_value = "/jdk/bin/java" if java_cached else None
        self.jdk.ensure_java.return_value = "/jdk/bin/java"

        def fake_download(name, engine, version, progress_cb):
            progress_cb(0.5)
            progress_cb(1.0)
            if download_ok and jar_bytes is not None:
                d = self.servers_dir / name
                d.mkdir(parents=True, exist_ok=True)
                (d / "server.jar").write_bytes(jar_bytes)
            return "server.jar" if download_ok else None

        self.download = stack.enter_context(patch("app.core.logic.download_server", side_effect=fake_download))
        self.install_fabric = stack.enter_context(patch("app.core.logic.install_fabric", side_effect=fake_download_installer(self, jar_bytes)))
        self.install_forge = stack.enter_context(patch("app.core.logic.install_forge", side_effect=fake_download_installer(self, jar_bytes)))
        self.junction = stack.enter_context(patch("app.core.logic.create_junction"))
        self.save_icon = stack.enter_context(patch("app.core.logic.save_server_icon"))
        self.update_meta = stack.enter_context(patch("app.core.logic.update_server_meta"))
        self.scaffold = stack.enter_context(patch("app.services.scaffolder.pre_boot_scaffold"))
        self.analyze = stack.enter_context(
            patch("app.services.bytecode_analyzer.analyze_jar_bytecode", return_value=bytecode_java))
        stack.enter_context(patch("app.services.java_detector.get_required_java", return_value=version_map_java))
        stack.enter_context(patch("app.services.java_installer.get_release_label", return_value="Temurin 17.0.9+9"))

        self.provisioner = ServerProvisioner(
            log=self.lines.append,
            get_server_port=lambda name: 25565,
            create_tunnel=self.tunnels.append,
            jdk_manager=self.jdk,
            servers_dir=str(self.servers_dir),
            jar_wait_seconds=1.0,
            jar_poll_interval=0.5,
            sleep=lambda s: None,
        )

    def run(self, **overrides):
        config = {"name": "srv", "version": "1.20.4", "type": "Vanilla", "location": str(self.servers_dir)}
        config.update(overrides)
        return self.provisioner.provision(config, lambda value, text=None: self.progress.append(value))


def fake_download_installer(env, jar_bytes):
    def _install(name, version, progress_cb, java_bin="java"):
        env.installer_java_bin = java_bin
        progress_cb(1.0)
        d = env.servers_dir / name
        d.mkdir(parents=True, exist_ok=True)
        if jar_bytes is not None:
            (d / "server.jar").write_bytes(jar_bytes)
        return "server.jar"
    return _install


@pytest.fixture
def make_env(tmp_path):
    with ExitStack() as stack:
        yield lambda **kw: _Env(tmp_path, stack, **kw)


class TestProvision:
    def test_vanilla_happy_path(self, make_env):
        env = make_env()
        result = env.run()

        assert result.ok and result.name == "srv" and result.required_java == 17
        env.download.assert_called_once()
        env.scaffold.assert_called_once()
        assert env.tunnels == ["srv"]
        env.update_meta.assert_any_call("srv", {"required_java": 17})
        env.jdk.ensure_java.assert_not_called()

    def test_progress_never_moves_backwards(self, make_env):
        env = make_env(java_cached=False, bytecode_java=21)
        env.run(icon_path="icon.png")

        assert env.progress == sorted(env.progress)
        assert env.progress[-1] == 1.0
        assert env.progress[:3] == [0.0, 0.125, 0.25]  # download mapped into its band

    def test_existing_server_is_rejected(self, make_env):
        env = make_env()
        (env.servers_dir / "srv").mkdir()

        result = env.run()

        assert not result.ok and "already exists" in result.error
        env.download.assert_not_called()

    def test_custom_location_creates_junction(self, make_env, tmp_path):
        env = make_env()
        custom = tmp_path / "elsewhere"

        env.run(location=str(custom))

        env.junction.assert_called_once_with(str(custom / "srv"), os.path.join(str(env.servers_dir), "srv"))

    def test_junction_failure_aborts(self, make_env, tmp_path):
        env = make_env()
        env.junction.side_effect = OSError("mklink /J failed")

        result = env.run(location=str(tmp_path / "elsewhere"))

        assert not result.ok and "custom location" in result.error
        env.download.assert_not_called()

    def test_download_failure_stops_before_tunnel(self, make_env):
        env = make_env(download_ok=False)
        result = env.run()

        assert not result.ok
        env.scaffold.assert_not_called()
        assert env.tunnels == []

    def test_unknown_engine_fails(self, make_env):
        env = make_env()
        result = env.run(type="Bukkit")

        assert not result.ok
        assert any("Unknown server type" in line for line in env.lines)

    def test_forge_installer_gets_jdk_and_shim_does_not_downgrade(self, make_env):
        env = make_env(bytecode_java=8, version_map_java=17)
        result = env.run(type="Forge")

        assert result.ok and result.required_java == 17
        assert env.installer_java_bin == "/jdk/bin/java"
        env.install_forge.assert_called_once()

    def test_bytecode_disagreement_is_reported(self, make_env):
        env = make_env(bytecode_java=21, version_map_java=17)
        result = env.run()

        assert result.required_java == 21
        assert any("Bytecode scan found this jar needs Java 21" in line for line in env.lines)

    def test_missing_jdk_is_installed(self, make_env):
        env = make_env(java_cached=False)
        env.run()

        env.jdk.ensure_java.assert_called_once_with(17)
        assert any("Installing Temurin 17.0.9+9" in line for line in env.lines)

    def test_jdk_install_failure_is_not_fatal(self, make_env):
        env = make_env(java_cached=False)
        env.jdk.ensure_java.side_effect = RuntimeError("offline")

        result = env.run()

        assert result.ok
        assert any("[Warning] Java 17 download failed" in line for line in env.lines)

    def test_missing_jar_skips_bytecode_analysis(self, make_env):
        env = make_env(jar_bytes=None)
        result = env.run()

        assert result.ok and result.required_java == 17
        env.analyze.assert_not_called()
        assert any("server.jar not found" in line for line in env.lines)

    def test_unexpected_error_returns_failure(self, make_env):
        env = make_env()
        env.scaffold.side_effect = ValueError("bad properties")

        result = env.run()

        assert not result.ok and result.error == "bad properties"
        assert any("[Error] Installation failed: bad properties" in line for line in env.lines)
