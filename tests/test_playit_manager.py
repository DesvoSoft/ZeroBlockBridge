import pytest
import os
import sys
import platform
import threading
import time
from unittest.mock import MagicMock, patch, PropertyMock
from app.core.playit_manager import PlayitManager


@pytest.fixture
def callbacks():
    return {
        "console": MagicMock(),
        "status": MagicMock(),
        "ready": MagicMock(),
        "notification": MagicMock(),
    }


@pytest.fixture
def manager(callbacks):
    with patch("app.core.playit_manager.PlayitApiClient") as mock_api_cls:
        mock_api = MagicMock()
        mock_api.load_secret_key.return_value = False
        mock_api.secret_rejected.return_value = False
        mock_api.consecutive_auth_failures = 0
        mock_api.list_account_tunnels.return_value = []
        mock_api_cls.return_value = mock_api
        m = PlayitManager(
            console_callback=callbacks["console"],
            status_callback=callbacks["status"],
            on_ready_callback=callbacks["ready"],
            notification_callback=callbacks["notification"],
        )
        return m, mock_api, callbacks


class TestInit:
    def test_not_linked_by_default(self, manager):
        m, mock_api, _ = manager
        assert m.is_linked is False
        assert m.current_address is None
        assert m.running is False
        mock_api.load_secret_key.assert_called_once()

    def test_linked_when_secret_exists(self, callbacks):
        with patch("app.core.playit_manager.PlayitApiClient") as mock_api_cls:
            mock_api = MagicMock()
            mock_api.load_secret_key.return_value = True
            mock_api_cls.return_value = mock_api
            m = PlayitManager(
                console_callback=callbacks["console"],
                status_callback=callbacks["status"],
            )
            assert m.is_linked is True


class TestBinaryPath:
    def test_windows_binary(self, manager):
        m, _, _ = manager
        with patch.object(platform, "system", return_value="Windows"):
            path = m._get_binary_path()
        assert path.name == "playit.exe"

    def test_linux_binary(self, manager):
        m, _, _ = manager
        with patch.object(platform, "system", return_value="Linux"):
            path = m._get_binary_path()
        assert path.name == "playit"

    def test_binary_is_resolved(self, manager):
        m, _, _ = manager
        path = m._get_binary_path()
        assert path == path.resolve()


class TestCleanStaleBinaries:
    def test_removes_stale(self, manager, tmp_path):
        m, _, _ = manager
        with patch("app.core.playit_manager.BIN_DIR", tmp_path):
            with patch.object(m, "binary_path", tmp_path / "playit.exe"):
                m.binary_path.touch()
                stale = tmp_path / "playit-old.exe"
                stale.touch()
                m._clean_stale_binaries()
                assert stale.exists() is False
                assert m.binary_path.exists() is True

    def test_skips_non_playit(self, manager, tmp_path):
        m, _, _ = manager
        with patch("app.core.playit_manager.BIN_DIR", tmp_path):
            with patch.object(m, "binary_path", tmp_path / "playit.exe"):
                m.binary_path.touch()
                other = tmp_path / "not-playit.txt"
                other.touch()
                m._clean_stale_binaries()
                assert other.exists() is True

    def test_no_bin_dir(self, manager):
        m, _, _ = manager
        with patch("app.core.playit_manager.BIN_DIR", PropertyMock(return_value=MagicMock(exists=False))):
            m._clean_stale_binaries()


