import json
import logging
import os
import subprocess
import shutil
import requests
import threading

import sys
import datetime
import time
from pathlib import Path

from app.core.constants import APP_CONFIG_PATH, SERVERS_DIR, VANILLA_MANIFEST_URL
from app.core.server_events import ServerEvent
from app.core.version_manager import VersionManager

# Per-server threading.Events for jar normalization synchronization
_jar_ready_events: dict[str, threading.Event] = {}
_jar_events_lock = threading.Lock()


def create_junction(source: str, dest: str) -> None:
    """Create a cross-platform filesystem link (junction on Windows, symlink on Linux)."""
    if sys.platform == "win32":
        import _winapi
        _winapi.CreateJunction(source, dest)
    else:
        os.symlink(source, dest)

def _get_jar_event(server_dir: str) -> threading.Event:
    """Get or create a threading.Event for a server's jar normalization."""
    with _jar_events_lock:
        if server_dir not in _jar_ready_events:
            _jar_ready_events[server_dir] = threading.Event()
        return _jar_ready_events[server_dir]

def wait_for_jar_ready(server_dir: str, timeout: float = 5.0) -> bool:
    """Wait until normalize_server_jar signals that the jar is ready."""
    ev = _get_jar_event(server_dir)
    return ev.wait(timeout=timeout)

logger = logging.getLogger(__name__)

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
        logger.warning("Config file corrupted. Resetting to defaults.")
        save_config(default_config)
        return default_config

def save_config(config):
    """Saves the configuration to config.json."""
    APP_CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(APP_CONFIG_PATH, "w") as f:
        json.dump(config, f, indent=4)

def get_server_meta(server_name):
    """Centralized reader for server metadata.json."""
    meta_path = os.path.join(SERVERS_DIR, server_name, "metadata.json")
    if not os.path.exists(meta_path):
        return {}
    try:
        with open(meta_path, "r") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError) as e:
        logger.error("Failed to load metadata for %s: %s", server_name, e)
        return {}

def set_server_meta(server_name, key, value):
    """Centralized writer for server metadata.json."""
    meta_path = os.path.join(SERVERS_DIR, server_name, "metadata.json")
    try:
        meta = get_server_meta(server_name)
        meta[key] = value
        with open(meta_path, "w") as f:
            json.dump(meta, f, indent=4)
        return True
    except (OSError, json.JSONDecodeError) as e:
        logger.error("Failed to set metadata %s for %s: %s", key, server_name, e)
        return False

def update_server_meta(server_name, updates):
    """Atomic multi-key update for server metadata.json."""
    meta_path = os.path.join(SERVERS_DIR, server_name, "metadata.json")
    try:
        meta = get_server_meta(server_name)
        meta.update(updates)
        with open(meta_path, "w") as f:
            json.dump(meta, f, indent=4)
        return True
    except (OSError, json.JSONDecodeError) as e:
        logger.error("Failed to update metadata for %s: %s", server_name, e)
        return False

def check_java():
    """Check if a compatible Java installation is available on the system.
    
    Returns:
        str: The path to the java executable if found, None otherwise.
    """
    from app.services.java_detector import JavaDetector
    
    detector = JavaDetector()
    installations = detector.detect_all()
    if installations:
        # Return the path to the most preferred installation (highest Java version)
        best = installations[0]
        return best.path
    return None

def create_server_directory(server_name, server_type="Vanilla", version="1.20.1"):
    """Creates the server directory if it doesn't exist."""
    path = os.path.join(SERVERS_DIR, server_name)
    if not os.path.exists(path):
        os.makedirs(path)
    # Atomic Metadata: ensure metadata.json exists immediately after folder creation
    metadata_path = os.path.join(path, "metadata.json")
    if not os.path.exists(metadata_path):
        with open(metadata_path, "w") as f:
            json.dump({"name": server_name, "ram": 2048, "type": server_type, "version": version}, f, indent=4)
    return path

