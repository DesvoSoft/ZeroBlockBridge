import json
import os
import subprocess
import shutil

import shutil
import requests
import threading
import platform

from app.constants import APP_CONFIG_PATH, SERVERS_DIR, MINECRAFT_VERSIONS, BACKUPS_DIR
from app.server_events import ServerEvent, ServerEventEmitter

def load_config():
    """Loads the configuration from config.json."""
    if not os.path.exists(APP_CONFIG_PATH):
        default_config = {
            "java_path": "auto",
            "ram_allocation": "2G",
            "accepted_eula": False,
            "last_server": None
        }
        save_config(default_config)
        return default_config
    
    try:
        with open(APP_CONFIG_PATH, "r") as f:
            return json.load(f)
    except json.JSONDecodeError:
        return load_config() # Return default if corrupted (or handle better)

def save_config(config):
    """Saves the configuration to config.json."""
    # Ensure the parent directory exists
    APP_CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(APP_CONFIG_PATH, "w") as f:
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
    url = MINECRAFT_VERSIONS.get(server_type, {}).get(version)
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
    installer_url = MINECRAFT_VERSIONS.get("Fabric", {}).get(mc_version)
    if not installer_url:
        print(f"Fabric installer not found for version {mc_version}")
        return None
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
            
        self.player_count = 0
        self.events = ServerEventEmitter()

    def _apply_pending_settings(self):
        """Checks for and applies initial settings from the wizard, creating the properties file if needed."""
        metadata_path = os.path.join(SERVERS_DIR, self.server_name, "metadata.json")
        if not os.path.exists(metadata_path):
            return

        try:
            with open(metadata_path, "r+") as f:
                meta = json.load(f)
                pending = meta.get("pending_settings")

                if not pending or not any(pending.values()):
                    return

                self.console_callback("[System] Applying initial server settings from wizard...")
                
                # Load existing properties or create an empty dictionary
                props = load_server_properties(self.server_name)
                
                # If props is empty, it's the first time, so set defaults
                if not props:
                    props["network-compression-threshold"] = "256"
                    props["sync-chunk-writes"] = "false"
                    props["entity-broadcast-range-percentage"] = "75"
                    props["allow-flight"] = "true"

                # Map wizard keys to server.properties keys
                if pending.get("seed"): props["level-seed"] = pending.get("seed")
                if pending.get("game_mode"): props["gamemode"] = pending.get("game_mode")
                if pending.get("difficulty"): props["difficulty"] = pending.get("difficulty")
                if pending.get("view_distance"): props["view-distance"] = pending.get("view_distance")
                if pending.get("simulation_distance"): props["simulation-distance"] = pending.get("simulation_distance")
                
                # Save the updated properties. This will create the file if it doesn't exist.
                save_server_properties(self.server_name, props)
                
                # Clear pending settings to prevent re-application
                meta["pending_settings"] = {}
                f.seek(0)
                f.truncate()
                json.dump(meta, f, indent=4)
                self.console_callback("[System] Initial settings applied successfully.")

        except Exception as e:
            self.console_callback(f"[Error] Failed to apply pending settings: {e}")

    def start(self):
        if self.running:
            return
        
        # Always apply settings before starting. This will create server.properties if it's the first time.
        self._apply_pending_settings()
        
        # Accept EULA if not already accepted.
        if not check_eula(self.server_name):
            accept_eula(self.server_name)
            self.console_callback("[System] EULA auto-accepted.")

        server_path = os.path.join(SERVERS_DIR, self.server_name)

        # Determine jar file
        jar_file = "server.jar"
        if os.path.exists(os.path.join(server_path, "fabric-server-launch.jar")):
            jar_file = "fabric-server-launch.jar"
        
        if not os.path.exists(os.path.join(server_path, jar_file)):
            self.console_callback(f"[Error] Server jar not found: {jar_file}")
            return

        # Build command with Java 24+ compatibility flags
        cmd = [
            "java",
            f"-Xms{self.ram_allocation}",
            f"-Xmx{self.ram_allocation}",
            "--enable-native-access=ALL-UNNAMED",
            "-Dorg.lwjgl.util.NoChecks=true",
            "-jar",
            jar_file,
            "nogui"
        ]
        
        self.console_callback(f"[System] Starting server with: {' '.join(cmd)}")
        self.events.emit(ServerEvent.STARTING)
        
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

    def send_command(self, command):
        """Sends a command to the server stdin."""
        if not self.running or not self.process or not self.process.stdin:
            return
            
        try:
            self.console_callback(f"> {command}")
            self.process.stdin.write(command + "\n")
            self.process.stdin.flush()
        except Exception as e:
            self.console_callback(f"[Error] Failed to send command: {e}")

    def _read_output(self):
        """Reads stdout from the process and sends it to the callback."""
        if not self.process:
            return

        for line in self.process.stdout:
            self.console_callback(line.strip())
            self._parse_player_count(line.strip())
            
            if "Done (" in line and "For help, type" in line:
                self.events.emit(ServerEvent.READY)
        
        self.process.wait()
        self.running = False
        self.process = None
        self.console_callback("[System] Server process exited.")
        self.events.emit(ServerEvent.STOPPED)

    def _parse_player_count(self, line):
        # Regex for "Player joined" and "Player left"
        # Vanilla/Fabric: "Player joined the game" / "Player left the game"
        if "joined the game" in line:
            self.player_count += 1
            self.events.emit(ServerEvent.PLAYER_COUNT, self.player_count)
        elif "left the game" in line:
            self.player_count = max(0, self.player_count - 1)
            self.events.emit(ServerEvent.PLAYER_COUNT, self.player_count)

