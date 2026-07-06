import json
import logging
import os
import shutil
import zipfile
from typing import Callable, Optional

from app.core.constants import SERVERS_DIR, check_disk_space
from app.core.logic import get_server_meta

logger = logging.getLogger(__name__)

_EXCLUDED_DIRS = {"logs", "crash_reports"}
_EXCLUDED_FILES_SUFFIXES = (".jar",)
_METADATA_STRIP_KEYS = {"crash_history", "required_java", "jdk_source", "port"}


class MigrationError(Exception):
    pass


def export_server(server_name: str, dest_path: str,
                   progress_callback: Optional[Callable[[str], None]] = None) -> str:
    server_dir = os.path.join(SERVERS_DIR, server_name)
    if not os.path.isdir(server_dir):
        raise MigrationError(f"Server '{server_name}' does not exist")

    meta = {k: v for k, v in get_server_meta(server_name).items() if k not in _METADATA_STRIP_KEYS}

    with zipfile.ZipFile(dest_path, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("metadata.json", json.dumps(meta, indent=4))

        for root, dirs, files in os.walk(server_dir):
            rel_root = os.path.relpath(root, server_dir)
            dirs[:] = [d for d in dirs if d not in _EXCLUDED_DIRS]

            for filename in files:
                if filename == "metadata.json":
                    continue
                if filename.lower().endswith(_EXCLUDED_FILES_SUFFIXES):
                    continue
                abs_path = os.path.join(root, filename)
                rel_path = os.path.join(rel_root, filename) if rel_root != "." else filename
                if progress_callback:
                    progress_callback(f"Archiving {rel_path}")
                zf.write(abs_path, arcname=rel_path)

    return dest_path


def import_server(zbbpack_path: str, new_server_name: str,
                   progress_callback: Optional[Callable[[str], None]] = None) -> dict:
    dest_dir = os.path.join(SERVERS_DIR, new_server_name)
    if os.path.exists(dest_dir):
        raise MigrationError(f"Server '{new_server_name}' already exists")

    if not zipfile.is_zipfile(zbbpack_path):
        raise MigrationError("Not a valid .zbbpack archive")

    with zipfile.ZipFile(zbbpack_path, "r") as zf:
        if "metadata.json" not in zf.namelist():
            raise MigrationError("Archive missing metadata.json")
        meta = json.loads(zf.read("metadata.json").decode("utf-8"))

        uncompressed_size = sum(zi.file_size for zi in zf.infolist())
        required_gb = (uncompressed_size / (2**30)) * 1.2
        if not check_disk_space(min_gb=required_gb, target_dir=SERVERS_DIR):
            raise MigrationError(f"Not enough disk space to import (need ~{required_gb:.2f} GB free)")

        try:
            os.makedirs(dest_dir, exist_ok=True)
            dest_dir_real = os.path.realpath(dest_dir)
            for member in zf.namelist():
                if member == "metadata.json":
                    continue
                member_path = os.path.realpath(os.path.join(dest_dir, member))
                if not member_path.startswith(dest_dir_real + os.sep):
                    raise MigrationError(f"Unsafe path in archive: {member}")
                if progress_callback:
                    progress_callback(f"Extracting {member}")
                zf.extract(member, dest_dir)
        except Exception:
            shutil.rmtree(dest_dir, ignore_errors=True)
            raise

    meta_path = os.path.join(dest_dir, "metadata.json")
    with open(meta_path, "w", encoding="utf-8") as f:
        json.dump(meta, f, indent=4)

    return meta
