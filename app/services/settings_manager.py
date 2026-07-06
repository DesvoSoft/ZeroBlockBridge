import json
import os
import threading
import logging
from typing import Any

from app.core.constants import CONFIG_DIR

logger = logging.getLogger(__name__)

class SettingsManager:
    _instance = None
    _lock = threading.Lock()

    def __new__(cls, *args, **kwargs):
        with cls._lock:
            if cls._instance is None:
                cls._instance = super(SettingsManager, cls).__new__(cls)
                cls._instance._init()
            return cls._instance

    def _init(self):
        self._settings_file = "zbb_settings.json"
        self._settings_path = str(CONFIG_DIR / self._settings_file)
        self._settings = None
        self._dirty = False
        self._timer = None
        self._settings_lock = threading.Lock()

    def _get_defaults(self) -> dict:
        return {
            "theme": "Dark",
            "servers_dir": "servers",
            "java_preferences": {"java8_path": "", "java17_path": "", "java21_path": ""},
            "discord_webhook_url": "",
        }

    def _ensure_loaded(self):
        if self._settings is not None:
            return
        with self._settings_lock:
            if self._settings is not None:
                return
            self._settings = self._get_defaults()
            if os.path.exists(self._settings_path):
                try:
                    with open(self._settings_path, "r", encoding="utf-8") as f:
                        self._settings.update(json.load(f))
                except Exception as e:
                    logger.error("Error loading settings: %s", e)

    def set_config_dir(self, config_dir: str):
        with self._settings_lock:
            self._settings_path = os.path.join(config_dir, self._settings_file)

    def get(self, key: str, default: Any = None) -> Any:
        self._ensure_loaded()
        return self._settings.get(key, default)

    def set(self, key: str, value: Any):
        self._ensure_loaded()
        with self._settings_lock:
            self._settings[key] = value
            self._dirty = True
            
            if self._timer is not None:
                self._timer.cancel()
            
            self._timer = threading.Timer(0.5, self._flush)
            self._timer.start()

    def _flush(self):
        with self._settings_lock:
            if not self._dirty:
                return
            try:
                with open(self._settings_path, "w", encoding="utf-8") as f:
                    json.dump(self._settings, f, indent=4)
                self._dirty = False
            except Exception as e:
                logger.error("Error saving settings: %s", e)

    def load(self):
        self._ensure_loaded()

    def save(self):
        self._ensure_loaded()
        self._flush()
