import requests
import json
import os
import sys
import time
import platform
import uuid
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
        self.session.headers["User-Agent"] = "ZeroBlockBridge/1.0"
        self._secret_key = None
        self._agent_id = None
        self._proto_key = None
        self.is_read_only = False
        self.toml_path = os.path.join(CONFIG_DIR, "playit.toml")
        self.client_id = str(uuid.uuid4())

    def load_secret_key(self) -> bool:
        """Loads secret key from playit.toml. Returns True if successful."""
        if not os.path.exists(self.toml_path):
            return self._secret_key is not None
            
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

    def _request(self, endpoint: str, json_data: dict = None, method: str = "POST") -> dict:
        """Helper to send requests to Playit API with error handling."""
        self.load_secret_key()
        if not self._secret_key:
            raise PlayitApiException("No secret key loaded. Cannot authenticate.")
            
        url = f"{self.api_base}/{endpoint.strip('/')}"
        headers = {"Authorization": f"agent-key {self._secret_key}"}
        try:
            response = self.session.request(method, url, json=json_data, headers=headers, timeout=10)
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

    def verify_secret_key(self) -> bool:
        """Ping the API to validate the secret key without creating/registering.
        Returns True if the key is valid, False otherwise."""
        if not self._secret_key:
            self.load_secret_key()
        if not self._secret_key:
            return False
        try:
            resp = self.session.get(
                f"{self.api_base}/agents/rundata",
                headers={"Authorization": f"agent-key {self._secret_key}"},
                timeout=5,
            )
            return resp.status_code == 200
        except Exception:
            return False

    def _get_platform_variant(self) -> str:
        """Variante segÃºn nomenclatura de GitHub para v0.17.1.
        Windows â†’ windows-x86_64, Linux â†’ linux-amd64.
        """
        machine = platform.machine().lower()
        sys_name = platform.system().lower()

        if sys_name == "windows":
            return "windows-x86_64"
        elif sys_name == "linux":
            if "arm64" in machine or "aarch64" in machine:
                return "linux-aarch64"
            return "linux-amd64"
        elif sys_name == "darwin":
            if "arm64" in machine or "aarch64" in machine:
                return "macos-aarch64"
            return "macos-amd64"

        return f"{sys_name}-{machine}"

    # --- Account Linking ---
    def link_account(self, setup_code: str, agent_name: str = "ZeroBlockBridge") -> bool:
        """Link to a playit account using a setup code from the third-party web flow.
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

        from app.core.app_config import AppConfig
        try:
            response = requests.post(
                AppConfig.PLAYIT_BRIDGE_URL,
                json=payload,
                timeout=20,
            )
            data = response.json()
        except requests.RequestException as e:
            raise PlayitApiException(f"Failed to connect to bridge: {e}")
        except ValueError:
            raise PlayitApiException(f"Invalid JSON from bridge (HTTP {response.status_code}): {response.text[:500]}")

        if response.status_code >= 400 or data.get("status") == "fail":
            logger.error("Bridge returned HTTP %d: %s", response.status_code, response.text)
            raise PlayitApiException(f"Bridge exchange failed (HTTP {response.status_code}): {response.text[:500]}")

        # Extract credentials
        result = data.get("data", data)
        secret_key = result.get("agent_secret_key") or result.get("secret_key")
        agent_id = result.get("agent_id")

        if not secret_key:
            logger.error("Bridge response body: %s", data)
            raise PlayitApiException(f"Bridge did not return a secret key: {data}")

        # Write playit.toml â€” persistencia crÃ­tica del secret_key
        os.makedirs(os.path.dirname(self.toml_path), exist_ok=True)
        with open(self.toml_path, "w", encoding="utf-8") as f:
            f.write(f'secret_key = "{secret_key}"\n')
        if platform.system() != "Windows":
            os.chmod(self.toml_path, 0o600)

        self._secret_key = secret_key
        self._agent_id = agent_id
        self.session.headers["Authorization"] = f"agent-key {secret_key}"
        logger.info("Successfully linked playit account (Agent ID: %s)", agent_id)
        return True

    # --- Agent Info ---
    def get_agent_id(self) -> str:
        """Retrieves and caches the agent_id."""
        if self._agent_id:
            return self._agent_id
            
        try:
            data = self._request("agents/rundata")
            if data.get("status") == "success":
                self._agent_id = data.get("data", {}).get("agent_id")
                return self._agent_id
        except PlayitApiException as e:
            logger.warning(f"Failed to get agent id via rundata: {e}")
            
        # Fallback: try tunnels/list to see if we can find the agent_id there
        try:
            data = self._request("tunnels/list", json_data={"agent_id": None})
            if data.get("status") == "success":
                tunnels = data.get("data", {}).get("tunnels", [])
                if tunnels:
                    self._agent_id = tunnels[0].get("origin", {}).get("data", {}).get("agent_id")
                    if self._agent_id:
                        return self._agent_id
        except Exception as e:
            logger.warning(f"Fallback agent_id detection failed: {e}")

    def get_agent_rundata(self) -> dict:
        """Returns full agent rundata including agent_id."""
        data = self._request("agents/rundata")
        if data.get("status") == "success":
            self._agent_id = data["data"]["agent_id"]
            agent_type = data["data"].get("agent_type")
            logger.info("Agent type from rundata: %s", agent_type)
            return data["data"]
        raise PlayitApiException(f"Failed to get agent rundata: {data}")

    def proto_register(self) -> Optional[str]:
        """Register client protocol version with the playit server."""
        os_name = platform.system().lower()
        if os_name == "darwin":
            os_name = "macos"

        from app.core.constants import PLAYIT_VERSION
        proto_data = {
            "agent_version": {
                "official": True,
                "details_website": None,
                "variant": self._get_platform_variant(),
                "version": {
                    "platform": os_name,
                    "version": PLAYIT_VERSION,
                },
            },
            "client_addr": "0.0.0.0:0",
            "tunnel_addr": "0.0.0.0:0",
        }

        data = self._request("proto/register", json_data=proto_data)
        if data.get("status") == "success":
            self._proto_key = data.get("data", {}).get("key")
            return self._proto_key
        return None

    def initialize(self) -> bool:
        """Full initialization: load secret, get agent ID, register protocol.
        Returns True if the API session is ready or in Guest Mode."""
        if not self.load_secret_key():
            return False

        try:
            self.get_agent_rundata()
            self.proto_register()
            return True
        except PlayitApiException as e:
            if self.is_read_only:
                logger.info("Playit API initialized in Guest mode (Read-Only).")
                return True
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
        Soporta: assigned_domain directo (AgentTunnel), connect_addresses (v1 web),
        y alloc.* (legacy).
        Returns 'domain:port' string or None."""

        # AgentTunnel format: assigned_domain + port
        domain = tunnel_data.get("assigned_domain")
        if domain:
            local_port = tunnel_data.get("local_port")
            if local_port:
                return f"{domain}:{local_port}"
            return domain

        # Web API format: connect_addresses
        connect_addrs = tunnel_data.get("connect_addresses", [])
        if connect_addrs:
            for entry in connect_addrs:
                addr = entry.get("value", {}).get("address")
                port = entry.get("value", {}).get("default_port")
                if addr:
                    return f"{addr}:{port}" if port else addr

        # Legacy format: alloc.data
        alloc = tunnel_data.get("alloc", {})
        if alloc.get("status") == "pending":
            return None
        alloc_data = alloc.get("data", {})

        public_dns = alloc_data.get("address", {}).get("public_dns") if isinstance(alloc_data.get("address"), dict) else None
        if public_dns:
            if ":" in public_dns:
                return public_dns
            port_start = alloc_data.get("port_start")
            if port_start:
                return f"{public_dns}:{port_start}"
            return public_dns

        domain = alloc_data.get("assigned_domain")
        if not domain:
            return None
        port_start = alloc_data.get("port_start")
        if port_start:
            return f"{domain}:{port_start}"
        return domain
    def get_tunnels(self) -> List[str]:
        """Obtiene todas las direcciones pÃºblicas de los tÃºneles vÃ­a API.
        Devuelve lista de strings 'domain:port'. VacÃ­a si no hay tÃºneles asignados."""
        try:
            tunnels = self.list_tunnels()
            addresses = []
            for t in tunnels:
                addr = self.get_tunnel_address(t)
                if addr:
                    addresses.append(addr)
            return addresses
        except PlayitApiException:
            return []

    def create_tunnel(self, port: int = 25565, tunnel_type: str = "minecraft-java", proxy_protocol: bool = False) -> Dict:
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
            "alloc": {
                "type": "region",
                "details": {"region": "global"},
            },
            "proxy_protocol": None,
            "firewall_id": None,
        }

        data = self._request("tunnels/create", json_data=tunnel_data)
        if data.get("status") != "success":
            raise PlayitApiException(f"Failed to create tunnel: {data}")

        tunnel_id = data.get("data", {}).get("id")
        if not tunnel_id:
            raise PlayitApiException("Tunnel creation returned success but no ID.")

        logger.info(f"Tunnel {tunnel_id} created, polling for assignment...")
        for _ in range(15):
            tunnels = self.list_tunnels()
            for t in tunnels:
                if t.get("id") == tunnel_id:
                    address = self.get_tunnel_address(t)
                    if address:
                        logger.info(f"Tunnel {tunnel_id} assigned to {address}")
                        return t
            time.sleep(1)

        logger.warning(f"Tunnel {tunnel_id} remained pending after 15s.")
        return data.get("data", {})

    def delete_tunnel(self, tunnel_id: str) -> bool:
        """Deletes a tunnel by ID using v2 API."""
        try:
            data = self._request("tunnels/delete", json_data={"tunnel_id": tunnel_id})
            if data.get("status") == "success":
                return True
            return False
        except PlayitApiException as e:
            if "401" in str(e):
                logger.warning(f"Tunnel {tunnel_id} already inaccessible (401).")
                return True
            raise e

    def delete_agent(self) -> bool:
        """Deletes the current agent from the account using v2 API."""
        try:
            agent_id = self._agent_id
            if not agent_id:
                try:
                    agent_id = self.get_agent_id()
                except PlayitApiException as e:
                    logger.warning("Could not fetch agent_id for deletion: %s", e)

            if not agent_id:
                logger.warning("Cannot delete agent: No agent_id found.")
                return False

            data = self._request("agents/delete", json_data={"agent_id": agent_id})
            if data.get("status") == "success":
                return True
            return False
        except PlayitApiException as e:
            if "401" in str(e):
                logger.warning("Agent deletion failed with 401. Your key might be read-only or revoked.")
                return False
            logger.error(f"Error during agent deletion: {e}")
            return False
        except Exception as e:
            logger.error(f"Unexpected error during agent deletion: {e}")
            return False



