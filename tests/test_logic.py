"""Unit tests for pure functions in app/core/logic.py."""

import os
import sys
import json
import tempfile
import shutil
from unittest.mock import patch, MagicMock, mock_open

import pytest

from app.core.server_events import ServerEvent

TMP = tempfile.gettempdir()

from app.core.logic import (
    normalize_server_jar,
    get_server_meta,
    set_server_meta,
    update_server_meta,
    _run_installer,
    download_server,
    ServerRunner,
)


class TestNormalizeServerJar:
    def setup_method(self):
        self.tmpdir = tempfile.mkdtemp()

    def teardown_method(self):
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def _make_jar(self, name, size=200):
        path = os.path.join(self.tmpdir, name)
        with open(path, "wb") as f:
            f.write(b"x" * size)
        return path

    def test_existing_valid_server_jar(self):
        self._make_jar("server.jar")
        result = normalize_server_jar(self.tmpdir)
        assert result is True

    def test_existing_server_jar_too_small(self):
        self._make_jar("server.jar", size=50)
        result = normalize_server_jar(self.tmpdir)
        # Should fall through to other detection since it's too small
        assert result is False  # No other jar to normalize

    def test_fabric_jar_symlink(self):
        self._make_jar("fabric-server-launch.jar")
        try:
            result = normalize_server_jar(self.tmpdir)
        except (OSError, NotImplementedError):
            # Symlink not supported on Windows - try copying
            os.remove(self.tmpdir)
            self.tmpdir = tempfile.mkdtemp()
            self._make_jar("fabric-server-launch.jar")
            with patch("os.symlink", side_effect=OSError("no symlink on win")):
                result = normalize_server_jar(self.tmpdir)
        jar_path = os.path.join(self.tmpdir, "server.jar")
        assert result is True
        assert os.path.exists(jar_path)
        assert os.path.getsize(jar_path) > 100

    def test_forge_legacy_jar(self):
        self._make_jar("forge-1.20.1-44.1.23.jar")
        try:
            result = normalize_server_jar(self.tmpdir)
        except (OSError, NotImplementedError):
            with patch("os.symlink", side_effect=OSError("no symlink")):
                result = normalize_server_jar(self.tmpdir)
        assert result is True
        assert os.path.exists(os.path.join(self.tmpdir, "server.jar"))

    def test_forge_modern_via_args_file(self):
        lib_dir = os.path.join(self.tmpdir, "libraries", "net", "minecraftforge")
        os.makedirs(lib_dir)
        # Create the main jar
        main_jar = os.path.join(lib_dir, "forge-1.20.1-44.1.23.jar")
        with open(main_jar, "wb") as f:
            f.write(b"x" * 200)
        args_file = "win_args.txt" if sys.platform == "win32" else "unix_args.txt"
        args_path = os.path.join(lib_dir, args_file)
        rel_jar = os.path.relpath(main_jar, self.tmpdir)
        with open(args_path, "w") as f:
            f.write(f"{rel_jar} nogui")
        result = normalize_server_jar(self.tmpdir)
        assert result is True
        assert os.path.exists(os.path.join(self.tmpdir, "server.jar"))

    def test_paper_purpur_jar(self):
        self._make_jar("paper-1.20.1.jar")
        try:
            result = normalize_server_jar(self.tmpdir)
        except (OSError, NotImplementedError):
            with patch("os.symlink", side_effect=OSError("no symlink")):
                result = normalize_server_jar(self.tmpdir)
        assert result is True

    def test_stub_server_jar_replaced_by_real_jar(self):
        # A truncated server.jar must not be picked as its own source.
        self._make_jar("server.jar", size=10)
        self._make_jar("purpur-1.21.jar")
        with patch("os.symlink", side_effect=OSError("no symlink")):
            result = normalize_server_jar(self.tmpdir)
        assert result is True
        assert os.path.getsize(os.path.join(self.tmpdir, "server.jar")) == 200

    def test_installer_jars_are_never_used(self):
        self._make_jar("forge-installer.jar")
        self._make_jar("fabric-installer.jar")
        assert normalize_server_jar(self.tmpdir) is False

    def test_no_valid_jar_returns_false(self):
        result = normalize_server_jar(self.tmpdir)
        assert result is False


