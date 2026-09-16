from unittest.mock import MagicMock, patch

import pytest

from app.core import players as pl
from app.core.constants import BANNED_PLAYERS_FILE, OPS_FILE, WHITELIST_FILE
from app.services.player_identity import PlayerIdentity, PlayerLookupError


def _orch(running=False, current="srv", online=()):
    manager = MagicMock()
    manager.current_server = current
    manager.is_running.return_value = running
    manager.server_runner = MagicMock(connected_players=set(online)) if running else None
    return pl.PlayerOrchestrator(manager), manager


@pytest.fixture
def files():
    props = {"online-mode": "true", "op-permission-level": "2", "white-list": "false"}
    with patch.object(pl, "add_entry") as add, \
         patch.object(pl, "remove_entry") as remove, \
         patch.object(pl, "load_json_list", return_value=[]) as load, \
         patch.object(pl, "load_usercache", return_value=[]) as cache, \
         patch.object(pl, "load_history", return_value={}) as history, \
         patch.object(pl, "load_server_properties", return_value=props), \
         patch.object(pl, "save_server_properties") as save, \
         patch.object(pl, "resolve_player", return_value=PlayerIdentity("Steve", "uuid-1", "mojang")) as resolve:
        yield MagicMock(add=add, remove=remove, load=load, cache=cache, history=history,
                        save=save, resolve=resolve, props=props)


# ------------------------------------------------------------------ running server owns the files
def test_running_whitelist_add_sends_command_without_lookup(files):
    orch, manager = _orch(running=True)
    result = orch.whitelist_add("srv", "Steve")
    assert result.ok
    manager.send_command.assert_called_once_with("whitelist add Steve")
    files.add.assert_not_called()
    files.resolve.assert_not_called()


def test_running_op_reports_effective_level(files):
    orch, manager = _orch(running=True)
    result = orch.op("srv", "Steve", 4)
    manager.send_command.assert_called_once_with("op Steve")
    assert "level 2" in result.message


def test_running_ban_and_kick_include_reason(files):
    orch, manager = _orch(running=True)
    orch.ban("srv", "Steve", "  griefing   spawn ")
    orch.kick("srv", "Steve", "afk")
    assert [c.args[0] for c in manager.send_command.call_args_list] == ["ban Steve griefing spawn", "kick Steve afk"]


def test_other_server_selected_is_not_live(files):
    orch, manager = _orch(running=True, current="other")
    orch.whitelist_add("srv", "Steve")
    manager.send_command.assert_not_called()
    files.add.assert_called_once()


# ------------------------------------------------------------------ stopped server: files with real UUIDs
def test_stopped_whitelist_add_writes_resolved_uuid(files):
    orch, _ = _orch()
    assert orch.whitelist_add("srv", "steve").ok
    files.resolve.assert_called_once_with("srv", "steve", True)
    files.add.assert_called_once_with("srv", WHITELIST_FILE, {"uuid": "uuid-1", "name": "Steve"})


def test_stopped_op_writes_requested_level(files):
    orch, _ = _orch()
    orch.op("srv", "Steve", 3)
    files.add.assert_called_once_with("srv", OPS_FILE, {
        "uuid": "uuid-1", "name": "Steve", "level": 3, "bypassesPlayerLimit": False})


def test_stopped_ban_writes_vanilla_entry(files):
    orch, _ = _orch()
    orch.ban("srv", "Steve", "")
    _, filename, entry = files.add.call_args.args
    assert filename == BANNED_PLAYERS_FILE
    assert entry["uuid"] == "uuid-1" and entry["expires"] == "forever"
    assert entry["reason"] == "Banned by an operator."


def test_lookup_failure_writes_nothing(files):
    files.resolve.side_effect = PlayerLookupError("No Minecraft account named 'Ghost'.")
    orch, _ = _orch()
    result = orch.whitelist_add("srv", "Ghost")
    assert not result.ok and "No Minecraft account" in result.message
    files.add.assert_not_called()


def test_removals_offline_edit_files(files):
    orch, _ = _orch()
    orch.whitelist_remove("srv", "Steve")
    orch.deop("srv", "Steve")
    orch.pardon("srv", "Steve")
    assert [c.args[1] for c in files.remove.call_args_list] == [WHITELIST_FILE, OPS_FILE, BANNED_PLAYERS_FILE]


def test_invalid_name_and_reason_rejected(files):
    orch, manager = _orch(running=True)
    assert not orch.whitelist_add("srv", "bad name").ok
    assert not orch.ban("srv", "Steve", "x; stop").ok
    manager.send_command.assert_not_called()


def test_kick_requires_running_server(files):
    orch, _ = _orch()
    assert not orch.kick("srv", "Steve").ok


def test_set_whitelist_enabled_persists_and_commands_when_live(files):
    orch, manager = _orch(running=True)
    orch.set_whitelist_enabled("srv", True)
    files.save.assert_called_once_with("srv", new_properties={"white-list": "true"})
    manager.send_command.assert_called_once_with("whitelist on")


# ------------------------------------------------------------------ roster
def test_roster_merges_sources_online_first(files):
    def lists(_server, filename):
        return {
            WHITELIST_FILE: [{"name": "Alex", "uuid": "u-alex"}],
            OPS_FILE: [{"name": "steve", "uuid": "u-steve", "level": 4}],
            BANNED_PLAYERS_FILE: [{"name": "Griefer", "uuid": "u-g", "reason": "tnt"}],
        }[filename]
    files.load.side_effect = lists
    files.cache.return_value = [{"name": "Steve", "uuid": "u-steve"}]
    files.history.return_value = {"Steve": {"first_seen": "a", "last_seen": "b", "playtime_seconds": 90}}
    orch, _ = _orch(running=True, online=["Alex"])

    roster = orch.roster("srv")
    assert [p["name"] for p in roster] == ["Alex", "Griefer", "Steve"]
    alex, griefer, steve = roster
    assert alex["online"] and alex["whitelisted"]
    assert griefer["banned"] and griefer["ban_reason"] == "tnt"
    assert steve["op_level"] == 4 and steve["playtime_seconds"] == 90 and steve["uuid"] == "u-steve"
