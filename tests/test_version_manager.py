"""Unit tests for VersionManager (app/core/version_manager.py)."""

import datetime
import json
import threading
from unittest.mock import patch, MagicMock, mock_open

from app.core.version_manager import VersionManager


def _reset_singleton():
    VersionManager._instance = None


class TestVersionManagerSingleton:
    def setup_method(self):
        _reset_singleton()

    def test_singleton_returns_same_instance(self):
        vm1 = VersionManager()
        vm2 = VersionManager()
        assert vm1 is vm2

    def test_init_only_runs_once(self):
        _reset_singleton()
        vm = VersionManager()
        assert vm._initialized
        # Calling __init__ again shouldn't change anything
        vm.__init__()
        assert vm._initialized


class TestVersionManagerDefaults:
    def setup_method(self):
        _reset_singleton()

    @patch("app.core.version_manager.os.path.exists", return_value=False)
    def test_get_default_cache_structure(self, mock_exists):
        vm = VersionManager()
        default = vm._get_default_cache()
        assert "last_updated" in default
        assert default["last_updated"] is None
        for key in ("Vanilla", "Fabric", "Forge", "Paper", "Purpur"):
            assert key in default
            assert isinstance(default[key], list)
            assert len(default[key]) > 0
        assert "1.21.11" in default["Vanilla"]
        assert "1.20.1" in default["Vanilla"]

    @patch("app.core.version_manager.os.path.exists", return_value=False)
    def test_fallback_cache_used_when_no_file(self, mock_exists):
        vm = VersionManager()
        assert vm.cache["last_updated"] is None
        assert len(vm.cache["Vanilla"]) > 0


class TestVersionManagerLoadCache:
    """Tests for _load_cache(). Cache is now lazy-loaded, so tests call
    _load_cache() directly and assign the result to vm.cache."""

    def setup_method(self):
        _reset_singleton()

    @patch("app.core.version_manager.VersionManager._fetch_defaults_sync")
    @patch("builtins.open", new_callable=mock_open, read_data=json.dumps({
        "last_updated": datetime.datetime.now().isoformat(),
        "Vanilla": ["1.20.1"],
        "Fabric": ["1.20.1"],
        "Paper": ["1.20.1"],
        "Purpur": ["1.20.1"],
    }))
    @patch("app.core.version_manager.os.path.exists", return_value=True)
    def test_load_cache_valid(self, mock_exists, mock_file, mock_fetch):
        mock_fetch.return_value = {"last_updated": datetime.datetime.now().isoformat(), "Vanilla": ["1.20.1"]}
        vm = VersionManager()
        vm.cache = vm._load_cache()
        assert vm.cache["Vanilla"] == ["1.20.1"]

    @patch("app.core.version_manager.os.path.exists", return_value=True)
    def test_load_cache_corrupted_returns_defaults(self, mock_exists):
        mock_opener = mock_open(read_data="not json")
        mock_opener.side_effect = json.JSONDecodeError("Boom", "", 0)
        with patch("builtins.open", mock_opener):
            vm = VersionManager()
            vm.cache = vm._load_cache()
            assert vm.cache["last_updated"] is None
            assert "1.21.11" in vm.cache["Vanilla"]

    @patch("builtins.open", new_callable=mock_open, read_data=json.dumps({
        "last_updated": None,
        "Vanilla": ["1.20.1"],
        "Fabric": ["0.1.0", "0.2.0"],
        "Forge": ["1.20.1"],
        "Paper": ["1.20.1"],
        "Purpur": ["1.20.1"],
    }))
    @patch("app.core.version_manager.os.path.exists", return_value=True)
    def test_stale_fabric_loader_triggers_refresh(self, mock_exists, mock_file):
        vm = VersionManager()
        vm.cache = vm._load_cache()
        # Stale Fabric triggers a return of default cache
        assert vm.cache["last_updated"] is None
        assert "1.21.11" in vm.cache["Vanilla"]

    @patch("builtins.open", new_callable=mock_open, read_data=json.dumps({
        "last_updated": None,
        "Vanilla": ["1.20.1"],
        "Fabric": ["1.20.1"],
        "Forge": ["26.1.2"],
        "Paper": ["1.20.1"],
        "Purpur": ["1.20.1"],
    }))
    @patch("app.core.version_manager.os.path.exists", return_value=True)
    @patch("app.core.version_manager.VersionManager._fetch_defaults_sync")
    def test_stale_forge_version_triggers_refresh(self, mock_fetch, mock_exists, mock_file):
        mock_fetch.return_value = {
            "last_updated": None,
            "Vanilla": ["1.21.11"],
            "Fabric": ["1.21.11"],
            "Forge": ["1.21.1"],
            "Paper": ["1.21.11"],
            "Purpur": ["1.21.11"],
        }
        vm = VersionManager()
        vm.cache = vm._load_cache()
        assert vm.cache["last_updated"] is None

    @patch("builtins.open", new_callable=mock_open, read_data=json.dumps({
        "last_updated": datetime.datetime.now().isoformat(),
        "Vanilla": ["1.20.1"],
        "Fabric": ["1.20.1"],
        "Paper": ["1.20.1"],
        "Purpur": ["1.20.1"],
    }))
    @patch("app.core.version_manager.os.path.exists", return_value=True)
    def test_cache_within_2_days_not_stale(self, mock_exists, mock_file):
        vm = VersionManager()
        vm.cache = vm._load_cache()
        assert vm.cache["Vanilla"] == ["1.20.1"]

    @patch("builtins.open", new_callable=mock_open, read_data=json.dumps({
        "last_updated": "2023-01-01T00:00:00",
        "Vanilla": ["1.20.1"],
        "Fabric": ["1.20.1"],
        "Forge": ["1.20.1"],
        "Paper": ["1.20.1"],
        "Purpur": ["1.20.1"],
    }))
    @patch("app.core.version_manager.os.path.exists", return_value=True)
    @patch("app.core.version_manager.VersionManager._fetch_all_versions")
    def test_cache_older_than_2_days_triggers_sync_refresh(self, mock_fetch, mock_exists, mock_file):
        mock_fetch.return_value = {
            "Vanilla": ["1.21.11", "1.21.10"],
            "Fabric": ["1.21.11"],
            "Forge": ["1.21.1"],
            "Paper": ["1.21.11"],
            "Purpur": ["1.21.11"],
        }
        vm = VersionManager()
        vm.cache = vm._load_cache()
        assert "1.21.11" in vm.cache["Vanilla"]


