import pytest
import sys
import os
from pathlib import Path
from unittest.mock import MagicMock, patch

# Add project root to path
sys.path.append(str(Path(__file__).resolve().parent.parent))

from app.version_manager import VersionManager

@pytest.fixture
def vm():
    # Reset singleton for testing
    VersionManager._instance = None
    manager = VersionManager()
    # Mock cache to avoid loading from disk
    manager.cache = {
        "last_updated": "2025-01-01T12:00:00",
        "Vanilla": ["1.21.1", "1.20.1"],
        "Fabric": ["0.14.22"],
        "Forge": ["1.20.1"]
    }
    return manager

def test_singleton(vm):
    vm2 = VersionManager()
    assert vm is vm2

def test_get_versions_vanilla(vm):
    versions = vm.get_versions("Vanilla")
    assert isinstance(versions, list)
    assert "1.21.1" in versions

def test_get_versions_fabric(vm):
    versions = vm.get_versions("Fabric")
    assert isinstance(versions, list)
    assert len(versions) > 0

@patch("requests.get")
def test_refresh_versions(mock_get, vm):
    # Mock responses
    mock_vanilla = MagicMock()
    mock_vanilla.status_code = 200
    mock_vanilla.json.return_value = {
        "versions": [{"id": "1.99.9", "type": "release", "url": "http://test"}]
    }
    
    mock_fabric = MagicMock()
    mock_fabric.status_code = 200
    mock_fabric.json.return_value = [{"version": "0.99.9", "stable": True}]
    
    mock_forge = MagicMock()
    mock_forge.status_code = 200
    mock_forge.json.return_value = {"promos": {"1.99.9-recommended": "1.0.0"}}

    mock_paper = MagicMock()
    mock_paper.status_code = 200
    mock_paper.json.return_value = {"versions": ["1.99.9"]}
    
    mock_get.side_effect = [mock_vanilla, mock_fabric, mock_forge, mock_paper]
    
    vm.refresh_versions()
    
    assert "1.99.9" in vm.cache["Vanilla"]
    assert "0.99.9" in vm.cache["Fabric"]
    assert "1.99.9" in vm.cache["Forge"]
    assert "1.99.9" in vm.cache["Paper"]

@patch("requests.get")
def test_get_download_url_vanilla(mock_get, vm):
    # Mock manifest fetch
    mock_manifest = MagicMock()
    mock_manifest.json.return_value = {
        "versions": [{"id": "1.21.1", "url": "http://version_json"}]
    }
    
    # Mock version json fetch
    mock_version = MagicMock()
    mock_version.json.return_value = {
        "downloads": {"server": {"url": "http://server.jar"}}
    }
    
    mock_get.side_effect = [mock_manifest, mock_version]
    
    url = vm.get_download_url("Vanilla", "1.21.1")
    assert url == "http://server.jar"

def test_get_download_url_forge(vm):
    # Test URL construction logic (no network needed if we mock the promotions fetch inside, 
    # but the current implementation fetches inside. We should mock that.)
    
    with patch("requests.get") as mock_get:
        mock_resp = MagicMock()
        mock_resp.json.return_value = {
            "promos": {"1.20.1-recommended": "47.2.0"}
        }
        mock_get.return_value = mock_resp
        
        url = vm.get_download_url("Forge", "1.20.1")
        assert "47.2.0" in url
        assert "installer.jar" in url

@patch("requests.get")
def test_get_download_url_paper(mock_get, vm):
    mock_resp = MagicMock()
    mock_resp.json.return_value = {
        "project_id": "paper",
        "version": "1.20.1",
        "builds": [100, 101, 102]
    }
    mock_get.return_value = mock_resp
    
    url = vm.get_download_url("Paper", "1.20.1")
    assert "builds/102/downloads/paper-1.20.1-102.jar" in url
