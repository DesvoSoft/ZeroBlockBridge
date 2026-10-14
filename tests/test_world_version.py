"""level.dat version reading and the world-vs-server version check."""
import gzip
import struct
import zipfile

import pytest

from app.services import nbt
from app.services.content_import import WorldInfo, inspect_world, world_version_check


# ----------------------------------------------------------------------
# Tiny NBT writer for fixtures (the app only reads NBT)
# ----------------------------------------------------------------------
def _name(s: str) -> bytes:
    raw = s.encode("utf-8")
    return struct.pack(">H", len(raw)) + raw


def _tag(tag: int, name: str, payload: bytes) -> bytes:
    return struct.pack(">b", tag) + _name(name) + payload


def _compound(entries: bytes) -> bytes:
    return entries + b"\x00"


def level_dat(version_name="1.21.4", snapshot=0, data_version=4189, extras=b"", compress=True) -> bytes:
    version = _compound(
        _tag(nbt.TAG_INT, "Id", struct.pack(">i", data_version))
        + _tag(nbt.TAG_STRING, "Name", _name(version_name))
        + _tag(nbt.TAG_STRING, "Series", _name("main"))
        + _tag(nbt.TAG_BYTE, "Snapshot", struct.pack(">b", snapshot))
    )
    data = _compound(
        extras
        + _tag(nbt.TAG_INT, "DataVersion", struct.pack(">i", data_version))
        + _tag(nbt.TAG_COMPOUND, "Version", version)
        + _tag(nbt.TAG_STRING, "LevelName", _name("My World"))
    )
    root = struct.pack(">b", nbt.TAG_COMPOUND) + _name("") + _compound(_tag(nbt.TAG_COMPOUND, "Data", data))
    return gzip.compress(root) if compress else root


# Every other tag type, so the reader has to skip them correctly.
_ALL_TYPES = (
    _tag(nbt.TAG_SHORT, "s", struct.pack(">h", 7))
    + _tag(nbt.TAG_LONG, "RandomSeed", struct.pack(">q", -123456789))
    + _tag(nbt.TAG_FLOAT, "f", struct.pack(">f", 1.5))
    + _tag(nbt.TAG_DOUBLE, "BorderSize", struct.pack(">d", 6e7))
    + _tag(nbt.TAG_BYTE_ARRAY, "ba", struct.pack(">i", 3) + b"abc")
    + _tag(nbt.TAG_INT_ARRAY, "ia", struct.pack(">i", 2) + struct.pack(">ii", 1, 2))
    + _tag(nbt.TAG_LONG_ARRAY, "la", struct.pack(">i", 1) + struct.pack(">q", 9))
    + _tag(nbt.TAG_LIST, "ServerBrands", struct.pack(">bi", nbt.TAG_STRING, 2) + _name("vanilla") + _name("fabric"))
    + _tag(nbt.TAG_LIST, "empty", struct.pack(">bi", nbt.TAG_END, 0))
)


# ----------------------------------------------------------------------
# NBT reader
# ----------------------------------------------------------------------
def test_reads_version_and_skips_every_tag_type():
    root = nbt.parse(level_dat("1.20.1", data_version=3465, extras=_ALL_TYPES))
    data = root["Data"]
    assert data["Version"]["Name"] == "1.20.1" and data["DataVersion"] == 3465
    assert data["ServerBrands"] == ["vanilla", "fabric"]
    assert data["RandomSeed"] == -123456789
    assert data["LevelName"] == "My World"


def test_uncompressed_nbt_is_read_too():
    assert nbt.parse(level_dat(compress=False))["Data"]["Version"]["Name"] == "1.21.4"


@pytest.mark.parametrize("blob", [
    b"",                                   # empty
    b"\x1f\x8bgarbage",                    # broken gzip
    gzip.compress(b"\x08\x00\x00"),        # root is not a compound
    gzip.compress(b"\x0a\x00\x00\x03"),    # truncated mid-tag
    gzip.compress(b"\x0a\x00\x00\x63\x00\x01x"),  # unknown tag 99
])
def test_corrupt_input_raises_nbt_error(blob):
    with pytest.raises(nbt.NbtError):
        nbt.parse(blob)


def test_negative_array_length_is_rejected():
    bad = struct.pack(">b", nbt.TAG_COMPOUND) + _name("") + _compound(
        _tag(nbt.TAG_INT_ARRAY, "x", struct.pack(">i", -5)))
    with pytest.raises(nbt.NbtError):
        nbt.parse(bad)


def test_oversized_file_is_refused(tmp_path, monkeypatch):
    monkeypatch.setattr(nbt, "MAX_BYTES", 100)
    big = tmp_path / "level.dat"
    big.write_bytes(b"\x00" * 200)
    with pytest.raises(nbt.NbtError):
        nbt.read_file(big)


# ----------------------------------------------------------------------
# inspect_world picks the version up
# ----------------------------------------------------------------------
def test_world_folder_version(tmp_path):
    world = tmp_path / "Survival"
    world.mkdir()
    (world / "level.dat").write_bytes(level_dat("1.21.4"))
    info = inspect_world(str(world))
    assert (info.mc_version, info.snapshot) == ("1.21.4", False)


def test_world_zip_version(tmp_path):
    archive = tmp_path / "w.zip"
    with zipfile.ZipFile(archive, "w") as zf:
        zf.writestr("Skyblock/level.dat", level_dat("26.3", data_version=5023))
        zf.writestr("Skyblock/region/r.0.0.mca", "x")
    assert inspect_world(str(archive)).mc_version == "26.3"


def test_unreadable_level_dat_leaves_version_unknown(tmp_path):
    """Never block an import because level.dat can't be parsed."""
    world = tmp_path / "Old"
    world.mkdir()
    (world / "level.dat").write_bytes(b"not nbt")
    info = inspect_world(str(world))
    assert info.mc_version is None and world_version_check(info, "1.21.4") is None


