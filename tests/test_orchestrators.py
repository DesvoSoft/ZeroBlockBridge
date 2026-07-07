import threading
import time
import pytest
from unittest.mock import MagicMock, patch

from tests.conftest import FakeEmitter
from app.core.orchestrators import (
    ServerOrchestrator,
    BackupOrchestrator,
    SchedulerOrchestrator,
    TunnelOrchestrator,
)
from app.core.server_events import ServerEvent
from app.core.constants import ServerState


# ---------------------------------------------------------------------------
# Shared fixtures
# ---------------------------------------------------------------------------

def _make_manager(**overrides):
    """Minimal manager stub that satisfies all orchestrators."""
    m = MagicMock()
    m.events = FakeEmitter()
    m.current_server = "test_srv"
    m.state = ServerState.OFFLINE
    m.server_runner = None
    m._start_lock = threading.Lock()
    m._backup_lock = threading.Lock()
    m._backup_in_progress = False
    m._tick_running = False
    m._restart_warnings_lock = threading.Lock()
    m.restart_warnings_sent = set()
    m._heartbeat = None
    for k, v in overrides.items():
        setattr(m, k, v)
    return m


# ---------------------------------------------------------------------------
# ServerOrchestrator
# ---------------------------------------------------------------------------

class TestServerOrchestrator:

    def test_start_blocked_when_already_running(self):
        runner = MagicMock(running=True)
        mgr = _make_manager(server_runner=runner)
        orch = ServerOrchestrator(mgr)

        result = orch.start_server()

        assert result is False
        lines = [e[1] for e in mgr.events.events if e[0] == ServerEvent.CONSOLE_LINE]
        assert any("already running" in l for l in lines)

    def test_start_blocked_when_no_server_selected(self):
        mgr = _make_manager(current_server=None)
        orch = ServerOrchestrator(mgr)

        with patch("app.core.constants.check_disk_space", return_value=True):
            result = orch.start_server()

        assert result is False

    def test_start_blocked_on_low_disk_space(self):
        mgr = _make_manager()
        orch = ServerOrchestrator(mgr)

        with patch("app.core.orchestrators.check_disk_space", return_value=False):
            result = orch.start_server()

        assert result is False
        notifs = [e[1] for e in mgr.events.events if e[0] == ServerEvent.NOTIFICATION]
        assert any(n["type"] == "error" for n in notifs)

    def test_stop_sets_state_offline(self):
        runner = MagicMock(running=True)
        mgr = _make_manager(server_runner=runner)
        orch = ServerOrchestrator(mgr)

        orch.stop_server()

        assert mgr.state == ServerState.OFFLINE
        mgr._stop_monitors.assert_called_once()
        runner.stop.assert_called_once()

    def test_stop_no_crash_when_runner_none(self):
        mgr = _make_manager(server_runner=None, _watchdog=None)
        orch = ServerOrchestrator(mgr)
        orch.stop_server()  # must not raise
        assert mgr.state == ServerState.OFFLINE

    def test_is_running_true_when_runner_running(self):
        runner = MagicMock(running=True)
        mgr = _make_manager(server_runner=runner)
        orch = ServerOrchestrator(mgr)
        assert orch.is_running() is True

    def test_is_running_false_when_no_runner(self):
        mgr = _make_manager(server_runner=None)
        orch = ServerOrchestrator(mgr)
        assert orch.is_running() is False

    def test_send_command_blocked_if_unsafe(self):
        runner = MagicMock(running=True)
        mgr = _make_manager(server_runner=runner)
        orch = ServerOrchestrator(mgr)

        with patch("app.core.orchestrators.is_safe_command", return_value=(False, "injection")):
            orch.send_command("rm -rf /")

        runner.send_command.assert_not_called()
        lines = [e[1] for e in mgr.events.events if e[0] == ServerEvent.CONSOLE_LINE]
        assert any("Blocked" in l for l in lines)

    def test_send_command_passes_safe_cmd(self):
        runner = MagicMock(running=True)
        mgr = _make_manager(server_runner=runner)
        orch = ServerOrchestrator(mgr)

        with patch("app.core.orchestrators.is_safe_command", return_value=(True, None)):
            orch.send_command("say hello")

        runner.send_command.assert_called_once_with("say hello")

    def test_send_command_noop_when_not_running(self):
        runner = MagicMock(running=False)
        mgr = _make_manager(server_runner=runner)
        orch = ServerOrchestrator(mgr)

        with patch("app.core.orchestrators.is_safe_command", return_value=(True, None)):
            orch.send_command("say hello")

        runner.send_command.assert_not_called()


