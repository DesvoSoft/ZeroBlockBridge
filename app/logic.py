import json
import os
import subprocess
import shutil
import requests
import threading
import platform
import sys
import datetime
import zipfile

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
                    downloaded += len(chunk)
                    if progress_callback and total_size > 0:
                        progress_callback(downloaded / total_size)
        
        if progress_callback:
            progress_callback(1.0)
            
        return jar_path
    except Exception as e:
        print(f"Download failed: {e}")
        if os.path.exists(jar_path):
            os.remove(jar_path)
        return None

def accept_eula(server_name):
    """Writes eula.txt=true."""
    server_path = os.path.join(SERVERS_DIR, server_name)
    eula_path = os.path.join(server_path, "eula.txt")
    with open(eula_path, "w") as f:
        f.write("eula=true\n")

def install_fabric(server_name, mc_version, progress_callback=None):
    """Installs Fabric."""
    server_path = create_server_directory(server_name)
    vm = VersionManager()
    installer_url = vm.get_download_url("Fabric", mc_version)
    
    if not installer_url:
        return None
    installer_path = os.path.join(server_path, "fabric-installer.jar")
    
    try:
        if progress_callback: progress_callback(0.1)
        response = requests.get(installer_url, stream=True)
        response.raise_for_status()
        with open(installer_path, "wb") as f:
            for chunk in response.iter_content(chunk_size=8192):
                f.write(chunk)
        if progress_callback: progress_callback(0.3)
    except Exception as e:
        return None

    cmd = ["java", "-jar", "fabric-installer.jar", "server", "-mcversion", mc_version, "-downloadMinecraft"]
    try:
        if progress_callback: progress_callback(0.5)
        subprocess.run(cmd, cwd=server_path, check=True, capture_output=True)
        if progress_callback: progress_callback(0.9)
        return os.path.join(server_path, "fabric-server-launch.jar")
    except subprocess.CalledProcessError:
        return None

def install_forge(server_name, mc_version, progress_callback=None):
    """Installs Forge."""
    server_path = create_server_directory(server_name)
    vm = VersionManager()
    installer_url = vm.get_download_url("Forge", mc_version)
    
    if not installer_url:
        return None
        
    installer_path = os.path.join(server_path, "forge-installer.jar")
    
    try:
        if progress_callback: progress_callback(0.1)
        response = requests.get(installer_url, stream=True)
        response.raise_for_status()
        with open(installer_path, "wb") as f:
            for chunk in response.iter_content(chunk_size=8192):
                f.write(chunk)
        if progress_callback: progress_callback(0.3)
    except Exception as e:
        return None

    cmd = ["java", "-jar", "forge-installer.jar", "--installServer"]
    try:
        if progress_callback: progress_callback(0.5)
        subprocess.run(cmd, cwd=server_path, check=True, capture_output=True, text=True)
        if progress_callback: progress_callback(0.9)
        
        for file in os.listdir(server_path):
            if file.startswith("forge-") and file.endswith(".jar") and "installer" not in file:
                return os.path.join(server_path, file)
        
        if os.path.exists(os.path.join(server_path, "run.bat")):
            return "FORGE_MODERN"
            
        return None
    except subprocess.CalledProcessError:
        return None

