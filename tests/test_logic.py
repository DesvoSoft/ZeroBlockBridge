"""Unit tests for pure functions in app/core/logic.py."""

import os
import sys
import json
import threading
import tempfile
import shutil
from unittest.mock import patch, MagicMock, mock_open

TMP = tempfile.gettempdir()

from app.core.logic import (
    normalize_server_jar,
    _get_jar_event,
    wait_for_jar_ready,
    get_server_meta,
    set_server_meta,
    update_server_meta,
    _run_installer,
    download_server,
)


class TestGetJarEvent:
    def test_get_or_create_event(self):
        ev = _get_jar_event(f"{TMP}/test_server")
        assert isinstance(ev, threading.Event)
        ev2 = _get_jar_event(f"{TMP}/test_server")
        assert ev is ev2

    def test_different_dirs_different_events(self):
        ev1 = _get_jar_event(f"{TMP}/server1")
        ev2 = _get_jar_event(f"{TMP}/server2")
        assert ev1 is not ev2

    def teardown_method(self):
        from app.core.logic import _jar_ready_events
        _jar_ready_events.clear()


class TestWaitForJarReady:
    def test_wait_returns_true_when_set(self):
        ev = _get_jar_event(f"{TMP}/test")
        ev.set()
        assert wait_for_jar_ready(f"{TMP}/test", timeout=1) is True

    def test_wait_returns_false_on_timeout(self):
        result = wait_for_jar_ready(f"{TMP}/nonexistent", timeout=0.1)
        assert result is False

    def teardown_method(self):
        from app.core.logic import _jar_ready_events
        _jar_ready_events.clear()


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