class TestServerMeta:
    def setup_method(self):
        self.tmpdir = tempfile.mkdtemp()

    def teardown_method(self):
        shutil.rmtree(self.tmpdir, ignore_errors=True)
        from app.core.logic import _meta_cache
        _meta_cache.clear()

    @patch("app.core.logic.SERVERS_DIR", new_callable=lambda: None)
    def test_get_server_meta_missing_returns_empty(self, mock_servers_dir):
        # Override SERVERS_DIR to point to temp
        with patch("app.core.logic.SERVERS_DIR", self.tmpdir):
            result = get_server_meta("nonexistent")
            assert result == {}

    def test_get_server_meta_valid(self):
        server_dir = os.path.join(self.tmpdir, "test_server")
        os.makedirs(server_dir)
        meta = {"name": "test", "ram": 2048}
        with open(os.path.join(server_dir, "metadata.json"), "w") as f:
            json.dump(meta, f)
        with patch("app.core.logic.SERVERS_DIR", self.tmpdir):
            result = get_server_meta("test_server")
            assert result == meta

    def test_get_server_meta_corrupted(self):
        server_dir = os.path.join(self.tmpdir, "test_server")
        os.makedirs(server_dir)
        with open(os.path.join(server_dir, "metadata.json"), "w") as f:
            f.write("not json")
        with patch("app.core.logic.SERVERS_DIR", self.tmpdir):
            result = get_server_meta("test_server")
            assert result == {}

    def test_set_server_meta_writes_correctly(self):
        server_dir = os.path.join(self.tmpdir, "test_server")
        os.makedirs(server_dir)
        with patch("app.core.logic.SERVERS_DIR", self.tmpdir):
            result = set_server_meta("test_server", "ram", 4096)
            assert result is True
            meta = get_server_meta("test_server")
            assert meta["ram"] == 4096

    def test_update_server_meta_multi_key(self):
        server_dir = os.path.join(self.tmpdir, "test_server")
        os.makedirs(server_dir)
        with patch("app.core.logic.SERVERS_DIR", self.tmpdir):
            set_server_meta("test_server", "ram", 2048)
            result = update_server_meta("test_server", {"ram": 4096, "version": "1.21"})
            assert result is True
            meta = get_server_meta("test_server")
            assert meta["ram"] == 4096
            assert meta["version"] == "1.21"

    def test_set_server_meta_io_error_returns_false(self):
        with patch("app.core.logic.SERVERS_DIR", self.tmpdir):
            with patch("builtins.open", side_effect=OSError("Permission denied")):
                result = set_server_meta("test_server", "ram", 2048)
                assert result is False


class TestSchedulerGetStatus:
    """Tests for Scheduler.get_status() — particularly the 'missed' field (MA-05)."""

    def _make_scheduler(self, meta_override):
        from app.core.logic import Scheduler
        with patch("app.core.logic.get_server_meta", return_value=meta_override):
            return Scheduler("test_server")

    def test_get_status_returns_none_when_no_schedule(self):
        from app.core.logic import Scheduler
        with patch("app.core.logic.get_server_meta", return_value={}):
            sched = Scheduler("test_server")
        with patch("app.core.logic.get_server_meta", return_value={}):
            assert sched.get_status() is None

    def test_get_status_interval_not_missed(self):
        import datetime
        from app.core.logic import Scheduler
        last_run = (datetime.datetime.now() - datetime.timedelta(hours=3)).isoformat()
        meta = {"scheduler": {"type": "interval", "interval_hours": 6,
                               "last_run": last_run, "backup_on_restart": False}}
        with patch("app.core.logic.get_server_meta", return_value=meta):
            sched = Scheduler("test_server")
            status = sched.get_status()
        assert status is not None
        assert status["missed"] is False
        assert status["remaining_seconds"] > 0

    def test_get_status_time_mode_missed_window(self):
        """If >120s past target time today, missed=True."""
        import datetime
        from app.core.logic import Scheduler
        now = datetime.datetime.now()
        # Target was 5 minutes ago, not run today
        target = now - datetime.timedelta(minutes=5)
        meta = {"scheduler": {
            "type": "time",
            "restart_time": f"{target.hour:02d}:{target.minute:02d}",
            "last_run": None,
            "backup_on_restart": False,
        }}
        with patch("app.core.logic.get_server_meta", return_value=meta):
            sched = Scheduler("test_server")
            status = sched.get_status()
        assert status is not None
        assert status["missed"] is True
        assert status["remaining_seconds"] < -120

    def test_get_status_time_mode_within_window(self):
        """If within 0-120s of target, missed=False (window still valid)."""
        import datetime
        from app.core.logic import Scheduler
        now = datetime.datetime.now()
        # Target was 30 seconds ago — still within window
        target = now - datetime.timedelta(seconds=30)
        meta = {"scheduler": {
            "type": "time",
            "restart_time": f"{target.hour:02d}:{target.minute:02d}",
            "last_run": None,
            "backup_on_restart": False,
        }}
        with patch("app.core.logic.get_server_meta", return_value=meta):
            sched = Scheduler("test_server")
            status = sched.get_status()
        assert status is not None
        assert status["missed"] is False

    def test_get_status_has_missed_key(self):
        """All returned dicts must have a 'missed' key."""
        import datetime
        from app.core.logic import Scheduler
        last_run = (datetime.datetime.now() - datetime.timedelta(hours=1)).isoformat()
        meta = {"scheduler": {"type": "interval", "interval_hours": 6,
                               "last_run": last_run, "backup_on_restart": False}}
        with patch("app.core.logic.get_server_meta", return_value=meta):
            sched = Scheduler("test_server")
            status = sched.get_status()
        assert "missed" in status
        assert "is_due" in status
        assert "remaining_seconds" in status


