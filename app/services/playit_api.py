import requests
import json
import os
import time
import logging
from typing import Dict, List, Optional
from app.constants import CONFIG_DIR

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
        self.toml_path = os.path.join(CONFIG_DIR, "playit.toml")

    def load_secret_key(self) -> bool:
        """Loads secret key from playit.toml. Returns True if successful."""
        if not os.path.exists(self.toml_path):
            return False
            
        try:
            with open(self.toml_path, "r", encoding="utf-8") as f:
                for line in f:
                    if "=" in line:
                        k, v = line.split("=", 1)
                        if k.strip() == "secret_key":
                            self._secret_key = v.strip().strip("'\"")
                            self.session.headers["Authorization"] = f"agent-key {self._secret_key}"
                            return True
        except Exception as e:
            logger.error(f"Failed to read playit.toml: {e}")
        return False

    def _request(self, endpoint: str, json_data: dict = None) -> dict:
        """Helper to send POST requests to Playit API with error handling."""
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
            error_detail = data.get("error") or data.get("message") or data.get("detail") or "Unknown API error"
            raise PlayitApiException(f"Playit API returned HTTP {response.status_code}: {error_detail}")

        return data

    def get_agent_id(self) -> str:
        """Retrieves and caches the agent_id."""
        if self._agent_id:
            return self._agent_id
            
        data = self._request("agents/rundata")
        if data.get("status") == "success":
            self._agent_id = data.get("data", {}).get("agent_id")
            return self._agent_id
        raise PlayitApiException(f"Failed to get agent id: {data}")

    def list_tunnels(self) -> List[Dict]:
        """Returns a list of all tunnels for the agent."""
        agent_id = self.get_agent_id()
        data = self._request("tunnels/list", json_data={"agent_id": agent_id})
        if data.get("status") == "success":
            return data.get("data", {}).get("tunnels", [])
        return []

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

        # Smart Polling
        logger.info(f"Tunnel {tunnel_id} created, polling for assignment...")
        for _ in range(15):
            tunnels = self.list_tunnels()
            for t in tunnels:
                if t.get("id") == tunnel_id:
                    status = t.get("alloc", {}).get("status")
                    if status != "pending":
                        domain = t.get("alloc", {}).get("data", {}).get("assigned_domain")
                        if domain:
                            logger.info(f"Tunnel {tunnel_id} assigned to {domain}")
                            return t
            time.sleep(1)
            
        raise PlayitApiException(f"Tunnel {tunnel_id} remained pending after 15s")

    def delete_tunnel(self, tunnel_id: str) -> bool:
        """Deletes a tunnel by ID."""
        data = self._request("tunnels/delete", json_data={"tunnel_id": tunnel_id})
        return data.get("status") == "success"
