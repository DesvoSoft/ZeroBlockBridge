import json
import zipfile
from unittest.mock import patch

import pytest

from app.services.content_import import (
    ContentImportError, import_world, inspect_modpack, inspect_world, install_modpack,
)


def _zip(path, files: dict):
    with zipfile.ZipFile(path, "w") as zf:
        for name, data in files.items():
            zf.writestr(name, data)
    return str(path)


def _world_folder(base, name="My World"):
    world = base / name
    (world / "region").mkdir(parents=True)
    (world / "level.dat").write_bytes(b"nbt")
    (world / "region" / "r.0.0.mca").write_bytes(b"chunk")
    (world / "session.lock").write_bytes(b"lock")
    return world


# ----------------------------------------------------------------------
# Worlds
# ----------------------------------------------------------------------
def test_world_folder_is_copied_as_world_without_session_lock(tmp_path):
    world = _world_folder(tmp_path)
    server = tmp_path / "srv"
    (server / "world").mkdir(parents=True)  # scaffolded empty world dir

    info = inspect_world(str(world))
    import_world(info, str(server))

    assert info.name == "My World" and not info.is_zip
    assert (server / "world" / "level.dat").read_bytes() == b"nbt"
    assert (server / "world" / "region" / "r.0.0.mca").exists()
    assert not (server / "world" / "session.lock").exists()


def test_world_found_one_level_down(tmp_path):
    _world_folder(tmp_path / "saves", "Survival")
    info = inspect_world(str(tmp_path / "saves"))
    assert info.name == "Survival"


def test_world_zip_with_wrapper_folder(tmp_path):
    archive = _zip(tmp_path / "w.zip", {
        "Skyblock/level.dat": "nbt",
        "Skyblock/region/r.0.0.mca": "chunk",
        "Skyblock/DIM-1/region/r.0.0.mca": "nether",
        "Skyblock/session.lock": "lock",
    })
    server = tmp_path / "srv"
    server.mkdir()

    info = inspect_world(archive)
    import_world(info, str(server))

    assert info.name == "Skyblock" and info.root == "Skyblock/"
    assert (server / "world" / "level.dat").read_text() == "nbt"
    assert (server / "world" / "DIM-1" / "region" / "r.0.0.mca").read_text() == "nether"
    assert not (server / "world" / "session.lock").exists()


def test_world_zip_at_root_takes_zip_name(tmp_path):
    archive = _zip(tmp_path / "Hardcore.zip", {"level.dat": "nbt"})
    assert inspect_world(archive).name == "Hardcore"


def test_folder_without_level_dat_is_rejected(tmp_path):
    (tmp_path / "empty").mkdir()
    with pytest.raises(ContentImportError, match="level.dat"):
        inspect_world(str(tmp_path / "empty"))


def test_world_zip_slip_is_rejected(tmp_path):
    archive = _zip(tmp_path / "evil.zip", {"level.dat": "nbt", "../../evil.txt": "x"})
    server = tmp_path / "a" / "srv"
    server.mkdir(parents=True)
    with pytest.raises(ContentImportError):
        import_world(inspect_world(archive), str(server))
    assert not (tmp_path / "evil.txt").exists()


# ----------------------------------------------------------------------
# Modpacks
# ----------------------------------------------------------------------
def _mrpack(tmp_path, deps, files=None, name="Cool Pack"):
    manifest = {"formatVersion": 1, "game": "minecraft", "name": name,
                "dependencies": deps, "files": files or []}
    return _zip(tmp_path / "pack.mrpack", {
        "modrinth.index.json": json.dumps(manifest),
        "overrides/config/a.toml": "client",
        "server-overrides/config/a.toml": "server",
    })