class ServerRunner:
    def __init__(self, server_name, ram_allocation, console_callback):
        self.server_name = server_name
        self.console_callback = console_callback
        self.process = None
        self.running = False

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
                props = load_server_properties(self.server_name)
                if not props:
                    props["network-compression-threshold"] = "256"
                    props["sync-chunk-writes"] = "false"
                    props["entity-broadcast-range-percentage"] = "75"
                    props["allow-flight"] = "true"
                    props["force-gamemode"] = "true"

                if pending.get("seed"): props["level-seed"] = pending.get("seed")
                if pending.get("game_mode"): props["gamemode"] = pending.get("game_mode")
                if pending.get("difficulty"): props["difficulty"] = pending.get("difficulty")
                if pending.get("view_distance"): props["view-distance"] = pending.get("view_distance")
                if pending.get("simulation_distance"): props["simulation-distance"] = pending.get("simulation_distance")
                
                save_server_properties(self.server_name, props)
                
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
        
        self._apply_pending_settings()
        
        if not check_eula(self.server_name):
            accept_eula(self.server_name)
            self.console_callback("[System] EULA auto-accepted.")

        server_path = os.path.join(SERVERS_DIR, self.server_name)

        # Determine startup method
        jar_file = "server.jar"
        is_forge_modern = False
        forge_args_file = None
        
        # Check for Fabric
        if os.path.exists(os.path.join(server_path, "fabric-server-launch.jar")):
            jar_file = "fabric-server-launch.jar"
        
        # Check for Forge (Modern 1.17+)
        elif os.path.exists(os.path.join(server_path, "run.bat")) or os.path.exists(os.path.join(server_path, "run.sh")):
            is_forge_modern = True
            args_pattern = "win_args.txt" if sys.platform == "win32" else "unix_args.txt"
            for root, dirs, files in os.walk(os.path.join(server_path, "libraries")):
                if args_pattern in files:
                    forge_args_file = os.path.relpath(os.path.join(root, args_pattern), server_path)
                    break
        
        # Check for Forge (Legacy)
        else:
            for file in os.listdir(server_path):
                if file.startswith("forge-") and file.endswith(".jar") and "installer" not in file:
                    jar_file = file
                    break
        
        if not is_forge_modern and not os.path.exists(os.path.join(server_path, jar_file)):
            self.console_callback(f"[Error] Server jar not found: {jar_file}")
            return

        # Build command
        if is_forge_modern and forge_args_file:
            cmd = [
                "java",
                f"-Xms{self.ram_allocation}",
                f"-Xmx{self.ram_allocation}",
                "--enable-native-access=ALL-UNNAMED",
                "-Dorg.lwjgl.util.NoChecks=true",
                f"@{forge_args_file}",
                "nogui"
            ]
        else:
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
            threading.Thread(target=self._read_output, daemon=True).start()
        except Exception as e:
            self.console_callback(f"[Error] Failed to start server: {e}")
            self.running = False

    def stop(self):
        if not self.running or not self.process:
            return

        self.console_callback("[System] Stopping server...")
        try:
            if self.process.stdin and self.process.poll() is None:
                try:
                    self.process.stdin.write("stop\n")
                    self.process.stdin.flush()
                except (IOError, BrokenPipeError):
                    pass
            
            try:
                self.process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                self.console_callback("[System] Server unresponsive, force killing...")
                self.process.kill()
                self.process.wait()
        except Exception as e:
            self.console_callback(f"[Error] Failed to stop server: {e}")
            if self.process:
                try: self.process.kill()
                except: pass

    def send_command(self, command):
        if not self.running or not self.process or not self.process.stdin:
            return
        try:
            self.console_callback(f"> {command}")
            self.process.stdin.write(command + "\n")
            self.process.stdin.flush()
        except Exception as e:
            self.console_callback(f"[Error] Failed to send command: {e}")

    def _read_output(self):
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
        if "joined the game" in line:
            self.player_count += 1
            self.events.emit(ServerEvent.PLAYER_COUNT, self.player_count)
        elif "left the game" in line:
            self.player_count = max(0, self.player_count - 1)
            self.events.emit(ServerEvent.PLAYER_COUNT, self.player_count)

def save_server_icon(server_name, image_path):
    try:
        from PIL import Image
        img = Image.open(image_path)
        img = img.resize((64, 64), Image.Resampling.LANCZOS)
        server_path = os.path.join(SERVERS_DIR, server_name)
        icon_path = os.path.join(server_path, "server-icon.png")
        img.save(icon_path, "PNG")
        return True
    except:
        return False

def check_eula(server_name):
    server_path = os.path.join(SERVERS_DIR, server_name)
    eula_path = os.path.join(server_path, "eula.txt")
    if not os.path.exists(eula_path): return False
    with open(eula_path, "r") as f:
        return "eula=true" in f.read()

def load_server_properties(server_name):
    props_path = os.path.join(SERVERS_DIR, server_name, "server.properties")
    properties = {}
    if not os.path.exists(props_path): return properties
    with open(props_path, "r") as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                key, value = line.split("=", 1)
                properties[key.strip()] = value.strip()
    return properties

