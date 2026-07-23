import os
from app.services.server_properties import list_worlds, get_active_world, set_active_world


def _make_world(base_dir, name):
    world_dir = os.path.join(base_dir, name)
    os.makedirs(world_dir, exist_ok=True)
    with open(os.path.join(world_dir, "level.dat"), "w", encoding="utf-8") as f:
        f.write("")


def test_list_worlds_empty(tmp_path):
    assert list_worlds(server_dir=str(tmp_path)) == []


def test_list_worlds_finds_level_dat_dirs(tmp_path):
    _make_world(tmp_path, "world")
    _make_world(tmp_path, "world_nether")
    os.makedirs(os.path.join(tmp_path, "logs"), exist_ok=True)
    os.makedirs(os.path.join(tmp_path, "mods"), exist_ok=True)

    worlds = list_worlds(server_dir=str(tmp_path))
    assert worlds == ["world", "world_nether"]


def test_get_active_world_defaults(tmp_path):
    assert get_active_world(server_dir=str(tmp_path)) == "world"


def test_set_and_get_active_world(tmp_path):
    set_active_world(server_dir=str(tmp_path), world_dir="custom_world")
    assert get_active_world(server_dir=str(tmp_path)) == "custom_world"
