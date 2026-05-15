import pytest
import hashlib
from pathlib import Path
from unittest.mock import MagicMock, patch
from app.services.java_installer import (
    JdkManager,
    JdkManagerInstance,
    JdkDownloadError,
    JdkIntegrityError,
    _platform_os,
    _platform_arch,
    _java_exe_name,
    _verify_checksum,
    _find_java_binary,
    _jdk_cache_dir,
    _get_common_prefix,
    _fetch_asset_info,
    MAX_RETRIES,
)


class TestHelpers:
    def test_platform_os(self):
        import sys
        expected = {"win32": "windows", "linux": "linux", "darwin": "mac"}
        assert _platform_os() == expected.get(sys.platform, "linux")

    def test_platform_arch(self):
        arch = _platform_arch()
        assert arch in ("x64", "arm64", "arm")

    def test_java_exe_name(self):
        import sys
        if sys.platform == "win32":
            assert _java_exe_name() == "java.exe"
        else:
            assert _java_exe_name() == "java"

    def test_verify_checksum_match(self, tmp_path):
        f = tmp_path / "test.bin"
        data = b"hello world"
        f.write_bytes(data)
        expected = hashlib.sha256(data).hexdigest()
        assert _verify_checksum(f, expected) is True

    def test_verify_checksum_mismatch(self, tmp_path):
        f = tmp_path / "test.bin"
        f.write_bytes(b"hello world")
        assert _verify_checksum(f, "0" * 64) is False

    def test_find_java_binary_found(self, tmp_path):
        java_dir = tmp_path / "jdk17" / "bin"
        java_dir.mkdir(parents=True)
        exe = java_dir / _java_exe_name()
        exe.write_text("")
        result = _find_java_binary(tmp_path / "jdk17")
        assert result == exe

    def test_find_java_binary_not_found(self, tmp_path):
        assert _find_java_binary(tmp_path) is None

    def test_get_common_prefix(self):
        paths = ["jdk-17.0.1/bin/java", "jdk-17.0.1/bin/javac", "jdk-17.0.1/lib/"]
        assert _get_common_prefix(paths) == "jdk-17.0.1/"

    def test_get_common_prefix_empty(self):
        assert _get_common_prefix([]) == ""

    def test_get_common_prefix_no_common(self):
        paths = ["foo/bar", "baz/qux"]
        assert _get_common_prefix(paths) == ""

    def test_jdk_cache_dir(self):
        d = _jdk_cache_dir(17)
        assert d.name == "jdk17"


