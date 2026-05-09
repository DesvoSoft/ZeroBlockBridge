import pytest
from unittest.mock import MagicMock, patch
from app.core import ZBBManager
from app.server_events import EventBus, ServerEvent

@pytest.fixture
def event_bus():
    return EventBus()

@pytest.fixture
def manager(event_bus):
    with patch("app.core.PlayitManager"):
        # PlayitManager is mocked to avoid side effects
        return ZBBManager(event_bus)

@patch("app.core.load_config", return_value={})
@patch("app.core.ServerRunner")
@patch("app.core.ZBBManager._setup_monitors")
def test_start_server_success(mock_setup_monitors, mock_runner_class, mock_config, manager):
    manager.select_server("test_server")
    
    mock_runner = MagicMock()
    mock_runner.running = False
    mock_runner_class.return_value = mock_runner
    
    # Initial state
    assert not manager.is_running()
    
    # Start server
    assert manager.start_server() is True
    mock_runner.start.assert_called_once()
    mock_setup_monitors.assert_called_once()

@patch("app.core.load_config", return_value={})
def test_start_no_server_selected(mock_config, manager):
    assert manager.start_server() is False

def test_stop_server(manager):
    manager.server_runner = MagicMock()
    manager.stop_server()
    manager.server_runner.stop.assert_called_once()

def test_tunnel_status_event(manager, event_bus):
    received = []
    event_bus.subscribe(ServerEvent.TUNNEL_STATUS, lambda data: received.append(data))
    
    with patch("app.core.load_config", return_value={"playit_dns": "custom.dns.com"}):
        manager._on_playit_status("Online", "127.0.0.1")
        
    assert len(received) == 1
    assert received[0]["status"] == "Online"
    assert received[0]["ip"] == "custom.dns.com"
