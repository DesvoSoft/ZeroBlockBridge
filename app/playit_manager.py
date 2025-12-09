import os
import sys
import platform
import subprocess
import threading
import requests
import re
import time

# Constants
BIN_DIR = "bin"
CONFIG_DIR = "config"
PLAYIT_VERSION = "0.15.26"
URL_WINDOWS = f"https://github.com/playit-cloud/playit-agent/releases/download/v{PLAYIT_VERSION}/playit-windows-x86_64-signed.exe"
URL_LINUX = f"https://github.com/playit-cloud/playit-agent/releases/download/v{PLAYIT_VERSION}/playit-linux-amd64"

class PlayitManager:
    def __init__(self, console_callback, status_callback, claim_callback):
        """
        Args:
            console_callback: func(str) -> None (Log message)
            status_callback: func(str, str) -> None (Status text, IP Address)
            claim_callback: func(str) -> None (Claim URL)
        """
        self.console_callback = console_callback
        self.status_callback = status_callback
        self.claim_callback = claim_callback
        self.process = None
        self.running = False
        self.binary_path = self._get_binary_path()
        self.claim_url_detected = False

    def _get_binary_path(self):
        system = platform.system()
        filename = "playit.exe" if system == "Windows" else "playit"
        # Return absolute path to ensure it works regardless of CWD
        return os.path.abspath(os.path.join(BIN_DIR, filename))

    def ensure_binary(self):
        """Downloads the playit binary if it doesn't exist."""
        if not os.path.exists(BIN_DIR):
            os.makedirs(BIN_DIR)
        
        if os.path.exists(self.binary_path):
            return True

        url = URL_WINDOWS if platform.system() == "Windows" else URL_LINUX
        self.console_callback(f"[Playit] Downloading agent from {url}...")
        
        try:
            response = requests.get(url, stream=True)
            response.raise_for_status()
            with open(self.binary_path, "wb") as f:
                for chunk in response.iter_content(chunk_size=8192):
                    f.write(chunk)
            
            if platform.system() != "Windows":
                os.chmod(self.binary_path, 0o755)
                
            self.console_callback("[Playit] Download complete.")
            return True
        except Exception as e:
            self.console_callback(f"[Playit] Download failed: {e}")
            return False

    def start(self):
        """Starts the playit agent subprocess."""
        if self.running:
            self.console_callback("[Debug] Agent already running.")
            return

        self.claim_url_detected = False

        if not self.ensure_binary():
            self.console_callback("[Debug] Binary check failed.")
            return

        # Ensure config directory exists
        if not os.path.exists(CONFIG_DIR):
            os.makedirs(CONFIG_DIR)

        self.console_callback(f"[Debug] Starting agent from: {self.binary_path}")
        self.console_callback(f"[Debug] CWD: {os.path.abspath(CONFIG_DIR)}")
        
        try:
            # Run in the config directory so playit.toml is stored there
            # Set RUST_LOG to force output
            env = os.environ.copy()
            env["RUST_LOG"] = "info"
            
            self.process = subprocess.Popen(
                [self.binary_path, "--stdout"],
                cwd=os.path.abspath(CONFIG_DIR),
                stdin=subprocess.DEVNULL,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=False, 
                bufsize=0,
                env=env
            )
            self.running = True
            self.status_callback("Starting...", None)
            self.console_callback(f"[Debug] Process started with PID: {self.process.pid}")
            
            # Start the output reader thread
            threading.Thread(target=self._read_output, daemon=True).start()
            
        except Exception as e:
            self.console_callback(f"[Playit] Failed to start: {e}")
            self.running = False
            self.status_callback("Error", None)

    def stop(self):
        """Stops the playit agent."""
        if not self.running or not self.process:
            return

        self.console_callback("[Playit] Stopping agent...")
        try:
            self.process.terminate()
            # We don't wait() here to avoid blocking the UI thread if it hangs.
            # The reader thread will handle the cleanup when stdout closes.
        except Exception as e:
            self.console_callback(f"[Playit] Error stopping: {e}")
        
        # We manually set running to False just in case, though reader thread does it too
        self.running = False
        self.status_callback("Offline", None)

    def _read_output(self):
        """Reads stdout from the process character by character (binary)."""
        self.console_callback("[Debug] Output reader thread started.")
        try:
            buffer = bytearray()
            while self.running and self.process:
                # Read 1 byte
                # self.console_callback("[Debug] Waiting for byte...") # Too spammy?
                byte = self.process.stdout.read(1)
                if not byte:
                    self.console_callback("[Debug] EOF received.")
                    break
                
                # self.console_callback(f"[Debug] Byte: {byte}") # Very spammy but useful if stuck
                
                if byte == b'\n' or byte == b'\r':
                    if buffer:
                        try:
                            line = buffer.decode('utf-8', errors='replace').strip()
                        except:
                            line = ""
                            
                        if line:
                            # Remove ANSI escape codes
                            clean_line = re.sub(r'\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])', '', line)
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
            self.status_callback("Offline", None)
            self.console_callback("[Playit] Agent process exited.")

    def _parse_line(self, line):
        """Parses a single line of output for relevant info."""
        # 1. Check for Claim URL
        # Pattern: "https://playit.gg/claim/..."
        claim_match = re.search(r"(https://playit\.gg/claim/[a-zA-Z0-9]+)", line)
        if claim_match:
            url = claim_match.group(1)
            if not self.claim_url_detected:
                self.claim_url_detected = True
                self.claim_callback(url)

        # 2. Check for Tunnel Address
        # Pattern: looks for .ply.gg domains
        # This might match the mapping log
        addr_match = re.search(r"([a-z0-9-]+\.ply\.gg)", line)
        if addr_match:
            address = addr_match.group(1)
            self.status_callback("Online", address)
