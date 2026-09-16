import pytest
import platform
from unittest.mock import MagicMock, patch
from typing import Optional
from app.services.playit_api import PlayitApiClient, PlayitApiException

@pytest.fixture
def mock_toml(tmp_path):
    toml_path = tmp_path / "playit.toml"
    toml_path.write_text("secret_key='test-secret-key'")
    return toml_path

@pytest.fixture
def client(mock_toml):
    c = PlayitApiClient()
    c.toml_path = str(mock_toml)
    return c

def test_load_secret_key(client):
    assert client.load_secret_key() is True
    assert client._secret_key == "test-secret-key"
    assert client.session.headers["Authorization"] == "agent-key test-secret-key"

def test_request_success(client):
    with patch.object(client.session, 'request') as mock_request:
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"status": "success", "data": {"agent_id": "123"}}
        mock_request.return_value = mock_response
        
        result = client._request("agents/rundata")
        assert result["status"] == "success"
        assert result["data"]["agent_id"] == "123"

def test_request_http_error(client):
    with patch.object(client.session, 'request') as mock_request:
        mock_response = MagicMock()
        mock_response.status_code = 400
        mock_response.json.return_value = {"error": "Invalid request"}
        mock_response.text = '{"error": "Invalid request"}'
        mock_request.return_value = mock_response
        
        with pytest.raises(PlayitApiException) as exc:
            client._request("agents/rundata")
        assert "Invalid request" in str(exc.value)

def test_get_agent_id_caching(client):
    with patch.object(client.session, 'request') as mock_request:
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"status": "success", "data": {"agent_id": "abc"}}
        mock_request.return_value = mock_response
        
        assert client.get_agent_id() == "abc"
        assert client.get_agent_id() == "abc"
        assert mock_request.call_count == 1  # Cached

@pytest.mark.parametrize("system, machine, expected", [
    ("Windows", "AMD64", "windows-x86_64"),
    ("Windows", "x86_64", "windows-x86_64"),
    ("Windows", "arm64", "windows-x86_64"),
    ("Linux", "x86_64", "linux-amd64"),
    ("Linux", "AMD64", "linux-amd64"),
    ("Linux", "aarch64", "linux-aarch64"),
    ("Linux", "arm64", "linux-aarch64"),
    ("Darwin", "arm64", "macos-aarch64"),
    ("Darwin", "x86_64", "macos-amd64"),
])
def test_get_platform_variant(client, system, machine, expected):
    with patch.object(platform, 'system', return_value=system), \
         patch.object(platform, 'machine', return_value=machine):
        assert client._get_platform_variant() == expected

def test_link_account_payload(client):
    """Verify the flat payload: account_setup_code, platform, flat int versions."""
    from app.core.app_config import AppConfig
    os_name = platform.system().lower()
    if os_name == "darwin":
        os_name = "macos"

    with patch("requests.post") as mock_post:
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "data": {
                "agent_secret_key": "abc123def456",
                "agent_id": "agent_42"
            }
        }
        mock_post.return_value = mock_response

        result = client.link_account("test-code-123")

        assert result is True
        assert client._secret_key == "abc123def456"

        call_args = mock_post.call_args
        assert call_args[0][0] == AppConfig.PLAYIT_BRIDGE_URL
        sent_payload = call_args[1]["json"]

        assert sent_payload["account_setup_code"] == "test-code-123"
        assert sent_payload["platform"] == os_name
        assert sent_payload["agent_name"] == "ZeroBlockBridge"
        assert sent_payload["version_major"] == 0
        assert sent_payload["version_minor"] == 17
        assert sent_payload["version_patch"] == 1
        assert isinstance(sent_payload["version_major"], int)
        assert isinstance(sent_payload["version_minor"], int)
        assert isinstance(sent_payload["version_patch"], int)

def test_client_id_is_persistent(client):
    assert client.client_id is not None
    assert len(client.client_id) == 36  # UUID4 format


def _response(status, json_body=None, text=""):
    resp = MagicMock()
    resp.status_code = status
    resp.text = text
    if json_body is None:
        resp.json.side_effect = ValueError("no json")
    else:
        resp.json.return_value = json_body
    return resp


def test_http_error_carries_status_code(client):
    with patch.object(client.session, "request", return_value=_response(404, {"error": "missing"})):
        with pytest.raises(PlayitApiException) as exc:
            client._request("tunnels/list")
    assert exc.value.status_code == 404
    assert not exc.value.is_auth_error


def test_auth_failure_counted_even_without_json_body(client):
    # A 401 with an HTML/empty body used to fail JSON parsing first, so the
    # dead-secret counter never moved.
    with patch.object(client.session, "request", return_value=_response(401, None, "<html>Unauthorized</html>")):
        with pytest.raises(PlayitApiException) as exc:
            client._request("agents/rundata")
    assert exc.value.is_auth_error
    assert client.consecutive_auth_failures == 1


def test_success_resets_auth_failure_counter(client):
    client.consecutive_auth_failures = 2
    with patch.object(client.session, "request", return_value=_response(200, {"status": "success"})):
        client._request("agents/rundata")
    assert client.consecutive_auth_failures == 0


def test_invalid_json_on_success_raises(client):
    with patch.object(client.session, "request", return_value=_response(200, None, "not json")):
        with pytest.raises(PlayitApiException) as exc:
            client._request("agents/rundata")
    assert "Invalid JSON" in str(exc.value)


def test_delete_tunnel_treats_401_as_already_gone(client):
    # Decided by status code, not by "401" appearing in the message text.
    with patch.object(client, "_request", side_effect=PlayitApiException("unauthorized", 401)):
        assert client.delete_tunnel("t-1") is True


def test_delete_tunnel_reraises_other_errors_even_if_message_mentions_401(client):
    with patch.object(client, "_request", side_effect=PlayitApiException("quota 401 exceeded", 429)):
        with pytest.raises(PlayitApiException):
            client.delete_tunnel("t-1")


def test_delete_agent_returns_false_on_401(client):
    client._agent_id = "agent-1"
    with patch.object(client, "_request", side_effect=PlayitApiException("unauthorized", 401)):
        assert client.delete_agent() is False
