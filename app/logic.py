import json
import os
import subprocess
import shutil

import shutil
import requests
import threading

CONFIG_PATH = "config.json"
SERVERS_DIR = "servers"

SERVER_URLS = {
    "Vanilla": {
        "1.21.1": "https://piston-data.mojang.com/v1/objects/59353fb40c36d304f2035d51e7d6e6baa98dc05c/server.jar"
    },
    "Fabric": {
        # Placeholder for Fabric if needed later
    }
}

def load_config():
    """Loads the configuration from config.json."""
    if not os.path.exists(CONFIG_PATH):
        default_config = {
            "java_path": "auto",
            "ram_allocation": "2G",
            "accepted_eula": False,
            "last_server": None
        }
        save_config(default_config)
        return default_config
    
    try:
        with open(CONFIG_PATH, "r") as f:
            return json.load(f)
    except json.JSONDecodeError:
        return load_config() # Return default if corrupted (or handle better)

def save_config(config):
    """Saves the configuration to config.json."""
    with open(CONFIG_PATH, "w") as f:
        json.dump(config, f, indent=4)

def check_java():
    """
    Checks for Java installation.
    Returns:
        str: Java version string if found.
        None: If Java is not found.
    """
    java_cmd = "java"
    
    # Check config first if we want to support custom paths later
    config = load_config()
    if config.get("java_path") != "auto":
        java_cmd = config.get("java_path")

    try:
        # Run java -version. Note: java -version outputs to stderr.
        result = subprocess.run([java_cmd, "-version"], capture_output=True, text=True, check=False)
        if result.returncode == 0:
            # Parse version from stderr (e.g., "openjdk version '17.0.1' ...")
            # For now, just return the first line or the whole stderr
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
    """
    Downloads the server jar to the server directory.
    progress_callback: function(float) -> None (0.0 to 1.0)
    """
    url = SERVER_URLS.get(server_type, {}).get(version)
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
                    downloaded += len(chunk)
                    if progress_callback and total_size > 0:
                        progress_callback(downloaded / total_size)
        
        if progress_callback:
            progress_callback(1.0) # Ensure 100% at end
            
        return jar_path
    except Exception as e:
        print(f"Download failed: {e}")
        return None

def accept_eula(server_name):
    """Writes eula.txt=true to the server directory."""
    server_path = os.path.join(SERVERS_DIR, server_name)
    eula_path = os.path.join(server_path, "eula.txt")
    
    with open(eula_path, "w") as f:
        f.write("eula=true\n")

