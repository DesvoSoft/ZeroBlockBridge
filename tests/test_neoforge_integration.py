"""NeoForge around existing servers: modpacks, folder import, mods."""
import json
import zipfile

import pytest

from app.core.logic import _infer_server_type, infer_server_version
from app.services.content_import import ModpackInfo, inspect_modpack, modpack_mismatch
from app.services.modrinth import MOD_LOADERS, loader_display, loader_for_server_type
from app.services.mrpack_installer import MrpackCompatibilityError, _check_compatibility


def _zip(path, files: dict):
    with zipfile.ZipFile(path, "w") as zf:
        for name, data in files.items():
            zf.writestr(name, data)
    return str(path)


def _mrpack(tmp_path, deps):
    manifest = {"formatVersion": 1, "game": "minecraft", "name": "Neo Pack", "dependencies": deps, "files": []}
    return _zip(tmp_path / "pack.mrpack", {"modrinth.index.json": json.dumps(manifest)})


# ----------------------------------------------------------------------
# Modpacks
# ----------------------------------------------------------------------
def test_neoforge_mrpack_is_accepted_on_a_neoforge_server():
    manifest = {"dependencies": {"minecraft": "1.21.1", "neoforge": "21.1.77"}}
    _check_compatibility(manifest, server_type="NeoForge", mc_version="1.21.1")  # no raise


def test_neoforge_mrpack_on_forge_is_rejected_with_proper_name():
    manifest = {"dependencies": {"minecraft": "1.21.1", "neoforge": "21.1.77"}}
    with pytest.raises(MrpackCompatibilityError, match="requires a NeoForge server"):
        _check_compatibility(manifest, server_type="Forge", mc_version="1.21.1")


def test_neoforge_1_20_1_mrpack_runs_on_forge():
    """NeoForge 1.20.1 is a Forge fork: its packs go to a Forge 1.20.1 server."""
    manifest = {"dependencies": {"minecraft": "1.20.1", "neoforge": "47.1.106"}}
    _check_compatibility(manifest, server_type="Forge", mc_version="1.20.1")  # no raise


def test_neoforge_1_20_1_mrpack_is_inspected_as_forge(tmp_path):
    info = inspect_modpack(_mrpack(tmp_path, {"minecraft": "1.20.1", "neoforge": "47.1.106"}))
    assert (info.loader, info.mc_version, info.pinned_loader_version) == ("Forge", "1.20.1", None)
    assert any("NeoForge 1.20.1" in note for note in info.notes)


def test_legacy_neoforge_server_pack_maps_to_forge(tmp_path):
    archive = _zip(tmp_path / "pack.zip", {
        "mods/a.jar": "a",
        "libraries/net/neoforged/forge/1.20.1-47.1.106/forge-1.20.1-47.1.106-universal.jar": "x",
    })
    info = inspect_modpack(archive)
    assert (info.loader, info.mc_version, info.loader_version) == ("Forge", "1.20.1", None)


def test_beta_neoforge_installer_jar(tmp_path):
    archive = _zip(tmp_path / "pack.zip", {"mods/a.jar": "a", "neoforge-21.6.20-beta-installer.jar": "x"})
    info = inspect_modpack(archive)
    assert (info.loader, info.loader_version, info.mc_version) == ("NeoForge", "21.6.20-beta", "1.21.6")


def test_variables_txt_with_only_a_neoforge_build(tmp_path):
    archive = _zip(tmp_path / "pack.zip", {
        "mods/a.jar": "a",
        "variables.txt": "MODLOADER=NeoForge\nMODLOADER_VERSION=26.1.2.117\n",
    })
    info = inspect_modpack(archive)
    assert (info.loader, info.mc_version, info.loader_version) == ("NeoForge", "26.1.2", "26.1.2.117")
    assert info.notes == []  # the build tells the Minecraft version


def test_unrecognised_neoforge_build_asks_the_user(tmp_path):
    archive = _zip(tmp_path / "pack.zip", {"mods/a.jar": "a", "neoforge-0.25w14craftmine.5-beta-installer.jar": "x"})
    info = inspect_modpack(archive)
    assert info.loader == "NeoForge" and info.mc_version is None and info.notes


def _installer(profile_path: str) -> bytes:
    """An installer jar whose install_profile.json names its maven artifact."""
    import io as _io
    buf = _io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("install_profile.json", json.dumps({"path": profile_path}))
    return buf.getvalue()


@pytest.mark.parametrize("folder", ["", "installer/"])
def test_neoforge_1_20_1_installer_only_pack_is_not_pinned_to_forge(tmp_path, folder):
    """NeoForge 1.20.1's installer is named forge-1.20.1-47.1.x-installer.jar,
    but 47.1.106 isn't a Forge build: pinning it makes the download 404."""
    archive = _zip(tmp_path / "pack.zip", {
        "mods/a.jar": "a",
        f"{folder}forge-1.20.1-47.1.106-installer.jar": _installer("net.neoforged:forge:1.20.1-47.1.106"),
    })
    info = inspect_modpack(archive)
    assert (info.loader, info.mc_version, info.pinned_loader_version) == ("Forge", "1.20.1", None)