class TestRunInstaller:
    @patch("builtins.open", mock_open())
    @patch("app.core.logic.create_server_directory")
    @patch("app.core.version_manager.VersionManager.get_download_url")
    @patch("app.core.version_manager.VersionManager._load_cache")
    @patch("app.core.version_manager.os.path.exists", return_value=False)
    @patch("app.core.logic.requests.get")
    @patch("app.core.logic.subprocess.run")
    @patch("app.core.logic.normalize_server_jar")
    def test_run_installer_success(self, mock_normalize, mock_subprocess, mock_get, mock_exists, mock_load_cache, mock_url, mock_create_dir):
        mock_load_cache.return_value = {"last_updated": None, "Vanilla": ["1.20.1"], "Fabric": ["1.20.1"], "Forge": ["1.20.1"], "Paper": ["1.20.1"], "Purpur": ["1.20.1"]}
        mock_create_dir.return_value = f"{TMP}/test_server"
        mock_url.return_value = "https://example.com/installer.jar"
        mock_resp = MagicMock()
        mock_resp.iter_content.return_value = [b"data"]
        mock_resp.raise_for_status = MagicMock()
        mock_get.return_value = mock_resp
        mock_subprocess.return_value = MagicMock(returncode=0)

        result = _run_installer("test", "Fabric", "1.20.1",
                                "fabric-installer.jar", ["server", "-mcversion", "1.20.1"])
        assert result == f"{TMP}/test_server"
        mock_normalize.assert_called_once_with(f"{TMP}/test_server")

    @patch("app.core.logic.create_server_directory")
    @patch("app.core.version_manager.VersionManager.get_download_url")
    @patch("app.core.version_manager.VersionManager._load_cache")
    @patch("app.core.version_manager.os.path.exists", return_value=False)
    def test_run_installer_no_url_returns_none(self, mock_exists, mock_load_cache, mock_url, mock_create_dir):
        mock_load_cache.return_value = {"last_updated": None, "Vanilla": ["1.20.1"], "Fabric": ["1.20.1"], "Forge": ["1.20.1"], "Paper": ["1.20.1"], "Purpur": ["1.20.1"]}
        mock_create_dir.return_value = f"{TMP}/test_server"
        mock_url.return_value = None
        result = _run_installer("test", "Fabric", "1.20.1",
                                "fabric-installer.jar", ["server", "-mcversion", "1.20.1"])
        assert result is None

    @patch("app.core.logic.create_server_directory")
    @patch("app.core.version_manager.VersionManager.get_download_url")
    @patch("app.core.version_manager.VersionManager._load_cache")
    @patch("app.core.version_manager.os.path.exists", return_value=False)
    @patch("app.core.logic.requests.get", side_effect=Exception("Download failed"))
    def test_run_installer_download_failure(self, mock_get, mock_exists, mock_load_cache, mock_url, mock_create_dir):
        mock_load_cache.return_value = {"last_updated": None, "Vanilla": ["1.20.1"], "Fabric": ["1.20.1"], "Forge": ["1.20.1"], "Paper": ["1.20.1"], "Purpur": ["1.20.1"]}
        mock_create_dir.return_value = f"{TMP}/test_server"
        mock_url.return_value = "https://example.com/installer.jar"
        result = _run_installer("test", "Fabric", "1.20.1",
                                "fabric-installer.jar", ["server", "-mcversion", "1.20.1"])
        assert result is None

    @patch("app.core.logic.create_server_directory")
    @patch("app.core.version_manager.VersionManager.get_download_url")
    @patch("app.core.version_manager.VersionManager._load_cache")
    @patch("app.core.version_manager.os.path.exists", return_value=False)
    @patch("app.core.logic.requests.get")
    @patch("app.core.logic.subprocess.run", side_effect=Exception("Java failed"))
    def test_run_installer_subprocess_failure(self, mock_subprocess, mock_get, mock_exists, mock_load_cache, mock_url, mock_create_dir):
        mock_load_cache.return_value = {"last_updated": None, "Vanilla": ["1.20.1"], "Fabric": ["1.20.1"], "Forge": ["1.20.1"], "Paper": ["1.20.1"], "Purpur": ["1.20.1"]}
        mock_create_dir.return_value = f"{TMP}/test_server"
        mock_url.return_value = "https://example.com/installer.jar"
        mock_resp = MagicMock()
        mock_resp.iter_content.return_value = [b"data"]
        mock_get.return_value = mock_resp
        result = _run_installer("test", "Fabric", "1.20.1",
                                "fabric-installer.jar", ["server", "-mcversion", "1.20.1"])
        assert result is None


