"""Unit tests for ModrinthClient (app/services/modrinth.py)."""

import sys
import os
import json
from pathlib import Path
from unittest.mock import patch, MagicMock

sys.path.append(str(Path(__file__).resolve().parent.parent))

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
        # Mock the actual download to avoid network calls
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.headers = {"content-length": "0"}
        mock_resp.iter_content.return_value = []
        mock_resp.raise_for_status = MagicMock()

        with patch.object(client.session, "get", return_value=mock_resp):
            with patch("os.makedirs"):
                with patch("builtins.open", MagicMock()):
                    # SHA1 of empty content won't match "def", so it'll fail validation
                    result = client.download_mod("sodium", "test_server", "1.20.1", "fabric")
                    # Either returns None (sha mismatch) or path — we just verify it tried the primary
                    client.session.get.assert_called_once()
                    call_url = client.session.get.call_args[0][0]
                    assert "primary.jar" in call_url
