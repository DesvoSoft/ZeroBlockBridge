"""
Modrinth .mrpack modpack installer for ZeroBlockBridge.

A .mrpack file is a ZIP archive containing:
  - modrinth.index.json  — manifest with mod download URLs
  - overrides/           — files to copy directly into the server dir

Format spec: https://support.modrinth.com/en/articles/8802351-modrinth-modpack-format-mrpack
"""

import json
import logging
import os
import zipfile
from typing import Callable, Optional

from app.core.constants import SERVERS_DIR
from app.services.sha1_validator import download_with_verification

logger = logging.getLogger(__name__)


def install_mrpack(
    mrpack_path: str,
    server_name: str,
    progress_callback: Optional[Callable[[str], None]] = None,
) -> int:
    """
    Install a .mrpack modpack into a server directory.

    Steps:
      1. Extract and parse modrinth.index.json
      2. Download each mod file from its listed URL(s)
      3. Copy overrides/* into the server dir (skips server.jar)

    Args:
        mrpack_path: Absolute path to the .mrpack file.
        server_name: Target server name (under SERVERS_DIR).
        progress_callback: Called with status strings during install.

    Returns:
        Number of mod files downloaded.

    Raises:
        ValueError: If the mrpack is invalid or missing the manifest.
        OSError: On I/O failures.
    """
    def _progress(msg: str):
        logger.info("mrpack: %s", msg)
        if progress_callback:
            progress_callback(msg)

    server_dir = os.path.join(SERVERS_DIR, server_name)
    if not os.path.isdir(server_dir):
        raise ValueError(f"Server directory does not exist: {server_dir}")

    if not zipfile.is_zipfile(mrpack_path):
        raise ValueError(f"Not a valid ZIP/mrpack file: {mrpack_path}")

    _progress("Reading modpack manifest…")

    with zipfile.ZipFile(mrpack_path, "r") as zf:
        # 1. Parse manifest
        if "modrinth.index.json" not in zf.namelist():
            raise ValueError("Missing modrinth.index.json in modpack archive.")

        with zf.open("modrinth.index.json") as fh:
            try:
                manifest = json.loads(fh.read().decode("utf-8"))
            except json.JSONDecodeError as exc:
                raise ValueError(f"Invalid modrinth.index.json: {exc}") from exc

        _validate_manifest(manifest)

        files_list = manifest.get("files", [])
        _progress(f"Found {len(files_list)} mod(s) in modpack.")

        # 2. Download mod files
        downloaded = 0
        for i, entry in enumerate(files_list):
            _progress(f"Downloading mod {i + 1}/{len(files_list)}…")
            _download_entry(entry, server_dir)
            downloaded += 1

        # 3. Copy overrides into server dir
        overrides_prefix = "overrides/"
        override_files = [n for n in zf.namelist() if n.startswith(overrides_prefix) and not n.endswith("/")]
        if override_files:
            _progress(f"Copying {len(override_files)} override file(s)…")
            for name in override_files:
                rel = name[len(overrides_prefix):]
                if not rel:
                    continue
                dest = os.path.join(server_dir, rel)
                os.makedirs(os.path.dirname(dest), exist_ok=True)
                with zf.open(name) as src, open(dest, "wb") as dst:
                    dst.write(src.read())

    _progress(f"Modpack installed — {downloaded} mods.")
    return downloaded


def _validate_manifest(manifest: dict):
    if manifest.get("formatVersion") != 1:
        raise ValueError(
            f"Unsupported mrpack format version: {manifest.get('formatVersion')}"
        )
    if "files" not in manifest:
        raise ValueError("modrinth.index.json missing 'files' key.")


def _download_entry(entry: dict, server_dir: str):
    """Download one file entry from the manifest."""
    downloads = entry.get("downloads", [])
    if not downloads:
        logger.warning("mrpack entry has no download URLs: %s", entry.get("path", "?"))
        return

    path = entry.get("path", "")
    filename = os.path.basename(path) or "unknown.jar"
    sha1 = entry.get("hashes", {}).get("sha1")

    # Determine destination directory from path hint in manifest
    # Modrinth uses paths like "mods/sodium-0.5.jar" or "plugins/luckperms.jar"
    path_parts = path.replace("\\", "/").split("/")
    if len(path_parts) >= 2:
        target_dir = os.path.join(server_dir, path_parts[0])
    else:
        target_dir = os.path.join(server_dir, "mods")

    os.makedirs(target_dir, exist_ok=True)
    dest_path = os.path.join(target_dir, filename)

    # Try each mirror URL until one succeeds
    for url in downloads:
        success, _, error = download_with_verification(url, dest_path, expected_sha1=sha1)
        if success:
            logger.info("Downloaded: %s", filename)
            return
        logger.debug("Download failed from %s: %s", url, error)

    logger.error("All download URLs failed for: %s", filename)
