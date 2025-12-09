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
        "1.20.1": "https://maven.fabricmc.net/net/fabricmc/fabric-installer/1.0.1/fabric-installer-1.0.1.jar"
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

def install_fabric(server_name, mc_version, progress_callback=None):
    """
    Downloads Fabric Installer and runs it to generate server files.
    """
    server_path = create_server_directory(server_name)
    installer_url = SERVER_URLS["Fabric"]["1.20.1"] # Hardcoded for now based on input
    installer_path = os.path.join(server_path, "fabric-installer.jar")
    
    # 1. Download Installer
    try:
        if progress_callback: progress_callback(0.1)
        response = requests.get(installer_url, stream=True)
        response.raise_for_status()
        with open(installer_path, "wb") as f:
            for chunk in response.iter_content(chunk_size=8192):
                f.write(chunk)
        if progress_callback: progress_callback(0.3)
    except Exception as e:
        print(f"Fabric download failed: {e}")
        return None

    # 2. Run Installer
    # java -jar fabric-installer.jar server -mcversion 1.20.1 -downloadMinecraft
    cmd = [
        "java", "-jar", "fabric-installer.jar", 
        "server", "-mcversion", mc_version, "-downloadMinecraft"
    ]
    
    try:
        if progress_callback: progress_callback(0.5)
        # Run in the server directory
        subprocess.run(cmd, cwd=server_path, check=True, capture_output=True)
        if progress_callback: progress_callback(0.9)
        
        # Cleanup installer? Maybe keep it.
        return os.path.join(server_path, "fabric-server-launch.jar")
        
    except subprocess.CalledProcessError as e:
        print(f"Fabric install failed: {e}")
        return None


class ServerRunner:
    def __init__(self, server_name, ram_allocation, console_callback):
        self.server_name = server_name
        self.console_callback = console_callback
        self.process = None
        self.running = False

        # Try to load RAM from metadata
        try:
            with open(os.path.join(SERVERS_DIR, server_name, "metadata.json"), "r") as f:
                meta = json.load(f)
                if "ram" in meta:
                    self.ram_allocation = f"{meta['ram']}M"
                else:
                    self.ram_allocation = ram_allocation
        except:
            self.ram_allocation = ram_allocation

    def start(self):
        if self.running:
            return
        
        server_path = os.path.join(SERVERS_DIR, self.server_name)
        
        # Check/Accept EULA
        if not check_eula(self.server_name):
            accept_eula(self.server_name)
            self.console_callback("[System] EULA auto-accepted.")

        # Determine jar file
        # Priority: fabric-server-launch.jar -> server.jar
        jar_file = "server.jar"
        if os.path.exists(os.path.join(server_path, "fabric-server-launch.jar")):
            jar_file = "fabric-server-launch.jar"
        
        if not os.path.exists(os.path.join(server_path, jar_file)):
            self.console_callback(f"[Error] Server jar not found: {jar_file}")
            return

        cmd = ["java", f"-Xmx{self.ram_allocation}", "-jar", jar_file, "nogui"]
        
        self.console_callback(f"[System] Starting server with: {' '.join(cmd)}")
        
        try:
            self.process = subprocess.Popen(
                cmd,
                cwd=server_path,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                bufsize=1
            )
            self.running = True
            
            # Start output reader thread
            threading.Thread(target=self._read_output, daemon=True).start()
            
        except Exception as e:
            self.console_callback(f"[Error] Failed to start server: {e}")
            self.running = False

    def stop(self):
        if not self.running or not self.process:
            return

        self.console_callback("[System] Stopping server...")
        try:
            if self.process.stdin:
                self.process.stdin.write("stop\n")
                self.process.stdin.flush()
            
            # Wait for graceful exit (up to 10 seconds)
            try:
                self.process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                self.console_callback("[System] Server unresponsive, force killing...")
                self.process.kill()
                self.process.wait()
                
        except Exception as e:
            self.console_callback(f"[Error] Failed to stop server: {e}")
            # Ensure it's dead if an error occurred during stop
            if self.process:
                try:
                    self.process.kill()
                except:
                    pass

    def _read_output(self):
        """Reads stdout from the process and sends it to the callback."""
        if not self.process:
            return

        for line in self.process.stdout:
            self.console_callback(line.strip())
        
        self.process.wait()
        self.running = False
        self.process = None
        self.console_callback("[System] Server process exited.")

def check_eula(server_name):
    """Checks if eula.txt exists and is true."""
    server_path = os.path.join(SERVERS_DIR, server_name)
    eula_path = os.path.join(server_path, "eula.txt")
    
    if not os.path.exists(eula_path):
        return False
        
    with open(eula_path, "r") as f:
        content = f.read()
        return "eula=true" in content

def load_server_properties(server_name):
    """Reads server.properties into a dict."""
    props_path = os.path.join(SERVERS_DIR, server_name, "server.properties")
    properties = {}
    
    if not os.path.exists(props_path):
        return properties
        
    with open(props_path, "r") as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#"):
                if "=" in line:
                    key, value = line.split("=", 1)
                    properties[key.strip()] = value.strip()
    return properties

