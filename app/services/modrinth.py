"""
Modrinth API v2 Client for ZeroBlockBridge.

Provides search, version listing, download, and update-checking for mods/plugins
hosted on Modrinth. All read operations are unauthenticated.

API Reference: https://docs.modrinth.com/api/
Rate Limit: 300 requests/minute per IP.
"""

import hashlib
import json
import logging
import os
import shutil
import time
from typing import Dict, List, Optional

import requests

from app.constants import SERVERS_DIR

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
MODRINTH_API = "https://api.modrinth.com/v2"
USER_AGENT = "DesvoSoft/ZeroBlockBridge/1.0 (github.com/DesvoSoft/ZeroBlockBridge)"
REQUEST_TIMEOUT = 12  # seconds


class ModrinthException(Exception):
    """Raised on non-recoverable Modrinth API errors."""
    pass


class ModrinthClient:
    """
    Stateless REST client for the Modrinth API v2.

    All methods are synchronous and intended to be called from worker threads
    to avoid blocking the UI.
    """

    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update({"User-Agent": USER_AGENT})
        self._rate_reset: float = 0.0

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------
    def _request(self, method: str, path: str, params: dict = None) -> dict | list:
        """
        Execute an HTTP request against the Modrinth API.

        Handles rate-limiting (429) with a single automatic retry, and
        converts >= 400 responses into ModrinthException.
        """
        url = f"{MODRINTH_API}/{path.lstrip('/')}"
        try:
            resp = self.session.request(method, url, params=params, timeout=REQUEST_TIMEOUT)
        except requests.RequestException as exc:
            raise ModrinthException(f"Network error: {exc}") from exc

        # Rate-limit handling
        if resp.status_code == 429:
            wait = int(resp.headers.get("X-Ratelimit-Reset", 5))
            logger.warning("Modrinth rate-limited. Waiting %ds…", wait)
            time.sleep(min(wait, 30))
            try:
                resp = self.session.request(method, url, params=params, timeout=REQUEST_TIMEOUT)
            except requests.RequestException as exc:
                raise ModrinthException(f"Network error on retry: {exc}") from exc

        if resp.status_code >= 400:
            raise ModrinthException(
                f"Modrinth API {resp.status_code}: {resp.text[:200]}"
            )

        try:
            return resp.json()
        except ValueError:
            raise ModrinthException("Invalid JSON from Modrinth API")

    # ------------------------------------------------------------------
    # Public API — Search
    # ------------------------------------------------------------------
    def search(
        self,
        query: str,
        mc_version: str = None,
        loader: str = None,
        project_type: str = "mod",
        limit: int = 20,
        offset: int = 0,
    ) -> Dict:
        """
        Search for projects on Modrinth.

        Args:
            query: Search terms.
            mc_version: Minecraft version filter (e.g. "1.20.1").
            loader: Mod loader filter (e.g. "fabric", "forge", "paper").
            project_type: One of "mod", "modpack", "resourcepack", "shader", "plugin".
            limit: Max results per page (1-100).
            offset: Pagination offset.

        Returns:
            dict with keys: hits (list), total_hits, offset, limit.
        """
        facets = []
        if project_type:
            facets.append(f'["project_type:{project_type}"]')
        if mc_version:
            facets.append(f'["versions:{mc_version}"]')
        if loader:
            facets.append(f'["categories:{loader}"]')

        params = {
            "query": query,
            "limit": min(limit, 100),
            "offset": offset,
        }
        if facets:
            params["facets"] = f"[{','.join(facets)}]"

        return self._request("GET", "/search", params=params)

    # ------------------------------------------------------------------
    # Public API — Project detail
    # ------------------------------------------------------------------
    def get_project(self, id_or_slug: str) -> Dict:
        """Fetch full project details by ID or slug."""
        return self._request("GET", f"/project/{id_or_slug}")

    # ------------------------------------------------------------------
    # Public API — Version listing
    # ------------------------------------------------------------------
    def get_versions(
        self,
        project_id: str,
        mc_version: str = None,
        loader: str = None,
    ) -> List[Dict]:
        """
        List versions for a project, optionally filtered.

        Args:
            project_id: Project ID or slug.
            mc_version: Filter by game version.
            loader: Filter by loader.

        Returns:
            List of version objects sorted newest-first.
        """
        params = {}
        if mc_version:
            params["game_versions"] = json.dumps([mc_version])
        if loader:
            params["loaders"] = json.dumps([loader])

        return self._request("GET", f"/project/{project_id}/version", params=params)

    # ------------------------------------------------------------------
    # Public API — Download + Install
    # ------------------------------------------------------------------
    def download_mod(
        self,
        project_id: str,
        server_name: str,
        mc_version: str,
        loader: str,
        progress_callback=None,
    ) -> Optional[str]:
        """
        Download the latest compatible version of a mod into the server's
        mods/ (or plugins/) directory.

        Returns the path to the downloaded file, or None on failure.
        """
        versions = self.get_versions(project_id, mc_version=mc_version, loader=loader)
        if not versions:
            logger.warning("No compatible version found for %s (MC %s, %s)", project_id, mc_version, loader)
            return None

        version = versions[0]  # newest compatible
        primary_file = None
        for f in version.get("files", []):
            if f.get("primary", False):
                primary_file = f
                break
        if not primary_file and version.get("files"):
            primary_file = version["files"][0]

        if not primary_file:
            logger.error("Version %s has no downloadable files", version.get("id"))
            return None

        download_url = primary_file["url"]
        filename = primary_file["filename"]
        expected_sha1 = primary_file.get("hashes", {}).get("sha1")

        # Determine target directory
        target_dir = "plugins" if loader in ("paper", "purpur", "spigot", "bukkit") else "mods"
        dest_dir = os.path.join(SERVERS_DIR, server_name, target_dir)
        os.makedirs(dest_dir, exist_ok=True)
        dest_path = os.path.join(dest_dir, filename)

        # Download with progress
        try:
            resp = self.session.get(download_url, stream=True, timeout=30)
            resp.raise_for_status()
            total = int(resp.headers.get("content-length", 0))
            downloaded = 0
            sha1 = hashlib.sha1()

            with open(dest_path, "wb") as fp:
                for chunk in resp.iter_content(chunk_size=8192):
                    if chunk:
                        fp.write(chunk)
                        sha1.update(chunk)
                        downloaded += len(chunk)
                        if progress_callback and total > 0:
                            progress_callback(downloaded / total)

            # SHA1 verification
            if expected_sha1 and sha1.hexdigest() != expected_sha1:
                logger.error(
                    "SHA1 mismatch for %s: expected %s, got %s",
                    filename, expected_sha1, sha1.hexdigest(),
                )
                os.remove(dest_path)
                return None

            logger.info("Downloaded %s to %s", filename, dest_path)
            return dest_path

        except Exception as exc:
            logger.error("Download failed for %s: %s", filename, exc)
            if os.path.exists(dest_path):
                os.remove(dest_path)
            return None

    # ------------------------------------------------------------------
    # Public API — Update checking
    # ------------------------------------------------------------------
    def check_updates(
        self,
        server_name: str,
        mc_version: str,
        loader: str,
    ) -> List[Dict]:
        """
        Scan the server's mods/plugins directory for installed Modrinth mods
        and check if newer versions are available.

        Returns a list of dicts:
            {"filename", "project_id", "installed_version", "latest_version", "update_url"}
        """
        target_dir = "plugins" if loader in ("paper", "purpur", "spigot", "bukkit") else "mods"
        mods_dir = os.path.join(SERVERS_DIR, server_name, target_dir)

        if not os.path.isdir(mods_dir):
            return []

        # Collect SHA1 hashes of installed files
        hashes = {}
        for fname in os.listdir(mods_dir):
            fpath = os.path.join(mods_dir, fname)
            if not os.path.isfile(fpath) or not fname.endswith(".jar"):
                continue
            sha1 = hashlib.sha1()
            with open(fpath, "rb") as fp:
                for chunk in iter(lambda: fp.read(8192), b""):
                    sha1.update(chunk)
            hashes[sha1.hexdigest()] = fname

        if not hashes:
            return []

        # Batch lookup via version-files endpoint
        try:
            data = self._request(
                "POST",
                "/version_files/update",
                params=None,
            )
            # The batch endpoint requires a POST body, so use session directly
            resp = self.session.post(
                f"{MODRINTH_API}/version_files/update",
                json={
                    "hashes": list(hashes.keys()),
                    "algorithm": "sha1",
                    "loaders": [loader],
                    "game_versions": [mc_version],
                },
                timeout=REQUEST_TIMEOUT,
            )
            if resp.status_code >= 400:
                logger.warning("Batch update check failed: HTTP %d", resp.status_code)
                return []
            results = resp.json()
        except Exception as exc:
            logger.error("Update check failed: %s", exc)
            return []

        updates = []
        for old_hash, new_version in results.items():
            if old_hash not in hashes:
                continue
            primary = None
            for f in new_version.get("files", []):
                if f.get("primary"):
                    primary = f
                    break
            if not primary:
                primary = new_version["files"][0] if new_version.get("files") else None
            if primary and primary.get("hashes", {}).get("sha1") != old_hash:
                updates.append({
                    "filename": hashes[old_hash],
                    "project_id": new_version.get("project_id"),
                    "installed_hash": old_hash,
                    "latest_version": new_version.get("version_number"),
                    "update_url": primary.get("url"),
                    "update_filename": primary.get("filename"),
                })

        return updates
