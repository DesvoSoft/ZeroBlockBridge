import json
import logging
import os
import requests
import threading
import datetime
from pathlib import Path

logger = logging.getLogger(__name__)
from app.constants import (
    VERSIONS_CACHE_FILE, 
    VANILLA_MANIFEST_URL, 
    FABRIC_META_URL, 
    FORGE_PROMOTIONS_URL
)

class VersionManager:
    """
    Singleton class for managing Minecraft server version information.
    
    Fetches, caches, and provides download URLs for Vanilla, Fabric, and Forge
    Minecraft servers. Implements automatic background refresh every 24 hours.
    
    Attributes:
        cache (dict): Cached version data with structure:
            {
                "last_updated": ISO datetime string,
                "Vanilla": [list of version strings],
                "Fabric": [list of version strings],
                "Forge": [list of version strings]
            }
        refresh_thread (Thread): Background thread for version refresh
        callbacks (list): Functions to call when versions are refreshed
    
    Example:
        >>> vm = VersionManager()
        >>> vanilla_versions = vm.get_versions("Vanilla")
        >>> url = vm.get_download_url("Vanilla", "1.20.1")
    """
    _instance = None
    _lock = threading.Lock()

    def __new__(cls):
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super(VersionManager, cls).__new__(cls)
                    cls._instance._initialized = False
        return cls._instance

    def __init__(self):
        if self._initialized:
            return
        self._initialized = True
        self.cache = self._load_cache()
        self.refresh_thread = None
        self.callbacks = []

    def add_callback(self, callback):
        """
        Registers a callback function to be notified when versions refresh.
        
        Args:
            callback (callable): Function to call after version refresh completes.
                                 Should accept no arguments.
        """
        if callback not in self.callbacks:
            self.callbacks.append(callback)

    def _notify_callbacks(self):
        for cb in self.callbacks:
            try:
                cb()
            except Exception as e:
                logger.error("Version callback failed: %s", e)

    def _load_cache(self):
        """
        Loads version cache from disk, with validation.
        
        Validates that cached Fabric versions are game versions (1.x) not loader
        versions (0.x), and that Forge versions are game versions (1.x) not
        build numbers (large integers).
        
        Returns:
            dict: Cached version data or default structure if invalid/missing
        """
        if os.path.exists(VERSIONS_CACHE_FILE):
            try:
                with open(VERSIONS_CACHE_FILE, "r") as f:
                    data = json.load(f)
                    
                    # VALIDATION: Check if Fabric versions look like Game versions (1.x) not Loader versions (0.x)
                    # Fabric game versions usually start with "1." (e.g. 1.20.1)
                    # Loader versions usually start with "0." (e.g. 0.14.22)
                    # If we see "0." versions in Fabric list, assume cache is stale/wrong type.
                    fabric_versions = data.get("Fabric", [])
                    if fabric_versions and any(v.startswith("0.") for v in fabric_versions[:3]):
                        logger.info("Detected stale Fabric loader versions in cache. Forcing refresh.")
                        return self._get_default_cache()

                    # VALIDATION: Check if Forge versions look like Game versions (1.x)
                    # Forge loader versions usually start with large numbers (e.g. 47.x, 14.x)
                    # Minecraft versions start with "1."
                    forge_versions = data.get("Forge", [])
                    if forge_versions and any(not v.startswith("1.") for v in forge_versions[:3]):
                        logger.info("Detected stale Forge loader versions in cache. Forcing refresh.")
                        return self._get_default_cache()
                        
                    return data
            except (json.JSONDecodeError, OSError):
                logger.warning("Version cache corrupted. Using defaults.")
        
        return self._get_default_cache()

    def _get_default_cache(self):
        return {
            "last_updated": None,
            "Vanilla": ["1.21.1", "1.20.1", "1.19.4"], # Minimal fallback
            "Fabric": ["1.21.1", "1.20.1"],
            "Forge": ["1.20.1", "1.19.2"],
            "Paper": ["1.21.1", "1.20.1", "1.19.4"],
            "Purpur": ["1.21.1", "1.20.1", "1.19.4"]
        }

    def _save_cache(self):
        """Persists current version cache to disk."""
        try:
            VERSIONS_CACHE_FILE.parent.mkdir(parents=True, exist_ok=True)
            with open(VERSIONS_CACHE_FILE, "w") as f:
                json.dump(self.cache, f, indent=4)
        except Exception as e:
            logger.error("Failed to save version cache: %s", e)

    def get_versions(self, server_type):
        """
        Returns list of available versions for a server type.
        
        Triggers background refresh if cache is older than 24 hours.
        
        Args:
            server_type (str): One of "Vanilla", "Fabric", or "Forge"
        
        Returns:
            list: Version strings for the specified server type
        """
        # Trigger background refresh if cache is old (> 24 hours) or empty
        self._check_and_refresh()
        return self.cache.get(server_type, [])

    def _check_and_refresh(self):
        """Checks if cache needs refresh and starts background thread."""
        should_refresh = False
        last_updated = self.cache.get("last_updated")
        
        if not last_updated:
            should_refresh = True
        else:
            try:
                last = datetime.datetime.fromisoformat(last_updated)
                if datetime.datetime.now() - last > datetime.timedelta(hours=24):
                    should_refresh = True
            except ValueError:
                should_refresh = True

        if should_refresh and (self.refresh_thread is None or not self.refresh_thread.is_alive()):
            self.refresh_thread = threading.Thread(target=self.refresh_versions, daemon=True)
            self.refresh_thread.start()

    def refresh_versions(self):
        """
        Fetches latest versions from all Minecraft APIs and updates cache.
        
        Runs in background thread. Updates Vanilla, Fabric, and Forge version
        lists from their respective APIs. Maintains existing versions if fetch
        fails for any server type.
        
        Automatically saves cache and notifies registered callbacks on completion.
        """
        logger.info("Refreshing server versions...")
        new_cache = self.cache.copy()
        
        # 1. Vanilla
        try:
            resp = requests.get(VANILLA_MANIFEST_URL, timeout=10)
            if resp.status_code == 200:
                data = resp.json()
                versions = [v["id"] for v in data.get("versions", []) if v["type"] == "release"]
                new_cache["Vanilla"] = versions[:20] # Keep top 20 latest
        except Exception as e:
            logger.warning("Failed to fetch Vanilla versions: %s", e)

        # 2. Fabric
        try:
            resp = requests.get(FABRIC_META_URL, timeout=10)
            if resp.status_code == 200:
                data = resp.json()
                # Fabric meta returns list of objects with "version"
                versions = [v["version"] for v in data if v.get("stable")]
                new_cache["Fabric"] = versions[:20]
        except Exception as e:
            logger.warning("Failed to fetch Fabric versions: %s", e)

        # 3. Forge
        try:
            resp = requests.get(FORGE_PROMOTIONS_URL, timeout=10)
            if resp.status_code == 200:
                data = resp.json()
                promos = data.get("promos", {})
                # Extract MC versions from keys like "1.20.1-recommended" or "1.20.1-latest"
                forge_versions = set()
                for key in promos.keys():
                    if "-" in key:
                        mc_ver = key.split("-")[0]
                        forge_versions.add(mc_ver)
                
                # Sort versions using semantic versioning logic
                def version_key(v):
                    try:
                        parts = []
                        for part in v.split('.'):
                            if part.isdigit():
                                parts.append(int(part))
                        return tuple(parts)
                    except:
                        return (0,)

                sorted_versions = sorted(list(forge_versions), key=version_key, reverse=True)
                new_cache["Forge"] = sorted_versions[:50]
        except Exception as e:
            logger.warning("Failed to fetch Forge versions: %s", e)

        # 4. Paper
        try:
            resp = requests.get("https://api.papermc.io/v2/projects/paper", timeout=10)
            if resp.status_code == 200:
                data = resp.json()
                versions = data.get("versions", [])
                versions.reverse() # Reverse to get newest first
                new_cache["Paper"] = versions[:30]
        except Exception as e:
            logger.warning("Failed to fetch Paper versions: %s", e)

        # 5. Purpur
        try:
            resp = requests.get("https://api.purpurmc.org/v2/purpur", timeout=10)
            if resp.status_code == 200:
                data = resp.json()
                versions = data.get("versions", [])
                versions.reverse() # Reverse to get newest first
                new_cache["Purpur"] = versions[:30]
        except Exception as e:
            logger.warning("Failed to fetch Purpur versions: %s", e)

        new_cache["last_updated"] = datetime.datetime.now().isoformat()
        self.cache = new_cache
        self._save_cache()
        logger.info("Server versions refreshed.")
        self._notify_callbacks()

    def get_download_url(self, server_type, version):
        """
        Resolves download URL for a specific server type and version.
        
        Args:
            server_type (str): One of "Vanilla", "Fabric", or "Forge"
            version (str): Minecraft version (e.g., "1.20.1")
        
        Returns:
            str: Direct download URL for the server installer/jar, or None if not found
        """
        if server_type == "Vanilla":
            return self._get_vanilla_url(version)
        elif server_type == "Fabric":
            return self._get_fabric_installer_url(version)
        elif server_type == "Forge":
            return self._get_forge_installer_url(version)
        elif server_type == "Paper":
            return self._get_paper_url(version)
        elif server_type == "Purpur":
            return self._get_purpur_url(version)
        return None

    def _get_vanilla_url(self, version):
        # Need to fetch manifest to get specific version json, then get server jar url
        # We can cache this too, but for now let's fetch on demand (it's one extra request)
        try:
            resp = requests.get(VANILLA_MANIFEST_URL, timeout=10)
            data = resp.json()
            for v in data.get("versions", []):
                if v["id"] == version:
                    # Get version details
                    v_resp = requests.get(v["url"], timeout=10)
                    v_data = v_resp.json()
                    return v_data["downloads"]["server"]["url"]
        except Exception as e:
            logger.error("Failed to resolve Vanilla URL for %s: %s", version, e)
        return None

    def _get_fabric_installer_url(self, version):
        # Fabric installer is generic, usually we just need the latest installer
        # But the user might want a specific loader version for a MC version.
        # For simplicity, we use the standard installer endpoint which works for all.
        # However, logic.py expects a direct URL to the installer jar.
        # We can use the maven metadata to find the latest installer version.
        try:
            # Get latest installer version
            meta_url = "https://meta.fabricmc.net/v2/versions/installer"
            resp = requests.get(meta_url, timeout=10)
            data = resp.json()
            if data:
                latest_installer = data[0]["version"]
                return f"https://maven.fabricmc.net/net/fabricmc/fabric-installer/{latest_installer}/fabric-installer-{latest_installer}.jar"
        except Exception as e:
            logger.error("Failed to resolve Fabric installer URL: %s", e)
        return None

    def _get_forge_installer_url(self, version):
        # Forge is tricky. We need the specific forge version for the MC version.
        try:
            resp = requests.get(FORGE_PROMOTIONS_URL, timeout=10)
            data = resp.json()
            promos = data.get("promos", {})
            
            # Try recommended, then latest
            forge_ver = promos.get(f"{version}-recommended") or promos.get(f"{version}-latest")
            
            if forge_ver:
                # Construct Maven URL
                # Format: https://maven.minecraftforge.net/net/minecraftforge/forge/{mc_ver}-{forge_ver}/forge-{mc_ver}-{forge_ver}-installer.jar
                # Sometimes it's just {forge_ver} if it includes mc_ver? No, usually {mc}-{forge}
                return f"https://maven.minecraftforge.net/net/minecraftforge/forge/{version}-{forge_ver}/forge-{version}-{forge_ver}-installer.jar"
        except Exception as e:
            logger.error("Failed to resolve Forge installer URL for %s: %s", version, e)
        return None

    def _get_paper_url(self, version):
        try:
            url = f"https://api.papermc.io/v2/projects/paper/versions/{version}"
            resp = requests.get(url, timeout=10)
            data = resp.json()
            builds = data.get("builds", [])
            if builds:
                latest_build = builds[-1]
                return f"{url}/builds/{latest_build}/downloads/paper-{version}-{latest_build}.jar"
        except Exception as e:
            logger.error("Failed to resolve Paper URL for %s: %s", version, e)
        return None

    def _get_purpur_url(self, version):
        try:
            url = f"https://api.purpurmc.org/v2/purpur/{version}"
            resp = requests.get(url, timeout=10)
            data = resp.json()
            builds = data.get("builds", {})
            latest_build = builds.get("latest")
            if latest_build:
                return f"{url}/{latest_build}/download"
        except Exception as e:
            logger.error("Failed to resolve Purpur URL for %s: %s", version, e)
        return None