class TestDownloadServer:
    @patch("app.core.logic.VersionManager")
    @patch("app.core.logic.create_server_directory")
    @patch("app.core.logic.VANILLA_MANIFEST_URL", "https://example.com/manifest.json")
    @patch("app.core.logic.requests.get")
    def test_download_server_no_url(self, mock_get, mock_create_dir, mock_vm):
        mock_vm_instance = MagicMock()
        mock_vm_instance.get_download_url.return_value = None
        mock_vm.return_value = mock_vm_instance
        import pytest
        with pytest.raises(ValueError, match="URL not found"):
            download_server("test", "Vanilla", "1.20.1")

    @patch("app.core.logic.VersionManager")
    @patch("app.core.logic.create_server_directory")
    @patch("app.core.logic.VANILLA_MANIFEST_URL", "https://example.com/manifest.json")
    @patch("app.core.logic.requests.get")
    @patch("app.core.logic.normalize_server_jar")
    @patch("app.services.sha1_validator.download_with_verification")
    def test_download_server_vanilla_with_sha1(
        self, mock_dl_verify, mock_normalize, mock_get, mock_create_dir, mock_vm
    ):
        mock_vm_instance = MagicMock()
        mock_vm_instance.get_download_url.return_value = "https://example.com/server.jar"
        mock_vm.return_value = mock_vm_instance
        mock_create_dir.return_value = os.path.join(TMP, "test_server")
        # Mock manifest request chain for SHA1
        mock_manifest_resp = MagicMock()
        mock_manifest_resp.status_code = 200
        mock_manifest_resp.json.return_value = {
            "versions": [
                {"id": "1.20.1", "url": "https://example.com/1.20.1.json"}
            ]
        }
        mock_version_resp = MagicMock()
        mock_version_resp.status_code = 200
        mock_version_resp.json.return_value = {
            "downloads": {
                "server": {"sha1": "abc123def456"}
            }
        }
        mock_get.side_effect = [mock_manifest_resp, mock_version_resp]
        mock_normalize.return_value = True

        expected_path = os.path.join(TMP, "test_server", "server.jar")
        mock_dl_verify.return_value = (True, expected_path, None)

        result = download_server("test", "Vanilla", "1.20.1")
        assert result == expected_path
        # Verify SHA1 was passed to download_with_verification
        _, kwargs = mock_dl_verify.call_args
        assert kwargs.get("expected_sha1") == "abc123def456"