class TestVersionManagerGetVersions:
    def setup_method(self):
        _reset_singleton()

    @patch("app.core.version_manager.os.path.exists", return_value=False)
    @patch("app.core.version_manager.VersionManager._check_and_refresh")
    def test_get_versions_returns_list(self, mock_check, mock_exists):
        vm = VersionManager()
        result = vm.get_versions("Vanilla")
        assert isinstance(result, list)
        assert "1.21.11" in result

    @patch("app.core.version_manager.os.path.exists", return_value=False)
    @patch("app.core.version_manager.VersionManager._check_and_refresh")
    def test_get_versions_unknown_type_returns_empty(self, mock_check, mock_exists):
        vm = VersionManager()
        result = vm.get_versions("Unknown")
        assert result == []

    @patch("app.core.version_manager.os.path.exists", return_value=False)
    def test_get_versions_calls_check_and_refresh(self, mock_exists):
        vm = VersionManager()
        with patch.object(vm, "_check_and_refresh") as mock_check:
            vm.get_versions("Vanilla")
            mock_check.assert_called_once()


class TestVersionManagerURLResolution:
    def setup_method(self):
        _reset_singleton()

    @patch("app.core.version_manager.VersionManager._get_vanilla_url")
    @patch("app.core.version_manager.os.path.exists", return_value=False)
    def test_get_download_url_vanilla(self, mock_exists, mock_url):
        mock_url.return_value = "https://example.com/server.jar"
        vm = VersionManager()
        url = vm.get_download_url("Vanilla", "1.20.1")
        assert url == "https://example.com/server.jar"
        mock_url.assert_called_once_with("1.20.1")

    @patch("app.core.version_manager.VersionManager._get_fabric_installer_url")
    @patch("app.core.version_manager.os.path.exists", return_value=False)
    def test_get_download_url_fabric(self, mock_exists, mock_url):
        mock_url.return_value = "https://maven.fabricmc.net/fabric.jar"
        vm = VersionManager()
        url = vm.get_download_url("Fabric", "1.20.1")
        assert url == "https://maven.fabricmc.net/fabric.jar"

    @patch("app.core.version_manager.VersionManager._get_forge_installer_url")
    @patch("app.core.version_manager.os.path.exists", return_value=False)
    def test_get_download_url_forge(self, mock_exists, mock_url):
        mock_url.return_value = "https://maven.minecraftforge.net/forge.jar"
        vm = VersionManager()
        url = vm.get_download_url("Forge", "1.20.1")
        assert url == "https://maven.minecraftforge.net/forge.jar"

    @patch("app.core.version_manager.VersionManager._get_paper_url")
    @patch("app.core.version_manager.os.path.exists", return_value=False)
    def test_get_download_url_paper(self, mock_exists, mock_url):
        mock_url.return_value = "https://api.papermc.io/paper.jar"
        vm = VersionManager()
        url = vm.get_download_url("Paper", "1.20.1")
        assert url == "https://api.papermc.io/paper.jar"

    @patch("app.core.version_manager.VersionManager._get_purpur_url")
    @patch("app.core.version_manager.os.path.exists", return_value=False)
    def test_get_download_url_purpur(self, mock_exists, mock_url):
        mock_url.return_value = "https://api.purpurmc.org/purpur.jar"
        vm = VersionManager()
        url = vm.get_download_url("Purpur", "1.20.1")
        assert url == "https://api.purpurmc.org/purpur.jar"

    @patch("app.core.version_manager.os.path.exists", return_value=False)
    def test_get_download_url_unknown_type(self, mock_exists):
        vm = VersionManager()
        url = vm.get_download_url("Unknown", "1.20.1")
        assert url is None