def test_mrpack_reports_loader_version_and_server_mods(tmp_path):
    files = [
        {"path": "mods/a.jar", "env": {"server": "required"}},
        {"path": "mods/b.jar", "env": {"server": "unsupported"}},
        {"path": "mods/c.jar"},
    ]
    info = inspect_modpack(_mrpack(tmp_path, {"minecraft": "1.20.1", "fabric-loader": "0.15.7"}, files))

    assert (info.kind, info.name, info.loader, info.loader_version, info.mc_version, info.mod_count) == \
        ("mrpack", "Cool Pack", "Fabric", "0.15.7", "1.20.1", 2)
    assert info.describe() == "Fabric 0.15.7 · Minecraft 1.20.1 · 2 mods"


def test_mrpack_for_unsupported_loader_is_rejected(tmp_path):
    with pytest.raises(ContentImportError, match="NeoForge"):
        inspect_modpack(_mrpack(tmp_path, {"minecraft": "1.21.1", "neoforge": "21.1.1"}))


def test_mrpack_install_applies_server_overrides_last(tmp_path):
    path = _mrpack(tmp_path, {"minecraft": "1.20.1", "fabric-loader": "0.15.7"})
    server = tmp_path / "srv"
    server.mkdir()

    summary = install_modpack(inspect_modpack(path), str(server), "Fabric", "1.20.1")

    assert (server / "config" / "a.toml").read_text() == "server"
    assert summary.startswith("0 mods installed")


def test_curseforge_client_export_points_to_server_pack(tmp_path):
    archive = _zip(tmp_path / "cf.zip", {
        "manifest.json": json.dumps({"manifestType": "minecraftModpack", "minecraft": {"version": "1.20.1"}}),
        "overrides/config/x.toml": "x",
    })
    with pytest.raises(ContentImportError, match="Server Pack"):
        inspect_modpack(archive)


def test_forge_server_pack_detected_from_libraries(tmp_path):
    archive = _zip(tmp_path / "ATM9-server.zip", {
        "Server Files/mods/a.jar": "a",
        "Server Files/mods/b.jar": "b",
        "Server Files/libraries/net/minecraftforge/forge/1.20.1-47.2.0/forge-1.20.1-47.2.0-server.jar": "f",
        "Server Files/config/c.toml": "c",
        "Server Files/run.bat": "java ...",
        "Server Files/server.properties": "level-type=skyblock",
    })
    info = inspect_modpack(archive)

    assert (info.kind, info.loader, info.mc_version, info.loader_version, info.mod_count, info.root) == \
        ("serverpack", "Forge", "1.20.1", "47.2.0", 2, "Server Files/")
    assert info.notes == []


def test_server_pack_variables_txt_wins(tmp_path):
    archive = _zip(tmp_path / "pack.zip", {
        "mods/a.jar": "a",
        "variables.txt": "MINECRAFT_VERSION=1.19.2\nMODLOADER=Forge\nMODLOADER_VERSION=43.3.0\n",
    })
    info = inspect_modpack(archive)
    assert (info.loader, info.mc_version, info.loader_version) == ("Forge", "1.19.2", "43.3.0")


def test_fabric_server_pack_detected(tmp_path):
    archive = _zip(tmp_path / "pack.zip", {
        "mods/a.jar": "a",
        "fabric-server-launch.jar": "x",
        "libraries/net/fabricmc/fabric-loader/0.14.21/fabric-loader-0.14.21.jar": "l",
        "libraries/net/fabricmc/intermediary/1.20.1/intermediary-1.20.1.jar": "i",
    })
    info = inspect_modpack(archive)
    assert (info.loader, info.loader_version, info.mc_version) == ("Fabric", "0.14.21", "1.20.1")


def test_unknown_server_pack_asks_user_to_pick(tmp_path):
    info = inspect_modpack(_zip(tmp_path / "pack.zip", {"mods/a.jar": "a"}))
    assert info.loader is None and info.mc_version is None
    assert info.notes