class TestServerRunnerJvmCustomFlags:
    def setup_method(self):
        self.tmpdir = tempfile.mkdtemp()

    def teardown_method(self):
        shutil.rmtree(self.tmpdir, ignore_errors=True)
        from app.core.logic import _meta_cache
        _meta_cache.clear()

    def _make_server(self, tmpdir, jvm_custom_flags=None):
        server_dir = os.path.join(tmpdir, "test_server")
        os.makedirs(server_dir)
        with open(os.path.join(server_dir, "server.jar"), "w", encoding="utf-8") as f:
            f.write("")
        meta = {"ram": 1024}
        if jvm_custom_flags is not None:
            meta["jvm_custom_flags"] = jvm_custom_flags
        with open(os.path.join(server_dir, "metadata.json"), "w", encoding="utf-8") as f:
            json.dump(meta, f)
        return server_dir

    @patch("app.core.logic._port_in_use", return_value=False)
    @patch("app.core.logic.subprocess.Popen")
    @patch("app.core.logic.probe_java", return_value=None)
    @patch("app.core.logic.check_eula", return_value=True)
    def test_custom_flags_appended_to_cmd(self, mock_eula, mock_probe, mock_popen, mock_port):
        self._make_server(self.tmpdir, jvm_custom_flags="-XX:+UseG1GC -Dfoo=bar")
        mock_popen.return_value = MagicMock(stdout=iter([]), stderr=iter([]), returncode=0)
        with patch("app.core.logic.SERVERS_DIR", self.tmpdir):
            runner = ServerRunner("test_server", "1024M", MagicMock())
            runner.start()
        cmd = mock_popen.call_args.args[0]
        assert "-XX:+UseG1GC" in cmd
        assert "-Dfoo=bar" in cmd

    @patch("app.core.logic._port_in_use", return_value=False)
    @patch("app.core.logic.subprocess.Popen")
    @patch("app.core.logic.probe_java", return_value=None)
    @patch("app.core.logic.check_eula", return_value=True)
    def test_empty_custom_flags_no_op(self, mock_eula, mock_probe, mock_popen, mock_port):
        self._make_server(self.tmpdir)
        mock_popen.return_value = MagicMock(stdout=iter([]), stderr=iter([]), returncode=0)
        with patch("app.core.logic.SERVERS_DIR", self.tmpdir):
            runner = ServerRunner("test_server", "1024M", MagicMock())
            runner.start()
        cmd = mock_popen.call_args.args[0]
        assert cmd.count("-jar") == 1
        assert "server.jar" in cmd

    @patch("app.core.logic._port_in_use", return_value=False)
    @patch("app.core.logic.subprocess.Popen")
    @patch("app.core.logic.probe_java", return_value=None)
    @patch("app.core.logic.check_eula", return_value=True)
    def test_malformed_custom_flags_caught(self, mock_eula, mock_probe, mock_popen, mock_port):
        self._make_server(self.tmpdir, jvm_custom_flags='-Dfoo="unterminated')
        mock_popen.return_value = MagicMock(stdout=iter([]), stderr=iter([]), returncode=0)
        with patch("app.core.logic.SERVERS_DIR", self.tmpdir):
            runner = ServerRunner("test_server", "1024M", MagicMock())
            runner.start()
        assert mock_popen.called
        cmd = mock_popen.call_args.args[0]
        assert "server.jar" in cmd


