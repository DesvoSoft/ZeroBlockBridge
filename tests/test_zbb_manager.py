import pytest
from unittest.mock import MagicMock, patch
from app.core.core import ZBBManager
from app.core.server_events import EventBus, ServerEvent

@pytest.fixture
def event_bus():
    return EventBus()

@pytest.fixture
def manager(event_bus):
    with patch("app.core.playit_manager.PlayitManager"):
        return ZBBManager(event_bus)


def _mock_java(major, is_jdk=True, path=None):
    """Create a mock JavaInstallation."""
    j = MagicMock()
    j.major = major
    j.is_jdk = is_jdk
    j.path = path or f"/fake/java{major}"
    j.source = "PATH"
    return j


# --- Smart Java Flexibility Tests ---

@patch("app.core.core.load_config", return_value={})
@patch("app.core.core.ServerRunner")
@patch("app.core.core.ZBBManager._setup_monitors")
def test_start_exact_java_match(mock_monitors, mock_runner_class, mock_config, manager):
    """CASE 1 (ideal): Exact Java version match — should start normally."""
    manager.select_server("test_server")
    mock_runner = MagicMock(running=False)
    mock_runner_class.return_value = mock_runner

    with patch("app.services.scaffolder.pre_boot_scaffold"), \
         patch("app.core.core.analyze_jar_bytecode", return_value=17), \
         patch("app.core.core.JavaDetector") as mock_det_cls, \
         patch("app.core.core.get_required_java", return_value=17), \
         patch("app.core.core.ZBBManager.get_server_port", return_value=25565), \
         patch("os.path.exists", return_value=False):

        mock_det_cls.return_value.detect_all.return_value = [_mock_java(17)]
        assert manager.start_server() is True
        mock_runner.start.assert_called_once()


@patch("app.core.core.load_config", return_value={})
@patch("app.core.core.ServerRunner")
@patch("app.core.core.ZBBManager._setup_monitors")
def test_start_flexible_java_21_for_17(mock_monitors, mock_runner_class, mock_config, manager):
    """CASE 2: Java 21 available for MC requiring 17 — should ALLOW with warning."""
    manager.select_server("test_server")
    mock_runner = MagicMock(running=False)
    mock_runner_class.return_value = mock_runner

    notifications = []
    manager.events.subscribe(ServerEvent.NOTIFICATION, lambda d: notifications.append(d))

    with patch("app.services.scaffolder.pre_boot_scaffold"), \
         patch("app.core.core.analyze_jar_bytecode", return_value=17), \
         patch("app.core.core.JavaDetector") as mock_det_cls, \
         patch("app.core.core.get_required_java", return_value=17), \
         patch("app.core.core.ZBBManager.get_server_port", return_value=25565), \
         patch("os.path.exists", return_value=False):

        mock_det_cls.return_value.detect_all.return_value = [_mock_java(21)]
        assert manager.start_server() is True
        mock_runner.start.assert_called_once()
        # Should emit a warning notification
        assert any(n.get("type") == "warning" for n in notifications)


@patch("app.core.core.load_config", return_value={})
def test_start_blocks_experimental_java(mock_config, manager):
    """CASE 3: Java 26 detected — should BLOCK as experimental."""
    manager.select_server("test_server")

    notifications = []
    manager.events.subscribe(ServerEvent.NOTIFICATION, lambda d: notifications.append(d))

    with patch("app.services.scaffolder.pre_boot_scaffold"), \
         patch("app.core.core.analyze_jar_bytecode", return_value=17), \
         patch("app.core.core.JavaDetector") as mock_det_cls, \
         patch("app.core.core.get_required_java", return_value=17), \
         patch("app.core.core.ZBBManager.get_server_port", return_value=25565), \
         patch("app.services.java_installer.JdkManager.ensure_java",
               side_effect=Exception("DL failed")), \
         patch("os.path.exists", return_value=False):

        mock_det_cls.return_value.detect_all.return_value = [_mock_java(26)]
        assert manager.start_server() is False
        assert any(n.get("type") == "error" for n in notifications)


@patch("app.core.core.load_config", return_value={})
def test_start_blocks_java_too_low(mock_config, manager):
    """CASE 1 (block): Java 8 for MC 1.20 needing 17 — should BLOCK."""
    manager.select_server("test_server")

    notifications = []
    manager.events.subscribe(ServerEvent.NOTIFICATION, lambda d: notifications.append(d))

    with patch("app.services.scaffolder.pre_boot_scaffold"), \
         patch("app.core.core.analyze_jar_bytecode", return_value=17), \
         patch("app.core.core.JavaDetector") as mock_det_cls, \
         patch("app.core.core.get_required_java", return_value=17), \
         patch("app.core.core.ZBBManager.get_server_port", return_value=25565), \
         patch("app.services.java_installer.JdkManager.ensure_java",
               side_effect=Exception("DL failed")), \
         patch("os.path.exists", return_value=False):

        mock_det_cls.return_value.detect_all.return_value = [_mock_java(8)]
        assert manager.start_server() is False
        assert any(n.get("type") == "error" for n in notifications)


