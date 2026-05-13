import json
import os
import logging
from typing import Dict, Any

logger = logging.getLogger(__name__)

class SettingsManager:
    """Manages global application settings via JSON."""
    _instance = None
    _settings_file = "zbb_settings.json"
    
    def __new__(cls, config_dir: str = None):
        if cls._instance is None:
            cls._instance = super(SettingsManager, cls).__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def __init__(self, config_dir: str = None):
        if getattr(self, '_initialized', False):
            return
            
        if config_dir:
            self.settings_path = os.path.join(config_dir, self._settings_file)
        else:
            self.settings_path = self._settings_file
            
        self.settings: Dict[str, Any] = self._get_default_settings()
        self.load_settings()
        self._initialized = True

    def _get_default_settings(self) -> Dict[str, Any]:
        return {
            "theme": "Dark",
            "servers_dir": "servers",
            "java_preferences": {
                "java8_path": "",
                "java17_path": "",
                "java21_path": ""
            }
        }

    def load_settings(self):
        if os.path.exists(self.settings_path):
            try:
                with open(self.settings_path, 'r', encoding='utf-8') as f:
                    loaded = json.load(f)
                    self.settings.update(loaded)
            except Exception as e:
                logger.error(f"Error loading settings: {e}")

    def save_settings(self):
        try:
            with open(self.settings_path, 'w', encoding='utf-8') as f:
                json.dump(self.settings, f, indent=4)
        except Exception as e:
            logger.error(f"Error saving settings: {e}")

    def get(self, key: str, default: Any = None) -> Any:
        return self.settings.get(key, default)

    def set(self, key: str, value: Any):
        self.settings[key] = value
        self.save_settings()