def download_server(server_name, server_type, version, progress_callback=None):
    """Downloads the server jar with SHA1 verification (PROV-04)."""
    vm = VersionManager()
    url = vm.get_download_url(server_type, version)

    if not url:
        raise ValueError(f"URL not found for {server_type} {version}")

    server_path = create_server_directory(server_name, server_type, version)
    jar_path = os.path.join(server_path, "server.jar")

    # Try to get expected SHA1 from Vanilla manifest
    expected_sha1 = None
    if server_type == "Vanilla":
        try:
            resp = requests.get(VANILLA_MANIFEST_URL, timeout=10)
            if resp.status_code == 200:
                manifest = resp.json()
                for v in manifest.get("versions", []):
                    if v["id"] == version:
                        v_resp = requests.get(v["url"], timeout=10)
                        if v_resp.status_code == 200:
                            v_data = v_resp.json()
                            expected_sha1 = v_data.get("downloads", {}).get("server", {}).get("sha1")
                        break
        except Exception as e:
            logger.warning("Failed to fetch SHA1 for validation: %s", e)

    if expected_sha1:
        from app.services.sha1_validator import download_with_verification
        success, path, error = download_with_verification(
            url, jar_path,
            expected_sha1=expected_sha1,
            progress_callback=progress_callback,
            max_retries=3,
        )
        if not success:
            logger.error("Download with SHA1 verification failed: %s", error)
            return None
    else:
        # Fallback to simple download with retry on network errors
        from app.services.sha1_validator import download_with_verification
        success, path, error = download_with_verification(
            url, jar_path,
            expected_sha1=None,
            progress_callback=progress_callback,
            max_retries=3,
        )
        if not success:
            logger.error("Download failed after retries: %s", error)
            return None

    normalize_server_jar(server_path)
    return jar_path

def accept_eula(server_name):
    """Writes eula.txt=true by delegating to scaffolder."""
    from app.services.scaffolder import _generate_eula
    server_path = os.path.join(SERVERS_DIR, server_name)
    _generate_eula(server_path, accepted=True)

def _run_installer(server_name, server_type, mc_version, installer_name, installer_args, progress_callback=None):
    server_path = create_server_directory(server_name, server_type, mc_version)
    vm = VersionManager()
    installer_url = vm.get_download_url(server_type, mc_version)

    if not installer_url:
        return None

    installer_path = os.path.join(server_path, installer_name)

    try:
        if progress_callback: progress_callback(0.1)
        response = requests.get(installer_url, stream=True, timeout=30)
        response.raise_for_status()
        with open(installer_path, "wb") as f:
            for chunk in response.iter_content(chunk_size=8192):
                f.write(chunk)
        if progress_callback: progress_callback(0.3)
    except Exception:
        return None

    cmd = ["java", "-jar", installer_name] + installer_args
    try:
        if progress_callback: progress_callback(0.5)
        subprocess.run(cmd, cwd=server_path, check=True, capture_output=True, text=True)
        if progress_callback: progress_callback(0.9)
        normalize_server_jar(server_path)
        return server_path
    except subprocess.CalledProcessError:
        return None


def install_fabric(server_name, mc_version, progress_callback=None):
    server_path = _run_installer(server_name, "Fabric", mc_version, "fabric-installer.jar",
                                  ["server", "-mcversion", mc_version, "-downloadMinecraft"], progress_callback)
    if server_path and os.path.exists(os.path.join(server_path, "fabric-server-launch.jar")):
        return os.path.join(server_path, "fabric-server-launch.jar")
    return None