class TestServerRunnerLaunch:
    """Characterizes how ServerRunner.start() picks the launch target and
    fails before spawning a process."""

    def setup_method(self):
        self.tmpdir = tempfile.mkdtemp()
        self.server_dir = os.path.join(self.tmpdir, "srv")
        os.makedirs(self.server_dir)

    def teardown_method(self):
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def _touch(self, rel, content=""):
        path = os.path.join(self.server_dir, rel)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            f.write(content)
        return path

    def _start(self, ram="1024M", use_aikars=False, port_busy=False, popen_error=None):
        events = MagicMock()
        with patch("app.core.logic.SERVERS_DIR", self.tmpdir),              patch("app.core.logic.check_eula", return_value=True),              patch("app.core.logic.probe_java", return_value=None),              patch("app.core.logic._port_in_use", return_value=port_busy),              patch("app.core.logic.subprocess.Popen") as mock_popen,              patch("app.core.process_job.assign_to_job"):
            if popen_error:
                mock_popen.side_effect = popen_error
            else:
                mock_popen.return_value = MagicMock(stdout=iter([]), stderr=iter([]), pid=1)
            runner = ServerRunner("srv", ram, events, use_aikars=use_aikars)
            try:
                runner.start()
            finally:
                self.events = events
                self.popen = mock_popen
        return runner

    def _cmd(self):
        return self.popen.call_args.args[0]

    def test_fabric_launch_jar_preferred(self):
        self._touch("fabric-server-launch.jar")
        self._touch("server.jar")
        self._start()
        assert self._cmd()[-2:] == ["fabric-server-launch.jar", "nogui"]

    def test_forge_legacy_jar_used(self):
        self._touch("forge-1.12.2-14.23.5.jar")
        self._touch("forge-installer.jar")
        self._start()
        assert "forge-1.12.2-14.23.5.jar" in self._cmd()

    def test_forge_modern_uses_args_file(self):
        self._touch("run.bat")
        args_name = "win_args.txt" if sys.platform == "win32" else "unix_args.txt"
        self._touch(os.path.join("libraries", "net", "minecraftforge", args_name), "forge.jar")
        self._start()
        cmd = self._cmd()
        assert any(part.startswith("@libraries") and part.endswith(args_name) for part in cmd)
        assert "-jar" not in cmd

    def test_gigabyte_ram_converted_without_aikars(self):
        self._touch("server.jar")
        self._start(ram="2G")
        assert "-Xmx2048M" in self._cmd() and "-Xms2048M" in self._cmd()

    def test_unparseable_ram_falls_back_to_2048(self):
        self._touch("server.jar")
        self._start(ram="lots")
        assert "-Xmx2048M" in self._cmd()

    def test_missing_jar_raises_before_spawn(self):
        from app.core.logic import ServerStartError
        with pytest.raises(ServerStartError, match="Server jar not found"):
            self._start()
        self.popen.assert_not_called()

    def test_busy_port_raises_before_spawn(self):
        from app.core.logic import ServerStartError
        self._touch("server.jar")
        with pytest.raises(ServerStartError, match="already in use"):
            self._start(port_busy=True)
        self.popen.assert_not_called()

    def test_spawn_failure_raises_server_start_error(self):
        # Popen failing (e.g. java binary missing) must surface like the other
        # pre-launch failures, or ZBBManager stays in STARTING.
        from app.core.logic import ServerStartError
        self._touch("server.jar")
        with pytest.raises(ServerStartError, match="Failed to start server"):
            self._start(popen_error=FileNotFoundError("java not found"))
        notifications = [c.args[1] for c in self.events.emit.call_args_list
                         if c.args and c.args[0] == ServerEvent.NOTIFICATION]
        assert any(n["type"] == "error" for n in notifications)


class TestDeleteServer:
    def test_deletes_real_directory(self, tmp_path):
        from app.core.logic import delete_server
        server = tmp_path / "myserver"
        (server / "world").mkdir(parents=True)
        (server / "server.jar").write_text("x")
        with patch("app.core.logic.SERVERS_DIR", str(tmp_path)):
            delete_server("myserver")
        assert not server.exists()

    def test_missing_server_is_noop(self, tmp_path):
        from app.core.logic import delete_server
        with patch("app.core.logic.SERVERS_DIR", str(tmp_path)):
            delete_server("ghost")  # must not raise

    def test_empty_directory_deleted(self, tmp_path):
        from app.core.logic import delete_server
        server = tmp_path / "empty"
        server.mkdir()
        with patch("app.core.logic.SERVERS_DIR", str(tmp_path)):
            delete_server("empty")
        assert not server.exists()


class TestServerRunnerMemoryUsage:
    def _runner(self, running=True, process=True):
        runner = ServerRunner("srv", "1024M", MagicMock())
        runner.process = MagicMock(pid=4242) if process else None
        runner.running = running
        return runner

    def test_sums_process_and_children(self):
        import psutil
        root = MagicMock()
        root.memory_info.return_value.rss = 1000
        child_ok = MagicMock()
        child_ok.memory_info.return_value.rss = 500
        child_gone = MagicMock()
        child_gone.memory_info.side_effect = psutil.NoSuchProcess(1)
        root.children.return_value = [child_ok, child_gone]
        with patch("psutil.Process", return_value=root) as mock_proc:
            assert self._runner().memory_usage_bytes() == 1500
        mock_proc.assert_called_once_with(4242)

    def test_none_when_not_running(self):
        assert self._runner(running=False).memory_usage_bytes() is None
        assert self._runner(process=False).memory_usage_bytes() is None

    def test_none_when_process_vanished(self):
        import psutil
        with patch("psutil.Process", side_effect=psutil.NoSuchProcess(4242)):
            assert self._runner().memory_usage_bytes() is None
