import json
import logging
import os
import requests
import threading
import datetime
import re
from concurrent.futures import ThreadPoolExecutor, as_completed

logger = logging.getLogger(__name__)
from app.core.constants import (
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
    _singleton_lock = threading.Lock()

    def __new__(cls):
        if cls._instance is None:
            with cls._singleton_lock:
                if cls._instance is None:
                    cls._instance = super(VersionManager, cls).__new__(cls)
                    cls._instance._initialized = False
        return cls._instance

    def __init__(self):
        if getattr(self, '_initialized', False):
            return
        self.cache_lock = threading.RLock()
        self.fallback_cache = self._get_default_cache()
        self.cache = self.fallback_cache
        self.cache = self._load_cache()
        self.refresh_thread = None
        self.callbacks = []
        self._initialized = True

    def add_callback(self, callback):
        with self.cache_lock:
            if callback not in self.callbacks:
                self.callbacks.append(callback)

    def remove_callback(self, callback):
        with self.cache_lock:
            try:
                self.callbacks.remove(callback)
            except ValueError:
                pass

    def _notify_callbacks(self):
        with self.cache_lock:
            cbs = list(self.callbacks)
        for cb in cbs:
            try:
                cb()
            except Exception as e:
                logger.error("Version callback failed: %s", e)

    def _load_cache(self):
        if os.path.exists(VERSIONS_CACHE_FILE):
            try:
                with open(VERSIONS_CACHE_FILE, "r") as f:
                    data = json.load(f)

                fabric_versions = data.get("Fabric", [])
                if fabric_versions and any(v.startswith("0.") for v in fabric_versions[:3]):
                    logger.info("Detected stale Fabric loader versions in cache. Forcing refresh.")
                    return self._get_default_cache()

                forge_versions = data.get("Forge", [])
                if forge_versions:
                    first = forge_versions[0]
                    if not first.startswith("1.") or re.match(r'^\d+\.\d+', first):
                        logger.info("Detected stale Forge loader versions in cache. Forcing refresh.")
                        return self._fetch_defaults_sync()

                for key in ("Paper", "Purpur"):
                    versions = data.get(key, [])
                    if versions and not versions[0].startswith("1."):
                        logger.info("Detected stale %s versions in cache. Forcing refresh.", key)
                        return self._fetch_defaults_sync()

                last_updated = data.get("last_updated")
                if last_updated:
                    try:
                        last = datetime.datetime.fromisoformat(last_updated)
                        if datetime.datetime.now() - last > datetime.timedelta(days=2):
                            logger.info("Version cache is >2 days old. Forcing sync refresh.")
                            fetched = self._fetch_all_versions(timeout=8)
                            if fetched:
                                data.update(fetched)
                                data["last_updated"] = datetime.datetime.now().isoformat()
                                self._save_cache()
                            return data
                    except ValueError:
                        pass

                return data
            except (json.JSONDecodeError, OSError):
                logger.warning("Version cache corrupted. Using defaults.")

        return self._get_default_cache()

    def _fetch_defaults_sync(self):
        """Try a synchronous foreground fetch when cache is stale.
        Returns fetched cache on success, default cache on failure."""
        try:
            new_cache = self._get_default_cache()
            data = self._fetch_all_versions(timeout=8)
            if data:
                new_cache.update(data)
                new_cache["last_updated"] = datetime.datetime.now().isoformat()
                self.cache = new_cache
                self._save_cache()
                logger.info("Synchronous version refresh completed.")
                return new_cache
        except Exception as e:
            logger.warning("Synchronous refresh failed: %s", e)
        return self._get_default_cache()

    def _get_default_cache(self):
        return {
            "last_updated": None,
            "Vanilla": [
                "1.21.11", "1.21.10", "1.21.9", "1.21.8", "1.21.7",
                "1.21.6", "1.21.5", "1.21.4", "1.21.3", "1.21.1", "1.21",
                "1.20.4", "1.20.1",
                "1.19.4", "1.19.2",
                "1.18.2",
                "1.17.1",
                "1.16.5", "1.15.2", "1.14.4",
                "1.12.2", "1.8.9",
            ],
            "Fabric": [
                "1.21.11", "1.21.10", "1.21.9", "1.21.8", "1.21.7",
                "1.21.6", "1.21.5", "1.21.4", "1.21.3", "1.21.1", "1.21",
                "1.20.4", "1.20.1",
                "1.19.4", "1.19.2",
                "1.18.2",
                "1.17.1",
                "1.16.5",
            ],
            "Forge": [
                "1.21.1", "1.20.1", "1.19.2", "1.18.2",
                "1.17.1", "1.16.5",
            ],
            "Paper": [
                "1.21.11", "1.21.10", "1.21.9", "1.21.8", "1.21.7",
                "1.21.6", "1.21.5", "1.21.4", "1.21.3", "1.21.1", "1.21",
                "1.20.4", "1.20.1",
                "1.19.4", "1.19.2",
                "1.18.2",
                "1.17.1",
                "1.16.5",
            ],
            "Purpur": [
                "1.21.11", "1.21.10", "1.21.9", "1.21.8", "1.21.7",
                "1.21.6", "1.21.5", "1.21.4", "1.21.3", "1.21.1", "1.21",
                "1.20.4", "1.20.1",
                "1.19.4", "1.19.2",
                "1.18.2",
                "1.17.1",
                "1.16.5",
            ],
        }

    @staticmethod
    def _fetch_vanilla(timeout=10):
        resp = requests.get(VANILLA_MANIFEST_URL, timeout=timeout)
        resp.raise_for_status()
        data = resp.json()
        return [v["id"] for v in data.get("versions", []) if v["type"] == "release"][:100]

    @staticmethod
    def _fetch_fabric(timeout=10):
        resp = requests.get(FABRIC_META_URL, timeout=timeout)
        resp.raise_for_status()
        data = resp.json()
        return [v["version"] for v in data if v.get("stable")][:100]

    @staticmethod
    def _fetch_forge(timeout=10):
        resp = requests.get(FORGE_PROMOTIONS_URL, timeout=timeout)
        resp.raise_for_status()
        data = resp.json()
        promos = data.get("promos", {})
        forge_versions = set()
        for key in promos.keys():
            if "-" in key:
                mc_ver = key.split("-")[0]
                forge_versions.add(mc_ver)
        def version_key(v):
            try:
                parts = []
                for part in v.split('.'):
                    if part.isdigit():
                        parts.append(int(part))
                return tuple(parts)
            except (ValueError, TypeError) as e:
                logger.debug("Forge version_key parse failed: %s", e)
                return (0,)
        return sorted(forge_versions, key=version_key, reverse=True)[:100]

    @staticmethod
    def _fetch_paper(timeout=10):
        resp = requests.get("https://api.papermc.io/v2/projects/paper", timeout=timeout)
        resp.raise_for_status()
        versions = resp.json().get("versions", [])
        versions.reverse()
        return versions[:100]

    @staticmethod
    def _fetch_purpur(timeout=10):
        resp = requests.get("https://api.purpurmc.org/v2/purpur", timeout=timeout)
        resp.raise_for_status()
        versions = resp.json().get("versions", [])
        versions.reverse()
        return versions[:100]

    def _fetch_all_versions(self, timeout=10):
        """Fetch all version lists in parallel using ThreadPoolExecutor."""
        fetchers = {
            "Vanilla": self._fetch_vanilla,
            "Fabric": self._fetch_fabric,
            "Forge": self._fetch_forge,
            "Paper": self._fetch_paper,
            "Purpur": self._fetch_purpur,
        }
        results = {}
        with ThreadPoolExecutor(max_workers=5) as exe:
            future_map = {exe.submit(fn, timeout=timeout): key for key, fn in fetchers.items()}
            for future in as_completed(future_map, timeout=timeout + 2):
                key = future_map[future]
                try:
                    results[key] = future.result()
                except Exception as e:
                    logger.warning("Failed to fetch %s versions: %s", key, e)
        return results

    def _save_cache(self):
        """Persists current version cache to disk."""
        try:
            VERSIONS_CACHE_FILE.parent.mkdir(parents=True, exist_ok=True)
            with open(VERSIONS_CACHE_FILE, "w") as f:
                json.dump(self.cache, f, indent=4)
        except Exception as e:
            logger.error("Failed to save version cache: %s", e)

    def get_versions(self, server_type):
        self._check_and_refresh()
        self._wait_for_background_refresh(timeout=4)
        with self.cache_lock:
            return list(self.cache.get(server_type, []))

    def _wait_for_background_refresh(self, timeout=4):
        thread = getattr(self, 'refresh_thread', None)
        if thread is not None and thread.is_alive():
            thread.join(timeout=timeout)
            return not thread.is_alive()
        return False

    def _check_and_refresh(self):
        with self.cache_lock:
            last_updated = self.cache.get("last_updated")
            should_refresh = False
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
        logger.info("Refreshing server versions...")
        with self.cache_lock:
            new_cache = self.cache.copy()
            results = self._fetch_all_versions(timeout=10)
            for key, versions in results.items():
                new_cache[key] = versions
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
