import json
import os
import pytest

import app.services.migration as migration


def _make_server(servers_dir, name, with_jar=True, with_logs=True):
    server_dir = os.path.join(servers_dir, name)
    os.makedirs(os.path.join(server_dir, "world"), exist_ok=True)
    with open(os.path.join(server_dir, "world", "level.dat"), "w", encoding="utf-8") as f:
        f.write("worlddata")
    with open(os.path.join(server_dir, "server.properties"), "w", encoding="utf-8") as f:
        f.write("level-name=world\n")
    with open(os.path.join(server_dir, "metadata.json"), "w", encoding="utf-8") as f:
        json.dump({"type": "Paper", "version": "1.21.1"}, f)
    if with_jar:
        with open(os.path.join(server_dir, "server.jar"), "wb") as f:
            f.write(b"fakejar")
    if with_logs:
        os.makedirs(os.path.join(server_dir, "logs"), exist_ok=True)
        with open(os.path.join(server_dir, "logs", "latest.log"), "w", encoding="utf-8") as f:
            f.write("log line\n")
    return server_dir


def test_export_server_missing_raises(tmp_path, monkeypatch):
    monkeypatch.setattr(migration, "SERVERS_DIR", str(tmp_path))
    with pytest.raises(migration.MigrationError):
        migration.export_server("nonexistent", str(tmp_path / "out.zbbpack"))


def test_export_excludes_jar_and_logs(tmp_path, monkeypatch):
    monkeypatch.setattr(migration, "SERVERS_DIR", str(tmp_path))
    monkeypatch.setattr(migration, "get_server_meta", lambda name: {"type": "Paper", "version": "1.21.1"})
    _make_server(tmp_path, "myserver")

    dest = str(tmp_path / "myserver.zbbpack")
    migration.export_server("myserver", dest)

    import zipfile
    with zipfile.ZipFile(dest) as zf:
        names = zf.namelist()
        assert "world/level.dat" in names
        assert "server.properties" in names
        assert "metadata.json" in names
        assert not any(n.endswith(".jar") for n in names)
        assert not any(n.startswith("logs/") for n in names)


def test_export_import_round_trip(tmp_path, monkeypatch):
    monkeypatch.setattr(migration, "SERVERS_DIR", str(tmp_path))
    monkeypatch.setattr(migration, "get_server_meta", lambda name: {"type": "Paper", "version": "1.21.1"})
    _make_server(tmp_path, "myserver")

    dest = str(tmp_path / "myserver.zbbpack")
    migration.export_server("myserver", dest)
    meta = migration.import_server(dest, "imported-server")

    assert meta["type"] == "Paper"
    imported_dir = os.path.join(tmp_path, "imported-server")
    assert os.path.exists(os.path.join(imported_dir, "world", "level.dat"))
    assert os.path.exists(os.path.join(imported_dir, "server.properties"))
    assert not os.path.exists(os.path.join(imported_dir, "server.jar"))


def test_import_existing_server_raises(tmp_path, monkeypatch):
    monkeypatch.setattr(migration, "SERVERS_DIR", str(tmp_path))
    monkeypatch.setattr(migration, "get_server_meta", lambda name: {"type": "Paper"})
    _make_server(tmp_path, "myserver")
    dest = str(tmp_path / "myserver.zbbpack")
    migration.export_server("myserver", dest)

    with pytest.raises(migration.MigrationError):
        migration.import_server(dest, "myserver")


def test_import_invalid_zip_raises(tmp_path, monkeypatch):
    monkeypatch.setattr(migration, "SERVERS_DIR", str(tmp_path))
    bad_file = tmp_path / "notazip.zbbpack"
    bad_file.write_text("not a zip")
    with pytest.raises(migration.MigrationError):
        migration.import_server(str(bad_file), "newserver")
