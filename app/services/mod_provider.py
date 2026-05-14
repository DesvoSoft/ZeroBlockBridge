import logging
import os
import threading
from typing import List, Dict, Optional, Callable
from app.services.modrinth import ModrinthClient, ModrinthException
from app.constants import SERVERS_DIR

logger = logging.getLogger(__name__)

class ModProvider:
    """Service to handle mod searches and downloads, specifically from Modrinth."""
    
    OPTIMIZERS = [
        {"slug": "sodium", "name": "Sodium", "description": "High performance rendering engine."},
        {"slug": "lithium", "name": "Lithium", "description": "General-purpose game code optimizer."},
        {"slug": "ferrite-core", "name": "FerriteCore", "description": "Memory usage optimization."},
        {"slug": "starlight", "name": "Starlight", "description": "Rewrite of light engine for performance."},
        {"slug": "iris", "name": "Iris Shaders", "description": "Modern shader support for Sodium."}
    ]

    def __init__(self):
        self.client = ModrinthClient()

    def search_mods(self, query: str, mc_version: str = None, loader: str = None, limit: int = 20) -> List[Dict]:
        """Search for mods with filters."""
        try:
            results = self.client.search(
                query,
                mc_version=mc_version,
                loader=loader,
                project_type="mod",
                limit=limit
            )
            return results.get("hits", [])
        except ModrinthException as e:
            logger.error(f"Search failed: {e}")
            return []

    def download_mod(self, slug: str, server_name: str, mc_version: str, loader: str, progress_callback: Callable = None) -> Optional[str]:
        """Download and install a mod."""
        return self.client.download_mod(slug, server_name, mc_version, loader, progress_callback)

    def get_optimizers(self) -> List[Dict]:
        """Returns a list of recommended optimization mods."""
        return self.OPTIMIZERS

    def install_optimizer_bundle(self, server_name: str, mc_version: str, loader: str, status_callback: Callable = None):
        """Installs a standard set of optimizers in a background thread."""
        def _run():
            for mod in self.OPTIMIZERS:
                if status_callback:
                    status_callback(f"Installing {mod['name']}...")
                try:
                    self.download_mod(mod['slug'], server_name, mc_version, loader)
                except Exception as e:
                    logger.error(f"Failed to install {mod['name']}: {e}")
            if status_callback:
                status_callback("Ready")

        threading.Thread(target=_run, daemon=True).start()
