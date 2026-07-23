"""Unit tests for install_missing_mods (app/services/modrinth.py)."""

from unittest.mock import MagicMock, patch

from app.services.modrinth import ModrinthClient, ModrinthException, install_missing_mods


def _make_client():
    return MagicMock(spec=ModrinthClient)


@patch("app.services.modrinth.mod_install_tracker.record_install")
def test_all_resolved_and_installed_with_dedup(mock_record):
    client = _make_client()
    client.get_versions.return_value = [{"id": "v1"}]
    client.download_mod.return_value = "/servers/TEST/mods/fabric-api-1.0.0.jar"

    result = install_missing_mods(
        client, ["fabric-api-base", "fabric-lifecycle-events-v1"], "TEST", "1.20.1", "fabric",
    )

    # Both ids resolve to the same slug -- only the first is installed, the
    # second is silently skipped as a duplicate (not downloaded twice).
    assert result["installed"] == ["fabric-api-base -> fabric-api-1.0.0.jar"]
    assert result["failed"] == []
    assert result["unresolved"] == []
    client.get_versions.assert_called_once()
    client.download_mod.assert_called_once()
    mock_record.assert_called_once_with("TEST", "fabric-api", "fabric-api-1.0.0.jar")


@patch("app.services.modrinth.mod_install_tracker.record_install")
def test_search_fallback_success(mock_record):
    client = _make_client()
    client.search.return_value = {"hits": [{"slug": "some-mod"}]}
    client.get_versions.return_value = [{"id": "v1"}]
    client.download_mod.return_value = "/servers/TEST/mods/some-mod.jar"

    result = install_missing_mods(client, ["totally-unknown-id"], "TEST", "1.20.1", "fabric")

    assert result["installed"] == ["totally-unknown-id -> some-mod.jar"]
    client.search.assert_called_once()


def test_search_fallback_no_hits_is_unresolved():
    client = _make_client()
    client.search.return_value = {"hits": []}

    result = install_missing_mods(client, ["totally-unknown-id"], "TEST", "1.20.1", "fabric")

    assert result["unresolved"] == ["totally-unknown-id"]
    assert result["installed"] == []
    assert result["failed"] == []


def test_search_fallback_raises_modrinth_exception_is_unresolved():
    client = _make_client()
    client.search.side_effect = ModrinthException("boom")

    result = install_missing_mods(client, ["totally-unknown-id"], "TEST", "1.20.1", "fabric")

    assert result["unresolved"] == ["totally-unknown-id"]


def test_failed_when_no_compatible_version():
    client = _make_client()
    client.get_versions.return_value = []

    result = install_missing_mods(client, ["fabric-api-base"], "TEST", "1.20.1", "fabric")

    assert result["failed"] == ["fabric-api-base"]
    assert result["installed"] == []
    assert result["unresolved"] == []


def test_failed_when_download_returns_none():
    client = _make_client()
    client.get_versions.return_value = [{"id": "v1"}]
    client.download_mod.return_value = None

    result = install_missing_mods(client, ["fabric-api-base"], "TEST", "1.20.1", "fabric")

    assert result["failed"] == ["fabric-api-base"]


def test_modrinth_exception_during_install_is_caught_as_failed():
    client = _make_client()
    client.get_versions.side_effect = ModrinthException("rate limited")

    result = install_missing_mods(client, ["fabric-api-base"], "TEST", "1.20.1", "fabric")

    assert result["failed"] == ["fabric-api-base"]


def test_empty_input_makes_no_calls():
    client = _make_client()

    result = install_missing_mods(client, [], "TEST", "1.20.1", "fabric")

    assert result == {"installed": [], "failed": [], "unresolved": []}
    client.search.assert_not_called()
    client.get_versions.assert_not_called()
    client.download_mod.assert_not_called()
