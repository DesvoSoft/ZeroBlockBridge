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

# manifest dependency key -> ZBB server engine name (lowercase)
_LOADER_DEPENDENCY_MAP = {
    "fabric-loader": "fabric",
    "forge": "forge",
    "quilt-loader": "quilt",
    "neoforge": "neoforge",
}

# Engines that can actually load mods from a mods/ folder
_MOD_CAPABLE_ENGINES = {"fabric", "forge"}


class MrpackCompatibilityError(ValueError):
    """Modpack cannot run on the target server (wrong loader or MC version)."""


def install_mrpack(
    mrpack_path: str,
    server_name: str,
    progress_callback: Optional[Callable[[str], None]] = None,
    server_type: Optional[str] = None,
    mc_version: Optional[str] = None,
) -> dict:
    """
    Install a .mrpack modpack into a server directory.

    Steps:
      1. Extract and parse modrinth.index.json
      2. Validate pack loader + MC version against the target server
      3. Download each server-side mod file (client-only entries are skipped)
      4. Copy overrides/* into the server dir

    Args:
        mrpack_path: Absolute path to the .mrpack file.
        server_name: Target server name (under SERVERS_DIR).
        progress_callback: Called with status strings during install.
        server_type: Server engine ("Fabric", "Paper", ...). When given, the
            pack's declared loader must match or MrpackCompatibilityError is
            raised before anything is downloaded.
        mc_version: Server MC version. When given, must match the pack's
            declared minecraft dependency.

    Returns:
        Summary dict: {"installed": int, "skipped_client": int, "failed": int}.

    Raises:
        ValueError: If the mrpack is invalid or missing the manifest.
        MrpackCompatibilityError: Loader/MC version mismatch with the server.
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

    summary = {"installed": 0, "skipped_client": 0, "failed": 0}

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

        # 2. Compatibility gate — fail fast, before any download
        _check_compatibility(manifest, server_type, mc_version)

        files_list = manifest.get("files", [])
        _progress(f"Found {len(files_list)} file(s) in modpack.")

        # 3. Download mod files (skip client-only entries per mrpack spec)
        for i, entry in enumerate(files_list):
            env_server = entry.get("env", {}).get("server")
            if env_server == "unsupported":
                logger.info("mrpack: skipping client-only file %s", entry.get("path", "?"))
                summary["skipped_client"] += 1
                continue
            _progress(f"Downloading mod {i + 1}/{len(files_list)}…")
            if _download_entry(entry, server_dir):
                summary["installed"] += 1
            else:
                summary["failed"] += 1

        # 4. Copy overrides into server dir
        overrides_prefix = "overrides/"
        override_files = [n for n in zf.namelist() if n.startswith(overrides_prefix) and not n.endswith("/")]
        if override_files:
            _progress(f"Copying {len(override_files)} override file(s)…")
            for name in override_files:
                rel = name[len(overrides_prefix):]
                if not rel:
                    continue
                dest = _safe_dest(server_dir, rel)
                os.makedirs(os.path.dirname(dest), exist_ok=True)
                with zf.open(name) as src, open(dest, "wb") as dst:
                    dst.write(src.read())

    _progress(
        f"Modpack installed — {summary['installed']} mods"
        + (f", {summary['skipped_client']} client-only skipped" if summary["skipped_client"] else "")
        + (f", {summary['failed']} failed" if summary["failed"] else "")
        + "."
    )
    return summary


def _check_compatibility(manifest: dict, server_type: Optional[str], mc_version: Optional[str]):
    """Raise MrpackCompatibilityError if the pack cannot run on this server."""
    deps = manifest.get("dependencies", {})

    required_loaders = [
        engine for key, engine in _LOADER_DEPENDENCY_MAP.items() if key in deps
    ]

    if server_type and required_loaders:
        engine = server_type.lower()
        if engine not in required_loaders:
            wanted = "/".join(sorted(required_loaders)).title()
            raise MrpackCompatibilityError(
                f"This modpack requires a {wanted} server, but "
                f"'{server_type}' cannot load its mods. Create a {wanted} "
                f"server to use this pack."
            )
        if engine not in _MOD_CAPABLE_ENGINES:
            # quilt/neoforge pack matching an engine ZBB doesn't ship
            raise MrpackCompatibilityError(
                f"Modpacks for {engine.title()} are not supported yet."
            )

    pack_mc = deps.get("minecraft")
    if mc_version and pack_mc and pack_mc != mc_version:
        raise MrpackCompatibilityError(
            f"This modpack targets Minecraft {pack_mc}, but the server runs "
            f"{mc_version}. Versions must match exactly."
        )


def _validate_manifest(manifest: dict):
    if manifest.get("formatVersion") != 1:
        raise ValueError(
            f"Unsupported mrpack format version: {manifest.get('formatVersion')}"
        )
    if "files" not in manifest:
        raise ValueError("modrinth.index.json missing 'files' key.")


def _safe_dest(base_dir: str, rel_path: str) -> str:
    """Join rel_path under base_dir, rejecting traversal outside it (zip-slip)."""
    base = os.path.realpath(base_dir)
    dest = os.path.realpath(os.path.join(base, rel_path.replace("\\", "/")))
    if os.path.commonpath([base, dest]) != base:
        raise ValueError(f"Unsafe path in modpack archive: {rel_path}")
    return dest


def _download_entry(entry: dict, server_dir: str) -> bool:
    """Download one file entry from the manifest. Returns True on success."""
    downloads = entry.get("downloads", [])
    if not downloads:
        logger.warning("mrpack entry has no download URLs: %s", entry.get("path", "?"))
        return False

    # Modrinth uses paths like "mods/sodium-0.5.jar" or "plugins/luckperms.jar"
    path = entry.get("path", "") or "mods/unknown.jar"
    sha1 = entry.get("hashes", {}).get("sha1")

    dest_path = _safe_dest(server_dir, path)
    os.makedirs(os.path.dirname(dest_path), exist_ok=True)

    # Try each mirror URL until one succeeds
    for url in downloads:
        success, _, error = download_with_verification(url, dest_path, expected_sha1=sha1)
        if success:
            logger.info("Downloaded: %s", os.path.basename(dest_path))
            return True
        logger.debug("Download failed from %s: %s", url, error)

    logger.error("All download URLs failed for: %s", os.path.basename(dest_path))
    return False