# ---------------------------------------------------------------------------
# BackupOrchestrator
# ---------------------------------------------------------------------------

class TestBackupOrchestrator:

    def test_check_auto_backup_skips_if_no_server(self):
        mgr = _make_manager(current_server=None)
        orch = BackupOrchestrator(mgr)
        orch._check_auto_backup()  # must not raise, must not submit
        mgr.executor.submit.assert_not_called()

    def test_check_auto_backup_skips_if_backup_in_progress(self):
        mgr = _make_manager(_backup_in_progress=True)
        orch = BackupOrchestrator(mgr)
        orch._check_auto_backup()
        mgr.executor.submit.assert_not_called()

    def test_check_auto_backup_skips_if_not_due(self):
        mgr = _make_manager()
        orch = BackupOrchestrator(mgr)

        with patch("app.core.orchestrators.BackupScheduler") as MockSched:
            MockSched.return_value.is_due.return_value = False
            orch._check_auto_backup()

        mgr.executor.submit.assert_not_called()

    def test_check_auto_backup_submits_when_due(self):
        mgr = _make_manager()
        orch = BackupOrchestrator(mgr)

        with patch("app.core.orchestrators.BackupScheduler") as MockSched:
            MockSched.return_value.is_due.return_value = True
            orch._check_auto_backup()

        mgr.executor.submit.assert_called_once_with(orch._run_auto_backup)
        assert mgr._backup_in_progress is True

    def test_run_auto_backup_emits_completed_on_success(self):
        mgr = _make_manager(_backup_in_progress=True)
        orch = BackupOrchestrator(mgr)

        fake_path = MagicMock()
        fake_path.name = "backup_2026.zip"

        with patch("app.core.orchestrators.BackupManager") as MockBM, \
             patch("app.core.orchestrators.BackupScheduler") as MockSched:
            MockBM.return_value.create_backup.return_value = (fake_path, None)
            MockSched.return_value.get_config.return_value = {"retention_count": 5}

            orch._run_auto_backup()

        events = [e[0] for e in mgr.events.events]
        assert ServerEvent.BACKUP_COMPLETED in events
        assert mgr._backup_in_progress is False

    def test_run_auto_backup_emits_failed_on_error(self):
        mgr = _make_manager(_backup_in_progress=True)
        orch = BackupOrchestrator(mgr)

        with patch("app.core.orchestrators.BackupManager") as MockBM, \
             patch("app.core.orchestrators.BackupScheduler") as MockSched:
            MockBM.return_value.create_backup.return_value = (None, "disk full")
            MockSched.return_value.get_config.return_value = {}

            orch._run_auto_backup()

        events = [e[0] for e in mgr.events.events]
        assert ServerEvent.BACKUP_FAILED in events
        assert mgr._backup_in_progress is False

    def test_run_auto_backup_always_clears_flag(self):
        """_backup_in_progress must be cleared even if BackupManager raises."""
        mgr = _make_manager(_backup_in_progress=True)
        orch = BackupOrchestrator(mgr)

        with patch("app.core.orchestrators.BackupManager") as MockBM, \
             patch("app.core.orchestrators.BackupScheduler") as MockSched:
            MockBM.return_value.create_backup.side_effect = RuntimeError("unexpected")
            MockSched.return_value.get_config.return_value = {}

            with pytest.raises(RuntimeError):
                orch._run_auto_backup()

        assert mgr._backup_in_progress is False


