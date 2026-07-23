import json
import logging
import os

from app.core.constants import CONFIG_DIR

logger = logging.getLogger(__name__)

TEMPLATES_DIR = os.path.join(CONFIG_DIR, "templates")

# wizard_data keys captured into a template (instance-specific fields like
# name/location/icon_path are intentionally excluded)
_TEMPLATE_FIELDS = (
    "type", "version", "ram", "game_mode", "difficulty", "hardcore",
    "whitelist", "enforce_whitelist", "pvp", "online_mode", "max_players",
    "spawn_protection", "enable_command_block", "allow_flight",
    "enforce_secure_profile", "view_distance", "simulation_distance", "seed",
)


def _template_path(name: str) -> str:
    return os.path.join(TEMPLATES_DIR, f"{name}.json")


def list_templates() -> list[dict]:
    if not os.path.isdir(TEMPLATES_DIR):
        return []
    templates = []
    for filename in sorted(os.listdir(TEMPLATES_DIR)):
        if not filename.endswith(".json"):
            continue
        name = filename[:-5]
        template = load_template(name)
        if template is not None:
            templates.append({
                "name": name,
                "engine": template.get("type", "Vanilla"),
                "version": template.get("version", ""),
                "description": template.get("_description", ""),
            })
    return templates


def load_template(name: str) -> dict | None:
    path = _template_path(name)
    if not os.path.exists(path):
        return None
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError) as exc:
        logger.warning("Failed to read template %s: %s", name, exc)
        return None


def save_template(name: str, wizard_data: dict, description: str = "") -> None:
    os.makedirs(TEMPLATES_DIR, exist_ok=True)
    data = {key: wizard_data[key] for key in _TEMPLATE_FIELDS if key in wizard_data}
    data["_description"] = description
    with open(_template_path(name), "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)
    logger.info("Saved template: %s", name)


def delete_template(name: str) -> None:
    path = _template_path(name)
    if os.path.exists(path):
        os.remove(path)
        logger.info("Deleted template: %s", name)