class TestVersionManagerVanillaURL:
    def setup_method(self):
        _reset_singleton()

    @patch("app.core.version_manager.requests.get")
    @patch("app.core.version_manager.os.path.exists", return_value=False)
    def test_get_vanilla_url_success(self, mock_exists, mock_get):
        mock_manifest_resp = MagicMock()
        mock_manifest_resp.json.return_value = {
            "versions": [
                {"id": "1.20.1", "url": "https://example.com/1.20.1.json"},
            ]
        }
        mock_version_resp = MagicMock()
        mock_version_resp.json.return_value = {
            "downloads": {
                "server": {"url": "https://example.com/server.jar"}
            }
        }
        mock_get.side_effect = [mock_manifest_resp, mock_version_resp]
        vm = VersionManager()
        url = vm._get_vanilla_url("1.20.1")
        assert url == "https://example.com/server.jar"
        assert mock_get.call_count == 2

    @patch("app.core.version_manager.requests.get")
    @patch("app.core.version_manager.os.path.exists", return_value=False)
    def test_get_vanilla_url_not_found(self, mock_exists, mock_get):
        mock_manifest_resp = MagicMock()
        mock_manifest_resp.json.return_value = {
            "versions": [{"id": "1.19", "url": "..."}]
        }
        mock_get.return_value = mock_manifest_resp
        vm = VersionManager()
        url = vm._get_vanilla_url("1.20.1")
        assert url is None

    @patch("app.core.version_manager.requests.get", side_effect=Exception("Network error"))
    @patch("app.core.version_manager.os.path.exists", return_value=False)
    def test_get_vanilla_url_network_error_returns_none(self, mock_exists, mock_get):
        vm = VersionManager()
        url = vm._get_vanilla_url("1.20.1")
        assert url is None


class TestVersionManagerFabricURL:
    def setup_method(self):
        _reset_singleton()

    @patch("app.core.version_manager.requests.get")
    @patch("app.core.version_manager.os.path.exists", return_value=False)
    def test_get_fabric_url_success(self, mock_exists, mock_get):
        mock_resp = MagicMock()
        mock_resp.json.return_value = [{"version": "1.0.1"}, {"version": "1.0.0"}]
        mock_get.return_value = mock_resp
        vm = VersionManager()
        url = vm._get_fabric_installer_url("1.20.1")
        assert url == "https://maven.fabricmc.net/net/fabricmc/fabric-installer/1.0.1/fabric-installer-1.0.1.jar"

    @patch("app.core.version_manager.requests.get", side_effect=Exception("Network error"))
    @patch("app.core.version_manager.os.path.exists", return_value=False)
    def test_get_fabric_url_network_error(self, mock_exists, mock_get):
        vm = VersionManager()
        url = vm._get_fabric_installer_url("1.20.1")
        assert url is None


class TestVersionManagerForgeURL:
    def setup_method(self):
        _reset_singleton()

    @patch("app.core.version_manager.requests.get")
    @patch("app.core.version_manager.os.path.exists", return_value=False)
    def test_get_forge_url_recommended(self, mock_exists, mock_get):
        mock_resp = MagicMock()
        mock_resp.json.return_value = {
            "promos": {
                "1.20.1-recommended": "47.1.0",
                "1.20.1-latest": "47.2.0",
            }
        }
        mock_get.return_value = mock_resp
        vm = VersionManager()
        url = vm._get_forge_installer_url("1.20.1")
        assert "47.1.0" in url  # recommended preferred over latest

    @patch("app.core.version_manager.requests.get")
    @patch("app.core.version_manager.os.path.exists", return_value=False)
    def test_get_forge_url_fallback_to_latest(self, mock_exists, mock_get):
        mock_resp = MagicMock()
        mock_resp.json.return_value = {
            "promos": {
                "1.20.1-latest": "47.2.0",
            }
        }
        mock_get.return_value = mock_resp
        vm = VersionManager()
        url = vm._get_forge_installer_url("1.20.1")
        assert "47.2.0" in url

    @patch("app.core.version_manager.requests.get", side_effect=Exception("Network error"))
    @patch("app.core.version_manager.os.path.exists", return_value=False)
    def test_get_forge_url_network_error(self, mock_exists, mock_get):
        vm = VersionManager()
        url = vm._get_forge_installer_url("1.20.1")
        assert url is None