# ----------------------------------------------------------------------
# The check
# ----------------------------------------------------------------------
def _world(version, snapshot=False):
    return WorldInfo(path="p", name="w", is_zip=False, root="", mc_version=version, snapshot=snapshot)


@pytest.mark.parametrize("world, server, level", [
    ("1.21.4", "1.20.1", "error"),     # newer world on older server: refuse
    ("26.3", "1.21.11", "error"),      # new version scheme compares numerically
    ("1.21.10", "1.21.9", "error"),    # not text order
    ("1.20.1", "1.21.4", "info"),      # older world: upgraded, fine
    ("1.21.4", "1.21.4", "info"),
    ("1.21.9", "1.21.10", "info"),
])
def test_version_check_levels(world, server, level):
    assert world_version_check(_world(world), server)[0] == level


def test_newer_world_message_tells_what_to_do():
    level, msg = world_version_check(_world("1.21.4"), "1.20.1")
    assert "1.21.4" in msg and "1.20.1" in msg and "Engine & Version" in msg


@pytest.mark.parametrize("world, server", [(None, "1.21.4"), ("1.21.4", "Unknown"), ("1.21.4", None),
                                           ("1.21.4-rc1", "1.21.4")])
def test_unknown_versions_are_not_judged(world, server):
    assert world_version_check(_world(world), server) is None


def test_snapshot_world_gets_a_warning_not_a_block():
    level, msg = world_version_check(_world("24w14a", snapshot=True), "1.20.4")
    assert level == "warning" and "24w14a" in msg


# ----------------------------------------------------------------------
# Wizard + provisioning gates
# ----------------------------------------------------------------------
def test_wizard_blocks_next_on_a_newer_world():
    from app.ui.server_wizard import imported_world_check, world_step_error
    data = {"world_path": "C:/w", "world_label": "w", "world_mc": "1.21.4", "world_snapshot": False,
            "version": "1.20.1"}
    check = imported_world_check(data)
    assert world_step_error("import", "C:/w", False, check) == check[1]
    data["version"] = "1.21.4"
    assert world_step_error("import", "C:/w", False, imported_world_check(data)) is None
    assert imported_world_check({"world_path": None}) is None


def test_provisioning_refuses_a_newer_world_before_creating_anything(tmp_path):
    """Version changed in step 2 after the world was picked: the preflight
    still catches it."""
    from contextlib import ExitStack
    from tests.test_provisioning import _Env
    world = tmp_path / "W"
    world.mkdir()
    (world / "level.dat").write_bytes(level_dat("1.21.4"))
    with ExitStack() as stack:
        env = _Env(tmp_path, stack)
        result = env.run(version="1.20.1", world_path=str(world))
    assert not result.ok and "newer than this server" in result.error
    env.download.assert_not_called()
    assert list(env.servers_dir.iterdir()) == []


def test_template_never_stores_the_world_version():
    from app.ui.server_wizard import _CONTENT_KEYS
    assert {"world_mc", "world_snapshot"} <= set(_CONTENT_KEYS)



# ----------------------------------------------------------------------
# Review round
# ----------------------------------------------------------------------
def test_gzip_bomb_is_refused_without_inflating_it(tmp_path, monkeypatch):
    """Review #2: gzip.decompress had no output limit -- a 305 KB level.dat
    peaked at ~600 MB. The cap now applies to the decompressed size."""
    import tracemalloc
    monkeypatch.setattr(nbt, "MAX_BYTES", 1024 * 1024)  # 1 MB cap
    bomb = gzip.compress(b"\x00" * (50 * 1024 * 1024), compresslevel=9)  # 50 MB of zeros, ~50 KB file
    tracemalloc.start()
    try:
        with pytest.raises(nbt.NbtError, match="size limit"):
            nbt.parse(bomb)
        _, peak = tracemalloc.get_traced_memory()
    finally:
        tracemalloc.stop()
    assert peak < 10 * 1024 * 1024


def test_oversized_level_dat_in_a_world_folder_is_not_read(tmp_path, monkeypatch):
    monkeypatch.setattr(nbt, "MAX_BYTES", 100)
    world = tmp_path / "W"
    world.mkdir()
    (world / "level.dat").write_bytes(level_dat() + b"\x00" * 200)
    assert inspect_world(str(world)).mc_version is None


def test_deep_nesting_raises_nbt_error_not_recursion_error():
    """Review #3: Python's recursion limit tripped before the depth guard."""
    depth = 600
    inner = b""
    for _ in range(depth):
        inner = _tag(nbt.TAG_COMPOUND, "c", _compound(inner))
    blob = struct.pack(">b", nbt.TAG_COMPOUND) + _name("") + _compound(inner)
    with pytest.raises(nbt.NbtError):
        nbt.parse(blob)


@pytest.mark.parametrize("world, server, level", [
    ("1.21.5-pre1", "1.21.4", "error"),    # review #4: pre-release of a newer version
    ("1.21.5-rc1", "1.21.4", "error"),
    ("1.21.5-pre1", "1.21.5", "warning"),  # its own release: fine to open, still flagged
    ("25w10a", "1.21.4", "warning"),       # weekly snapshot: can't be ordered by name
])
def test_prerelease_worlds(world, server, level):
    assert world_version_check(_world(world, snapshot=True), server)[0] == level


def test_switching_to_new_world_clears_the_world_version():
    """Review #1: the summary kept "(Minecraft 1.21.4)" after switching to New world."""
    import inspect
    from app.ui.server_wizard import ServerWizard
    src = inspect.getsource(ServerWizard._collect_step5_fields)
    assert "world_mc=None" in src and "world_snapshot=False" in src
