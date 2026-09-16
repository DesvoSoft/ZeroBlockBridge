import json
from unittest.mock import MagicMock, patch

import pytest
import requests

from app.services import player_identity as pi


@pytest.fixture
def server(tmp_path):
    (tmp_path / "srv").mkdir()
    with patch.object(pi, "SERVERS_DIR", str(tmp_path)):
        yield tmp_path / "srv"


def test_valid_names():
    assert pi.is_valid_player_name("Steve")
    assert pi.is_valid_player_name("a_b")
    assert pi.is_valid_player_name(".BedrockGuy")
    assert not pi.is_valid_player_name("ab")
    assert not pi.is_valid_player_name("seventeen_chars_x")
    assert not pi.is_valid_player_name("bad name")
    assert not pi.is_valid_player_name("x;op")


def test_offline_uuid_matches_java_name_uuid_from_bytes():
    # Known value for UUID.nameUUIDFromBytes("OfflinePlayer:Notch")
    assert pi.offline_uuid("Notch") == "b50ad385-829d-3141-a216-7e7d7539ba7f"


def test_usercache_wins_case_insensitively(server):
    (server / "usercache.json").write_text(json.dumps([
        {"name": "Desvox", "uuid": "d71329da-27ae-4635-8b4e-f5f1354153cb", "expiresOn": "x"},
    ]), encoding="utf-8")
    with patch.object(pi, "mojang_profile") as mojang:
        ident = pi.resolve_player("srv", "desvox", online_mode=True)
    assert ident == pi.PlayerIdentity("Desvox", "d71329da-27ae-4635-8b4e-f5f1354153cb", "usercache")
    mojang.assert_not_called()


def test_offline_mode_uses_offline_uuid(server):
    ident = pi.resolve_player("srv", "Alex", online_mode=False)
    assert ident.source == "offline"
    assert ident.uuid == pi.offline_uuid("Alex")


def test_online_mode_uses_mojang_canonical_name(server):
    with patch.object(pi, "mojang_profile", return_value=("069a79f4-44e9-4726-a5be-fca90e38aaf5", "Notch")):
        ident = pi.resolve_player("srv", "notch", online_mode=True)
    assert ident == pi.PlayerIdentity("Notch", "069a79f4-44e9-4726-a5be-fca90e38aaf5", "mojang")


def test_online_mode_unknown_account(server):
    with patch.object(pi, "mojang_profile", return_value=None):
        with pytest.raises(pi.PlayerLookupError, match="No Minecraft account"):
            pi.resolve_player("srv", "NobodyHere1", online_mode=True)


def test_online_mode_network_error_is_user_facing(server):
    with patch.object(pi, "mojang_profile", side_effect=requests.ConnectionError("down")):
        with pytest.raises(pi.PlayerLookupError, match="no connection"):
            pi.resolve_player("srv", "Steve", online_mode=True)


def test_invalid_name_rejected_before_any_lookup(server):
    with patch.object(pi, "mojang_profile") as mojang:
        with pytest.raises(pi.PlayerLookupError, match="valid player name"):
            pi.resolve_player("srv", "not valid!", online_mode=True)
    mojang.assert_not_called()


def test_bedrock_player_must_have_joined(server):
    with pytest.raises(pi.PlayerLookupError, match="hasn't joined"):
        pi.resolve_player("srv", ".Phone", online_mode=True)


def test_mojang_profile_parses_and_dashes():
    resp = MagicMock(status_code=200)
    resp.json.return_value = {"id": "069a79f444e94726a5befca90e38aaf5", "name": "Notch"}
    with patch.object(pi.requests, "get", return_value=resp):
        assert pi.mojang_profile("notch") == ("069a79f4-44e9-4726-a5be-fca90e38aaf5", "Notch")


def test_mojang_profile_not_found():
    with patch.object(pi.requests, "get", return_value=MagicMock(status_code=404)):
        assert pi.mojang_profile("nobody") is None
