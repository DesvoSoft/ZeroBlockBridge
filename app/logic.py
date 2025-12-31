import json
import os
import subprocess
import shutil
import requests
import threading
import platform
import sys
import datetime

from app.constants import APP_CONFIG_PATH, SERVERS_DIR, BACKUPS_DIR
from app.server_events import ServerEvent, ServerEventEmitter
from app.version_manager import VersionManager

def load_config():
    """Loads the configuration from config.json."""
    default_config = {
        "java_path": "auto",
        "ram_allocation": "2G",
        "accepted_eula": False,
        "last_server": None,
        "playit_dns": None
    }

    if not os.path.exists(APP_CONFIG_PATH):
        save_config(default_config)
        return default_config
    
    try:
        with open(APP_CONFIG_PATH, "r") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        print("[Warning] Config file corrupted. Resetting to defaults.")
        save_config(default_config)
        return default_config

def save_config(config):
    """Saves the configuration to config.json."""
    APP_CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(APP_CONFIG_PATH, "w") as f:
        json.dump(config, f, indent=4)

def check_java():
    """Checks for Java installation."""
    java_cmd = "java"
    config = load_config()
    if config.get("java_path") != "auto":
        java_cmd = config.get("java_path")

    try:
        result = subprocess.run([java_cmd, "-version"], capture_output=True, text=True, check=False)
        if result.returncode == 0:
            return result.stderr.splitlines()[0] if result.stderr else "Java detected (Unknown version)"
        else:
            return None
    except FileNotFoundError:
        return None

def create_server_directory(server_name):
    """Creates the server directory if it doesn't exist."""
    path = os.path.join(SERVERS_DIR, server_name)
    if not os.path.exists(path):
        os.makedirs(path)
    return path

def download_server(server_name, server_type, version, progress_callback=None):
    """Downloads the server jar."""
    vm = VersionManager()
    url = vm.get_download_url(server_type, version)
    
    if not url:
        raise ValueError(f"URL not found for {server_type} {version}")

    server_path = create_server_directory(server_name)
    jar_path = os.path.join(server_path, "server.jar")

    try:
        response = requests.get(url, stream=True)
        response.raise_for_status()
        
        total_size = int(response.headers.get('content-length', 0))
        downloaded = 0

        with open(jar_path, "wb") as f:
            for chunk in response.iter_content(chunk_size=8192):
                if chunk:
                    f.write(chunk)
        data = self._load_metadata()
        scheduler = data.get("scheduler")
        if not scheduler: return False
        if scheduler["type"] == "interval":
            last_run_str = scheduler.get("last_run")
            if not last_run_str:
                self.update_last_run()
                return False
            last_run = datetime.datetime.fromisoformat(last_run_str)
            interval = datetime.timedelta(hours=scheduler["interval_hours"])
            if datetime.datetime.now() >= last_run + interval: return True
        elif scheduler["type"] == "time":
            restart_time_str = scheduler["restart_time"]
            last_run_str = scheduler.get("last_run")
            hour, minute = map(int, restart_time_str.split(":"))
            now = datetime.datetime.now()
            target_time_today = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
            if last_run_str:
                last_run = datetime.datetime.fromisoformat(last_run_str)
                if last_run.date() == now.date():
                    if (now - last_run).total_seconds() < 300: return False
            time_diff = (now - target_time_today).total_seconds()
            if 0 <= time_diff < 120: return True
        return False

    def update_last_run(self):
        data = self._load_metadata()
        if "scheduler" in data:
            data["scheduler"]["last_run"] = datetime.datetime.now().isoformat()
            self._save_metadata(data)

def apply_server_settings(server_name, ram, seed, game_mode, difficulty, view_distance, simulation_distance):
    server_path = os.path.join(SERVERS_DIR, server_name)
    metadata = {
        "ram": ram,
        "created": datetime.datetime.now().isoformat(),
        "pending_settings": {
            "seed": seed, "game_mode": game_mode, "difficulty": difficulty,
            "view_distance": view_distance, "simulation_distance": simulation_distance
        }
    }
    metadata_path = os.path.join(server_path, "metadata.json")
    with open(metadata_path, "w") as f: json.dump(metadata, f, indent=4)
    accept_eula(server_name)
    props = {
        "network-compression-threshold": "256", "sync-chunk-writes": "false",
        "entity-broadcast-range-percentage": "75", "allow-flight": "true",
        "level-seed": seed if seed else "", "gamemode": game_mode,
        "force-gamemode": "true", "difficulty": difficulty,
        "view-distance": view_distance, "simulation-distance": simulation_distance
    }
    save_server_properties(server_name, props)
    metadata["pending_settings"] = {}
    with open(metadata_path, "w") as f: json.dump(metadata, f, indent=4)

def get_server_ram(server_name):
    try:
        with open(os.path.join(SERVERS_DIR, server_name, "metadata.json"), "r") as f:
            return json.load(f).get("ram", 2048)
    except: return 2048

def set_server_ram(server_name, ram_mb):
    metadata_path = os.path.join(SERVERS_DIR, server_name, "metadata.json")
    try:
        if os.path.exists(metadata_path):
            with open(metadata_path, "r") as f: meta = json.load(f)
        else: meta = {}
        meta["ram"] = int(ram_mb)
        with open(metadata_path, "w") as f: json.dump(meta, f, indent=4)
        return True
    except: return False

def play_sound(sound_path):
    if not os.path.exists(sound_path): return
    system = platform.system()
    try:
        if system == "Windows":
            import winsound
            winsound.PlaySound(str(sound_path), winsound.SND_FILENAME | winsound.SND_ASYNC)
        elif system == "Linux":
            players = [["paplay", str(sound_path)], ["aplay", str(sound_path)], ["canberra-gtk-play", "-f", str(sound_path)], ["mpg123", str(sound_path)]]
            for cmd in players:
                try:
                    subprocess.run(cmd, check=True, capture_output=True)
                    break
                except: continue
    except: pass