class TestEnsureBinary:
    def make_binary(self, m, tmp_path):
        fake_bin = tmp_path / "playit.exe"
        fake_bin.touch()
        with patch("app.core.playit_manager.BIN_DIR", tmp_path):
            with patch.object(m, "binary_path", fake_bin):
                return fake_bin

    def test_binary_exists_and_version_matches(self, manager, tmp_path):
        m, _, _ = manager
        fake_bin = self.make_binary(m, tmp_path)
        with patch("subprocess.run") as mock_run:
            mock_result = MagicMock()
            mock_result.stdout = "0.17.1"
            mock_result.stderr = ""
            mock_run.return_value = mock_result
            assert m.ensure_binary() is True

    def test_binary_exists_version_mismatch_replaces(self, manager, tmp_path):
        m, _, _ = manager
        fake_bin = self.make_binary(m, tmp_path)
        with patch("subprocess.run") as mock_run:
            mock_result = MagicMock()
            mock_result.stdout = "0.16.0"
            mock_result.stderr = ""
            mock_run.return_value = mock_result
            with patch("requests.get") as mock_get:
                mock_response = MagicMock()
                mock_response.iter_content.return_value = [b"data"]
                mock_response.raise_for_status = MagicMock()
                mock_get.return_value = mock_response
                assert m.ensure_binary() is True

    def test_download_failure(self, manager, tmp_path):
        m, _, _ = manager
        with patch("app.core.playit_manager.BIN_DIR", tmp_path):
            fake_bin = tmp_path / "playit.exe"
            with patch.object(m, "binary_path", fake_bin):
                with patch("requests.get") as mock_get:
                    mock_get.side_effect = Exception("Network error")
                    assert m.ensure_binary() is False
                    m.console_callback.assert_any_call("[Playit] Download failed: Network error")


class TestGetOrCreateTunnel:
    def test_no_secret_key(self, manager):
        m, mock_api, _ = manager
        mock_api.load_secret_key.return_value = False
        assert m.get_or_create_tunnel(25565) is None

    def test_existing_tunnel_found(self, manager):
        m, mock_api, _ = manager
        mock_api.load_secret_key.return_value = True
        mock_api.list_tunnels.return_value = [
            {"origin": {"data": {"local_port": 25565}}},
        ]
        mock_api.get_tunnel_address.return_value = "abc.ply.gg:25565"
        result = m.get_or_create_tunnel(25565)
        assert result == "abc.ply.gg:25565"
        assert m._api_dns == "abc.ply.gg:25565"

    def test_creates_tunnel_when_missing(self, manager):
        m, mock_api, _ = manager
        mock_api.load_secret_key.return_value = True
        mock_api.list_tunnels.return_value = [
            {"origin": {"data": {"local_port": 19132}}},
        ]
        mock_api.create_tunnel.return_value = {"id": "new-tunnel"}
        mock_api.get_tunnel_address.side_effect = [None, "new.ply.gg:19132"]
        result = m.get_or_create_tunnel(19132)
        assert result == "new.ply.gg:19132"
        mock_api.create_tunnel.assert_called_once_with(19132)

    def test_pending_tunnel_warns_about_port_quota(self, manager):
        m, mock_api, _ = manager
        mock_api.load_secret_key.return_value = True
        mock_api.list_tunnels.return_value = []
        mock_api.create_tunnel.return_value = {"id": "pending-tunnel"}
        mock_api.get_tunnel_address.return_value = None
        result = m.get_or_create_tunnel(25565)
        assert result is None
        m.notification_callback.assert_called_once()
        assert "warning" in m.notification_callback.call_args[0]

    def test_cleanup_deletes_stale_zbb_tunnels_only(self, manager):
        m, mock_api, _ = manager
        mock_api.get_agent_id.return_value = "current-agent"
        mock_api.list_account_tunnels.return_value = [
            # stale ZBB tunnel from a dead agent — must be deleted
            {"id": "t1", "name": "minecraft-java_ab12",
             "origin": {"data": {"agent_id": "dead-agent"}}},
            # same-name tunnel owned by current agent — keep
            {"id": "t2", "name": "minecraft-java_cd34",
             "origin": {"data": {"agent_id": "current-agent"}}},
            # user-made tunnel on another agent — keep
            {"id": "t3", "name": "my-custom-tunnel",
             "origin": {"data": {"agent_id": "dead-agent"}}},
        ]
        mock_api.delete_tunnel.return_value = True
        m._cleanup_stale_tunnels()
        mock_api.delete_tunnel.assert_called_once_with("t1")

    def test_read_only_guest_mode(self, manager):
        m, mock_api, _ = manager
        from app.services.playit_api import PlayitApiException
        mock_api.load_secret_key.return_value = True
        mock_api.list_tunnels.side_effect = PlayitApiException("NotAllowedWithReadOnly: Account is in Guest mode")
        result = m.get_or_create_tunnel(25565)
        assert result is None
        m.notification_callback.assert_called_once()


