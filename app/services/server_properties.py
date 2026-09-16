import logging
import os

from app.core.constants import SERVERS_DIR, atomic_write_text

logger = logging.getLogger(__name__)


def _props_path(server_name: str | None = None, server_dir: str | None = None) -> str:
    if server_dir:
        return os.path.join(server_dir, "server.properties")
    return os.path.join(SERVERS_DIR, server_name, "server.properties")


def load_server_properties(server_name: str | None = None, server_dir: str | None = None) -> dict[str, str]:
    props_path = _props_path(server_name, server_dir)
    properties = {}
    if not os.path.exists(props_path):
        return properties
    with open(props_path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                key, value = line.split("=", 1)
                properties[key.strip()] = value.strip()
    return properties



def save_server_properties(server_name: str | None = None, server_dir: str | None = None, new_properties: dict[str, str] | None = None) -> None:
    if new_properties is None:
        new_properties = {}
    props_path = _props_path(server_name, server_dir)
    if not os.path.exists(props_path):
        new_lines = [f"{k}={v}\n" for k, v in new_properties.items()]
        atomic_write_text(props_path, lambda f: f.writelines(new_lines))
        return
    with open(props_path, "r", encoding="utf-8") as f:
        lines = f.readlines()
    updated_keys = set()
    new_lines = []
    for line in lines:
        stripped = line.strip()
        if stripped and not stripped.startswith("#") and "=" in stripped:
            key = stripped.split("=", 1)[0].strip()
            if key in new_properties:
                new_lines.append(f"{key}={new_properties[key]}\n")
                updated_keys.add(key)
            else:
                new_lines.append(line)
        else:
            new_lines.append(line)
    for k, v in new_properties.items():
        if k not in updated_keys:
            new_lines.append(f"{k}={v}\n")
    atomic_write_text(props_path, lambda f: f.writelines(new_lines))


def list_worlds(server_name: str | None = None, server_dir: str | None = None) -> list[str]:
    base_dir = server_dir if server_dir else os.path.join(SERVERS_DIR, server_name)
    if not os.path.isdir(base_dir):
        return []
    worlds = []
    for entry in os.listdir(base_dir):
        entry_path = os.path.join(base_dir, entry)
        if os.path.isdir(entry_path) and os.path.exists(os.path.join(entry_path, "level.dat")):
            worlds.append(entry)
    return sorted(worlds)


def get_active_world(server_name: str | None = None, server_dir: str | None = None) -> str:
    properties = load_server_properties(server_name, server_dir)
    return properties.get("level-name", "world")


def set_active_world(server_name: str | None = None, server_dir: str | None = None, world_dir: str = "world") -> None:
    save_server_properties(server_name, server_dir, {"level-name": world_dir})
