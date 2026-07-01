"""Unit tests for ModrinthClient (app/services/modrinth.py)."""

import json
from unittest.mock import patch, MagicMock, mock_open

from app.services.modrinth import ModrinthClient, ModrinthException


class TestModrinthSearch:
    def _make_client(self):
        return ModrinthClient()

    @patch("app.services.modrinth.ModrinthClient._request")
    def test_search_basic(self, mock_req):
        mock_req.return_value = {
            "hits": [{"title": "Sodium", "project_id": "AANobbMI"}],
            "total_hits": 1,
            "offset": 0,
            "limit": 20,
        }
        client = self._make_client()
        result = client.search("Sodium")
        assert result["total_hits"] == 1
        assert result["hits"][0]["title"] == "Sodium"
        mock_req.assert_called_once()

    @patch("app.services.modrinth.ModrinthClient._request")
    def test_search_with_filters(self, mock_req):
        mock_req.return_value = {"hits": [], "total_hits": 0, "offset": 0, "limit": 20}
        client = self._make_client()
        client.search("test", mc_version="1.20.1", loader="fabric", project_type="mod")
        _, kwargs = mock_req.call_args
        params = kwargs.get("params") or mock_req.call_args[0][2]
        assert "1.20.1" in str(params) or "facets" in str(mock_req.call_args)


class TestModrinthVersions:
    @patch("app.services.modrinth.ModrinthClient._request")
    def test_get_versions_basic(self, mock_req):
        mock_req.return_value = [
            {"id": "v1", "version_number": "1.0.0", "files": [{"url": "https://cdn.modrinth.com/test.jar", "primary": True, "filename": "test.jar"}]},
        ]
        client = ModrinthClient()
        versions = client.get_versions("sodium")
        assert len(versions) == 1
        assert versions[0]["version_number"] == "1.0.0"

    @patch("app.services.modrinth.ModrinthClient._request")
    def test_get_versions_with_filters(self, mock_req):
        mock_req.return_value = []
        client = ModrinthClient()
        client.get_versions("sodium", mc_version="1.20.1", loader="fabric")
        call_args = mock_req.call_args
        params = call_args[1].get("params") or call_args[0][2]
        assert "1.20.1" in json.dumps(params)
        assert "fabric" in json.dumps(params)


class TestModrinthProject:
    @patch("app.services.modrinth.ModrinthClient._request")
    def test_get_project(self, mock_req):
        mock_req.return_value = {"id": "AANobbMI", "title": "Sodium", "slug": "sodium"}
        client = ModrinthClient()
        project = client.get_project("sodium")
        assert project["title"] == "Sodium"


class TestModrinthErrorHandling:
    @patch("app.services.modrinth.ModrinthClient._request")
    def test_network_error_raises(self, mock_req):
        mock_req.side_effect = ModrinthException("Network error: Connection refused")
        client = ModrinthClient()
        try:
            client.search("test")
            assert False, "Should have raised"
        except ModrinthException:
            pass

    def test_rate_limit_handling(self):
        client = ModrinthClient()
        mock_response_429 = MagicMock()
        mock_response_429.status_code = 429
        mock_response_429.headers = {"X-Ratelimit-Reset": "1"}

        mock_response_200 = MagicMock()
        mock_response_200.status_code = 200
        mock_response_200.json.return_value = {"hits": [], "total_hits": 0}

        with patch.object(client.session, "request", side_effect=[mock_response_429, mock_response_200]):
            result = client._request("GET", "/search", params={"query": "test"})
            assert result["total_hits"] == 0

    def test_api_error_raises(self):
        client = ModrinthClient()
        mock_response = MagicMock()
        mock_response.status_code = 404
        mock_response.text = "Not found"

        with patch.object(client.session, "request", return_value=mock_response):
            try:
                client._request("GET", "/project/nonexistent")
                assert False, "Should have raised"
            except ModrinthException as e:
                assert "404" in str(e)


class TestModrinthDownload:
    @patch("app.services.modrinth.ModrinthClient.get_versions")
    def test_download_no_versions_returns_none(self, mock_versions):
        mock_versions.return_value = []
        client = ModrinthClient()
        result = client.download_mod("sodium", "test_server", "1.20.1", "fabric")
        assert result is None

    @patch("app.services.modrinth.ModrinthClient.get_versions")
    def test_download_picks_primary_file(self, mock_versions):
        mock_versions.return_value = [
            {
                "id": "v1",
                "files": [
                    {"url": "https://cdn.modrinth.com/secondary.jar", "primary": False, "filename": "secondary.jar", "hashes": {"sha1": "abc"}},
                    {"url": "https://cdn.modrinth.com/primary.jar", "primary": True, "filename": "primary.jar", "hashes": {"sha1": "def"}},
                ],
            }
        ]
        client = ModrinthClient()
        # Mock download_with_verification to avoid network calls
        with patch("app.services.modrinth.download_with_verification", return_value=(True, "primary.jar", None)) as mock_dl:
            with patch("os.makedirs"):
                with patch("builtins.open", MagicMock()):
                    client.download_mod("sodium", "test_server", "1.20.1", "fabric")
                    mock_dl.assert_called_once()
                    call_url = mock_dl.call_args[0][0]
                    assert "primary.jar" in call_url