def normalize_server_jar(server_dir):
    """Normalize the server jar to 'server.jar' for consistent access.

    Forge uses dynamic names like 'forge-1.20.1-44.1.23.jar'.
    This function finds the actual server entry jar and creates a
    copy or symlink named 'server.jar' so the bytecode analyzer
    and ServerRunner can always find it.

    After creating the jar, verifies it is readable and has minimum
    content size (> 100 bytes), then signals the per-server
    threading.Event so consumers (bytecode analyzer, server starter)
    can wait on it synchronously.
    """
    server_jar_path = os.path.join(server_dir, "server.jar")
    result = False

    # Verify existing server.jar is valid
    if os.path.exists(server_jar_path):
        try:
            if os.path.getsize(server_jar_path) > 100:
                with open(server_jar_path, "rb") as _f:
                    _f.read(4)
                result = True
        except OSError as e:
            logger.debug("Normalize: existing server.jar validation failed: %s", e)
        if result:
            _get_jar_event(server_dir).set()
            return True

    # Fabric
    fabric_jar = os.path.join(server_dir, "fabric-server-launch.jar")
    if os.path.exists(fabric_jar):
        try:
            os.symlink("fabric-server-launch.jar", server_jar_path)
            result = True
        except (OSError, NotImplementedError):
            try:
                shutil.copy2(fabric_jar, server_jar_path)
                result = True
            except Exception as e:
                logger.debug("Normalize: fabric copy failed: %s", e)

    # Forge (legacy: forge-*.jar, excluding installer)
    if not result:
        for fname in os.listdir(server_dir):
            if fname.startswith("forge-") and fname.endswith(".jar") and "installer" not in fname:
                src = os.path.join(server_dir, fname)
                try:
                    os.symlink(fname, server_jar_path)
                    result = True
                except (OSError, NotImplementedError):
                    try:
                        shutil.copy2(src, server_jar_path)
                        result = True
                    except Exception as e:
                        logger.debug("Normalize: forge legacy copy failed: %s", e)
                if result:
                    break

    # Forge Modern (1.17+) — look in libraries/ for the main jar via win_args.txt / unix_args.txt
    if not result:
        args_pattern = "win_args.txt" if sys.platform == "win32" else "unix_args.txt"
        for root, _dirs, files in os.walk(os.path.join(server_dir, "libraries")):
            if args_pattern in files:
                args_path = os.path.join(root, args_pattern)
                try:
                    with open(args_path, "r") as f:
                        content = f.read()
                    import re as _re
                    lib_jar_match = _re.search(r'([^\s]+\.jar)', content)
                    if lib_jar_match:
                        lib_rel = lib_jar_match.group(1)
                        lib_abs = os.path.join(server_dir, lib_rel)
                        if os.path.exists(lib_abs):
                            try:
                                os.symlink(os.path.relpath(lib_abs, server_dir), server_jar_path)
                            except (OSError, NotImplementedError):
                                shutil.copy2(lib_abs, server_jar_path)
                            result = True
                except Exception as e:
                    logger.debug("Normalize: forge modern detection failed: %s", e)
                break

    # Paper / Purpur — find any jar that is not an installer
    if not result:
        for fname in os.listdir(server_dir):
            if fname.endswith(".jar") and fname not in ("forge-installer.jar", "fabric-installer.jar"):
                src = os.path.join(server_dir, fname)
                try:
                    os.symlink(fname, server_jar_path)
                    result = True
                except (OSError, NotImplementedError):
                    try:
                        shutil.copy2(src, server_jar_path)
                        result = True
                    except Exception as e:
                        logger.debug("Normalize: paper/purpur copy failed: %s", e)
                if result:
                    break

    # Final verification: ensure the created symlink/copy is readable
    if result:
        try:
            import time
            for _ in range(10):
                if os.path.exists(server_jar_path) and os.path.getsize(server_jar_path) > 100:
                    break
                time.sleep(0.5)

            if not os.path.exists(server_jar_path) or os.path.getsize(server_jar_path) <= 100:
                size = os.path.getsize(server_jar_path) if os.path.exists(server_jar_path) else 0
                logger.warning("normalize_server_jar: %s is missing or too small (%d bytes)", server_jar_path, size)
                result = False
            else:
                with open(server_jar_path, "rb") as _f:
                    _f.read(4)
        except OSError as e:
            logger.debug("Normalize: final verification failed: %s", e)
            result = False

    # Signal consumers the jar is ready (or timeout will handle failure)
    _get_jar_event(server_dir).set()
    return result


def install_forge(server_name, mc_version, progress_callback=None):
    """Installs Forge."""
    server_path = create_server_directory(server_name, "Forge", mc_version)
    vm = VersionManager()
    installer_url = vm.get_download_url("Forge", mc_version)
    
    if not installer_url:
        return None
        
    installer_path = os.path.join(server_path, "forge-installer.jar")
    
    try:
        if progress_callback: progress_callback(0.1)
        response = requests.get(installer_url, stream=True, timeout=30)
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
        
        # Normalize: ensure server.jar exists for bytecode analyzer
        normalize_server_jar(server_path)
        
        for file in os.listdir(server_path):
            if file.startswith("forge-") and file.endswith(".jar") and "installer" not in file:
                return os.path.join(server_path, file)
        
        if os.path.exists(os.path.join(server_path, "run.bat")):
            return "FORGE_MODERN"
            
        return None
    except subprocess.CalledProcessError:
        return None