class FakeProcess:
    def __init__(self):
        self.pid = 12345
        self.stdout = MagicMock()
        self.stdout.readline = MagicMock(return_value=b"")
        self.stderr = None
        self.returncode = None

    def poll(self):
        return None

    def kill(self):
        pass

    def terminate(self):
        pass


class TestStart:
    def test_start_already_running(self, manager):
        m, _, _ = manager
        m.running = True
        m._api_dns = "existing.ply.gg:25565"
        m.start()
        m.status_callback.assert_called_with("Online", "existing.ply.gg:25565")

    def test_start_binary_failure(self, manager):
        m, _, _ = manager
        m.running = False
        with patch.object(m, "ensure_binary", return_value=False):
            m.start(25565)
            m.console_callback.assert_any_call("[Playit] Binary check failed.")

    def test_start_not_linked(self, manager):
        m, _, _ = manager
        def _exists_side_effect(path):
            if str(path) == str(m.toml_path):
                return False
            return True
        with patch.object(m, "ensure_binary", return_value=True):
            with patch("os.path.exists", side_effect=_exists_side_effect):
                with patch("os.makedirs"):
                    m.start(25565)
                    m.console_callback.assert_any_call("[Playit] No playit.toml found. Link account first.")

    def test_start_full_flow(self, manager):
        m, mock_api, _ = manager
        m.is_linked = True
        with patch.object(m, "ensure_binary", return_value=True):
            with patch.object(m, "_current_port", 25565, create=True):
                with patch("os.path.exists", return_value=True):
                    with patch("subprocess.Popen") as mock_popen:
                        mock_popen.return_value = FakeProcess()
                        with patch("threading.Thread", side_effect=lambda target=None, daemon=False, **kw: MagicMock(start=MagicMock())):
                            m.start(25565)
                            # Agent launched — address resolved via _parse_line or dns poll, not in start()
                            assert m.running is True

    def test_oserror_handling(self, manager):
        m, _, _ = manager
        m.is_linked = True
        with patch.object(m, "ensure_binary", return_value=True):
            with patch.object(m, "get_or_create_tunnel", return_value="tunnel.ply.gg:25565"):
                with patch("os.path.exists", return_value=True):
                    with patch("subprocess.Popen", side_effect=OSError("Access denied")):
                        with patch("threading.Thread", side_effect=lambda target=None, daemon=False, **kw: MagicMock(start=MagicMock())):
                            m.start(25565)
                            assert m.running is False


