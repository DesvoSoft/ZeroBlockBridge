import json
import zipfile
from contextlib import ExitStack
from unittest.mock import MagicMock, patch

import pytest

from app.services import content_import
from tests.test_provisioning import _Env

from app.services.content_import import (
    ContentImportError, ModpackInfo, import_world, inspect_modpack, inspect_world, install_modpack,
    modpack_mismatch,
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
    with pytest.raises(ContentImportError, match="Quilt"):
        inspect_modpack(_mrpack(tmp_path, {"minecraft": "1.21.1", "quilt-loader": "0.26.0"}))


def test_neoforge_mrpack_pins_its_build(tmp_path):
    info = inspect_modpack(_mrpack(tmp_path, {"minecraft": "1.21.1", "neoforge": "21.1.77"}))
    assert (info.loader, info.mc_version, info.pinned_loader_version) == ("NeoForge", "1.21.1", "21.1.77")


def test_mrpack_install_applies_server_overrides_last(tmp_path):
    path = _mrpack(tmp_path, {"minecraft": "1.20.1", "fabric-loader": "0.15.7"})
    server = tmp_path / "srv"
    server.mkdir()

    result = install_modpack(inspect_modpack(path), str(server), "Fabric", "1.20.1")

    assert (server / "config" / "a.toml").read_text() == "server"
    assert result.summary.startswith("0 mods installed") and result.failed == 0


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


def test_provisioning_rejects_bad_modpack_before_creating_anything(tmp_path):
    bogus = tmp_path / "x.zip"
    bogus.write_text("nope")
    with ExitStack() as stack:
        env = _Env(tmp_path, stack)
        result = env.run(type="Fabric", version="1.20.1", modpack_path=str(bogus))
    assert not result.ok and "zip" in result.error
    env.install_fabric.assert_not_called()
    assert not (env.servers_dir / "srv").exists()


def test_modpack_ram_suggestion():
    from app.ui.server_wizard import modpack_ram_mb
    assert modpack_ram_mb(2048, 50, 16384) == 4096
    assert modpack_ram_mb(2048, 300, 16384) == 6144
    assert modpack_ram_mb(8192, 300, 16384) == 8192   # never lowers
    assert modpack_ram_mb(2048, 300, 6144) == 4096    # leaves 2 GB to the system



# ----------------------------------------------------------------------
# Review fixes: detection
# ----------------------------------------------------------------------
@pytest.mark.parametrize("jar, mc, forge", [
    ("forge-1.12.2-14.23.5.2860.jar", "1.12.2", "14.23.5.2860"),
    ("forge-1.12.2-14.23.5.2860-universal.jar", "1.12.2", "14.23.5.2860"),
    ("forge-1.20.1-47.2.0-installer.jar", "1.20.1", "47.2.0"),
])
def test_forge_root_jar_detected_anywhere_in_the_archive(tmp_path, jar, mc, forge):
    # Not first and not last entry: the regex must match per name.
    archive = _zip(tmp_path / "pack.zip", {"mods/a.jar": "a", jar: "j", "run.bat": "java"})
    info = inspect_modpack(archive)
    assert (info.loader, info.mc_version, info.loader_version) == ("Forge", mc, forge)
    assert info.pinned_loader_version == forge


@pytest.mark.parametrize("marker", [
    "libraries/net/neoforged/neoforge/20.4.237/neoforge-20.4.237-universal.jar",
    "neoforge-21.1.77-installer.jar",
])
def test_neoforge_server_pack_is_detected_with_its_build(tmp_path, marker):
    """Was rejected before NeoForge support; the build number carries the
    Minecraft version (20.4.237 -> 1.20.4, 21.1.77 -> 1.21.1)."""
    archive = _zip(tmp_path / "pack.zip", {"mods/a.jar": "a", marker: "x", "run.sh": "java"})
    info = inspect_modpack(archive)
    build = "20.4.237" if "20.4" in marker else "21.1.77"
    assert (info.loader, info.loader_version) == ("NeoForge", build)
    assert info.mc_version == ("1.20.4" if build.startswith("20.4") else "1.21.1")
    assert info.notes == []


def test_wrapper_folder_with_readme_and_macosx_junk(tmp_path):
    archive = _zip(tmp_path / "pack.zip", {
        "README.txt": "hi",
        "__MACOSX/Pack/mods/._a.jar": "junk",
        "Pack/mods/a.jar": "a",
        "Pack/config/c.toml": "c",
    })
    info = inspect_modpack(archive)
    assert info.root == "Pack/" and info.mod_count == 1

    server = tmp_path / "srv"
    server.mkdir()
    install_modpack(info, str(server), "Forge", "1.20.1")
    assert (server / "mods" / "a.jar").exists()
    assert not (server / "__MACOSX").exists() and not (server / "Pack").exists()


def test_variables_without_mc_version_fill_it_from_libraries(tmp_path):
    archive = _zip(tmp_path / "pack.zip", {
        "mods/a.jar": "a",
        "variables.txt": "MODLOADER=forge\nMODLOADER_VERSION=47.2.0\n",
        "libraries/net/minecraftforge/forge/1.20.1-47.2.0/x.jar": "l",
    })
    info = inspect_modpack(archive)
    assert (info.loader, info.mc_version, info.pinned_loader_version) == ("Forge", "1.20.1", "47.2.0")


def test_loader_version_is_not_pinned_without_mc_version(tmp_path):
    archive = _zip(tmp_path / "pack.zip", {
        "mods/a.jar": "a",
        "variables.txt": "MODLOADER=forge\nMODLOADER_VERSION=47.2.0\n",
    })
    info = inspect_modpack(archive)
    assert info.loader == "Forge" and info.mc_version is None
    assert info.pinned_loader_version is None
    assert info.notes


def test_full_forge_build_in_variables_is_trimmed(tmp_path):
    archive = _zip(tmp_path / "pack.zip", {
        "mods/a.jar": "a",
        "variables.txt": "MINECRAFT_VERSION=1.20.1\nMODLOADER=Forge\nMODLOADER_VERSION=1.20.1-47.2.0\n",
    })
    assert inspect_modpack(archive).pinned_loader_version == "47.2.0"


def test_curseforge_client_export_with_override_mods_points_to_server_pack(tmp_path):
    archive = _zip(tmp_path / "cf.zip", {
        "manifest.json": json.dumps({"manifestType": "minecraftModpack"}),
        "overrides/mods/bundled.jar": "x",
        "overrides/config/c.toml": "c",
    })
    with pytest.raises(ContentImportError, match="CurseForge client"):
        inspect_modpack(archive)


def test_fabric_launcher_properties_from_pack_is_not_copied(tmp_path):
    archive = _zip(tmp_path / "pack.zip", {
        "mods/a.jar": "a",
        "fabric-server-launch.jar": "x",
        "fabric-server-launcher.properties": "serverJar=minecraft_server.1.20.1.jar",
    })
    server = tmp_path / "srv"
    server.mkdir()
    install_modpack(inspect_modpack(archive), str(server), "Fabric", "1.20.1")
    assert not (server / "fabric-server-launcher.properties").exists()


# ----------------------------------------------------------------------
# Review fixes: archive safety
# ----------------------------------------------------------------------
@pytest.mark.parametrize("bad", ["config/CON", "config/aux.txt", "config/a:b.toml", "mods/trailing."])
def test_windows_invalid_names_rejected_before_copying(tmp_path, bad):
    archive = _zip(tmp_path / "pack.zip", {"mods/a.jar": "a", bad: "x"})
    server = tmp_path / "srv"
    server.mkdir()
    with pytest.raises(ContentImportError, match="Windows can't create"):
        install_modpack(inspect_modpack(archive), str(server), "Forge", "1.20.1")
    assert list(server.iterdir()) == []  # nothing half-copied


def test_oversized_archive_rejected(tmp_path, monkeypatch):
    monkeypatch.setattr(content_import, "MAX_UNPACKED_BYTES", 10)
    archive = _zip(tmp_path / "w.zip", {"level.dat": "x" * 50})
    with pytest.raises(ContentImportError, match="limit"):
        content_import.validate_world(inspect_world(archive), str(tmp_path))


def test_archive_larger_than_free_space_rejected(tmp_path, monkeypatch):
    monkeypatch.setattr(content_import.shutil, "disk_usage", lambda p: type("U", (), {"free": 100})())
    archive = _zip(tmp_path / "w.zip", {"level.dat": "x" * 50})
    with pytest.raises(ContentImportError, match="disk space"):
        content_import.validate_world(inspect_world(archive), str(tmp_path / "not" / "yet"))


def test_world_imports_into_custom_level_name_and_rejects_traversal(tmp_path):
    archive = _zip(tmp_path / "w.zip", {"level.dat": "nbt", "__MACOSX/._level.dat": "junk"})
    server = tmp_path / "srv"
    server.mkdir()
    info = inspect_world(archive)
    import_world(info, str(server), level_name="SkyWorld")
    assert (server / "SkyWorld" / "level.dat").read_text() == "nbt"
    with pytest.raises(ContentImportError):
        import_world(info, str(server), level_name="../escape")
    with pytest.raises(ContentImportError):
        import_world(info, str(server), level_name=".")


def test_mrpack_failed_downloads_are_counted(tmp_path):
    path = _mrpack(tmp_path, {"minecraft": "1.20.1", "fabric-loader": "0.15.7"},
                   [{"path": "mods/a.jar", "downloads": ["https://x/a.jar"], "hashes": {}}])
    server = tmp_path / "srv"
    server.mkdir()
    with patch("app.services.mrpack_installer.download_with_verification", return_value=(False, None, "404")):
        result = install_modpack(inspect_modpack(path), str(server), "Fabric", "1.20.1")
    assert result.failed == 1 and "1 failed" in result.summary


def test_modpack_mismatch_messages():
    info = ModpackInfo(path="p", kind="mrpack", name="P", mc_version="1.20.1", loader="Fabric")
    assert modpack_mismatch(info, "Fabric", "1.20.1") is None
    assert "Fabric server" in modpack_mismatch(info, "Forge", "1.20.1")
    assert "Minecraft 1.20.1" in modpack_mismatch(info, "Fabric", "1.21")
    assert "Fabric, Forge or NeoForge" in modpack_mismatch(info, "Paper", "1.20.1")


# ----------------------------------------------------------------------
# Review fixes: provisioning
# ----------------------------------------------------------------------
def _pack_zip(tmp_path, props=None, mc="1.20.1"):
    files = {"mods/a.jar": "a",
             "variables.txt": f"MINECRAFT_VERSION={mc}\nMODLOADER=Forge\nMODLOADER_VERSION=47.2.0\n"}
    if props:
        files["server.properties"] = props
    return _zip(tmp_path / "pack.zip", files)


def test_mismatched_modpack_fails_before_jar_install(tmp_path):
    with ExitStack() as stack:
        env = _Env(tmp_path, stack)
        result = env.run(type="Forge", version="1.21.1", modpack_path=_pack_zip(tmp_path))
    assert not result.ok and "Minecraft 1.20.1" in result.error
    env.install_forge.assert_not_called()
    assert not (env.servers_dir / "srv").exists()


def test_failure_after_jar_install_rolls_back_server_dir(tmp_path):
    world = _world_folder(tmp_path / "saves")
    with ExitStack() as stack:
        env = _Env(tmp_path, stack)
        stack.enter_context(patch("app.services.content_import.import_world", side_effect=OSError("disk full")))
        result = env.run(world_path=str(world))
    assert not result.ok and "disk full" in result.error
    assert not (env.servers_dir / "srv").exists()
    assert any("Removed the partially created server" in line for line in env.lines)


def test_rollback_keeps_a_custom_folder_that_already_existed(tmp_path):
    custom = tmp_path / "elsewhere"
    (custom / "srv").mkdir(parents=True)
    (custom / "srv" / "mine.txt").write_text("user data")
    with ExitStack() as stack:
        env = _Env(tmp_path, stack)
        env.download.side_effect = lambda *a, **k: None
        result = env.run(location=str(custom))
    assert not result.ok
    assert (custom / "srv" / "mine.txt").read_text() == "user data"


def test_rollback_removes_a_custom_folder_it_created(tmp_path):
    custom = tmp_path / "elsewhere"
    with ExitStack() as stack:
        env = _Env(tmp_path, stack)
        env.download.side_effect = lambda *a, **k: None
        result = env.run(location=str(custom))
    assert not result.ok
    assert not (custom / "srv").exists()


def test_duplicate_name_never_deletes_the_existing_server(tmp_path):
    with ExitStack() as stack:
        env = _Env(tmp_path, stack)
        (env.servers_dir / "srv").mkdir()
        (env.servers_dir / "srv" / "world.dat").write_text("precious")
        result = env.run()
    assert not result.ok and "already exists" in result.error
    assert (env.servers_dir / "srv" / "world.dat").read_text() == "precious"


def test_wizard_settings_win_over_pack_properties_and_world_follows_level_name(tmp_path):
    world = _world_folder(tmp_path / "saves")
    pack = _pack_zip(tmp_path, props="gamemode=creative\nlevel-name=SkyWorld\nlevel-type=skyblock\n")
    with ExitStack() as stack:
        env = _Env(tmp_path, stack)
        result = env.run(type="Forge", version="1.20.1", modpack_path=pack, world_path=str(world),
                         game_mode="survival")
    assert result.ok, result.error
    assert env.scaffold.call_args.kwargs["override_existing"] is True
    assert (env.servers_dir / "srv" / "SkyWorld" / "level.dat").exists()


def test_scaffold_override_existing_replaces_only_wizard_keys(tmp_path):
    from app.services.scaffolder import pre_boot_scaffold
    props = tmp_path / "server.properties"
    props.write_text("gamemode=creative\nlevel-type=skyblock\nmotd=Pack MOTD\n", encoding="utf-8")

    pre_boot_scaffold(str(tmp_path), port=25570, config={"game_mode": "adventure"}, override_existing=True)

    text = props.read_text(encoding="utf-8")
    assert "gamemode=adventure" in text and "gamemode=creative" not in text
    assert "level-type=skyblock" in text and "motd=Pack MOTD" in text
    assert "server-port=25570" in text


def test_scaffold_override_keeps_pack_values_for_untouched_wizard_defaults(tmp_path):
    """Review N1: the wizard always sends every key; defaults the user never
    changed (allow-flight=false, view-distance=10...) must not clobber a
    pack's tuning, or jetpack/flight mods get players kicked."""
    from app.services.scaffolder import PROPERTY_DEFAULTS, pre_boot_scaffold
    props = tmp_path / "server.properties"
    props.write_text("allow-flight=true\nview-distance=6\nmax-players=50\ngamemode=adventure\n"
                     "difficulty=peaceful\nlevel-seed=\n", encoding="utf-8")
    config = dict(PROPERTY_DEFAULTS, difficulty="hard", seed="12345")

    pre_boot_scaffold(str(tmp_path), port=25565, config=config, override_existing=True)

    text = props.read_text(encoding="utf-8")
    for kept in ("allow-flight=true", "view-distance=6", "max-players=50", "gamemode=adventure"):
        assert kept in text, kept
    assert "difficulty=hard" in text            # changed by the user: wins
    assert "level-seed=12345" in text           # typed by the user: wins
    assert "level-seed=\n" not in text


def test_wizard_defaults_come_from_the_scaffolder():
    """One source of truth, so 'did the user change it?' can't drift."""
    import inspect
    from app.api.creation import CreationApi
    from app.services.scaffolder import PROPERTY_DEFAULTS
    from app.ui import server_wizard
    assert "**self.creation.property_defaults()" in inspect.getsource(server_wizard.ServerWizard.__init__)
    assert CreationApi.property_defaults() == PROPERTY_DEFAULTS


def test_same_name_claimed_atomically(tmp_path):
    """Review N3: a second creation with the same name must fail up front
    instead of sharing (and on rollback deleting) the first run's folder."""
    from app.core.provisioning import ServerProvisioner
    servers = tmp_path / "servers"
    prov = ServerProvisioner(log=lambda m: None, get_server_port=lambda n: 25565,
                             create_tunnel=lambda n: None, jdk_manager=MagicMock(),
                             servers_dir=str(servers))
    prov._created = []
    assert prov._prepare_location({"name": "srv", "location": str(servers)}) is None
    assert (servers / "srv").is_dir()
    other = ServerProvisioner(log=lambda m: None, get_server_port=lambda n: 25565,
                              create_tunnel=lambda n: None, jdk_manager=MagicMock(),
                              servers_dir=str(servers))
    other._created = []
    assert "already exists" in other._prepare_location({"name": "srv", "location": str(servers)})
    assert other._created == []


def test_scaffold_keeps_existing_values_without_override(tmp_path):
    from app.services.scaffolder import pre_boot_scaffold
    props = tmp_path / "server.properties"
    props.write_text("gamemode=creative\nserver-port=1\n", encoding="utf-8")
    pre_boot_scaffold(str(tmp_path), port=25570, config={"game_mode": "survival"})
    text = props.read_text(encoding="utf-8")
    assert "gamemode=creative" in text and "server-port=25570" in text


def test_failed_mod_downloads_become_a_warning(tmp_path):
    with ExitStack() as stack:
        env = _Env(tmp_path, stack)
        stack.enter_context(patch("app.services.content_import.install_modpack",
                                  return_value=content_import.ModpackInstall("1 mods installed", failed=2)))
        result = env.run(type="Forge", version="1.20.1", modpack_path=_pack_zip(tmp_path))
    assert result.ok
    assert result.warnings and "2 mods from the modpack" in result.warnings[0]


def test_tunnel_failure_keeps_the_server_with_a_warning(tmp_path):
    with ExitStack() as stack:
        env = _Env(tmp_path, stack)
        env.provisioner._create_tunnel = lambda name: (_ for _ in ()).throw(RuntimeError("playit down"))
        result = env.run()
    assert result.ok and "playit down" in result.warnings[0]
    assert (env.servers_dir / "srv").exists()


# ----------------------------------------------------------------------
# Review fixes: wizard validation helpers
# ----------------------------------------------------------------------
def test_modpack_step_error_enforces_engine_and_version():
    from app.ui.server_wizard import modpack_step_error
    base = {"modpack_path": "p", "modpack_loader": "Forge", "modpack_mc": "1.20.1",
            "type": "Forge", "version": "1.20.1"}
    assert modpack_step_error(base) is None
    assert modpack_step_error({**base, "modpack_path": None, "type": "Paper"}) is None
    assert "1.20.1" in modpack_step_error({**base, "version": "1.21.4"})
    assert "Forge server" in modpack_step_error({**base, "type": "Fabric"})
    assert "Fabric, Forge or NeoForge" in modpack_step_error({**base, "type": "Vanilla", "modpack_loader": None})


def test_world_step_error_blocks_import_without_a_world():
    from app.ui.server_wizard import world_step_error
    assert world_step_error("new", None, False) is None
    assert world_step_error("import", "C:/w", False) is None
    assert "Choose a world" in world_step_error("import", None, False)
    assert "Still reading" in world_step_error("import", None, True)


def test_version_sort_key_orders_numerically():
    from app.ui.server_wizard import version_sort_key
    assert sorted(["1.9", "1.20.1", "1.21-pre1", "26.1"], key=version_sort_key) == \
        ["1.9", "1.20.1", "1.21-pre1", "26.1"]