class TestVersionManagerPaperURL:
    def setup_method(self):
        _reset_singleton()

    @patch("app.core.version_manager.requests.get")
    @patch("app.core.version_manager.os.path.exists", return_value=False)
    def test_get_paper_url_success(self, mock_exists, mock_get):
        mock_resp = MagicMock()
        mock_resp.json.return_value = {
            "downloads": {
                "server:default": {
                    "name": "paper-1.20.1-196.jar",
                    "url": "https://fill-data.papermc.io/v1/objects/abc123/paper-1.20.1-196.jar",
                }
            }
        }
        mock_get.return_value = mock_resp
        vm = VersionManager()
        url = vm._get_paper_url("1.20.1")
        assert url == "https://fill-data.papermc.io/v1/objects/abc123/paper-1.20.1-196.jar"

    @patch("app.core.version_manager.requests.get", side_effect=Exception("Network error"))
    @patch("app.core.version_manager.os.path.exists", return_value=False)
    def test_get_paper_url_network_error(self, mock_exists, mock_get):
        vm = VersionManager()
        url = vm._get_paper_url("1.20.1")
        assert url is None

    @patch("app.core.version_manager.requests.get")
    @patch("app.core.version_manager.os.path.exists", return_value=False)
    def test_get_paper_url_no_builds(self, mock_exists, mock_get):
        mock_resp = MagicMock()
        mock_resp.json.return_value = {"builds": []}
        mock_get.return_value = mock_resp
        vm = VersionManager()
        url = vm._get_paper_url("1.20.1")
        assert url is None


class TestVersionManagerPurpurURL:
    def setup_method(self):
        _reset_singleton()

    @patch("app.core.version_manager.requests.get")
    @patch("app.core.version_manager.os.path.exists", return_value=False)
    def test_get_purpur_url_success(self, mock_exists, mock_get):
        mock_resp = MagicMock()
        mock_resp.json.return_value = {
            "builds": {"latest": "42"},
        }
        mock_get.return_value = mock_resp
        vm = VersionManager()
        url = vm._get_purpur_url("1.20.1")
        assert url.endswith("/42/download")

    @patch("app.core.version_manager.requests.get", side_effect=Exception("Network error"))
    @patch("app.core.version_manager.os.path.exists", return_value=False)
    def test_get_purpur_url_network_error(self, mock_exists, mock_get):
        vm = VersionManager()
        url = vm._get_purpur_url("1.20.1")
        assert url is None


class TestVersionManagerRefresh:
    def setup_method(self):
        _reset_singleton()

    @patch("app.core.version_manager.VersionManager._fetch_all_versions")
    @patch("app.core.version_manager.VersionManager._save_cache")
    @patch("app.core.version_manager.os.path.exists", return_value=False)
    def test_refresh_versions_updates_cache(self, mock_exists, mock_save, mock_fetch):
        mock_fetch.return_value = {
            "Vanilla": ["1.21", "1.20.4"],
        }
        vm = VersionManager()
        vm.refresh_versions()
        assert "1.21" in vm.cache["Vanilla"]

    @patch("app.core.version_manager.os.path.exists", return_value=False)
    def test_check_and_refresh_starts_thread_when_stale(self, mock_exists):
        vm = VersionManager()
        vm.cache["last_updated"] = None
        assert vm.refresh_thread is None or not vm.refresh_thread.is_alive()
        vm._check_and_refresh()
        assert vm.refresh_thread is not None
        assert vm.refresh_thread.is_alive()
        vm.refresh_thread.join(timeout=5)

    @patch("app.core.version_manager.os.path.exists", return_value=False)
    def test_check_and_refresh_does_not_start_if_alive(self, mock_exists):
        vm = VersionManager()
        vm.refresh_thread = threading.Thread(target=lambda: None)
        vm.refresh_thread.start()
        vm._check_and_refresh()
        assert vm.refresh_thread.is_alive()