class TestAuthFailure:
    def test_start_blocked_when_secret_rejected(self, manager):
        m, mock_api, _ = manager
        mock_api.secret_rejected.return_value = True
        with patch.object(m, "ensure_binary", return_value=True):
            with patch("os.path.exists", return_value=True):
                with patch("subprocess.Popen") as mock_popen:
                    m.start(25565)
                    mock_popen.assert_not_called()
        assert m._auth_failed is True
        assert m.running is False
        m.status_callback.assert_any_call("Error", None)
        m.notification_callback.assert_called_once()

    def test_start_proceeds_when_check_inconclusive(self, manager):
        m, mock_api, _ = manager
        mock_api.secret_rejected.return_value = False
        with patch.object(m, "ensure_binary", return_value=True):
            with patch("os.path.exists", return_value=True):
                with patch("subprocess.Popen") as mock_popen:
                    mock_popen.return_value = FakeProcess()
                    with patch("threading.Thread", side_effect=lambda target=None, daemon=False, **kw: MagicMock(start=MagicMock())):
                        m.start(25565)
        assert m.running is True
        assert m._auth_failed is False

    def test_handle_auth_failure_idempotent(self, manager):
        m, _, _ = manager
        m._handle_auth_failure("Agent secret invalid")
        m._handle_auth_failure("Agent secret invalid")
        assert m._auth_failed is True
        m.notification_callback.assert_called_once()

    def test_dns_polling_stops_after_repeated_401(self, manager):
        m, mock_api, _ = manager
        m.running = True
        m._api_dns = None
        m._stdout_dns = None
        mock_api.get_tunnels.return_value = []
        mock_api.consecutive_auth_failures = 3
        with patch("time.sleep"):
            m._dns_polling_loop()
        assert m._auth_failed is True
        m.status_callback.assert_any_call("Error", None)

    def test_got_error_without_dns_sets_error_status(self, manager):
        m, _, _ = manager
        m.running = True
        mock_proc = MagicMock()
        mock_proc.stdout.readline.side_effect = [
            b"2026-07-05T00:10:42Z  INFO playit_cli::ui: Got Error\n",
            b"",
        ]
        m.process = mock_proc
        m._read_output()
        m.status_callback.assert_any_call("Error", None)

    def test_got_error_with_dns_is_ignored(self, manager):
        m, _, _ = manager
        m.running = True
        m._api_dns = "abc.ply.gg:25565"
        mock_proc = MagicMock()
        mock_proc.stdout.readline.side_effect = [
            b"2026-07-05T00:10:42Z  INFO playit_cli::ui: Got Error\n",
            b"",
        ]
        m.process = mock_proc
        m._read_output()
        for call in m.status_callback.call_args_list:
            assert call[0][0] != "Error"

    def test_auth_failure_soon_after_link_mentions_account_limit(self, manager):
        m, _, _ = manager
        m._linked_at = time.time() - 60
        m._handle_auth_failure("Agent secret invalid")
        joined = " ".join(str(c) for c in m.console_callback.call_args_list)
        assert "over its agent/port limit" in joined

    def test_invalid_agent_key_stdout_marks_auth_failed(self, manager):
        m, _, _ = manager
        m.running = True
        mock_proc = MagicMock()
        mock_proc.stdout.readline.side_effect = [
            b"error: InvalidAgentKey\n",
            b"",
        ]
        m.process = mock_proc
        m._read_output()
        assert m._auth_failed is True
        assert m._tunnel_create_inflight is False
        m.status_callback.assert_any_call("Error", None)


class TestStop:
    def test_stop_no_process(self, manager):
        m, _, _ = manager
        m.process = None
        m.stop()
        m.status_callback.assert_called_with("Offline", None)

    def test_stop_fallback_taskkill(self, manager):
        m, _, _ = manager
        mock_proc = MagicMock()
        mock_proc.pid = 12345
        m.running = True
        m.process = mock_proc
        with patch.object(platform, "system", return_value="Windows"):
            with patch("subprocess.CREATE_NO_WINDOW", 0x08000000, create=True):
                with patch("subprocess.run") as mock_run:
                    m.stop()
                    taskkill_calls = [c for c in mock_run.call_args_list if "taskkill" in str(c)]
                    assert len(taskkill_calls) >= 1
                    assert m.running is False
                    assert m.current_address is None

    def test_stop_linux_terminate(self, manager):
        m, _, _ = manager
        mock_proc = MagicMock()
        mock_proc.pid = 12345
        m.running = True
        m.process = mock_proc
        with patch.object(platform, "system", return_value="Linux"):
            m.stop()
            mock_proc.terminate.assert_called_once()
            assert m.running is False


