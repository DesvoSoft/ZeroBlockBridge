import os
import platform
import subprocess
import threading
import requests
import re
import time
import logging
import webbrowser

from app.core.constants import BIN_DIR, CONFIG_DIR, PLAYIT_VERSION, PLAYIT_URL_WINDOWS, PLAYIT_URL_LINUX
from app.services.playit_api import PlayitApiClient, PlayitApiException

logger = logging.getLogger(__name__)

class PlayitManager:
    def __init__(self, console_callback, status_callback, notification_callback=None):
        self.console_callback = console_callback
        self.status_callback = status_callback
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
        self._stdout_dns = None
        self._current_port = 25565
        self._restarting = False

        # Persistence: Check if already linked
        if self.api_client.load_secret_key():
            self.is_linked = True
            logger.info("Playit linked state persisted from playit.toml")

        # Register global cleanup
        import atexit
        atexit.register(self.stop, force=True)

    def _get_binary_path(self):
        system = platform.system()
        filename = "playit.exe" if system == "Windows" else "playit"
        return (BIN_DIR / filename).resolve()

    def ensure_binary(self):
        """Downloads the playit binary if it doesn't exist or is outdated."""
        if not BIN_DIR.exists():
            BIN_DIR.mkdir(parents=True, exist_ok=True)

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
            response = requests.get(url, stream=True)
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
        """Uses API to find an existing tunnel for the port, or creates one.
        Returns the full connectable address (domain:port) or None."""

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
            tunnel = self.api_client.create_tunnel(port=port)
            address = self.api_client.get_tunnel_address(tunnel)
            return address

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
        """Starts the playit agent subprocess."""
        with self._lock:
            if self.running:
                self.console_callback("[Playit] Agent already running. Reporting status...")
                if self._api_dns:
                    self.current_address = self._api_dns
                    self.status_callback("Online", self._api_dns)
                else:
                    address = self.get_or_create_tunnel(port)
                    if address:
                        self.current_address = address
                        self.status_callback("Online", address)
                return

        try:
            self._start_internal(port)
        except Exception as e:
            logger.error(f"[PlayitManager] Fatal error in start thread: {e}")
            self.console_callback(f"[Playit] Internal start failure: {e}")
            self.status_callback("Error", None)

    def _start_internal(self, port: int):
        self._api_dns = None
        self._stdout_dns = None
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
                    else:
                        self.console_callback("[Playit] Waiting for tunnel DNS assignment...")
            except Exception as e:
                self.console_callback(f"[Playit] API tunnel setup: {e}")

        try:
            env = os.environ.copy()
            env["RUST_LOG"] = "debug"

            cmd = [str(self.binary_path), "--stdout", "--secret_path", str(self.toml_path)]

            self.process = subprocess.Popen(
                cmd,
                cwd=os.path.abspath(CONFIG_DIR),
                stdin=subprocess.DEVNULL,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=False,
                bufsize=0,
                env=env
            )
            self.running = True
            if not self.current_address:
                self.status_callback("Starting...", None)

            threading.Thread(target=self._read_output, daemon=True).start()

        except OSError as e:
            self.console_callback(f"[Playit] Failed to start: {e}")
            self.running = False
            self.status_callback("Error", None)

    def stop(self, force=False):
        """Stops the playit agent."""
        with self._lock:
            if self.process:
                self.console_callback("[Playit] Stopping agent...")
                try:
                    import psutil
                    parent = psutil.Process(self.process.pid)
                    for child in parent.children(recursive=True):
                        child.kill()
                    parent.kill()
                except Exception:
                    if platform.system() == "Windows":
                        subprocess.run(['taskkill', '/F', '/T', '/PID', str(self.process.pid)],
                                     capture_output=True, check=False)
                    try:
                        self.process.terminate()
                    except Exception:
                        pass

                self.process = None

            if force and platform.system() == "Windows":
                import subprocess
                for proc_name in ["playit.exe", "playit-cli.exe"]:
                    subprocess.run(['taskkill', '/F', '/IM', proc_name],
                                 capture_output=True, check=False)

            self.running = False
            self.current_address = None
            self._api_dns = None
            self._stdout_dns = None
            self.status_callback("Offline", None)

    def reset(self):
        """Wipes the playit configuration, stops any running agent, and cleans up API resources."""
        try:
            self.console_callback("[Playit] Starting full reset...")
            self.stop()

            if self.is_linked:
                self.console_callback("[Playit] Attempting to clean up API resources...")
                try:
                    if self.api_client.initialize():
                        if self.api_client.delete_agent():
                            self.console_callback("[Playit] Remote agent deleted successfully (all tunnels cleared).")
                        else:
                            self.console_callback("[Playit] Agent deletion restricted. Cleaning up tunnels individually...")
                            tunnels = self.api_client.list_tunnels()
                            for t in tunnels:
                                tid = t.get("id")
                                if tid:
                                    if self.api_client.delete_tunnel(tid):
                                        self.console_callback(f"[Playit] Deleted remote tunnel: {tid}")
                    else:
                        self.console_callback("[Playit] API key invalid or expired. Skipping remote cleanup.")
                except PlayitApiException as e:
                    if "401" in str(e):
                        self.console_callback("[Playit] Authentication failed (401). Your agent key may have been revoked.")
                        self.console_callback("[Playit] Please verify and delete unused agents at https://playit.gg/dashboard/agents")
                    else:
                        self.console_callback(f"[Playit] API cleanup failed: {e}")
                except Exception as e:
                    self.console_callback(f"[Playit] API cleanup failed: {e}")

            if os.path.exists(self.toml_path):
                os.remove(self.toml_path)
                self.console_callback("[Playit] Local config playit.toml removed.")

            self.is_linked = False
            self.current_address = None
            self._api_dns = None
            self._stdout_dns = None
            self.api_client.is_read_only = False
            self.api_client._secret_key = None
            self.api_client._agent_id = None
            self.console_callback("[Playit] Reset complete. Account unlinked.")

            if self.notification_callback:
                self.notification_callback("Playit account unlinked and reset.", "success")
        except Exception as e:
            self.console_callback(f"[Playit] Reset failed: {e}")

    def link_manually(self, setup_code: str):
        """Link the account manually using a setup code from the web wizard."""
        try:
            self.console_callback(f"[Playit] Exchanging setup code with secure bridge...")
            if self.api_client.link_account(setup_code):
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
                    self._parse_line(clean_line)
        except Exception as e:
            self.console_callback(f"[Playit] Read error: {e}")
        finally:
            self.running = False
            self.process = None
            addr = self._api_dns or self._stdout_dns
            self.current_address = addr
            if not addr:
                self.current_address = None
            self.status_callback("Offline", None)

    def _parse_line(self, line):
        if not line:
            return

        if "NetworkUnreachable" in line or "Os { code: 10051" in line or "Os { code: 101" in line:
            return

        if "AgentDisabledOverLimit" in line or "Account limit reached" in line:
            self.status_callback("Error", None)
            self.console_callback("[Playit] ERROR: Account limit reached!")
            self.console_callback("[Playit] You have too many agents. Delete unused agents at https://playit.gg/dashboard/agents")
            return

        if "agent registered" in line:
            if not self.is_linked:
                self.is_linked = True
                self.console_callback("[Playit] Agent linked successfully.")
                if self.notification_callback:
                    self.notification_callback("Agent linked! Creating tunnel...", "success")
                self.status_callback("Connecting...", None)

                port = getattr(self, '_current_port', 25565)
                self.console_callback("[Playit] Restarting agent to create tunnel...")
                if not self._restarting:
                    self._restarting = True
                    threading.Thread(target=self._restart_with_mapping, args=(port,), daemon=True).start()
            return

        # DNS from API takes priority over stdout
        if self._api_dns:
            return

        dns_patterns = [
            r"([a-z0-9][a-z0-9-]*\.(?:gl\.)?(?:ply|playit)\.gg(?::\d+)?)",
            r"([a-z0-9][a-z0-9-]*\.(?:gl\.)?joinmc\.link(?::\d+)?)",
        ]
        for pattern in dns_patterns:
            dns_match = re.search(pattern, line)
            if dns_match:
                address = dns_match.group(1).rstrip('.')
                if address != self.current_address:
                    self._stdout_dns = address
                    self.current_address = address
                    self.status_callback("Online", address)
                    self.console_callback(f"[Playit] Public address: {address}")
                    if self.notification_callback:
                        self.notification_callback(f"Tunnel online: {address}", "success")
                return

        if "tunnel running" in line and not self.current_address:
            self.status_callback("Connecting...", None)
            self.console_callback("[Playit] Tunnel active, waiting for DNS assignment...")

    def _restart_with_mapping(self, port: int):
        """Restarts the agent process to pick up new tunnel configurations."""
        try:
            time.sleep(1)
            self.stop(force=True)
            self.start(port)
        finally:
            self._restarting = False