class TestModrinthDownloadVersion:
    @patch("app.services.modrinth.ModrinthClient._resolve_version_file")
    def test_download_version_no_file_returns_none(self, mock_resolve):
        mock_resolve.return_value = None
        client = ModrinthClient()
        result = client.download_version({"id": "v1", "version_number": "1.0.0"}, "test_server", "fabric")
        assert result is None

    @patch("app.services.modrinth.ModrinthClient._resolve_version_file")
    def test_download_version_resolves_and_downloads(self, mock_resolve):
        mock_resolve.return_value = {
            "url": "https://cdn.modrinth.com/mod.jar",
            "filename": "mod.jar",
            "hashes": {"sha1": "abc123"},
        }
        with patch("app.services.modrinth.ModrinthClient._download_file") as mock_dl:
            mock_dl.return_value = "/servers/test_server/mods/mod.jar"
            client = ModrinthClient()
            result = client.download_version({"id": "v1"}, "test_server", "fabric")
            assert result == "/servers/test_server/mods/mod.jar"
            mock_dl.assert_called_once_with(
                "https://cdn.modrinth.com/mod.jar", "mod.jar",
                "abc123", mock_dl.call_args[0][3], None,
            )

    @patch("app.services.modrinth.ModrinthClient._resolve_version_file")
    def test_download_version_plugins_dir(self, mock_resolve):
        mock_resolve.return_value = {
            "url": "https://cdn.modrinth.com/plugin.jar",
            "filename": "plugin.jar",
            "hashes": {"sha1": "def456"},
        }
        with patch("app.services.modrinth.ModrinthClient._download_file") as mock_dl:
            mock_dl.return_value = "/servers/test_server/plugins/plugin.jar"
            client = ModrinthClient()
            result = client.download_version({"id": "v1"}, "test_server", "paper")
            assert result == "/servers/test_server/plugins/plugin.jar"


class TestModrinthDownloadVersionTo:
    @patch("app.services.modrinth.ModrinthClient._resolve_version_file")
    def test_no_file_returns_none(self, mock_resolve):
        mock_resolve.return_value = None
        client = ModrinthClient()
        result = client.download_version_to({"id": "v1"}, "/tmp/somewhere")
        assert result is None

    @patch("app.services.modrinth.os.makedirs")
    @patch("app.services.modrinth.ModrinthClient._resolve_version_file")
    def test_downloads_to_given_dir(self, mock_resolve, mock_makedirs):
        mock_resolve.return_value = {
            "url": "https://cdn.modrinth.com/pack.mrpack",
            "filename": "pack.mrpack",
            "hashes": {"sha1": "abc123"},
        }
        with patch("app.services.modrinth.ModrinthClient._download_file") as mock_dl:
            mock_dl.return_value = "/tmp/somewhere/pack.mrpack"
            client = ModrinthClient()
            result = client.download_version_to({"id": "v1"}, "/tmp/somewhere")
            assert result == "/tmp/somewhere/pack.mrpack"
            mock_dl.assert_called_once_with(
                "https://cdn.modrinth.com/pack.mrpack", "pack.mrpack",
                "abc123", "/tmp/somewhere", None,
            )
            mock_makedirs.assert_called_once_with("/tmp/somewhere", exist_ok=True)


