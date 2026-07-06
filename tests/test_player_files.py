import app.services.player_files as player_files


def test_load_json_list_missing_file(tmp_path, monkeypatch):
    monkeypatch.setattr(player_files, "SERVERS_DIR", tmp_path)
    assert player_files.load_json_list("myserver", "whitelist.json") == []


def test_save_and_load_round_trip(tmp_path, monkeypatch):
    monkeypatch.setattr(player_files, "SERVERS_DIR", tmp_path)
    entries = [{"uuid": "", "name": "Steve"}]
    player_files.save_json_list("myserver", "whitelist.json", entries)
    assert player_files.load_json_list("myserver", "whitelist.json") == entries


def test_add_entry_appends(tmp_path, monkeypatch):
    monkeypatch.setattr(player_files, "SERVERS_DIR", tmp_path)
    player_files.add_entry("myserver", "ops.json", {"uuid": "", "name": "Alex", "level": 4})
    player_files.add_entry("myserver", "ops.json", {"uuid": "", "name": "Steve", "level": 2})
    entries = player_files.load_json_list("myserver", "ops.json")
    names = {e["name"] for e in entries}
    assert names == {"Alex", "Steve"}


def test_add_entry_dedups_by_name(tmp_path, monkeypatch):
    monkeypatch.setattr(player_files, "SERVERS_DIR", tmp_path)
    player_files.add_entry("myserver", "ops.json", {"uuid": "", "name": "Alex", "level": 2})
    player_files.add_entry("myserver", "ops.json", {"uuid": "", "name": "Alex", "level": 4})
    entries = player_files.load_json_list("myserver", "ops.json")
    assert len(entries) == 1
    assert entries[0]["level"] == 4


def test_remove_entry(tmp_path, monkeypatch):
    monkeypatch.setattr(player_files, "SERVERS_DIR", tmp_path)
    player_files.add_entry("myserver", "banned-players.json", {"uuid": "", "name": "Griefer"})
    player_files.remove_entry("myserver", "banned-players.json", "Griefer")
    assert player_files.load_json_list("myserver", "banned-players.json") == []


def test_load_json_list_handles_corrupt_json(tmp_path, monkeypatch):
    monkeypatch.setattr(player_files, "SERVERS_DIR", tmp_path)
    server_dir = tmp_path / "myserver"
    server_dir.mkdir()
    (server_dir / "ops.json").write_text("{not valid json", encoding="utf-8")
    assert player_files.load_json_list("myserver", "ops.json") == []