@patch("app.core.core.load_config", return_value={})
def test_start_no_java_found_auto_install_succeeds(mock_config, manager):
    """No Java installations — auto-install should succeed."""
    manager.select_server("test_server")

    with patch("app.services.scaffolder.pre_boot_scaffold"), \
         patch("app.core.core.analyze_jar_bytecode", return_value=17), \
         patch("app.core.core.JavaDetector") as mock_det_cls, \
         patch("app.core.core.get_required_java", return_value=17), \
         patch("app.core.core.ZBBManager.get_server_port", return_value=25565), \
         patch("app.core.core.ServerRunner") as mock_runner_class, \
         patch("app.core.core.ZBBManager._setup_monitors"), \
         patch("app.core.core.JdkManagerInstance.ensure_java",
               return_value="/fake/auto-jdk17/bin/java"), \
         patch("os.path.exists", return_value=False):

        mock_det_cls.return_value.detect_all.return_value = []
        mock_runner = MagicMock(running=False)
        mock_runner_class.return_value = mock_runner
        assert manager.start_server() is True
        mock_runner.start.assert_called_once()


@patch("app.core.core.load_config", return_value={})
def test_start_no_java_found_auto_install_fails(mock_config, manager):
    """No Java installations — auto-install fails, should BLOCK."""
    manager.select_server("test_server")

    with patch("app.services.scaffolder.pre_boot_scaffold"), \
         patch("app.core.core.analyze_jar_bytecode", return_value=17), \
         patch("app.core.core.JavaDetector") as mock_det_cls, \
         patch("app.core.core.get_required_java", return_value=17), \
         patch("app.core.core.ZBBManager.get_server_port", return_value=25565), \
         patch("app.services.java_installer.JdkManager.ensure_java",
               side_effect=Exception("Download failed")), \
         patch("os.path.exists", return_value=False):

        mock_det_cls.return_value.detect_all.return_value = []
        assert manager.start_server() is False


# --- Basic lifecycle tests ---

@patch("app.core.core.load_config", return_value={})
def test_start_no_server_selected(mock_config, manager):
    assert manager.start_server() is False

def test_stop_server(manager):
    manager.server_runner = MagicMock()
    manager.stop_server()
    manager.server_runner.stop.assert_called_once()

def test_tunnel_status_event(manager, event_bus):
    received = []
    event_bus.subscribe(ServerEvent.TUNNEL_STATUS, lambda data: received.append(data))

    with patch("app.core.core.load_config", return_value={"playit_dns": "custom.dns.com"}):
        manager._on_playit_status("Online", "127.0.0.1")

    assert len(received) == 1
    assert received[0]["status"] == "Online"
    assert received[0]["ip"] == "custom.dns.com"


# --- Maintenance API (F14 Settings dialog) ---

class TestMaintenanceApi:
    def test_purge_jdk_refused_while_running(self, manager):
        with patch.object(manager, "is_running", return_value=True), \
             patch("app.core.core.JdkManagerInstance") as jdk:
            assert manager.purge_jdk(17) is False
            jdk.purge_cache.assert_not_called()

    def test_purge_jdk_delegates_when_stopped(self, manager):
        with patch.object(manager, "is_running", return_value=False), \
             patch("app.core.core.JdkManagerInstance") as jdk:
            assert manager.purge_jdk(17) is True
            jdk.purge_cache.assert_called_once_with(17)

    def test_purge_unused_refused_while_running(self, manager):
        with patch.object(manager, "is_running", return_value=True), \
             patch("app.core.core.JdkManagerInstance") as jdk:
            assert manager.purge_unused_jdks() is False
            jdk.purge_unused_jdks.assert_not_called()

    def test_purge_unused_delegates_when_stopped(self, manager):
        with patch.object(manager, "is_running", return_value=False), \
             patch("app.core.core.JdkManagerInstance") as jdk:
            assert manager.purge_unused_jdks() is True
            jdk.purge_unused_jdks.assert_called_once_with()

    def test_list_managed_jdks_delegates(self, manager):
        with patch("app.core.core.JdkManagerInstance") as jdk:
            jdk.list_installed.return_value = [{"version": 21}]
            assert manager.list_managed_jdks() == [{"version": 21}]

    def test_purge_crash_reports_removes_dirs(self, manager, tmp_path):
        srv_a = tmp_path / "alpha" / "crash_reports"
        srv_a.mkdir(parents=True)
        (srv_a / "report.json").write_text("{}", encoding="utf-8")
        (tmp_path / "beta").mkdir()  # server without reports
        with patch("app.core.constants.SERVERS_DIR", tmp_path):
            removed = manager.purge_crash_reports()
        assert removed == 1
        assert not srv_a.exists()
        assert (tmp_path / "beta").exists()

    def test_purge_crash_reports_missing_servers_dir(self, manager, tmp_path):
        with patch("app.core.constants.SERVERS_DIR", tmp_path / "nope"):
            assert manager.purge_crash_reports() == 0
