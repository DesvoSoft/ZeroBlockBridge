import requests
import json
import os
import time
import platform
import logging
from typing import Dict, List, Optional
from app.core.constants import CONFIG_DIR, PLAYIT_VERSION

logger = logging.getLogger(__name__)

class PlayitApiException(Exception):
    """Exception raised for API errors from Playit.gg"""
    pass

class PlayitApiClient:
    def __init__(self):
        self.api_base = "https://api.playit.gg"
        self.session = requests.Session()
        self._secret_key = None
        self._agent_id = None
        self._proto_key = None
        self.is_read_only = False
        self.toml_path = os.path.join(CONFIG_DIR, "playit.toml")

    def load_secret_key(self) -> bool:
        """Loads secret key from playit.toml. Returns True if successful."""
        if not os.path.exists(self.toml_path):
            self._secret_key = None
            return False
            
        mtime = os.path.getmtime(self.toml_path)
        if getattr(self, '_last_mtime', None) == mtime and self._secret_key:
            return True
            
        try:
            with open(self.toml_path, "r", encoding="utf-8") as f:
                content = f.read()
            import re
            match = re.search(r'secret_key\s*=\s*[\'"]?([a-zA-Z0-9_-]+)[\'"]?', content)
            if match:
                self._secret_key = match.group(1)
                self.session.headers["Authorization"] = f"agent-key {self._secret_key}"
                self._last_mtime = mtime
                # Reset identity so it fetches again
                self._agent_id = None
                self._proto_key = None
                return True
        except Exception as e:
            logger.error(f"Failed to read playit.toml: {e}")
        return False

    def _request(self, endpoint: str, json_data: dict = None) -> dict:
        """Helper to send POST requests to Playit API with error handling."""
        self.load_secret_key()
        if not self._secret_key:
            raise PlayitApiException("No secret key loaded. Cannot authenticate.")
            
        url = f"{self.api_base}/{endpoint.strip('/')}"
        try:
            response = self.session.post(url, json=json_data, timeout=10)
        except requests.RequestException as e:
            raise PlayitApiException(f"Network error communicating with Playit API: {e}")

        try:
            data = response.json()
        except ValueError:
            raise PlayitApiException(f"Invalid JSON response from Playit API (HTTP {response.status_code})")

        if response.status_code >= 400:
            if "AgentDisabledOverLimit" in response.text:
                raise PlayitApiException("AgentDisabledOverLimit: Agent limit reached. Delete old agents at playit.gg/dashboard")
            if "NotAllowedWithReadOnly" in response.text:
                self.is_read_only = True
                raise PlayitApiException("NotAllowedWithReadOnly: Account is in Guest mode (Read-Only). Use CLI for tunnel management.")
            error_detail = data.get("error") or data.get("message") or data.get("detail") or response.text or "Unknown API error"
            raise PlayitApiException(f"Playit API returned HTTP {response.status_code}: {error_detail}")

        return data

    # --- Account Linking ---
    def link_account(self, setup_code: str, agent_name: str = "ZeroBlockBridge") -> bool:
        """Link to a playit account using a setup code from the third-party web flow.
        (Based on the auto-mcs reference project flow).
        Returns True if linking succeeded and playit.toml was written.
        """
        os_name = platform.system().lower()
        if os_name == "darwin":
            os_name = "macos"

        payload = {
            "account_setup_code": setup_code,
            "agent_name": agent_name,
            "platform": os_name,
            "version_major": 0,
            "version_minor": 17,
            "version_patch": 1,
        }
        
        try:
            response = requests.post(
                "https://playit.auto-mcs.com/link",
                json=payload,
                timeout=20,
            )
            data = response.json()
        except requests.RequestException as e:
            raise PlayitApiException(f"Failed to link account via reference worker: {e}")
        except ValueError:
            raise PlayitApiException("Invalid JSON from claim exchange")
        
        if data.get("status") != "success":
            error = data.get("error") or data.get("message") or str(data)
            raise PlayitApiException(f"Claim exchange failed: {error}")
        
        secret_key = data.get("data", {}).get("agent_secret_key")
        agent_id = data.get("data", {}).get("agent_id")
        
        if not secret_key:
            raise PlayitApiException(f"Claim exchange did not return a secret key: {data}")
        
        # Write playit.toml
        os.makedirs(os.path.dirname(self.toml_path), exist_ok=True)
        with open(self.toml_path, "w", encoding="utf-8") as f:
            f.write(f'secret_key = "{secret_key}"\n')
        
        self._secret_key = secret_key
        self._agent_id = agent_id
        self.session.headers["Authorization"] = f"agent-key {secret_key}"
        logger.info("Successfully linked playit account via auto-mcs worker")
        return True

    # --- Agent Info ---
    def get_agent_id(self) -> str:
        """Retrieves and caches the agent_id."""
        if self._agent_id:
            return self._agent_id
            
        data = self._request("agents/rundata")
        if data.get("status") == "success":
            self._agent_id = data.get("data", {}).get("agent_id")
            return self._agent_id
        raise PlayitApiException(f"Failed to get agent id: {data}")

    def get_agent_rundata(self) -> dict:
        """Returns full agent rundata including agent_id."""
        data = self._request("agents/rundata")
        if data.get("status") == "success":
            self._agent_id = data["data"]["agent_id"]
            return data["data"]
        raise PlayitApiException(f"Failed to get agent rundata: {data}")

    def proto_register(self) -> Optional[str]:
        """Register client protocol version with the playit server."""
        os_name = platform.system().lower()
        if os_name == "darwin":
            os_name = "macos"
        
        proto_data = {
            "agent_version": {
                "official": True,
                "details_website": None,
                "version": {
                    "platform": os_name,
                    "version": PLAYIT_VERSION
                }
            },
            "client_addr": "0.0.0.0:0",
            "tunnel_addr": "0.0.0.0:0"
        }
        
        data = self._request("proto/register", json_data=proto_data)
        if data.get("status") == "success":
            self._proto_key = data.get("data", {}).get("key")
            return self._proto_key
        return None

    def initialize(self) -> bool:
        """Full initialization: load secret, get agent ID, register protocol.
        Returns True if the API session is ready."""
        if not self.load_secret_key():
            return False
        
        try:
            self.get_agent_rundata()
            self.proto_register()
            return True
        except PlayitApiException as e:
            logger.error(f"Playit API initialization failed: {e}")
            return False

    # --- Tunnel Management ---
    def list_tunnels(self) -> List[Dict]:
        """Returns a list of all tunnels for the agent."""
        agent_id = self.get_agent_id()
        data = self._request("tunnels/list", json_data={"agent_id": agent_id})
        if data.get("status") == "success":
            return data.get("data", {}).get("tunnels", [])
        return []

    def get_tunnel_address(self, tunnel_data: dict) -> Optional[str]:
        """Extract the full connectable address from tunnel API data.
        Returns 'domain:port' for shared tunnels, just 'domain' for dedicated.
        Returns None if the tunnel is pending or has no assigned domain."""
        alloc = tunnel_data.get("alloc", {})
        if alloc.get("status") == "pending":
            return None
        
        alloc_data = alloc.get("data", {})
        domain = alloc_data.get("assigned_domain")
        port_start = alloc_data.get("port_start")
        
        if not domain:
            return None
        
        # Include the port for all tunnels (playit shared IPs need it)
        if port_start:
            return f"{domain}:{port_start}"
        
        return domain

    def create_tunnel(self, port: int = 25565, tunnel_type: str = "minecraft-java") -> Dict:
        """Creates a new tunnel and polls up to 15s for the assigned domain."""
        agent_id = self.get_agent_id()
        import random
        import string
        suffix = ''.join(random.choices(string.ascii_lowercase + string.digits, k=4))
        
        tunnel_data = {
            "name": f"{tunnel_type}_{suffix}",
            "tunnel_type": tunnel_type,
            "port_type": "tcp",
            "port_count": 1,
            "enabled": True,
            "origin": {
                "type": "agent",
                "data": {
                    "agent_id": agent_id,
                    "local_ip": "127.0.0.1",
                    "local_port": port,
                },
            },
        }

        data = self._request("tunnels/create", json_data=tunnel_data)
        if data.get("status") != "success":
            raise PlayitApiException(f"Failed to create tunnel: {data}")
            
        tunnel_id = data.get("data", {}).get("id")
        if not tunnel_id:
            raise PlayitApiException("Tunnel creation returned success but no ID.")

        # Smart Polling: wait for the tunnel to be assigned
        logger.info(f"Tunnel {tunnel_id} created, polling for assignment...")
        for _ in range(15):
            tunnels = self.list_tunnels()
            for t in tunnels:
                if t.get("id") == tunnel_id:
                    status = t.get("alloc", {}).get("status")
                    if status != "pending":
                        address = self.get_tunnel_address(t)
                        if address:
                            logger.info(f"Tunnel {tunnel_id} assigned to {address}")
                            return t
            time.sleep(1)
            
        raise PlayitApiException(f"Tunnel {tunnel_id} remained pending after 15s")

    def delete_tunnel(self, tunnel_id: str) -> bool:
        """Deletes a tunnel by ID."""
        data = self._request("tunnels/delete", json_data={"tunnel_id": tunnel_id})
        return data.get("status") == "success"