def save_server_properties(server_name, new_properties):
    props_path = os.path.join(SERVERS_DIR, server_name, "server.properties")
    if not os.path.exists(props_path):
        with open(props_path, "w") as f:
            for k, v in new_properties.items():
                f.write(f"{k}={v}\n")
        return
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
            else: new_lines.append(line)
        else: new_lines.append(line)
    for k, v in new_properties.items():
        if k not in updated_keys: new_lines.append(f"{k}={v}\n")
    with open(props_path, "w") as f:
        f.writelines(new_lines)

class BackupManager:
    def __init__(self, server_name):
        self.server_name = server_name
        self.server_path = SERVERS_DIR / server_name
        self.backup_dir = BACKUPS_DIR / server_name
        if not self.backup_dir.exists():
            self.backup_dir.mkdir(parents=True, exist_ok=True)

    def create_backup(self):
        timestamp = datetime.datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
        backup_filename = f"{timestamp}.zip"
        backup_path = self.backup_dir / backup_filename
        abs_backup_dir = self.backup_dir.resolve()
        try:
            with zipfile.ZipFile(backup_path, 'w', zipfile.ZIP_DEFLATED) as zipf:
                for root, dirs, files in os.walk(self.server_path):
                    root_path = os.path.abspath(root)
                    if os.path.commonpath([root_path, str(abs_backup_dir)]) == str(abs_backup_dir):
                        continue
                    for file in files:
                        file_path = os.path.join(root, file)
                        if os.path.abspath(file_path) == str(os.path.abspath(backup_path)):
                            continue
                        arcname = os.path.relpath(file_path, self.server_path)
                        zipf.write(file_path, arcname)
            return backup_path, None
        except Exception as e:
            return None, str(e)

    def list_backups(self):
        backups = []
        if not self.backup_dir.exists(): return backups
        for f in self.backup_dir.iterdir():
            if f.is_file() and f.suffix == ".zip":
                size_mb = f.stat().st_size / (1024 * 1024)
                backups.append({
                    "name": f.name,
                    "path": str(f),
                    "size": f"{size_mb:.2f} MB",
                    "date": datetime.datetime.strptime(f.stem, "%Y-%m-%d_%H-%M-%S").strftime("%d %b %Y %H:%M")
                })
        backups.sort(key=lambda x: x["name"], reverse=True)
        return backups

    def get_latest_backup(self):
        if not self.backup_dir.exists(): return None
        backups = [f for f in self.backup_dir.iterdir() if f.is_file() and f.suffix == ".zip"]
        if not backups: return None
        backups.sort(key=lambda x: x.name, reverse=True)
        latest = backups[0]
        return {
            "name": latest.name,
            "path": str(latest),
            "date": datetime.datetime.strptime(latest.stem, "%Y-%m-%d_%H-%M-%S").strftime("%d %b %Y %H:%M")
        }

    def restore_backup(self, backup_path_str):
        backup_path = BACKUPS_DIR / self.server_name / os.path.basename(backup_path_str)
        if not backup_path.exists(): return False
        try:
            for item in self.server_path.iterdir():
                if item.is_file() or item.is_symlink(): item.unlink()
                elif item.is_dir(): shutil.rmtree(item)
            with zipfile.ZipFile(backup_path, 'r') as zipf:
                zipf.extractall(self.server_path)
            return True
        except: return False

class Scheduler:
    def __init__(self, server_name):
        self.server_name = server_name
        self.server_path = os.path.join(SERVERS_DIR, server_name)
        self.metadata_path = os.path.join(self.server_path, "metadata.json")
        
    def _load_metadata(self):
        if not os.path.exists(self.metadata_path): return {}
        try:
            with open(self.metadata_path, "r") as f: return json.load(f)
        except: return {}

    def _save_metadata(self, data):
        with open(self.metadata_path, "w") as f: json.dump(data, f)

    def set_restart_schedule(self, enabled, interval_hours=None, restart_time=None, backup_on_restart=False):
        data = self._load_metadata()
        if not enabled:
            if "scheduler" in data: del data["scheduler"]
        else:
            if restart_time:
                data["scheduler"] = {"type": "time", "restart_time": restart_time, "last_run": None, "backup_on_restart": backup_on_restart}
            else:
                data["scheduler"] = {"type": "interval", "interval_hours": interval_hours, "last_run": datetime.datetime.now().isoformat(), "backup_on_restart": backup_on_restart}
        self._save_metadata(data)

    def get_schedule(self):
        return self._load_metadata().get("scheduler", None)

    def check_due(self):
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
