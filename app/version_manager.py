import json
import os
import requests
import threading
import datetime
from pathlib import Path
from app.constants import (
    VERSIONS_CACHE_FILE, 
    VANILLA_MANIFEST_URL, 
    FABRIC_META_URL, 
    FORGE_PROMOTIONS_URL
)

class VersionManager:
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
        """Adds a callback to be notified when versions are refreshed."""
        if callback not in self.callbacks:
            self.callbacks.append(callback)

    def _notify_callbacks(self):
        for cb in self.callbacks:
            try:
                cb()
            except Exception as e:
                print(f"[Error] Version callback failed: {e}")

    def _load_cache(self):
        """Loads versions from cache file."""
        if os.path.exists(VERSIONS_CACHE_FILE):
            try:
                with open(VERSIONS_CACHE_FILE, "r") as f:
                    return json.load(f)
            except (json.JSONDecodeError, OSError):
                print("[Warning] Version cache corrupted. Using defaults.")
        
        # Default fallback if cache missing/corrupt
        return {
            "last_updated": None,
            "Vanilla": ["1.21.1", "1.20.1", "1.19.4"], # Minimal fallback
            "Fabric": ["1.21.1", "1.20.1"],
            "Forge": ["1.20.1", "1.19.2"]
        }

    def _save_cache(self):
        """Saves current versions to cache file."""
        try:
            VERSIONS_CACHE_FILE.parent.mkdir(parents=True, exist_ok=True)
            with open(VERSIONS_CACHE_FILE, "w") as f:
                json.dump(self.cache, f, indent=4)
        except Exception as e:
            print(f"[Error] Failed to save version cache: {e}")

    def get_versions(self, server_type):
        """Returns a list of available versions for the given server type."""
        # Trigger background refresh if cache is old (e.g., > 24 hours) or empty
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
        """Fetches latest versions from APIs."""
        print("[System] Refreshing server versions...")
        new_cache = self.cache.copy()
        
        # 1. Vanilla
        try:
            resp = requests.get(VANILLA_MANIFEST_URL, timeout=10)
            if resp.status_code == 200:
                data = resp.json()
                versions = [v["id"] for v in data.get("versions", []) if v["type"] == "release"]
                new_cache["Vanilla"] = versions[:20] # Keep top 20 latest
        except Exception as e:
            print(f"[Warning] Failed to fetch Vanilla versions: {e}")

        # 2. Fabric
        try:
            resp = requests.get(FABRIC_META_URL, timeout=10)
            if resp.status_code == 200:
                data = resp.json()
                # Fabric meta returns list of objects with "version"
                versions = [v["version"] for v in data if v.get("stable")]
                new_cache["Fabric"] = versions[:20]
        except Exception as e:
            print(f"[Warning] Failed to fetch Fabric versions: {e}")

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
                
                # Sort versions (simple string sort is flawed for versions, but sufficient for now or use packaging.version)
                # Let's just rely on the fact we have a set.
                sorted_versions = sorted(list(forge_versions), reverse=True)
                new_cache["Forge"] = sorted_versions[:20]
        except Exception as e:
            print(f"[Warning] Failed to fetch Forge versions: {e}")

        new_cache["last_updated"] = datetime.datetime.now().isoformat()
        self.cache = new_cache
        self._save_cache()
        self._save_cache()
        print("[System] Server versions refreshed.")
        self._notify_callbacks()

    def get_download_url(self, server_type, version):
        """Resolves the download URL for a specific version."""
        if server_type == "Vanilla":
            return self._get_vanilla_url(version)
        elif server_type == "Fabric":
            return self._get_fabric_installer_url(version)
        elif server_type == "Forge":
            return self._get_forge_installer_url(version)
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
            print(f"[Error] Failed to resolve Vanilla URL for {version}: {e}")
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
            print(f"[Error] Failed to resolve Fabric installer URL: {e}")
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
            print(f"[Error] Failed to resolve Forge installer URL for {version}: {e}")
        return None