class ServerRunner:
    def __init__(self, server_name, ram_allocation, event_bus, java_bin="java", use_aikars=True):
        self.server_name = server_name
        self.events = event_bus
        self.process = None
        self.running = False
        self.exit_code = None
        self._stderr_buffer = []
        self._stderr_thread = None
        self.java_bin = java_bin
        self.use_aikars = use_aikars

        try:
            with open(os.path.join(SERVERS_DIR, server_name, "metadata.json"), "r") as f:
                meta = json.load(f)
                if "ram" in meta:
                    self.ram_allocation = f"{meta['ram']}M"
                else:
                    self.ram_allocation = ram_allocation
        except (FileNotFoundError, json.JSONDecodeError, OSError) as e:
            logger.warning("Could not load metadata for %s: %s", server_name, e)
            self.ram_allocation = ram_allocation
            
        self.player_count = 0
        self._stderr_done = threading.Event()

    def start(self):
        if self.running:
            return
        
        if not check_eula(self.server_name):
            accept_eula(self.server_name)
            self.events.emit(ServerEvent.CONSOLE_LINE, "[System] EULA auto-accepted.")

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
            self.events.emit(ServerEvent.CONSOLE_LINE, f"[Error] Server jar not found: {jar_file}")
            return

        # Parse RAM in MB for flags calculator
        ram_str = self.ram_allocation.rstrip("MmGg")
        try:
            ram_mb = int(ram_str)
            if self.ram_allocation.upper().endswith("G"):
                ram_mb *= 1024
        except ValueError:
            ram_mb = 2048

        # Find Java major version
        java_major = 17
        try:
            from app.services.java_detector import _probe_java
            inst = _probe_java(self.java_bin, "PROBE")
            if inst:
                java_major = inst.major
        except Exception:
            pass

        from app.services.aikars_flags import calculate_flags
        aikars = calculate_flags(ram_mb, java_major=java_major) if self.use_aikars else [f"-Xms{ram_mb}M", f"-Xmx{ram_mb}M"]

        if is_forge_modern and forge_args_file:
            cmd = [self.java_bin] + aikars + [
                "--enable-native-access=ALL-UNNAMED",
                "-Dorg.lwjgl.util.NoChecks=true",
                f"@{forge_args_file}",
                "nogui",
            ]
        else:
            cmd = [self.java_bin] + aikars + [
                "-jar",
                jar_file,
                "nogui",
            ]
        
        self.events.emit(ServerEvent.CONSOLE_LINE, f"[System] Starting server with: {' '.join(cmd)}")
        self.events.emit(ServerEvent.STARTING)
        
        try:
            self._stderr_buffer = []
            self.process = subprocess.Popen(
                cmd,
                cwd=server_path,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                bufsize=1
            )
            self.running = True
            threading.Thread(target=self._read_output, daemon=True).start()
            self._stderr_thread = threading.Thread(target=self._read_stderr, daemon=True)
            self._stderr_thread.start()
        except Exception as e:
            self.events.emit(ServerEvent.CONSOLE_LINE, f"[Error] Failed to start server: {e}")
            self.running = False

    def stop(self):
        if not self.running or not self.process:
            return

        self.events.emit(ServerEvent.CONSOLE_LINE, "[System] Stopping server...")
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
                self.events.emit(ServerEvent.CONSOLE_LINE, "[System] Server unresponsive, force killing...")
                self.process.kill()
                self.process.wait()
        except Exception as e:
            self.events.emit(ServerEvent.CONSOLE_LINE, f"[Error] Failed to stop server: {e}")
            if self.process:
                try:
                    self.process.kill()
                except OSError as kill_err:
                    logger.warning("Force kill failed: %s", kill_err)

    def send_command(self, command):
        if not self.running or not self.process or not self.process.stdin:
            return
        try:
            self.events.emit(ServerEvent.CONSOLE_LINE, f"> {command}")
            self.process.stdin.write(command + "\n")
            self.process.stdin.flush()
        except Exception as e:
            self.events.emit(ServerEvent.CONSOLE_LINE, f"[Error] Failed to send command: {e}")

    def _read_output(self):
        if not self.process:
            return
        start_time = time.time()
        for line in self.process.stdout:
            self.events.emit(ServerEvent.CONSOLE_LINE, line.strip())
            self._parse_player_count(line.strip())
            if "Done (" in line and "For help, type" in line:
                self.events.emit(ServerEvent.READY)
        self.process.wait()
        self._stderr_done.wait(timeout=2)
        self.exit_code = self.process.returncode
        stderr_snapshot = self.get_stderr_snapshot()
        uptime = time.time() - start_time
        self.running = False
        self.process = None
        self.events.emit(ServerEvent.CONSOLE_LINE, f"[System] Server process exited (code {self.exit_code}, uptime {uptime:.1f}s).")
        self.events.emit(ServerEvent.STOPPED, {
            "exit_code": self.exit_code,
            "uptime": uptime,
            "stderr": stderr_snapshot,
        })

    def _read_stderr(self):
        self._stderr_done.clear()
        if not self.process or not self.process.stderr:
            self._stderr_done.set()
            return
        for line in self.process.stderr:
            stripped = line.strip()
            if stripped:
                self._stderr_buffer.append(stripped)
                if len(self._stderr_buffer) > 100:
                    self._stderr_buffer.pop(0)
                self.events.emit(ServerEvent.CONSOLE_LINE, f"[JVM] {stripped}")
        self._stderr_done.set()

    def get_stderr_snapshot(self):
        return "\n".join(self._stderr_buffer[-50:])

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
    except (FileNotFoundError, OSError, ValueError) as e:
        logger.error("Failed to save server icon: %s", e)
        return False