def save_server_icon(server_name, image_path):
    """
    Resizes and saves the server icon.
    """
    try:
        from PIL import Image
        img = Image.open(image_path)
        img = img.resize((64, 64), Image.Resampling.LANCZOS)
        
        server_path = os.path.join(SERVERS_DIR, server_name)
        icon_path = os.path.join(server_path, "server-icon.png")
        img.save(icon_path, "PNG")
        return True
    except Exception as e:
        print(f"Failed to save icon: {e}")
        return False

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
        self.server_path = SERVERS_DIR / server_name
        self.backup_dir = BACKUPS_DIR / server_name
        
        if not self.backup_dir.exists():
            self.backup_dir.mkdir(parents=True, exist_ok=True)

    def create_backup(self):
        """Creates a zip backup of the server directory."""
        timestamp = datetime.datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
        backup_filename = f"{timestamp}.zip"
        backup_path = self.backup_dir / backup_filename
        
        try:
            with zipfile.ZipFile(backup_path, 'w', zipfile.ZIP_DEFLATED) as zipf:
                for root, dirs, files in os.walk(self.server_path):
                    # Exclude backups folder if it's somehow inside
                    if "backups" in root:
                        continue
                        
                    for file in files:
                        file_path = os.path.join(root, file)
                        arcname = os.path.relpath(file_path, self.server_path)
                        zipf.write(file_path, arcname)
            return backup_path
        except Exception as e:
            print(f"Backup failed: {e}")
            return None

    def list_backups(self):
        """Returns a list of dicts with backup info."""
        backups = []
        if not self.backup_dir.exists():
            return backups
            
        for f in self.backup_dir.iterdir():
            if f.is_file() and f.suffix == ".zip":
                size_mb = f.stat().st_size / (1024 * 1024)
                backups.append({
                    "name": f.name,
                    "path": str(f),
                    "size": f"{size_mb:.2f} MB",
                    # Parse and reformat the date string to a more readable format
                    "date": datetime.datetime.strptime(f.stem, "%Y-%m-%d_%H-%M-%S").strftime("%d %b %Y %H:%M")
                })
        # Sort by name (which is the date) desc
        backups.sort(key=lambda x: x["name"], reverse=True)
        return backups

    def restore_backup(self, backup_path_str):
        """Restores a backup, wiping the current server directory first."""
        backup_path = BACKUPS_DIR / self.server_name / os.path.basename(backup_path_str)
        if not backup_path.exists():
            return False
            
        try:
            # 1. Clear server directory
            for item in self.server_path.iterdir():
                if item.is_file() or item.is_symlink():
                    item.unlink()
                elif item.is_dir():
                    shutil.rmtree(item)
            
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

    def set_restart_schedule(self, enabled, interval_hours=None, restart_time=None):
        """
        Sets the restart schedule.
        enabled: bool
        interval_hours: int (e.g., 6, 12, 24) for interval mode
        restart_time: str (e.g., "03:00") for time mode
        """
        data = self._load_metadata()
        
        if not enabled:
            if "scheduler" in data:
                del data["scheduler"]
        else:
            if restart_time:
                # Time-based schedule
                data["scheduler"] = {
                    "type": "time",
                    "restart_time": restart_time,
                    "last_run": None  # Will be set after first restart
                }
            else:
               # Interval-based schedule
                data["scheduler"] = {
                    "type": "interval",
                    "interval_hours": interval_hours,
                    "last_run": datetime.datetime.now().isoformat()
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
                self.update_last_run()
                return False
                
            last_run = datetime.datetime.fromisoformat(last_run_str)
            interval = datetime.timedelta(hours=scheduler["interval_hours"])
            
            if datetime.datetime.now() >= last_run + interval:
                return True
                
        elif scheduler["type"] == "time":
            # Time-based restart (e.g., daily at 03:00)
            restart_time_str = scheduler["restart_time"]  # "HH:MM"
            last_run_str = scheduler.get("last_run")
            
            # Parse target time for today
            hour, minute = map(int, restart_time_str.split(":"))
            now = datetime.datetime.now()
            target_time_today = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
            
            # Check if we've already restarted today
            if last_run_str:
                last_run = datetime.datetime.fromisoformat(last_run_str)
                # If last restart was today and within 5 minutes of target, don't restart again
                if last_run.date() == now.date():
                    time_since_last = (now - last_run).total_seconds()
                    if time_since_last < 300:  # 5 minutes
                        return False
            
            # Check if we're within the 2-minute window around target time
            time_diff = (now - target_time_today).total_seconds()
            # Trigger if we're past the target time but within 2 minutes
            if 0 <= time_diff < 120:
                return True

        return False

    def update_last_run(self):
        data = self._load_metadata()
        if "scheduler" in data:
            data["scheduler"]["last_run"] = datetime.datetime.now().isoformat()
            self._save_metadata(data)


def apply_server_settings(server_name, ram, seed, game_mode, difficulty, view_distance, simulation_distance):
    """
    Applies initial server settings after server installation.
    Creates metadata.json and accepts EULA.
    Server properties will be configured after first server start.
    """
    server_path = os.path.join(SERVERS_DIR, server_name)
    
    # 1. Create metadata.json with RAM and other settings
    metadata = {
        "ram": ram,
        "created": datetime.datetime.now().isoformat(),
        "pending_settings": {
            "seed": seed,
            "game_mode": game_mode,
            "difficulty": difficulty,
            "view_distance": view_distance,
            "simulation_distance": simulation_distance
        }
    }
    metadata_path = os.path.join(server_path, "metadata.json")
    with open(metadata_path, "w") as f:
        json.dump(metadata, f, indent=4)
    
    # 2. Accept EULA so server can start
    accept_eula(server_name)
    
    # Note: server.properties will be generated on first server start
    # The pending_settings will be applied by the UI after the server generates the file
    
    # Create a default server.properties so the settings button is enabled immediately
    props = {
        "network-compression-threshold": "256",
        "sync-chunk-writes": "false",
        "entity-broadcast-range-percentage": "75",
        "allow-flight": "true",
        "level-seed": seed if seed else "",
        "gamemode": game_mode,
        "difficulty": difficulty,
        "view-distance": view_distance,
        "simulation-distance": simulation_distance
    }
    save_server_properties(server_name, props)
    
    # Clear pending settings since we just applied them
    metadata["pending_settings"] = {}
    with open(metadata_path, "w") as f:
        json.dump(metadata, f, indent=4)

def get_server_ram(server_name):
    """Gets the RAM allocation (MB) from metadata.json."""
    try:
        with open(os.path.join(SERVERS_DIR, server_name, "metadata.json"), "r") as f:
            meta = json.load(f)
            return meta.get("ram", 2048)
    except:
        return 2048

def set_server_ram(server_name, ram_mb):
    """Sets the RAM allocation (MB) in metadata.json."""
    metadata_path = os.path.join(SERVERS_DIR, server_name, "metadata.json")
    try:
        if os.path.exists(metadata_path):
            with open(metadata_path, "r") as f:
                meta = json.load(f)
        else:
            meta = {}
            
        meta["ram"] = int(ram_mb)
        
        with open(metadata_path, "w") as f:
            json.dump(meta, f, indent=4)
        return True
    except Exception as e:
        print(f"Failed to set RAM: {e}")
        return False



def play_sound(sound_path):
    """
    Plays a sound file in a cross-platform manner.
    Supports Windows (playsound/winsound) and Linux (paplay/aplay).
    """
    if not os.path.exists(sound_path):
        print(f"[Warning] Sound file not found: {sound_path}")
        return

    system = platform.system()

    try:
        if system == "Windows":
            # Try playsound first, fallback to winsound
            try:
                from playsound import playsound
                playsound(str(sound_path))
            except Exception as e:
                print(f"[Debug] playsound failed ({e}), trying winsound...")
                try:
                    import winsound
                    winsound.PlaySound(str(sound_path), winsound.SND_FILENAME)
                except Exception as ws_e:
                    print(f"[Error] Windows sound failed: {ws_e}")

        elif system == "Linux":
            # Try common Linux players
            # paplay is for PulseAudio (most common)
            # aplay is for ALSA (fallback)
            # canberra-gtk-play is for GTK systems
            players = [
                ["paplay", str(sound_path)],
                ["aplay", str(sound_path)],
                ["canberra-gtk-play", "-f", str(sound_path)],
                ["mpg123", str(sound_path)]
            ]
            
            success = False
            for cmd in players:
                try:
                    subprocess.run(cmd, check=True, capture_output=True)
                    success = True
                    break
                except (FileNotFoundError, subprocess.CalledProcessError):
                    continue
            
            if not success:
                print("[Warning] No suitable audio player found on Linux (tried paplay, aplay, canberra-gtk-play).")

        else:
            print(f"[Warning] Sound not supported on {system}")

    except Exception as e:
        print(f"[Error] Failed to play sound: {e}")

