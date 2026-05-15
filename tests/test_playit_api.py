import pytest
from unittest.mock import MagicMock, patch
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
    with patch.object(client.session, 'post') as mock_post:
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"status": "success", "data": {"agent_id": "123"}}
        mock_post.return_value = mock_response
        
        result = client._request("agents/rundata")
        assert result["status"] == "success"
        assert result["data"]["agent_id"] == "123"

def test_request_http_error(client):
    with patch.object(client.session, 'post') as mock_post:
        mock_response = MagicMock()
        mock_response.status_code = 400
        mock_response.json.return_value = {"error": "Invalid request"}
        mock_post.return_value = mock_response
        
        with pytest.raises(PlayitApiException) as exc:
            client._request("agents/rundata")
        assert "Invalid request" in str(exc.value)

def test_get_agent_id_caching(client):
    with patch.object(client.session, 'post') as mock_post:
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"status": "success", "data": {"agent_id": "abc"}}
        mock_post.return_value = mock_response
        
        assert client.get_agent_id() == "abc"
        assert client.get_agent_id() == "abc"
        assert mock_post.call_count == 1  # Cached

@patch("time.sleep", return_value=None)
def test_create_tunnel_polling(mock_sleep, client):
    # Mock get_agent_id
    client._agent_id = "agent_1"
    
    with patch.object(client, '_request') as mock_req:
        # First request: create tunnel
        # Subsequent requests: list tunnels
        mock_req.side_effect = [
            # Create response
            {"status": "success", "data": {"id": "tunnel_1"}},
            # List response 1: pending
            {"status": "success", "data": {"tunnels": [{"id": "tunnel_1", "alloc": {"status": "pending"}}]}},
            # List response 2: allocated
            {"status": "success", "data": {"tunnels": [{"id": "tunnel_1", "alloc": {"status": "allocated", "data": {"assigned_domain": "test.playit.gg"}}}]}}
        ]
        
        tunnel = client.create_tunnel()
        assert tunnel["id"] == "tunnel_1"
        assert tunnel["alloc"]["data"]["assigned_domain"] == "test.playit.gg"
        assert mock_req.call_count == 3
