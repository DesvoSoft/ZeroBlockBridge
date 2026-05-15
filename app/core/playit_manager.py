import atexit
import os
import platform
import subprocess
import threading
import requests
import re
import time
import logging

from app.core.constants import BIN_DIR, CONFIG_DIR, PLAYIT_VERSION, PLAYIT_URL_WINDOWS, PLAYIT_URL_LINUX
from app.services.playit_api import PlayitApiClient, PlayitApiException

logger = logging.getLogger(__name__)

class PlayitManager:
    def __init__(self, console_callback, status_callback, on_ready_callback=None, notification_callback=None):
        self.console_callback = console_callback
        self.status_callback = status_callback
        self.on_ready_callback = on_ready_callback
        self.notification_callback = notification_callback
        self.process = None
        self.running = False
        self.binary_path = self._get_binary_path()
        self.current_address = None
        self.is_linked = False
        self.toml_path = os.path.join(CONFIG_DIR, "playit.toml")

        # API Client and state
        self.api_client = PlayitApiClient()
        self._lock = threading.RLock()
        self._api_dns = None
        self._current_port = 25565

        # Persistence: Check if already linked
        if self.api_client.load_secret_key():
            self.is_linked = True
            self._fix_permissions()
            logger.info("Playit linked state persisted from playit.toml")

        atexit.register(self.stop, force=True)

    def _get_binary_path(self):
        system = platform.system()
        filename = "playit.exe" if system == "Windows" else "playit"
        return (BIN_DIR / filename).resolve()

    def _clean_stale_binaries(self):
        if not BIN_DIR.exists():
            return
        for f in BIN_DIR.iterdir():
            if f.is_file() and f.name.startswith("playit"):
                if f.samefile(self.binary_path):
                    continue
                try:
                    f.unlink()
                    logger.info(f"[Playit] Removed stale binary: {f.name}")
                except OSError:
                    pass

    def ensure_binary(self):
        if not BIN_DIR.exists():
            BIN_DIR.mkdir(parents=True, exist_ok=True)

        self._clean_stale_binaries()

        if self.binary_path.exists():
            try:
                result = subprocess.run(
                    [str(self.binary_path), "version"],
                    capture_output=True, text=True, check=False
                )
                if PLAYIT_VERSION not in result.stdout and PLAYIT_VERSION not in result.stderr:
                    self.console_callback(f"[Playit] Found old version. Updating to {PLAYIT_VERSION}...")
                    os.remove(self.binary_path)
                else:
                    return True
            except OSError as e:
                self.console_callback(f"[Playit] Version check failed ({e}). Redownloading...")
                try:
                    os.remove(self.binary_path)
                except OSError:
                    pass

        url = PLAYIT_URL_WINDOWS if platform.system() == "Windows" else PLAYIT_URL_LINUX
        self.console_callback(f"[Playit] Downloading agent v{PLAYIT_VERSION} from {url}...")

        try:
            response = requests.get(url, stream=True, timeout=30)
            response.raise_for_status()
            with open(self.binary_path, "wb") as f:
                for chunk in response.iter_content(chunk_size=8192):
                    f.write(chunk)

            if platform.system() != "Windows":
                self.binary_path.chmod(0o755)

            self.console_callback("[Playit] Download complete.")
            return True
        except Exception as e:
            self.console_callback(f"[Playit] Download failed: {e}")
            return False

    def get_or_create_tunnel(self, port: int) -> str:
        if not self.api_client.load_secret_key():
            self.console_callback("[Playit] Agent not linked yet.")
            return None

        try:
            tunnels = self.api_client.list_tunnels()
            for t in tunnels:
                origin_port = t.get("origin", {}).get("data", {}).get("local_port")
                if origin_port == port:
                    address = self.api_client.get_tunnel_address(t)
                    if address:
                        self._api_dns = address
                        return address

            self.console_callback(f"[Playit] No tunnel for port {port}. Creating via API...")
            tunnel = self.api_client.create_tunnel(port)
            if tunnel:
                address = self.api_client.get_tunnel_address(tunnel)
                if address:
                    self._api_dns = address
                    return address
            return None

        except PlayitApiException as e:
            if "NotAllowedWithReadOnly" in str(e):
                self.console_callback("[Playit] ERROR: Account is in Guest mode (Read-Only).")
                self.console_callback("[Playit] Please use 'Get Code' + 'Link' with a Setup Code to enable tunnel creation.")
                if self.notification_callback:
                    self.notification_callback("Account Read-Only. Use Setup Code to link.", "error")
            else:
                self.console_callback(f"[Playit] API Error: {e}")
            return None

    def start(self, port: int = 25565):
        with self._lock:
            if self.running:
                self.console_callback("[Playit] Agent already running.")
                if self._api_dns:
                    with self._lock:
                        self.current_address = self._api_dns
                    self.status_callback("Online", self._api_dns)
                return

        try:
            self._start_internal(port)
        except Exception as e:
            logger.error(f"[PlayitManager] Fatal error in start thread: {e}")
            self.console_callback(f"[Playit] Internal start failure: {e}")
            self.status_callback("Error", None)

    def _start_internal(self, port: int):
        with self._lock:
            self._api_dns = None
            self.current_address = None
            self._current_port = port

        self.status_callback("Starting...", None)

        if self.notification_callback:
            self.notification_callback("Initializing tunnel relay...", "info")

        if not self.ensure_binary():
            self.console_callback("[Playit] Binary check failed.")
            return

        if not os.path.exists(CONFIG_DIR):
            os.makedirs(CONFIG_DIR)

        self.is_linked = os.path.exists(self.toml_path)
        if self.is_linked:
            self.api_client.is_read_only = False
            self.console_callback("[Playit] Existing config found. Starting agent...")
            try:
                if self.api_client.initialize():
                    address = self.get_or_create_tunnel(port)
                    if address:
                        self._api_dns = address
                        self.current_address = address
                        self.status_callback("Online", address)
                        self.console_callback(f"[Playit] Tunnel ready: {address}")
                        if self.notification_callback:
                            self.notification_callback(f"Tunnel Online: {address}", "success")
                        if self.on_ready_callback:
                            self.on_ready_callback()
                    else:
                        self.console_callback("[Playit] Waiting for tunnel DNS assignment...")
            except Exception as e:
                self.console_callback(f"[Playit] API tunnel setup: {e}")
        else:
            self.console_callback("[Playit] No playit.toml found. Link account first.")
            return

        try:
            env = os.environ.copy()
            env["RUST_LOG"] = "debug"

            self.api_client.load_secret_key()
            env["PLAYIT_SECRET_KEY"] = self.api_client._secret_key or ""

            cmd = [
                str(self.binary_path),
                "--stdout",
                "--secret_path", str(self.toml_path),
            ]

            self.process = subprocess.Popen(
                cmd,
                cwd=os.path.abspath(CONFIG_DIR),
                stdin=subprocess.DEVNULL,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                env=env,
            )
            self.running = True
            if not self.current_address:
                self.status_callback("Starting...", None)

            threading.Thread(target=self._read_output, daemon=True).start()
            threading.Thread(target=self._heartbeat_loop, daemon=True).start()

        except OSError as e:
            self.console_callback(f"[Playit] Failed to start: {e}")
            self.running = False
            self.status_callback("Error", None)

    def stop(self, force=False):
        with self._lock:
            proc = self.process
            self.process = None
            if proc:
                self.console_callback("[Playit] Stopping agent...")
                pid = proc.pid
                try:
                    import psutil
                    parent = psutil.Process(pid)
                    for child in parent.children(recursive=True):
                        child.kill()
                    parent.kill()
                except Exception:
                    if platform.system() == "Windows":
                        subprocess.run(['taskkill', '/F', '/T', '/PID', str(pid)],
                                     capture_output=True, check=False)
                    try:
                        proc.terminate()
                    except Exception:
                        pass

            if force and platform.system() == "Windows":
                for proc_name in ["playit.exe", "playit-cli.exe"]:
                    subprocess.run(['taskkill', '/F', '/IM', proc_name],
                                 capture_output=True, check=False)

            self.running = False
            with self._lock:
                self.current_address = None
                self._api_dns = None
            self.status_callback("Offline", None)

    def reset(self, reuse_agent: bool = True):
        try:
            self.console_callback("[Playit] Starting reset...")
            self.stop()

            key_valid = self.api_client.verify_secret_key()
            if key_valid and reuse_agent:
                self.console_callback("[Playit] Secret key valid. Reusing existing agent — deleting tunnels only...")
                try:
                    tunnels = self.api_client.list_tunnels()
                    for t in tunnels:
                        tid = t.get("id")
                        if tid:
                            if self.api_client.delete_tunnel(tid):
                                self.console_callback(f"[Playit] Deleted tunnel: {tid}")
                    self.console_callback("[Playit] Tunnels cleared. Agent kept intact.")
                except PlayitApiException as e:
                    self.console_callback(f"[Playit] Tunnel cleanup failed: {e}")
            elif key_valid:
                self.console_callback("[Playit] Destructive reset requested. Deleting remote agent...")
                try:
                    if self.api_client.delete_agent():
                        self.console_callback("[Playit] Remote agent deleted.")
                except PlayitApiException as e:
                    self.console_callback(f"[Playit] Agent deletion failed: {e}")
            else:
                self.console_callback("[Playit] Secret key invalid/expired. Skipping remote cleanup.")

            if not key_valid or not reuse_agent:
                if os.path.exists(self.toml_path):
                    os.remove(self.toml_path)
                    self.console_callback("[Playit] Local config playit.toml removed.")
                self.is_linked = False
                self.api_client.is_read_only = False
                self.api_client._secret_key = None
                self.api_client._agent_id = None
                self.console_callback("[Playit] Account unlinked.")
            else:
                self.console_callback("[Playit] Local config preserved (non-destructive reset).")

            self.current_address = None
            self._api_dns = None
            self.console_callback("[Playit] Reset complete.")

            if self.notification_callback:
                msg = "Playit reset complete (non-destructive)." if reuse_agent else "Playit account unlinked and reset."
                self.notification_callback(msg, "success")
        except Exception as e:
            self.console_callback(f"[Playit] Reset failed: {e}")

    def link_manually(self, setup_code: str):
        if not setup_code or len(setup_code.strip()) < 8:
            self.console_callback("[Playit] Invalid setup code. Must be at least 8 characters.")
            if self.notification_callback:
                self.notification_callback("Invalid setup code.", "error")
            return False

        # Download binary proactively before linking
        self.ensure_binary()

        clean_code = setup_code.strip()
        try:
            self.console_callback(f"[Playit] Exchanging setup code with secure bridge...")
            if self.api_client.link_account(clean_code):
                self.console_callback("[Playit] Account linked successfully! Starting agent...")
                self.is_linked = True
                self.api_client.is_read_only = False

                if self.running:
                    self.stop(force=True)

                self.start(getattr(self, '_current_port', 25565))
                return True
        except Exception as e:
            self.console_callback(f"[Playit] Link failed: {e}")
            if self.notification_callback:
                self.notification_callback(f"Link failed: {e}", "error")
        return False

    def _fix_permissions(self):
        if platform.system() != "Windows" and os.path.exists(self.toml_path):
            try:
                mode = os.stat(self.toml_path).st_mode
                if mode & 0o077:
                    os.chmod(self.toml_path, 0o600)
                    logger.info("Fixed playit.toml permissions to 600")
            except Exception as e:
                logger.warning(f"Could not fix playit.toml permissions: {e}")

    def _heartbeat_loop(self):
        max_failures = 3
        fail_count = 0
        while self.running:
            time.sleep(15)
            if not self.running:
                break
            with self._lock:
                if self.process is None or self.process.poll() is not None:
                    fail_count += 1
                    logger.warning("[Playit] Heartbeat #%d: process not running.", fail_count)
                    if fail_count >= max_failures:
                        self.console_callback("[Playit] CRITICAL: Agent process dead. Auto-restarting...")
                        if self.notification_callback:
                            self.notification_callback("Playit agent crashed. Restarting...", "error")
                        port = getattr(self, '_current_port', 25565)
                        threading.Thread(target=self.start, args=(port,), daemon=True).start()
                        fail_count = 0
                        break
                else:
                    fail_count = 0

    SPAM_LOGS = [
        "tunnel running", "udp channel requires auth", "udp session details received",
        "send KeepAlive", "agent registered details", "authenticate control last_pong",
        "session expired reason=SessionNotSetup",
        "failed to send initial ping error=Os { code: 10051",
        "failed to send initial ping error=Os { code: 101", "failed to ping tunnel server",
        "failed to parse json", "ReqProtoRegister",
        "NetworkUnreachable"
    ]

    def _read_output(self):
        try:
            while self.running and self.process:
                try:
                    raw = self.process.stdout.readline()
                except Exception:
                    break
                if not raw:
                    break
                try:
                    line = raw.decode('utf-8', errors='replace').strip()
                except Exception:
                    continue
                if line:
                    clean_line = re.sub(r'\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])', '', line)
                    is_spam = any(s in clean_line for s in self.SPAM_LOGS)
                    if not is_spam or "ERROR" in clean_line:
                        self.console_callback(f"[Playit] {clean_line}")
                    if "AgentDisabledOverLimit" in clean_line or "Account limit reached" in clean_line:
                        self.status_callback("Error", None)
                        self.console_callback("[Playit] ERROR: Account limit reached!")
                        self.console_callback("[Playit] You have too many agents. Delete unused agents at https://playit.gg/dashboard/agents")
        except Exception as e:
            self.console_callback(f"[Playit] Read error: {e}")
        finally:
            self.running = False
            self.process = None
            if not self._api_dns:
                self.current_address = None
            self.status_callback("Offline", None)


