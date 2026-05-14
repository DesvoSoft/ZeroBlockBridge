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
    def __init__(self, console_callback, status_callback, claim_callback, on_ready_callback=None, notification_callback=None):
        self.console_callback = console_callback
        self.status_callback = status_callback
        self.claim_callback = claim_callback
        self.on_ready_callback = on_ready_callback
        self.notification_callback = notification_callback
        self.process = None
        self.running = False
        self.binary_path = self._get_binary_path()
        self.current_address = None
        self.is_linked = False
        self.secret_dir = str(CONFIG_DIR)
        self.toml_path = os.path.join(CONFIG_DIR, "playit.toml")
        
        # API Client and state
        self.api_client = PlayitApiClient()
        self.in_use_count = 0
        self._lock = threading.Lock()
        self._api_dns = None       # Authoritative DNS from API -- never overwritten by stdout
        self._claim_code = None    # Captured claim code from CLI stdout

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
                    capture_output=True,
                    text=True,
                    check=False
                )
                if PLAYIT_VERSION not in result.stdout and PLAYIT_VERSION not in result.stderr:
                    self.console_callback(f"[Playit] Found old version. Updating to {PLAYIT_VERSION}...")
                    os.remove(self.binary_path)
                else:
                    return True
            except Exception as e:
                self.console_callback(f"[Playit] Version check failed ({e}). Redownloading...")
                try:
                    os.remove(self.binary_path)
                except Exception:
                    pass

        if self.binary_path.exists():
             return True

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



    def _inject_toml_mapping(self, port: int):
        """Appends a [[mapping]] block to playit.toml so the agent automatically creates a tunnel."""
        try:
            if not os.path.exists(self.toml_path):
                return
            with open(self.toml_path, "r", encoding="utf-8") as f:
                content = f.read()
            if "[[mapping]]" not in content:
                mapping_block = (
                    "\n\n[[mapping]]\n"
                    "local_ip = \"127.0.0.1\"\n"
                    "port_type = \"tcp\"\n"
                    f"local_port = {port}\n"
                )
                with open(self.toml_path, "a", encoding="utf-8") as f:
                    f.write(mapping_block)
                logger.info("Injected [[mapping]] into playit.toml for auto-tunnel creation.")
        except Exception as e:
            logger.error(f"Failed to prepare tunnel via TOML mapping: {e}")

    def get_or_create_tunnel(self, port: int) -> str:
        """Uses API to find an existing tunnel for the port.
        If not found, injects a TOML mapping to force the CLI to create one."""
        
        if not self.api_client.load_secret_key():
            self.console_callback("[Playit] Agent not linked yet. Using fallback mode.")
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
                        
            # Not found, inject TOML mapping so the agent creates it
            self.console_callback(f"[Playit] Creating new tunnel for port {port} via local mapping...")
            self._inject_toml_mapping(port)
            return None
            
        except PlayitApiException as e:
            self.console_callback(f"[Playit] API Error: {e}")
            return None

    def start(self, port: int = 25565):
        """Starts the playit agent subprocess with reference counting."""
        with self._lock:
            self.in_use_count += 1
            if self.running:
                self.console_callback(f"[Debug] Agent already running (In use: {self.in_use_count}).")
                
                # If we already have API DNS, just report it
                if self._api_dns:
                    self.current_address = self._api_dns
                    self.status_callback("Online", self._api_dns)
                    if self.on_ready_callback:
                        self.on_ready_callback()
                    return
                
                # Try to get or create tunnel via API if linked
                address = self.get_or_create_tunnel(port)
                if address:
                    self.current_address = address
                    self.status_callback("Online", address)
                    if self.on_ready_callback:
                        self.on_ready_callback()
                return

        self._api_dns = None
        self._claim_code = None
        self.current_address = None
        self._current_port = port

        if not self.ensure_binary():
            self.console_callback("[Debug] Binary check failed.")
            with self._lock: self.in_use_count -= 1
            return

        if not os.path.exists(CONFIG_DIR):
            os.makedirs(CONFIG_DIR)
        self.secret_dir = str(CONFIG_DIR)

        # If already linked, inject mapping for auto-tunnel creation
        self.is_linked = os.path.exists(self.toml_path)
        if self.is_linked:
            self._inject_toml_mapping(port)
            self.console_callback("[Playit] Existing config found. Starting agent...")

        # Start the agent process (needed for actual traffic relay)
        try:
            env = os.environ.copy()
            env["RUST_LOG"] = "debug"

            cmd_str = f'"{self.binary_path}" --stdout --secret_path "{self.toml_path}"'

            self.process = subprocess.Popen(
                cmd_str,
                shell=True,
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
            
        except Exception as e:
            self.console_callback(f"[Playit] Failed to start: {e}")
            self.running = False
            self.status_callback("Error", None)
            with self._lock: self.in_use_count -= 1

    def stop(self):
        """Stops the playit agent using reference counting."""
        with self._lock:
            if self.in_use_count > 0:
                self.in_use_count -= 1
            
            if self.in_use_count > 0:
                self.console_callback(f"[Playit] Agent kept alive (In use: {self.in_use_count}).")
                return

        if not self.running or not self.process:
            return

        self.console_callback("[Playit] Stopping agent...")
        try:
            self.process.terminate()
        except Exception as e:
            self.console_callback(f"[Playit] Error stopping: {e}")
        
        self.running = False
        self.current_address = None
        self._api_dns = None
        self.status_callback("Offline", None)

    def reset(self):
        """Resets the playit agent configuration (clears secret and deletes playit.toml)."""
        with self._lock:
            self.in_use_count = 0
            
        if self.running and self.process:
            try:
                self.process.terminate()
                self.process.wait(timeout=2)
            except Exception:
                pass
                
        self.console_callback("[Playit] Resetting agent configuration...")
        try:
            subprocess.run(
                [str(self.binary_path), "reset"],
                cwd=os.path.abspath(CONFIG_DIR),
                check=False,
                capture_output=True,
                text=True
            )
            # Delete secret file to force re-link on next start
            if os.path.exists(self.toml_path):
                os.remove(self.toml_path)
                self.console_callback("[Playit] Deleted playit.toml secret.")
            self.console_callback("[Playit] Agent reset complete. You can now start a new tunnel.")
            self._claim_code = None
            self._api_dns = None
            self.current_address = None
            self.is_linked = False
            self.api_client._secret_key = None
            self.api_client._agent_id = None
            self.running = False
            self.status_callback("Offline", None)
        except Exception as e:
            self.console_callback(f"[Playit] Reset failed: {e}")

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
            buffer = bytearray()
            while self.running and self.process:
                byte = self.process.stdout.read(1)
                if not byte: break
                
                if byte == b'\n' or byte == b'\r':
                    if buffer:
                        try:
                            line = buffer.decode('utf-8', errors='replace').strip()
                        except Exception:
                            line = ""
                        if line:
                            clean_line = re.sub(r'\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])', '', line)
                            is_spam = any(s in clean_line for s in self.SPAM_LOGS)
                            if not is_spam or "ERROR" in clean_line:
                                self.console_callback(f"[Playit] {clean_line}")
                            self._parse_line(clean_line)
                        buffer = bytearray()
                else:
                    buffer.extend(byte)
        except Exception as e:
            self.console_callback(f"[Playit] Read error: {e}")
        finally:
            self.running = False
            self.process = None
            if not self._api_dns:
                self.current_address = None
            self.status_callback("Offline", None)

    def _parse_line(self, line):
        # --- Claim code detection (only if not already linked) ---
        if not self.is_linked:
            claim_match = re.search(r"https://playit\.gg/claim/([a-zA-Z0-9]+)", line)
            if claim_match:
                claim_code = claim_match.group(1)
                if not self._claim_code:
                    self._claim_code = claim_code
                    self.console_callback(f"[Playit] Claim code detected: {claim_code}")
                    self.console_callback("[Playit] Waiting for manual browser confirmation...")
                    self.console_callback("[System] Action Required: Please log in or create a Playit.gg account in your browser to approve the agent.")
                    if self.notification_callback:
                        self.notification_callback("Approve the agent in your browser to continue", "warning")
                    
                    full_url = f"https://playit.gg/claim/{claim_code}"
                    # Store URL for the UI
                    self.claim_callback(full_url)
                    
                    self.console_callback(f"[UI] Opening claim URL in browser: {full_url}")
                    try:
                        webbrowser.open(full_url)
                    except Exception as e:
                        logger.error(f"Failed to auto-open browser: {e}")
                return

        # --- Network unreachable -- agent will auto-retry via IPv4 ---
        if "NetworkUnreachable" in line or "Os { code: 10051" in line or "Os { code: 101" in line:
            return

        # --- Account limit error ---
        if "AgentDisabledOverLimit" in line or "Account limit reached" in line:
            self.status_callback("Error", None)
            self.console_callback("[Playit] ERROR: Account limit reached!")
            self.console_callback("[Playit] You have too many agents. Delete unused agents at https://playit.gg/dashboard/agents")
            return

        # --- Agent registered -- LINKED state confirmed ---
        if "agent registered" in line:
            if not self.is_linked:
                self.is_linked = True
                self.console_callback("[Playit] Agent linked successfully.")
                if self.notification_callback:
                    self.notification_callback("Agent linked! Restarting to apply tunnel config...", "success")
                self.status_callback("Connecting...", None)
                
                # Inject TOML mapping so the agent auto-creates the tunnel on restart
                port = getattr(self, '_current_port', 25565)
                self._inject_toml_mapping(port)
                self.console_callback(f"[Playit] Tunnel mapping injected for port {port}.")
                
                # Restart the agent so it picks up the new [[mapping]]
                self.console_callback("[Playit] Restarting agent to activate tunnel...")
                threading.Thread(target=self._restart_with_mapping, args=(port,), daemon=True).start()
                return

        # --- DNS from stdout (always scrape when linked) ---
        if not self.is_linked:
            return
        
        # Skip if we already have a confirmed address
        if self._api_dns:
            return

        # Only match real Playit DNS domains — never raw IPs (those are false positives from Pong)
        dns_patterns = [
            r"([a-z0-9][a-z0-9-]*\.(?:ply|playit)\.gg(?::\d+)?)",
            r"([a-z0-9][a-z0-9-]*\.joinmc\.link(?::\d+)?)",
        ]
        for pattern in dns_patterns:
            dns_match = re.search(pattern, line)
            if dns_match:
                address = dns_match.group(1).rstrip('.')
                if address != self.current_address:
                    self._api_dns = address
                    self.current_address = address
                    self.status_callback("Online", address)
                    self.console_callback(f"[Playit] Public address: {address}")
                    if self.notification_callback:
                        self.notification_callback(f"Tunnel online: {address}", "success")
                    if self.on_ready_callback:
                        self.on_ready_callback()
                return

        # Fallback: "tunnel running" but no explicit address yet
        if "tunnel running" in line and not self.current_address:
            self.status_callback("Connecting...", None)
            self.console_callback("[Playit] Tunnel active, waiting for DNS assignment...")

    def _restart_with_mapping(self, port: int):
        """Restarts the agent process after mapping injection so the CLI picks up the new tunnel config."""
        time.sleep(1)
        # Kill current process
        if self.process:
            try:
                self.process.terminate()
                self.process.wait(timeout=3)
            except Exception:
                pass
            self.process = None
        
        self.running = False
        time.sleep(0.5)
        
        # Restart
        self.console_callback("[Playit] Restarting agent with tunnel configuration...")
        if self.notification_callback:
            self.notification_callback("Restarting tunnel agent...", "info")
        
        with self._lock:
            self.in_use_count = max(0, self.in_use_count - 1)
        
        self.start(port)
