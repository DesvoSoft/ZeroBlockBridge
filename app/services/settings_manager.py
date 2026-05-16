import json
import os
import logging
from typing import Any

logger = logging.getLogger(__name__)

_settings_file = "zbb_settings.json"
_settings_path = _settings_file
_settings: dict = None


def _get_defaults() -> dict:
    return {
        "theme": "Dark",
        "servers_dir": "servers",
        "java_preferences": {"java8_path": "", "java17_path": "", "java21_path": ""},
    }


def _ensure_loaded():
    global _settings
    if _settings is not None:
        return
    _settings = _get_defaults()
    if os.path.exists(_settings_path):
        try:
            with open(_settings_path, "r", encoding="utf-8") as f:
                _settings.update(json.load(f))
        except Exception as e:
            logger.error("Error loading settings: %s", e)


def set_config_dir(config_dir: str):
    global _settings_path
    _settings_path = os.path.join(config_dir, _settings_file)


def get(key: str, default: Any = None) -> Any:
    _ensure_loaded()
    return _settings.get(key, default)


def set(key: str, value: Any):
    _ensure_loaded()
    _settings[key] = value
    try:
        with open(_settings_path, "w", encoding="utf-8") as f:
            json.dump(_settings, f, indent=4)
    except Exception as e:
        logger.error("Error saving settings: %s", e)


def load():
    _ensure_loaded()


def save():
    _ensure_loaded()
    try:
        with open(_settings_path, "w", encoding="utf-8") as f:
            json.dump(_settings, f, indent=4)
    except Exception as e:
        logger.error("Error saving settings: %s", e)