# ---------------------------------------------------------------------------
# SchedulerOrchestrator
# ---------------------------------------------------------------------------

class TestSchedulerOrchestrator:

    def test_tick_loop_starts_thread(self):
        mgr = _make_manager()
        orch = SchedulerOrchestrator(mgr)

        orch._start_tick_loop()
        time.sleep(0.05)
        mgr._tick_running = False

        assert mgr._tick_thread is not None

    def test_tick_loop_idempotent(self):
        """Calling _start_tick_loop when already running must not spawn a new thread."""
        mgr = _make_manager(_tick_running=True)
        mgr._tick_thread = None  # explicit None, not MagicMock auto-attribute
        orch = SchedulerOrchestrator(mgr)

        orch._start_tick_loop()

        # _tick_running was already True → early return → _tick_thread stays None
        assert mgr._tick_thread is None

    def test_tick_loop_emits_player_count_when_running(self):
        runner = MagicMock(running=True, player_count=3)
        mgr = _make_manager(server_runner=runner)
        orch = SchedulerOrchestrator(mgr)

        orch._start_tick_loop()
        time.sleep(0.15)  # allow at least one tick (50ms interval)
        mgr._tick_running = False
        if mgr._tick_thread:
            mgr._tick_thread.join(timeout=1.0)

        emitted = [e[0] for e in mgr.events.events]
        assert ServerEvent.PLAYER_COUNT in emitted

    def test_tick_loop_calls_check_auto_backup(self):
        """Scheduler tick must call backup_orchestrator._check_auto_backup on schedule."""
        runner = MagicMock(running=True, player_count=0)
        mgr = _make_manager(server_runner=runner)

        # Make scheduler interval effectively 0 so it triggers on first tick
        with patch("app.core.orchestrators.AppConfig") as MockConfig:
            MockConfig.SCHEDULER_CHECK_INTERVAL = 0.0

            orch = SchedulerOrchestrator(mgr)
            orch._start_tick_loop()
            time.sleep(0.15)
            mgr._tick_running = False
            if mgr._tick_thread:
                mgr._tick_thread.join(timeout=1.0)

        mgr.backup_orchestrator._check_auto_backup.assert_called()


# ---------------------------------------------------------------------------
# TunnelOrchestrator
# ---------------------------------------------------------------------------

class TestTunnelOrchestrator:

    def test_start_tunnel_submits_to_executor(self):
        mgr = _make_manager()
        mgr.get_server_port.return_value = 25565
        orch = TunnelOrchestrator(mgr)

        orch.start_tunnel()

        mgr.executor.submit.assert_called_once()

    def test_stop_tunnel_calls_playit_stop(self):
        mgr = _make_manager()
        orch = TunnelOrchestrator(mgr)

        orch.stop_tunnel()

        mgr.playit_manager.stop.assert_called_once_with(force=True)

    def test_reset_tunnel_passes_mode(self):
        mgr = _make_manager()
        orch = TunnelOrchestrator(mgr)

        orch.reset_tunnel(mode="soft")

        mgr.playit_manager.reset.assert_called_once_with("soft")

    def test_get_tunnel_ip_returns_address(self):
        mgr = _make_manager()
        mgr.playit_manager.current_address = "abc.ply.gg"
        orch = TunnelOrchestrator(mgr)

        assert orch.get_tunnel_ip() == "abc.ply.gg"

    def test_create_tunnel_for_server_submits(self):
        mgr = _make_manager()
        mgr.get_server_port.return_value = 25565
        orch = TunnelOrchestrator(mgr)

        orch.create_tunnel_for_server("my_server")

        mgr.executor.submit.assert_called_once()