class TestModrinthApplyUpdate:
    @patch("app.services.modrinth.os.remove")
    @patch("app.services.modrinth.os.path.exists", return_value=True)
    @patch("app.services.modrinth.ModrinthClient._download_file")
    def test_apply_update_downloads_and_removes_old(self, mock_dl, mock_exists, mock_remove):
        mock_dl.return_value = "/servers/test_server/mods/new-mod-2.0.jar"
        client = ModrinthClient()
        update = {
            "filename": "old-mod-1.0.jar",
            "update_url": "https://cdn.modrinth.com/new-mod-2.0.jar",
            "update_filename": "new-mod-2.0.jar",
            "update_sha1": "def456",
        }
        result = client.apply_update(update, "test_server", "fabric")
        assert result is True
        mock_remove.assert_called_once()
        assert "old-mod-1.0.jar" in mock_remove.call_args[0][0]

    @patch("app.services.modrinth.ModrinthClient._download_file")
    def test_apply_update_download_fails_returns_false(self, mock_dl):
        mock_dl.return_value = None
        client = ModrinthClient()
        update = {
            "filename": "old-mod-1.0.jar",
            "update_url": "https://cdn.modrinth.com/new-mod-2.0.jar",
            "update_filename": "new-mod-2.0.jar",
            "update_sha1": "def456",
        }
        result = client.apply_update(update, "test_server", "fabric")
        assert result is False

    @patch("app.services.modrinth.os.path.exists", return_value=True)
    @patch("app.services.modrinth.ModrinthClient._download_file")
    def test_apply_update_plugins_dir_for_paper(self, mock_dl, mock_exists):
        mock_dl.return_value = "/servers/test_server/plugins/new-plugin-2.0.jar"
        client = ModrinthClient()
        update = {
            "filename": "old-plugin-1.0.jar",
            "update_url": "https://cdn.modrinth.com/new-plugin-2.0.jar",
            "update_filename": "new-plugin-2.0.jar",
            "update_sha1": "def456",
        }
        with patch("app.services.modrinth.os.remove") as mock_remove:
            client.apply_update(update, "test_server", "paper")
            assert "plugins" in mock_remove.call_args[0][0]


class TestModrinthCheckUpdates:
    @patch("app.services.modrinth.os.path.isdir", return_value=False)
    def test_no_mods_dir_returns_empty(self, mock_isdir):
        client = ModrinthClient()
        result = client.check_updates("test_server", "1.20.1", "fabric")
        assert result == []

    @patch("app.services.modrinth.os.path.isdir", return_value=True)
    @patch("app.services.modrinth.os.listdir", return_value=[])
    def test_empty_mods_dir_returns_empty(self, mock_listdir, mock_isdir):
        client = ModrinthClient()
        result = client.check_updates("test_server", "1.20.1", "fabric")
        assert result == []

    @patch("app.services.modrinth.os.path.isdir", return_value=True)
    @patch("app.services.modrinth.os.listdir", return_value=["readme.txt", "config.yml"])
    @patch("app.services.modrinth.os.path.isfile", return_value=True)
    def test_no_jar_files_returns_empty(self, mock_isfile, mock_listdir, mock_isdir):
        client = ModrinthClient()
        result = client.check_updates("test_server", "1.20.1", "fabric")
        assert result == []

    @patch("app.services.modrinth.os.path.isdir", return_value=True)
    @patch("app.services.modrinth.os.listdir", return_value=["test-mod.jar"])
    @patch("app.services.modrinth.os.path.isfile", return_value=True)
    @patch("app.services.modrinth.hashlib.sha1")
    def test_check_updates_with_updates(self, mock_sha1, mock_isfile, mock_listdir, mock_isdir):
        mock_hash = MagicMock()
        mock_hash.hexdigest.return_value = "aaabbb"
        mock_hash.update = MagicMock()
        mock_sha1.return_value = mock_hash

        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "aaabbb": {
                "files": [{"primary": True, "url": "https://cdn.modrinth.com/new.jar", "filename": "new.jar", "hashes": {"sha1": "newhash"}}],
            }
        }

        client = ModrinthClient()
        with patch.object(client, "session") as mock_session:
            mock_session.post.return_value = mock_resp
            with patch("builtins.open", mock_open(read_data=b"jarcontent")):
                results = client.check_updates("test_server", "1.20.1", "fabric")

        assert len(results) > 0
        assert results[0]["installed_hash"] == "aaabbb"

    @patch("app.services.modrinth.os.path.isdir", return_value=True)
    @patch("app.services.modrinth.os.listdir", return_value=["test-mod.jar"])
    @patch("app.services.modrinth.os.path.isfile", return_value=True)
    @patch("app.services.modrinth.hashlib.sha1")
    def test_check_updates_api_failure_returns_empty(self, mock_sha1, mock_isfile, mock_listdir, mock_isdir):
        mock_hash = MagicMock()
        mock_hash.hexdigest.return_value = "aaabbb"
        mock_hash.update = MagicMock()
        mock_sha1.return_value = mock_hash

        mock_resp = MagicMock()
        mock_resp.status_code = 500

        client = ModrinthClient()
        with patch.object(client, "session") as mock_session:
            mock_session.post.return_value = mock_resp
            with patch("builtins.open", mock_open(read_data=b"jarcontent")):
                results = client.check_updates("test_server", "1.20.1", "fabric")

        assert results == []