def test_zip_without_mods_is_rejected(tmp_path):
    with pytest.raises(ContentImportError, match="mods/"):
        inspect_modpack(_zip(tmp_path / "x.zip", {"readme.txt": "hi"}))


def test_server_pack_copy_skips_launchers_and_libraries(tmp_path):
    archive = _zip(tmp_path / "pack.zip", {
        "Pack/mods/a.jar": "a",
        "Pack/config/c.toml": "c",
        "Pack/server.properties": "level-type=skyblock",
        "Pack/forge-1.20.1-47.2.0-installer.jar": "installer",
        "Pack/run.bat": "java",
        "Pack/start.sh": "java",
        "Pack/eula.txt": "eula=false",
        "Pack/libraries/net/minecraftforge/forge/1.20.1-47.2.0/x.jar": "lib",
    })
    server = tmp_path / "srv"
    server.mkdir()

    install_modpack(inspect_modpack(archive), str(server), "Forge", "1.20.1")

    assert (server / "mods" / "a.jar").read_text() == "a"
    assert (server / "config" / "c.toml").exists()
    assert (server / "server.properties").read_text() == "level-type=skyblock"
    for skipped in ("forge-1.20.1-47.2.0-installer.jar", "run.bat", "start.sh", "eula.txt", "libraries"):
        assert not (server / skipped).exists(), skipped


def test_not_a_zip_is_rejected(tmp_path):
    bogus = tmp_path / "pack.mrpack"
    bogus.write_text("nope")
    with pytest.raises(ContentImportError, match="zip"):
        inspect_modpack(str(bogus))


# ----------------------------------------------------------------------
# Provisioning wiring
# ----------------------------------------------------------------------
def test_provisioning_installs_modpack_then_world_with_pinned_loader(tmp_path):
    from tests.test_provisioning import _Env
    from contextlib import ExitStack

    world = _world_folder(tmp_path / "saves")
    pack = _zip(tmp_path / "pack.zip", {
        "mods/a.jar": "a",
        "variables.txt": "MINECRAFT_VERSION=1.20.1\nMODLOADER=Forge\nMODLOADER_VERSION=47.2.0\n",
    })
    with ExitStack() as stack:
        env = _Env(tmp_path, stack)
        calls = []

        def fake_forge(name, version, progress_cb, java_bin="java", loader_version=None):
            calls.append((version, loader_version))
            d = env.servers_dir / name
            d.mkdir(parents=True, exist_ok=True)
            (d / "server.jar").write_bytes(b"jar")
            return "server.jar"
        env.install_forge.side_effect = fake_forge

        result = env.run(type="Forge", version="1.20.1", modpack_path=pack,
                         loader_version="47.2.0", world_path=str(world))

    srv = env.servers_dir / "srv"
    assert result.ok, result.error
    assert calls == [("1.20.1", "47.2.0")]
    assert (srv / "mods" / "a.jar").exists()
    assert (srv / "world" / "level.dat").exists()
    assert any("Modpack ready" in line for line in env.lines)
    assert env.progress == sorted(env.progress)


def test_provisioning_fails_cleanly_on_bad_modpack(tmp_path):
    from tests.test_provisioning import _Env
    from contextlib import ExitStack

    bogus = tmp_path / "x.zip"
    bogus.write_text("nope")
    with ExitStack() as stack:
        env = _Env(tmp_path, stack)
        with patch("app.core.provisioning.logger"):
            result = env.run(type="Fabric", version="1.20.1", modpack_path=str(bogus))
    assert not result.ok and "zip" in result.error


def test_modpack_ram_suggestion():
    from app.ui.server_wizard import modpack_ram_mb
    assert modpack_ram_mb(2048, 50, 16384) == 4096
    assert modpack_ram_mb(2048, 300, 16384) == 6144
    assert modpack_ram_mb(8192, 300, 16384) == 8192   # never lowers
    assert modpack_ram_mb(2048, 300, 6144) == 4096    # leaves 2 GB to the system