def test_real_forge_installer_is_still_pinned(tmp_path):
    archive = _zip(tmp_path / "pack.zip", {
        "mods/a.jar": "a",
        "forge-1.20.1-47.2.0-installer.jar": _installer("net.minecraftforge:forge:1.20.1-47.2.0"),
    })
    info = inspect_modpack(archive)
    assert (info.loader, info.mc_version, info.pinned_loader_version) == ("Forge", "1.20.1", "47.2.0")


def test_variables_with_a_neoforge_1_20_1_build_go_to_forge(tmp_path):
    archive = _zip(tmp_path / "pack.zip", {
        "mods/a.jar": "a",
        "variables.txt": "MODLOADER=NeoForge\nMODLOADER_VERSION=47.1.106\n",
        "libraries/net/neoforged/forge/1.20.1-47.1.106/forge-1.20.1-47.1.106-server.jar": "s",
    })
    info = inspect_modpack(archive)
    assert (info.loader, info.mc_version) == ("Forge", "1.20.1")
    assert modpack_mismatch(info, "Forge", "1.20.1") is None


def test_modpack_mismatch_for_neoforge():
    info = ModpackInfo(path="p", kind="mrpack", name="P", mc_version="1.21.1", loader="NeoForge")
    assert modpack_mismatch(info, "NeoForge", "1.21.1") is None
    assert "NeoForge server" in modpack_mismatch(info, "Forge", "1.21.1")


# ----------------------------------------------------------------------
# Folder import
# ----------------------------------------------------------------------
def test_neoforge_folder_detected_with_version(tmp_path):
    for build in ("21.1.9", "21.1.77"):
        (tmp_path / "libraries/net/neoforged/neoforge" / build).mkdir(parents=True)
    (tmp_path / "run.bat").write_text("java @libraries/...")
    assert _infer_server_type(str(tmp_path)) == "NeoForge"
    assert infer_server_version(str(tmp_path)) == "1.21.1"


def test_neoforge_26x_folder_version(tmp_path):
    (tmp_path / "libraries/net/neoforged/neoforge/26.3.0.77").mkdir(parents=True)
    assert infer_server_version(str(tmp_path)) == "26.3"


def test_root_neoforge_jar_is_not_misread_as_forge(tmp_path):
    """Regression: the "forge" substring matched "neoforge-*.jar"."""
    (tmp_path / "neoforge-21.1.77-installer.jar").write_bytes(b"x")
    assert _infer_server_type(str(tmp_path)) == "NeoForge"


def test_legacy_neoforge_1_20_1_folder_runs_as_forge(tmp_path):
    (tmp_path / "libraries/net/neoforged/forge/1.20.1-47.1.106").mkdir(parents=True)
    assert _infer_server_type(str(tmp_path)) == "Forge"
    assert infer_server_version(str(tmp_path)) == "1.20.1"


def test_quilt_folder_is_not_reported_as_fabric(tmp_path):
    (tmp_path / "libraries/org/quiltmc/quilt-loader/0.26.0").mkdir(parents=True)
    (tmp_path / "libraries/net/fabricmc/intermediary/1.21.1").mkdir(parents=True)
    (tmp_path / "quilt-server-launch.jar").write_bytes(b"x")
    assert _infer_server_type(str(tmp_path)) != "Fabric"
    assert infer_server_version(str(tmp_path)) == "1.21.1"


# ----------------------------------------------------------------------
# Mods (Modrinth)
# ----------------------------------------------------------------------
@pytest.mark.parametrize("server_type, loader", [
    ("NeoForge", "neoforge"), ("Forge", "forge"), ("Fabric", "fabric"),
    ("Paper", "paper"), ("Purpur", "purpur"), ("Vanilla", None), (None, None), ("Quilt", None),
])
def test_loader_for_server_type(server_type, loader):
    assert loader_for_server_type(server_type) == loader


def test_neoforge_loads_mods_and_displays_properly():
    assert "neoforge" in MOD_LOADERS
    assert loader_display("neoforge") == "NeoForge"
    assert loader_display(None) == "Vanilla"


def test_optimizer_bundle_for_neoforge():
    from app.ui.modrinth_browser import ModrinthBrowser
    bundle = ModrinthBrowser.optimizer_bundle("neoforge")
    assert bundle and {m["slug"] for m in bundle} >= {"modernfix", "ferrite-core"}
    assert ModrinthBrowser.optimizer_bundle("paper") is None
    assert ModrinthBrowser.bundle_summary("neoforge").startswith("NeoForge: ModernFix")