class TestReset:
    def test_soft_reset_clears_address(self, manager):
        m, mock_api, _ = manager
        m.current_address = "old.ply.gg"
        m._api_dns = "old.ply.gg"
        m.is_linked = True
        m.running = True
        with patch.object(m, "stop"):
            mock_api.load_secret_key.return_value = True
            mock_api.list_tunnels.return_value = [{"id": "t1"}]
            mock_api.delete_tunnel.return_value = True
            m.reset(mode="tunnel")
            assert m.current_address is None
            assert m._api_dns is None
            assert m.is_linked is True

    def test_full_reset_unlinks(self, manager, tmp_path):
        m, mock_api, _ = manager
        m.current_address = "old.ply.gg"
        m._api_dns = "old.ply.gg"
        m.is_linked = True
        m.running = True
        toml = tmp_path / "playit.toml"
        toml.touch()
        with patch.object(m, "toml_path", toml):
            with patch.object(m, "stop"):
                mock_api.load_secret_key.return_value = True
                mock_api.list_tunnels.return_value = [{"id": "t1"}]
                mock_api.delete_tunnel.return_value = True
                mock_api.delete_agent.return_value = True
                m.reset(mode="full")
                assert toml.exists() is False
                assert m.is_linked is False
                assert m.current_address is None
                assert m._api_dns is None
                assert mock_api._secret_key is None

    def test_soft_reset_escalates_to_full_when_auth_failed(self, manager, tmp_path):
        m, mock_api, _ = manager
        m.is_linked = True
        m._auth_failed = True
        toml = tmp_path / "playit.toml"
        toml.touch()
        with patch.object(m, "toml_path", toml):
            with patch.object(m, "stop"):
                mock_api.load_secret_key.return_value = True
                mock_api.list_tunnels.return_value = []
                mock_api.delete_agent.return_value = True
                m.reset(mode="soft")
                assert toml.exists() is False
                assert m.is_linked is False
                assert m._auth_failed is False
                assert mock_api.consecutive_auth_failures == 0

    def test_full_reset_api_delete_fails(self, manager, tmp_path):
        m, mock_api, _ = manager
        toml = tmp_path / "playit.toml"
        toml.touch()
        with patch.object(m, "toml_path", toml):
            with patch.object(m, "stop"):
                mock_api.load_secret_key.return_value = True
                mock_api.list_tunnels.return_value = [{"id": "t1"}]
                mock_api.delete_tunnel.return_value = True
                mock_api.delete_agent.return_value = False
                m.reset(mode="full")
                assert m.is_linked is False
                assert any("delete manually" in c[0][0].lower() for c in m.console_callback.call_args_list)


class TestLinkManually:
    def test_invalid_code_short(self, manager):
        m, _, _ = manager
        result = m.link_manually("abc")
        assert result is False
        m.notification_callback.assert_called_once()

    def test_link_success(self, manager):
        m, mock_api, _ = manager
        with patch.object(m, "ensure_binary"):
            mock_api.link_account.return_value = True
            with patch.object(m, "start"):
                result = m.link_manually("valid-setup-code-12345")
                assert result is True
                assert m.is_linked is True
                assert m.api_client.is_read_only is False

    def test_link_failure(self, manager):
        m, mock_api, _ = manager
        mock_api.link_account.return_value = False
        with patch.object(m, "ensure_binary"):
            result = m.link_manually("valid-setup-code-12345")
            assert result is False
            m.notification_callback.assert_not_called()

    def test_link_exception(self, manager):
        m, mock_api, _ = manager
        mock_api.link_account.side_effect = Exception("API error")
        with patch.object(m, "ensure_binary"):
            result = m.link_manually("valid-setup-code-12345")
            assert result is False
            m.notification_callback.assert_called_once()


class TestFixPermissions:
    def test_skips_on_windows(self, manager):
        m, _, _ = manager
        with patch.object(platform, "system", return_value="Windows"):
            with patch("os.path.exists", return_value=True):
                with patch("os.chmod") as mock_chmod:
                    m._fix_permissions()
                    mock_chmod.assert_not_called()

    def test_fixes_on_linux(self, manager):
        m, _, _ = manager
        with patch.object(platform, "system", return_value="Linux"):
            with patch("os.path.exists", return_value=True):
                with patch("os.stat") as mock_stat:
                    mock_stat.return_value.st_mode = 0o644
                    with patch("os.chmod") as mock_chmod:
                        m._fix_permissions()
                        mock_chmod.assert_called_once()


class TestDnsPollingLoop:
    def test_exits_if_already_resolved(self, manager):
        m, mock_api, _ = manager
        m.running = True
        m._api_dns = "resolved.ply.gg"
        m._dns_polling_loop()
        mock_api.get_tunnels.assert_not_called()

    def test_polls_and_resolves(self, manager):
        m, mock_api, _ = manager
        m.running = True
        m._stdout_dns = None
        m._api_dns = None
        mock_api.get_tunnels.return_value = ["dns.ply.gg:25565"]
        with patch.object(m, "_dns_polling_loop", wraps=m._dns_polling_loop) as wrapped:
            pass
        with patch("time.sleep"):
            m._dns_polling_loop()
            assert m.current_address == "dns.ply.gg:25565"
            m.status_callback.assert_called_with("Online", "dns.ply.gg:25565")


