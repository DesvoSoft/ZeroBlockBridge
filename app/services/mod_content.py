"""A server's mod and plugin files: list, install, delete, update, modpacks.

Every delete goes through ``resolve_content_file``, which refuses anything
that isn't a file directly inside that server's ``mods/`` or ``plugins/``
folder, so a stale or tampered ``installed_mods.json`` entry, or a path
handed over by a UI, can never remove something else.
"""

import logging
import os
import shutil
import tempfile
from dataclasses import dataclass, field
from typing import Callable, Optional

from app.core.constants import SERVERS_DIR
from app.core.logic import get_server_meta
from app.services import mod_install_tracker
from app.services.mrpack_installer import install_mrpack
from app.services.server_paths import UnsafePathError, check_server_name

logger = logging.getLogger(__name__)

CONTENT_DIRS = ("mods", "plugins")


class ModDownloadError(RuntimeError):
    """A Modrinth file could not be downloaded."""


class NoCompatibleVersionError(LookupError):
    """Modrinth has no build of the project for this server."""


def content_dirs(server_name: str) -> list[str]:
    check_server_name(server_name)
    return [os.path.join(SERVERS_DIR, server_name, d) for d in CONTENT_DIRS]


def installed_jar_files(server_name: str) -> list[str]:
    """Absolute paths of the .jar files in mods/ and plugins/, sorted per folder."""
    files = []
    for d in content_dirs(server_name):
        if os.path.isdir(d):
            files.extend(os.path.join(d, f) for f in sorted(os.listdir(d)) if f.endswith(".jar"))
    return files


def resolve_content_file(server_name: str, path: str) -> str:
    """Return ``path`` if it names an entry directly inside the server's
    mods/ or plugins/ folder; raise UnsafePathError otherwise.

    The parent folder is compared after resolving links (a server imported
    from another folder is a junction), the entry itself is not: removing a
    link only removes the link.
    """
    allowed = {os.path.normcase(os.path.realpath(d)) for d in content_dirs(server_name)}
    absolute = os.path.abspath(path)
    parent = os.path.normcase(os.path.realpath(os.path.dirname(absolute)))
    if parent not in allowed:
        raise UnsafePathError(f"{path!r} is not in the mods or plugins folder of {server_name!r}")
    if os.path.isdir(absolute) and not os.path.islink(absolute):
        raise UnsafePathError(f"{path!r} is a folder")
    return absolute


def delete_content_file(server_name: str, path: str) -> str:
    """Delete one mod/plugin file and forget its Modrinth record. Returns the filename."""
    path = resolve_content_file(server_name, path)
    fname = os.path.basename(path)
    os.remove(path)
    mod_install_tracker.remove_install_by_filename(server_name, fname)
    logger.info("Deleted %s from %s", fname, server_name)
    return fname


@dataclass
class DeleteResult:
    deleted: list = field(default_factory=list)   # filenames
    failed: list = field(default_factory=list)    # (path, error message)
    removed_slugs: set = field(default_factory=set)


def delete_content_files(server_name: str, paths) -> DeleteResult:
    """Delete several files; one failure doesn't stop the others."""
    filename_to_slug = {mod_install_tracker.get_installed_filename(server_name, slug): slug
                        for slug in mod_install_tracker.get_installed_slugs(server_name)}
    result = DeleteResult()
    for path in paths:
        try:
            fname = delete_content_file(server_name, path)
        except (OSError, UnsafePathError) as exc:
            logger.warning("Failed to delete %s: %s", path, exc)
            result.failed.append((path, str(exc)))
            continue
        result.deleted.append(fname)
        if fname in filename_to_slug:
            result.removed_slugs.add(filename_to_slug[fname])
    return result


def uninstall(server_name: str, slug: str) -> Optional[str]:
    """Remove a mod installed from Modrinth by its slug. Returns the deleted
    filename, or None when the slug isn't recorded. A recorded file that is
    already gone only drops the record."""
    fname = mod_install_tracker.get_installed_filename(server_name, slug)
    if not fname:
        return None
    for d in content_dirs(server_name):
        candidate = resolve_content_file(server_name, os.path.join(d, fname))
        if os.path.isfile(candidate):
            os.remove(candidate)
            logger.info("Uninstalled %s (%s) from %s", slug, fname, server_name)
            break
    mod_install_tracker.remove_install(server_name, slug)
    return fname


def install_version(client, version: dict, server_name: str, loader: str, slug: str,
                    progress: Optional[Callable[[float], None]] = None) -> Optional[str]:
    """Download one Modrinth version into mods/ or plugins/ and record its
    slug. Returns the file path, or None when the download failed."""
    check_server_name(server_name)
    path = client.download_version(version, server_name, loader, progress_callback=progress)
    if path:
        mod_install_tracker.record_install(server_name, slug, os.path.basename(path))
    return path


def install_latest(client, slug: str, server_name: str, mc_version: str, loader: str) -> Optional[str]:
    """Install the newest compatible build of a project. Raises
    NoCompatibleVersionError when there is none; None on a failed download."""
    check_server_name(server_name)
    if not client.get_versions(slug, mc_version=mc_version, loader=loader):
        raise NoCompatibleVersionError(slug)
    path = client.download_mod(slug, server_name, mc_version, loader)
    if path:
        mod_install_tracker.record_install(server_name, slug, os.path.basename(path))
    return path


def install_modpack(client, version: dict, server_name: str,
                    on_download: Optional[Callable[[float], None]] = None,
                    on_status: Optional[Callable[[str], None]] = None) -> dict:
    """Download a .mrpack version to a temporary folder and install it into
    the server. Returns install_mrpack's summary; raises ModDownloadError
    or MrpackCompatibilityError. The temporary folder is always removed."""
    check_server_name(server_name)
    tmp_dir = tempfile.mkdtemp(prefix="zbb_modpack_")
    try:
        downloaded = client.download_version_to(version, tmp_dir, progress_callback=on_download)
        if not downloaded:
            raise ModDownloadError(version.get("id", "?"))
        meta = get_server_meta(server_name)
        return install_mrpack(
            downloaded, server_name,
            progress_callback=on_status,
            server_type=meta.get("type"),
            mc_version=meta.get("version"),
        )
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)


def snapshot_then_apply(create_snapshot: Optional[Callable], server_name: str,
                        updates: list, apply_one: Callable[[dict], bool]) -> tuple[Optional[str], int, int]:
    """Snapshot the server, then apply each update in order.

    Returns (snapshot_error, updated, failed). When the snapshot fails no
    update is applied — updating without a rollback point is exactly the
    false confidence this flow exists to prevent.
    """
    if create_snapshot is None:
        return "Snapshot service unavailable.", 0, 0
    path, error = create_snapshot(server_name)
    if not path:
        return error or "Unknown snapshot error.", 0, 0

    updated, failed = 0, 0
    for update in updates:
        try:
            ok = apply_one(update)
        except Exception as exc:
            logger.warning("Update failed for %s: %s", update.get("filename"), exc)
            ok = False
        if ok:
            updated += 1
        else:
            failed += 1
    return None, updated, failed


def filter_updates_for_selection(updates: list, selected_filenames: set) -> list:
    """The subset of check_updates() results matching the selected filenames."""
    return [u for u in updates if u.get("filename") in selected_filenames]
