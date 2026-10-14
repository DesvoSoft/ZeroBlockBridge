"""Type/version inference for servers added from an existing folder."""
import json
import zipfile
from unittest.mock import patch

import pytest

from app.core.logic import _infer_server_type, infer_server_version


def _jar(path, files: dict):
    path.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(path, "w") as zf:
        for name, data in files.items():
            zf.writestr(name, data)
    return path


def test_vanilla_version_from_version_json(tmp_path):
    _jar(tmp_path / "server.jar", {"version.json": json.dumps({"id": "1.21.4", "name": "1.21.4"})})
    assert _infer_server_type(str(tmp_path)) == "Vanilla"
    assert infer_server_version(str(tmp_path)) == "1.21.4"


def test_paper_version_from_paperclip_versions_list(tmp_path):
    _jar(tmp_path / "paper-1.20.4-499.jar",
         {"META-INF/versions.list": "abc123\tpaper-1.20.4\tversions/1.20.4/paper-1.20.4.jar\n"})
    assert _infer_server_type(str(tmp_path)) == "Paper"
    assert infer_server_version(str(tmp_path)) == "1.20.4"


def test_modern_forge_detected_from_libraries(tmp_path):
    """Forge 1.17+ has no forge*.jar at the root, just run.bat + libraries/."""
    (tmp_path / "libraries/net/minecraftforge/forge/1.20.1-47.2.0").mkdir(parents=True)
    (tmp_path / "run.bat").write_text("java @libraries/...")
    assert _infer_server_type(str(tmp_path)) == "Forge"
    assert infer_server_version(str(tmp_path)) == "1.20.1"


def test_fabric_detected_from_libraries_and_intermediary(tmp_path):
    (tmp_path / "libraries/net/fabricmc/fabric-loader/0.15.7").mkdir(parents=True)
    (tmp_path / "libraries/net/fabricmc/intermediary/1.20.1").mkdir(parents=True)
    assert _infer_server_type(str(tmp_path)) == "Fabric"
    assert infer_server_version(str(tmp_path)) == "1.20.1"


def test_custom_jar_name_is_checked_first(tmp_path):
    _jar(tmp_path / "server.jar", {"version.json": json.dumps({"id": "1.19.2"})})
    _jar(tmp_path / "custom.jar", {"version.json": json.dumps({"id": "1.21.1"})})
    assert infer_server_version(str(tmp_path), "custom.jar") == "1.21.1"


@pytest.mark.parametrize("files", [
    {},                                        # no jars at all
    {"server.jar": b"not a zip"},              # corrupt jar
    {"server.jar": "zip-without-version"},     # jar without version info
])
def test_unknown_when_nothing_tells(tmp_path, files):
    for name, data in files.items():
        if data == "zip-without-version":
            _jar(tmp_path / name, {"a.class": "x"})
        else:
            (tmp_path / name).write_bytes(data)
    assert infer_server_version(str(tmp_path)) == "Unknown"


def test_installer_jars_are_ignored(tmp_path):
    _jar(tmp_path / "forge-1.20.1-47.2.0-installer.jar", {"version.json": json.dumps({"id": "bogus"})})
    assert infer_server_version(str(tmp_path)) == "Unknown"


def test_load_server_manually_records_inferred_type_and_version(tmp_path):
    """Regression: every added server used to be saved as Vanilla/Unknown."""
    from app.core.core import ZBBManager

    folder = tmp_path / "MyFabric"
    (folder / "libraries/net/fabricmc/fabric-loader/0.15.7").mkdir(parents=True)
    _jar(folder / "server.jar", {"version.json": json.dumps({"id": "1.20.1"})})
    (folder / "fabric-server-launch.jar").write_bytes(b"x")
    servers = tmp_path / "servers"
    servers.mkdir()

    manager = ZBBManager.__new__(ZBBManager)  # only the method under test is needed
    with patch("app.core.core.SERVERS_DIR", str(servers)), \
            patch("app.core.logic.SERVERS_DIR", str(servers)):
        assert manager.load_server_manually(str(folder)) is True
        meta = json.loads((servers / "MyFabric" / "metadata.json").read_text(encoding="utf-8"))

    assert meta["type"] == "Fabric" and meta["version"] == "1.20.1"


def test_newest_version_folder_wins_numerically(tmp_path):
    """Review #4: text sort reported 1.21.9 over 1.21.10 (and 1.9.4 over 1.12.2)."""
    for v in ("1.21.9", "1.21.10"):
        (tmp_path / "fabric/libraries/net/fabricmc/intermediary" / v).mkdir(parents=True)
    for v in ("1.9.4-12.17.0.2317", "1.12.2-14.23.5.2860"):
        (tmp_path / "forge/libraries/net/minecraftforge/forge" / v).mkdir(parents=True)
    assert infer_server_version(str(tmp_path / "fabric")) == "1.21.10"
    assert infer_server_version(str(tmp_path / "forge")) == "1.12.2"


def test_unreadable_jar_never_blocks_inference(tmp_path):
    """Review #5: odd compression/encryption raised past the probe and made
    the whole folder import fail."""
    import zipfile as _zip
    _jar(tmp_path / "server.jar", {"version.json": "{}"})
    with patch.object(_zip.ZipFile, "read", side_effect=NotImplementedError("compression type 99")):
        assert infer_server_version(str(tmp_path)) == "Unknown"


@pytest.mark.parametrize("folders, newest", [
    (["1.20.1", "1.20.1-pre1"], "1.20.1"),            # release beats its pre-release
    (["1.20.4-rc1", "1.20.4"], "1.20.4"),
    (["24w14a", "1.20.5"], "1.20.5"),                 # snapshots rank below releases
    (["1.20.1-47.1.0", "1.20.1-47.2.0"], "1.20.1"),   # newer Forge build, same MC
])
def test_prereleases_and_snapshots_rank_below_releases(tmp_path, folders, newest):
    base = tmp_path / "libraries/net/fabricmc/intermediary"
    if "-47." in folders[0]:
        base = tmp_path / "libraries/net/minecraftforge/forge"
    for name in folders:
        (base / name).mkdir(parents=True)
    assert infer_server_version(str(tmp_path)) == newest
