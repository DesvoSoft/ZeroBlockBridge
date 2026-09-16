"""PlayersDashboard write paths, tested without a display.

Handlers are called on a stand-in `self`: while the server runs it owns
whitelist/ops/ban JSON (console command + in-memory update only); while it
is stopped the dashboard writes the file itself.
"""

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from app.core.constants import BANNED_PLAYERS_FILE, OPS_FILE, WHITELIST_FILE
from app.ui.players_dashboard import PlayersDashboard


def _dash(running, **lists):
    zbb = MagicMock()
    zbb.is_running.return_value = running
    return SimpleNamespace(
        zbb_manager=zbb,
        server_name="srv",
        whitelisted_players=list(lists.get("whitelist", [])),
        operators=list(lists.get("ops", [])),
        banned_players=list(lists.get("bans", [])),
        entry_whitelist_add=MagicMock(get=MagicMock(return_value="Alex")),
        entry_op_add=MagicMock(get=MagicMock(return_value="Alex")),
        op_level_var=MagicMock(get=MagicMock(return_value="4")),
        refresh_ui=MagicMock(),
    )


@pytest.fixture
def files():
    with patch("app.ui.players_dashboard.add_entry") as add, \
         patch("app.ui.players_dashboard.remove_entry") as remove, \
         patch("app.ui.players_dashboard.load_json_list", return_value=[{"name": "from-disk"}]) as load, \
         patch("app.ui.players_dashboard.ZBBDialog.confirm", return_value=True):
        yield SimpleNamespace(add=add, remove=remove, load=load)


class TestWhileRunning:
    def test_whitelist_add_sends_command_only(self, files):
        d = _dash(running=True)
        PlayersDashboard._add_to_whitelist(d)
        d.zbb_manager.send_command.assert_called_once_with("whitelist add Alex")
        files.add.assert_not_called()
        assert d.whitelisted_players == [{"uuid": "", "name": "Alex"}]

    def test_operator_add_sends_command_only(self, files):
        d = _dash(running=True)
        PlayersDashboard._add_operator(d)
        d.zbb_manager.send_command.assert_called_once_with("op Alex")
        files.add.assert_not_called()
        assert d.operators[0]["level"] == 4

    def test_ban_sends_command_only(self, files):
        d = _dash(running=True)
        PlayersDashboard._ban_player(d, "Steve")
        d.zbb_manager.send_command.assert_called_once_with("ban Steve")
        files.add.assert_not_called()
        assert d.banned_players[0]["name"] == "Steve"

    @pytest.mark.parametrize("method,command,attr", [
        ("_remove_from_whitelist", "whitelist remove Steve", "whitelisted_players"),
        ("_remove_operator", "deop Steve", "operators"),
        ("_pardon_player", "pardon Steve", "banned_players"),
    ])
    def test_removals_send_command_only(self, files, method, command, attr):
        d = _dash(running=True, whitelist=[{"name": "Steve"}], ops=[{"name": "Steve"}], bans=[{"name": "Steve"}])
        getattr(PlayersDashboard, method)(d, "Steve")
        d.zbb_manager.send_command.assert_called_once_with(command)
        files.remove.assert_not_called()
        assert getattr(d, attr) == []


class TestWhileStopped:
    @pytest.mark.parametrize("method,filename,attr", [
        ("_add_to_whitelist", WHITELIST_FILE, "whitelisted_players"),
        ("_add_operator", OPS_FILE, "operators"),
    ])
    def test_adds_write_file_and_reload(self, files, method, filename, attr):
        d = _dash(running=False)
        getattr(PlayersDashboard, method)(d)
        d.zbb_manager.send_command.assert_not_called()
        assert files.add.call_args.args[:2] == ("srv", filename)
        assert getattr(d, attr) == [{"name": "from-disk"}]

    def test_ban_writes_file(self, files):
        d = _dash(running=False)
        PlayersDashboard._ban_player(d, "Steve")
        assert files.add.call_args.args[:2] == ("srv", BANNED_PLAYERS_FILE)
        d.zbb_manager.send_command.assert_not_called()

    def test_pardon_removes_from_file(self, files):
        d = _dash(running=False, bans=[{"name": "Steve"}])
        PlayersDashboard._pardon_player(d, "Steve")
        files.remove.assert_called_once_with("srv", BANNED_PLAYERS_FILE, "Steve")


def test_duplicate_whitelist_entry_is_ignored(files):
    d = _dash(running=True, whitelist=[{"name": "Alex"}])
    PlayersDashboard._add_to_whitelist(d)
    d.zbb_manager.send_command.assert_not_called()


def test_cancelled_ban_does_nothing(files):
    d = _dash(running=True)
    with patch("app.ui.players_dashboard.ZBBDialog.confirm", return_value=False):
        PlayersDashboard._ban_player(d, "Steve")
    d.zbb_manager.send_command.assert_not_called()