class TestJdkManager:
    def test_get_java_path_no_cache(self, tmp_path):
        with patch("app.services.java_installer._JDK_CACHE_DIR", tmp_path):
            mgr = JdkManager()
            assert mgr.get_java_path(17) is None

    def test_get_java_path_with_cache(self, tmp_path):
        cache_dir = tmp_path / "jdks" / "jdk17"
        bin_dir = cache_dir / "bin"
        bin_dir.mkdir(parents=True)
        exe = bin_dir / _java_exe_name()
        exe.write_text("")

        with patch("app.services.java_installer._JDK_CACHE_DIR", tmp_path / "jdks"):
            mgr = JdkManager()
            result = mgr.get_java_path(17)
            assert result == str(exe)

    def test_get_java_path_cache_no_binary_cleans_up(self, tmp_path):
        cache_dir = tmp_path / "jdks" / "jdk17"
        cache_dir.mkdir(parents=True)
        (cache_dir / "some_file.txt").write_text("")

        with patch("app.services.java_installer._JDK_CACHE_DIR", tmp_path / "jdks"):
            mgr = JdkManager()
            assert mgr.get_java_path(17) is None
            assert not cache_dir.exists()

    def test_ensure_java_uses_cache(self, tmp_path):
        cache_dir = tmp_path / "jdks" / "jdk17"
        bin_dir = cache_dir / "bin"
        bin_dir.mkdir(parents=True)
        exe = bin_dir / _java_exe_name()
        exe.write_text("")

        with patch("app.services.java_installer._JDK_CACHE_DIR", tmp_path / "jdks"):
            mgr = JdkManager()
            result = mgr.ensure_java(17)
            assert result == str(exe)

    @patch("app.services.java_installer._fetch_asset_info")
    @patch("app.services.java_installer.JdkManager._download_and_install")
    def test_ensure_java_downloads(self, mock_dl, mock_fetch, tmp_path):
        cache_dir = tmp_path / "jdks"
        mock_dl.return_value = str(cache_dir / "jdk17")

        with patch("app.services.java_installer._JDK_CACHE_DIR", cache_dir):
            mgr = JdkManager()
            result = mgr.ensure_java(17)
            mock_dl.assert_called_once_with(17)
            assert result == mock_dl.return_value

    @patch("app.services.java_installer._fetch_asset_info")
    @patch("app.services.java_installer.JdkManager._download_file")
    @patch("app.services.java_installer._verify_checksum", return_value=True)
    def test_download_and_install_success(self, mock_verify, mock_dl, mock_fetch, tmp_path):
        mock_fetch.return_value = {
            "url": "https://example.com/jdk.zip",
            "checksum": "ABC123",
            "version": "17.0.1",
        }
        cache_dir = tmp_path / "jdks"

        with patch("app.services.java_installer._JDK_CACHE_DIR", cache_dir), \
             patch("app.services.java_installer.JdkManager._extract_zip") as mock_extract:

            mgr = JdkManager()
            result = mgr._download_and_install(17)
            assert "jdk17" in result
            mock_dl.assert_called_once()
            mock_verify.assert_called_once()
            mock_extract.assert_called_once()

    @patch("app.services.java_installer._fetch_asset_info")
    def test_download_and_install_checksum_mismatch(self, mock_fetch, tmp_path):
        mock_fetch.return_value = {
            "url": "https://example.com/jdk.zip",
            "checksum": "A" * 64,
            "version": "17.0.1",
        }
        cache_dir = tmp_path / "jdks"

        with patch("app.services.java_installer._JDK_CACHE_DIR", cache_dir), \
             patch("app.services.java_installer.JdkManager._download_file"), \
             patch("app.services.java_installer._verify_checksum", return_value=False):

            mgr = JdkManager()
            with pytest.raises(JdkIntegrityError):
                mgr._download_and_install(17)

    def test_download_file_connection_error(self, tmp_path):
        mgr = JdkManager()
        dest = tmp_path / "jdk.zip"
        with patch("requests.get", side_effect=__import__("requests").ConnectionError):
            with pytest.raises(JdkDownloadError, match="No internet connection"):
                mgr._download_file("https://example.com/jdk.zip", dest)

    def test_download_file_timeout(self, tmp_path):
        mgr = JdkManager()
        dest = tmp_path / "jdk.zip"
        with patch("requests.get", side_effect=__import__("requests").Timeout):
            with pytest.raises(JdkDownloadError, match="timed out"):
                mgr._download_file("https://example.com/jdk.zip", dest)

    def test_download_file_request_error(self, tmp_path):
        mgr = JdkManager()
        dest = tmp_path / "jdk.zip"
        with patch("requests.get", side_effect=__import__("requests").RequestException("500")):
            with pytest.raises(JdkDownloadError, match="JDK download failed"):
                mgr._download_file("https://example.com/jdk.zip", dest)

    def test_purge_cache_single_version(self, tmp_path):
        cache_dir = tmp_path / "jdks" / "jdk17"
        cache_dir.mkdir(parents=True)
        (cache_dir / "bin" / _java_exe_name()).parent.mkdir(parents=True)
        (cache_dir / "bin" / _java_exe_name()).write_text("")

        with patch("app.services.java_installer._JDK_CACHE_DIR", tmp_path / "jdks"):
            mgr = JdkManager()
            mgr.purge_cache(17)
            assert not cache_dir.exists()

    @patch("app.services.java_installer.shutil.rmtree")
    def test_purge_cache_all(self, mock_rmtree, tmp_path):
        with patch("app.services.java_installer._JDK_CACHE_DIR", tmp_path):
            mgr = JdkManager()
            mgr.purge_cache()
            mock_rmtree.assert_called_once_with(tmp_path, ignore_errors=True)


class TestFetchAssetInfo:
    @patch("app.services.java_installer.requests.get")
    def test_fetch_success(self, mock_get):
        mock_get.return_value.status_code = 200
        mock_get.return_value.json.return_value = [{
            "binary": {
                "package": {
                    "link": "https://example.com/jdk.zip",
                    "checksum": "abc123",
                }
            },
            "version_data": {"semver": "17.0.1"},
        }]
        mock_get.return_value.raise_for_status = MagicMock()

        result = _fetch_asset_info(17)
        assert result["url"] == "https://example.com/jdk.zip"
        assert result["checksum"] == "ABC123"

    @patch("app.services.java_installer.requests.get")
    def test_fetch_empty_assets(self, mock_get):
        mock_get.return_value.status_code = 200
        mock_get.return_value.json.return_value = []
        mock_get.return_value.raise_for_status = MagicMock()

        with pytest.raises(JdkDownloadError, match="No JDK 17 asset"):
            _fetch_asset_info(17)

    @patch("app.services.java_installer.requests.get")
    def test_fetch_no_link(self, mock_get):
        mock_get.return_value.status_code = 200
        mock_get.return_value.json.return_value = [{
            "binary": {"package": {}},
        }]
        mock_get.return_value.raise_for_status = MagicMock()

        with pytest.raises(JdkDownloadError, match="missing package link"):
            _fetch_asset_info(17)

    @patch("app.services.java_installer.requests.get")
    def test_fetch_connection_error(self, mock_get):
        mock_get.side_effect = __import__("requests").ConnectionError()
        with pytest.raises(JdkDownloadError, match="No internet connection"):
            _fetch_asset_info(17)

    @patch("app.services.java_installer.requests.get")
    def test_fetch_timeout(self, mock_get):
        mock_get.side_effect = __import__("requests").Timeout()
        with pytest.raises(JdkDownloadError, match="timed out"):
            _fetch_asset_info(17)

    @patch("app.services.java_installer.requests.get")
    def test_fetch_request_exception(self, mock_get):
        mock_get.side_effect = __import__("requests").RequestException("bad")
        with pytest.raises(JdkDownloadError, match="Adoptium API request failed"):
            _fetch_asset_info(17)