def check_eula(server_name):
    server_path = os.path.join(SERVERS_DIR, server_name)
    eula_path = os.path.join(server_path, "eula.txt")
    if not os.path.exists(eula_path): return False
    with open(eula_path, "r") as f:
        return "eula=true" in f.read()

from app.services.server_properties import load_server_properties, save_server_properties

class Scheduler:
    def __init__(self, server_name):
        self.server_name = server_name
        self.server_path = os.path.join(SERVERS_DIR, server_name)
        self.metadata_path = os.path.join(self.server_path, "metadata.json")
        
    def _load_metadata(self):
        return get_server_meta(self.server_name)
    
    def _save_metadata(self, data):
        meta_path = self.metadata_path
        try:
            with open(meta_path, "w") as f: 
                json.dump(data, f, indent=4)
        except Exception as e:
            logger.error("Failed to save scheduler metadata: %s", e)

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

    def get_status(self):
        schedule = self.get_schedule()
        if not schedule:
            return None
        now = datetime.datetime.now()
        remaining = None
        if schedule["type"] == "interval":
            last_run_str = schedule.get("last_run")
            if last_run_str:
                last_run = datetime.datetime.fromisoformat(last_run_str)
                remaining = (last_run + datetime.timedelta(hours=schedule["interval_hours"]) - now).total_seconds()
        elif schedule["type"] == "time":
            hour, minute = map(int, schedule["restart_time"].split(":"))
            remaining = (now.replace(hour=hour, minute=minute, second=0, microsecond=0) - now).total_seconds()
        return {"is_due": self.check_due(), "remaining_seconds": remaining}

    @staticmethod
    def get_warning_message(remaining_seconds, sent_warnings):
        if remaining_seconds is None or remaining_seconds <= 0:
            return None, None
        if 3600 < remaining_seconds <= 3630 and '1h' not in sent_warnings:
            return '1h', "Server will restart in 1 hour!"
        if 1800 < remaining_seconds <= 1830 and '30m' not in sent_warnings:
            return '30m', "Server will restart in 30 minutes!"
        if 900 < remaining_seconds <= 930 and '15m' not in sent_warnings:
            return '15m', "Server will restart in 15 minutes!"
        if 60 < remaining_seconds <= 90 and '1m' not in sent_warnings:
            return '1m', "Server will restart in 1 minute!"
        return None, None


class BackupScheduler:
    DEFAULTS = {"enabled": False, "interval_hours": 4, "retention_count": 10, "last_run": None}

    def __init__(self, server_name: str):
        self.server_name = server_name

    def _load(self) -> dict:
        meta = get_server_meta(self.server_name)
        return meta.get("auto_backup", {})

    def _save(self, data: dict) -> bool:
        return update_server_meta(self.server_name, {"auto_backup": data})

    def get_config(self) -> dict:
        config = self.DEFAULTS.copy()
        config.update(self._load())
        return config

    def set_config(self, enabled: bool, interval_hours: int = 4, retention_count: int = 10):
        data = self._load()
        data["enabled"] = enabled
        if enabled:
            data["interval_hours"] = interval_hours
            data["retention_count"] = retention_count
        return self._save(data)

    def is_due(self) -> bool:
        config = self.get_config()
        if not config["enabled"]:
            return False
        last_run = config.get("last_run")
        if not last_run:
            return True
        elapsed = (datetime.datetime.now() - datetime.datetime.fromisoformat(last_run)).total_seconds()
        return elapsed >= config["interval_hours"] * 3600

    def mark_run(self):
        data = self._load()
        data["last_run"] = datetime.datetime.now().isoformat()
        return self._save(data)

    def seconds_until_next(self) -> float | None:
        config = self.get_config()
        if not config["enabled"]:
            return None
        last_run = config.get("last_run")
        if not last_run:
            return 0.0
        elapsed = (datetime.datetime.now() - datetime.datetime.fromisoformat(last_run)).total_seconds()
        return max(0.0, config["interval_hours"] * 3600 - elapsed)


def get_server_ram(server_name):
    return get_server_meta(server_name).get("ram", 2048)

def set_server_ram(server_name, ram_mb):
    return set_server_meta(server_name, "ram", int(ram_mb))