def save_server_properties(server_name, new_properties):
    """Updates server.properties while preserving comments/order if possible."""
    props_path = os.path.join(SERVERS_DIR, server_name, "server.properties")
    
    if not os.path.exists(props_path):
        # Create new
        with open(props_path, "w") as f:
            for k, v in new_properties.items():
                f.write(f"{k}={v}\n")
        return

    # Read existing lines to preserve comments
    with open(props_path, "r") as f:
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
            
    # Append new keys that weren't in the file
    for k, v in new_properties.items():
        if k not in updated_keys:
            new_lines.append(f"{k}={v}\n")
            
    with open(props_path, "w") as f:
        f.writelines(new_lines)

import datetime
import zipfile

class BackupManager:
    def __init__(self, server_name):
        self.server_name = server_name
        self.server_path = os.path.join(SERVERS_DIR, server_name)
        self.backup_dir = os.path.join("backups", server_name)
        
        if not os.path.exists(self.backup_dir):
            os.makedirs(self.backup_dir)

    def create_backup(self):
        """Creates a zip backup of the server directory."""
        timestamp = datetime.datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
        backup_filename = f"{timestamp}.zip"
        backup_path = os.path.join(self.backup_dir, backup_filename)
        
        try:
            with zipfile.ZipFile(backup_path, 'w', zipfile.ZIP_DEFLATED) as zipf:
                for root, dirs, files in os.walk(self.server_path):
                    # Exclude backups folder if it's somehow inside (shouldn't be, but safety first)
                    if "backups" in root:
                        continue
                        
                    for file in files:
                        file_path = os.path.join(root, file)
                        # Archive name relative to server root
                        arcname = os.path.relpath(file_path, self.server_path)
                        zipf.write(file_path, arcname)
            return backup_path
        except Exception as e:
            print(f"Backup failed: {e}")
            return None

    def list_backups(self):
        """Returns a list of dicts with backup info."""
        backups = []
        if not os.path.exists(self.backup_dir):
            return backups
            
        for filename in os.listdir(self.backup_dir):
            if filename.endswith(".zip"):
                path = os.path.join(self.backup_dir, filename)
                size_mb = os.path.getsize(path) / (1024 * 1024)
                backups.append({
                    "name": filename,
                    "path": path,
                    "size": f"{size_mb:.2f} MB",
                    "date": filename.replace(".zip", "")
                })
        # Sort by date desc
        backups.sort(key=lambda x: x["name"], reverse=True)
        return backups

    def restore_backup(self, backup_path):
        """Restores a backup, wiping the current server directory first."""
        if not os.path.exists(backup_path):
            return False
            
        # Safety: Create a temp backup of current state? 
        # For now, let's just wipe and restore.
        
        try:
            # 1. Clear server directory
            for item in os.listdir(self.server_path):
                item_path = os.path.join(self.server_path, item)
                if os.path.isfile(item_path) or os.path.islink(item_path):
                    os.unlink(item_path)
                elif os.path.isdir(item_path):
                    shutil.rmtree(item_path)
            
            # 2. Extract backup
            with zipfile.ZipFile(backup_path, 'r') as zipf:
                zipf.extractall(self.server_path)
                
            return True
        except Exception as e:
            print(f"Restore failed: {e}")
            return False

class Scheduler:
    def __init__(self, server_name):
        self.server_name = server_name
        self.server_path = os.path.join(SERVERS_DIR, server_name)
        self.metadata_path = os.path.join(self.server_path, "metadata.json")
        
    def _load_metadata(self):
        if not os.path.exists(self.metadata_path):
            return {}
        try:
            with open(self.metadata_path, "r") as f:
                return json.load(f)
        except:
            return {}

    def _save_metadata(self, data):
        with open(self.metadata_path, "w") as f:
            json.dump(data, f)

    def set_restart_schedule(self, enabled, interval_hours=None):
        """
        Sets the restart schedule.
        enabled: bool
        interval_hours: int (e.g., 6, 12, 24)
        """
        data = self._load_metadata()
        
        if not enabled:
            if "scheduler" in data:
                del data["scheduler"]
        else:
            data["scheduler"] = {
                "type": "interval",
                "interval_hours": interval_hours,
                "last_run": datetime.datetime.now().isoformat() # Reset timer on set
            }
            
        self._save_metadata(data)

    def get_schedule(self):
        data = self._load_metadata()
        return data.get("scheduler", None)

    def check_due(self):
        """Checks if a restart is due. Returns True if yes."""
        data = self._load_metadata()
        scheduler = data.get("scheduler")
        
        if not scheduler:
            return False
            
        if scheduler["type"] == "interval":
            last_run_str = scheduler.get("last_run")
            if not last_run_str:
                # First run?
                self.update_last_run()
                return False
                
            last_run = datetime.datetime.fromisoformat(last_run_str)
            interval = datetime.timedelta(hours=scheduler["interval_hours"])
            
            if datetime.datetime.now() >= last_run + interval:
                return True
                
        return False

    def update_last_run(self):
        data = self._load_metadata()
        if "scheduler" in data:
            data["scheduler"]["last_run"] = datetime.datetime.now().isoformat()
            self._save_metadata(data)