class TestHeartbeatLoop:
    def test_no_restart_on_healthy(self, manager):
        m, _, _ = manager
        m.running = True
        mock_proc = MagicMock()
        mock_proc.poll.return_value = None
        m.process = mock_proc
        with patch("time.sleep", side_effect=StopIteration):
            with pytest.raises(StopIteration):
                m._heartbeat_loop()
            assert m.console_callback.call_count == 0

    def test_restarts_after_10_failures(self, manager):
        m, _, _ = manager
        m.running = True
        m.process = None
        with patch("time.sleep"):
            with patch.object(m, "start"):
                m._heartbeat_loop()
                assert m.start.call_count == 9
                m.console_callback.assert_any_call("[Playit] CRITICAL: Max restart attempts reached. Agent halted.")


class TestParseLine:
    def test_ply_gg_domain(self, manager):
        m, _, _ = manager
        m._api_dns = None
        m._stdout_dns = None
        m.current_address = None
        m._parse_line("[agent] tunnel running at minecraft.ply.gg:25565")
        assert m._stdout_dns == "minecraft.ply.gg:25565"
        assert m.current_address == "minecraft.ply.gg:25565"

    def test_gl_ply_gg_domain(self, manager):
        m, _, _ = manager
        m._api_dns = None
        m._stdout_dns = None
        m.current_address = None
        m._parse_line("address is my-tunnel.gl.ply.gg:19132")
        assert m._stdout_dns == "my-tunnel.gl.ply.gg:19132"

    def test_joinmc_link_domain(self, manager):
        m, _, _ = manager
        m._api_dns = None
        m._stdout_dns = None
        m.current_address = None
        m._parse_line("server at mc-server.joinmc.link:25565")
        assert m._stdout_dns == "mc-server.joinmc.link:25565"

    def test_skips_if_already_resolved(self, manager):
        m, _, _ = manager
        m._api_dns = "existing.ply.gg"
        m._parse_line("minecraft.ply.gg:25565")
        assert m._stdout_dns is None

    def test_no_match_returns_none(self, manager):
        m, _, _ = manager
        m._api_dns = None
        m._stdout_dns = None
        m._parse_line("some random debug line")
        assert m._stdout_dns is None

    def test_notifies_on_new_address(self, manager):
        m, _, _ = manager
        m._api_dns = None
        m._stdout_dns = None
        m.current_address = None
        m._parse_line("tunnel at new.ply.gg:25565")
        m.status_callback.assert_called_with("Online", "new.ply.gg:25565")
        m.notification_callback.assert_called_once()


class TestReadOutput:
    def test_read_single_line(self, manager):
        m, _, _ = manager
        m.running = True
        mock_proc = MagicMock()
        mock_proc.stdout.readline.side_effect = [
            b"[agent] tunnel running at my.ply.gg:25565\n",
            b"",
        ]
        m.process = mock_proc
        m._read_output()
        assert m._stdout_dns == "my.ply.gg:25565"

    def test_account_limit_error(self, manager):
        m, _, _ = manager
        m.running = True
        mock_proc = MagicMock()
        mock_proc.stdout.readline.side_effect = [
            b"AgentDisabledOverLimit: too many agents\n",
            b"",
        ]
        m.process = mock_proc
        m._read_output()
        m.status_callback.assert_any_call("Error", None)

    def test_spam_filtering(self, manager):
        m, _, _ = manager
        m.running = True
        mock_proc = MagicMock()
        mock_proc.stdout.readline.side_effect = [
            b"[info] tunnel running\n",
            b"",
        ]
        m.process = mock_proc
        m._read_output()
        assert m.console_callback.call_count == 0

    def test_ansi_removal(self, manager):
        m, _, _ = manager
        m.running = True
        mock_proc = MagicMock()
        mock_proc.stdout.readline.side_effect = [
            b"\x1b[31m[error]\x1b[0m something broke\n",
            b"",
        ]
        m.process = mock_proc
        m._read_output()
        m.console_callback.assert_called_with("[Playit] [error] something broke")
