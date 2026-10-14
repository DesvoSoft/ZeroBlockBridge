"""
Modrinth .mrpack modpack installer for ZeroBlockBridge.

A .mrpack file is a ZIP archive containing:
  - modrinth.index.json  — manifest with mod download URLs
  - overrides/           — files to copy directly into the server dir
  - server-overrides/    — server-only files, applied after overrides/

Format spec: https://support.modrinth.com/en/articles/8802351-modrinth-modpack-format-mrpack
"""

import json
import logging
import os
import zipfile
import queue
import threading
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
    server_dir: Optional[str] = None,
) -> dict:
    """
    Install a .mrpack modpack into a server directory.

    Steps:
      1. Extract and parse modrinth.index.json
      2. Validate pack loader + MC version against the target server
      3. Download each server-side mod file (client-only entries are skipped)
      4. Copy overrides/* then server-overrides/* into the server dir

    Args:
        mrpack_path: Absolute path to the .mrpack file.
        server_name: Target server name (under SERVERS_DIR).
        progress_callback: Called with status strings during install.
        server_type: Server engine ("Fabric", "Paper", ...). When given, the
            pack's declared loader must match or MrpackCompatibilityError is
            raised before anything is downloaded.
        mc_version: Server MC version. When given, must match the pack's
            declared minecraft dependency.
        server_dir: Install here instead of SERVERS_DIR/<server_name>.

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

    server_dir = server_dir or os.path.join(SERVERS_DIR, server_name)
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
        wanted = [e for e in files_list if e.get("env", {}).get("server") != "unsupported"]
        summary["skipped_client"] = len(files_list) - len(wanted)
        summary["installed"], summary["failed"] = _download_all(wanted, server_dir, _progress)

        # 4. Copy overrides into server dir (server-specific ones win)
        for overrides_prefix in ("overrides/", "server-overrides/"):
            _copy_overrides(zf, overrides_prefix, server_dir, _progress)

    _progress(
        f"Modpack installed — {summary['installed']} mods"
        + (f", {summary['skipped_client']} client-only skipped" if summary["skipped_client"] else "")
        + (f", {summary['failed']} failed" if summary["failed"] else "")
        + "."
    )
    return summary


# Parallel downloads: big packs have 100-400 small jars, where one-at-a-time
# spends most of its time on per-request latency. Six keeps a home
# connection busy without hammering Modrinth's CDN.
DOWNLOAD_WORKERS = 6


def _unique_entries(entries: list, server_dir: str) -> list:
    """Validate every path (rejecting traversal before anything downloads)
    and drop entries that would write the same file -- concurrent writers
    to one path could leave a mix of both downloads on disk."""
    seen, unique = set(), []
    for entry in entries:
        dest = os.path.normcase(_safe_dest(server_dir, entry.get("path", "") or "mods/unknown.jar"))
        if dest in seen:
            logger.warning("mrpack: duplicate path %s skipped", entry.get("path"))
            continue
        seen.add(dest)
        unique.append(entry)
    return unique


def _download_all(entries: list, server_dir: str, progress: Callable[[str], None]) -> tuple:
    """Download entries concurrently; returns (installed, failed). Progress
    is only ever reported from the calling thread.

    Plain daemon threads, not a ThreadPoolExecutor: an executor's workers
    are joined at interpreter exit and drain the whole queue first, so
    closing the app mid-install would leave a hidden process downloading
    for minutes after the single-instance lock was released."""
    pending = queue.Queue()
    unique = _unique_entries(entries, server_dir)
    for entry in unique:
        pending.put(entry)
    total = len(unique)
    if not total:
        return 0, 0
    results: queue.Queue = queue.Queue()
    stop = threading.Event()

    def worker():
        while not stop.is_set():
            try:
                entry = pending.get_nowait()
            except queue.Empty:
                return
            try:
                ok = bool(_download_entry(entry, server_dir))
            except Exception as e:  # one bad mod must not abort the pack
                logger.error("mrpack download failed for %s: %s", entry.get("path", "?"), e)
                ok = False
            results.put(ok)

    for i in range(min(DOWNLOAD_WORKERS, total)):
        threading.Thread(target=worker, daemon=True, name=f"mrpack-dl-{i}").start()
    installed = failed = 0
    try:
        for done in range(1, total + 1):
            ok = results.get()
            installed += ok
            failed += not ok
            progress(f"Downloading mods {done}/{total}…")
    finally:
        stop.set()  # caller gave up (e.g. the window closed): take no new jobs
    return installed, failed


def _copy_overrides(zf: zipfile.ZipFile, prefix: str, server_dir: str, progress: Callable[[str], None]):
    override_files = [n for n in zf.namelist() if n.startswith(prefix) and not n.endswith("/")]
    if not override_files:
        return
    progress(f"Copying {len(override_files)} {prefix.rstrip('/')} file(s)…")
    for name in override_files:
        rel = name[len(prefix):]
        if not rel:
            continue
        dest = _safe_dest(server_dir, rel)
        os.makedirs(os.path.dirname(dest), exist_ok=True)
        with zf.open(name) as src, open(dest, "wb") as dst:
            dst.write(src.read())


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