class TestVersionManagerCallbacks:
    def setup_method(self):
        _reset_singleton()

    @patch("app.core.version_manager.os.path.exists", return_value=False)
    def test_add_callback(self, mock_exists):
        vm = VersionManager()

        def cb():
            pass
        vm.add_callback(cb)
        assert cb in vm.callbacks

    @patch("app.core.version_manager.os.path.exists", return_value=False)
    def test_add_callback_duplicate_not_added(self, mock_exists):
        vm = VersionManager()

        def cb():
            pass
        vm.add_callback(cb)
        vm.add_callback(cb)
        assert vm.callbacks.count(cb) == 1

    @patch("app.core.version_manager.os.path.exists", return_value=False)
    def test_notify_callbacks_calls_all(self, mock_exists):
        vm = VersionManager()
        results = []

        def cb1():
            results.append(1)

        def cb2():
            results.append(2)
        vm.add_callback(cb1)
        vm.add_callback(cb2)
        vm._notify_callbacks()
        assert results == [1, 2]

    @patch("app.core.version_manager.os.path.exists", return_value=False)
    def test_notify_callbacks_handles_exception(self, mock_exists):
        vm = VersionManager()
        results = []

        def cb_bad():
            raise ValueError("Boom")

        def cb_good():
            results.append("ok")
        vm.add_callback(cb_bad)
        vm.add_callback(cb_good)
        vm._notify_callbacks()
        assert results == ["ok"]


class TestVersionManagerFetchAll:
    def setup_method(self):
        _reset_singleton()

    @patch("app.core.version_manager.os.path.exists", return_value=False)
    @patch("app.core.version_manager.VersionManager._fetch_vanilla", return_value=["1.21"])
    @patch("app.core.version_manager.VersionManager._fetch_fabric", return_value=["1.21"])
    @patch("app.core.version_manager.VersionManager._fetch_forge", return_value=["1.21.1"])
    @patch("app.core.version_manager.VersionManager._fetch_paper", return_value=["1.21"])
    @patch("app.core.version_manager.VersionManager._fetch_purpur", return_value=["1.21"])
    def test_fetch_all_versions(self, mock_purpur, mock_paper, mock_forge, mock_fabric, mock_vanilla, mock_exists):
        vm = VersionManager()
        result = vm._fetch_all_versions(timeout=10)
        assert result["Vanilla"] == ["1.21"]
        assert result["Fabric"] == ["1.21"]
        assert result["Forge"] == ["1.21.1"]
        assert result["Paper"] == ["1.21"]
        assert result["Purpur"] == ["1.21"]

    @patch("app.core.version_manager.os.path.exists", return_value=False)
    @patch("app.core.version_manager.VersionManager._fetch_vanilla", side_effect=Exception("Fail"))
    @patch("app.core.version_manager.VersionManager._fetch_fabric", return_value=["1.21"])
    @patch("app.core.version_manager.VersionManager._fetch_forge", side_effect=Exception("Fail"))
    @patch("app.core.version_manager.VersionManager._fetch_paper", return_value=["1.21"])
    @patch("app.core.version_manager.VersionManager._fetch_purpur", return_value=["1.21"])
    def test_fetch_all_versions_partial_failure(self, mock_purpur, mock_paper, mock_forge, mock_fabric, mock_vanilla, mock_exists):
        vm = VersionManager()
        result = vm._fetch_all_versions(timeout=10)
        assert "Vanilla" not in result
        assert result["Fabric"] == ["1.21"]
        assert "Forge" not in result
        assert result["Paper"] == ["1.21"]
        assert result["Purpur"] == ["1.21"]


class TestVersionManagerSaveCache:
    def setup_method(self):
        _reset_singleton()

    @patch("app.core.version_manager.os.path.exists", return_value=False)
    @patch("app.core.version_manager.VersionManager._save_cache")
    def test_save_cache_called_on_refresh(self, mock_save, mock_exists):
        vm = VersionManager()
        with patch.object(vm, "_fetch_all_versions") as mock_fetch:
            mock_fetch.return_value = {"Vanilla": ["1.21"]}
            vm.refresh_versions()
            mock_save.assert_called_once()

    @patch("app.core.version_manager.os.path.exists", return_value=False)
    def test_save_cache_writes_json(self, mock_exists):
        vm = VersionManager()
        with patch("builtins.open", mock_open()) as mock_file:
            with patch("app.core.version_manager.VERSIONS_CACHE_FILE") as mock_path:
                mock_path.parent.mkdir = MagicMock()
                vm._save_cache()
                mock_file.assert_called_once()
                handle = mock_file()
                written = "".join(call[0][0] for call in handle.write.call_args_list)
                assert "Vanilla" in written
