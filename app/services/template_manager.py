import json
import logging
import os
import re

from app.core import resources
from app.core.constants import CONFIG_DIR, atomic_write_json

logger = logging.getLogger(__name__)

TEMPLATES_DIR = os.path.join(CONFIG_DIR, "templates")
# Read-only templates shipped with the app (assets/ is bundled into the exe).
# A user template with the same name takes precedence.
BUILTIN_TEMPLATES_DIR = str(resources.assets_dir() / "templates")

# wizard_data keys captured into a template (instance-specific fields like
# name/location/icon_path are intentionally excluded)
_TEMPLATE_FIELDS = (
    "type", "version", "ram", "game_mode", "difficulty", "hardcore",
    "whitelist", "enforce_whitelist", "pvp", "online_mode", "max_players",
    "spawn_protection", "enable_command_block", "allow_flight",
    "enforce_secure_profile", "view_distance", "simulation_distance", "seed",
)


# A template name is a file name: no separators, drive letters or dot-files.
_NAME_RE = re.compile(r"^[a-z0-9][a-z0-9._-]{0,63}$")


def normalize_template_name(raw: str) -> str | None:
    """The file-safe name for what the user typed ("My Template" ->
    "my-template"), or None if it can't be one."""
    name = (raw or "").strip().lower().replace(" ", "-")
    return name if _NAME_RE.match(name) else None


def _template_path(name: str) -> str:
    if not _NAME_RE.match(name or ""):
        raise ValueError(f"Invalid template name: {name!r}")
    return os.path.join(TEMPLATES_DIR, f"{name}.json")


def _template_names(folder: str) -> set:
    if not os.path.isdir(folder):
        return set()
    return {f[:-5] for f in os.listdir(folder) if f.endswith(".json")}


def list_templates() -> list[dict]:
    templates = []
    for name in sorted(_template_names(TEMPLATES_DIR) | _template_names(BUILTIN_TEMPLATES_DIR)):
        template = load_template(name)
        if template is not None:
            templates.append({
                "name": name,
                "engine": template.get("type", "Vanilla"),
                "version": template.get("version", ""),
                "description": template.get("_description", ""),
            })
    return templates


def _read_template(path: str, name: str) -> dict | None:
    if not os.path.exists(path):
        return None
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError) as exc:
        logger.warning("Failed to read template %s: %s", name, exc)
        return None


def load_template(name: str) -> dict | None:
    """The user's template, else the built-in one (also when the user's
    file is unreadable)."""
    if not _NAME_RE.match(name or ""):
        return None
    return (_read_template(_template_path(name), name)
            or _read_template(os.path.join(BUILTIN_TEMPLATES_DIR, f"{name}.json"), name))


def template_exists(name: str) -> bool:
    return name in _template_names(TEMPLATES_DIR) | _template_names(BUILTIN_TEMPLATES_DIR)


def save_template(name: str, wizard_data: dict, description: str = "") -> None:
    """Raises ValueError for an unsafe name, OSError if it can't be written."""
    path = _template_path(name)
    data = {key: wizard_data[key] for key in _TEMPLATE_FIELDS if key in wizard_data}
    data["_description"] = description
    atomic_write_json(path, data, indent=2)
    logger.info("Saved template: %s", name)


def delete_template(name: str) -> None:
    path = _template_path(name)
    if os.path.exists(path):
        os.remove(path)
        logger.info("Deleted template: %s", name)
