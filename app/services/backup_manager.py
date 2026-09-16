import datetime
import logging
import os
import shutil
import tempfile
import zipfile
from pathlib import Path
from typing import Any

from app.core.constants import SERVERS_DIR, BASE_DIR

logger = logging.getLogger(__name__)


class BackupManager:
    # Tagged (non-manual) backups aren't covered by the user's own retention
    # policy, so cap them here to avoid unbounded disk growth from repeated
    # mod updates — each snapshot is a full server-directory zip.
    _DEFAULT_TAGGED_RETENTION = 5

    def __init__(self, server_name: str):
        self.server_name = server_name
        self.server_path = SERVERS_DIR / server_name
        self.backup_dir = BASE_DIR / "backups" / server_name
        if not self.backup_dir.exists():
            self.backup_dir.mkdir(parents=True, exist_ok=True)

    def create_backup(self, retention_count: int | None = None, reason: str = "manual") -> tuple[Path | None, str | None]:
        from app.core.constants import check_disk_space
        if not check_disk_space(min_gb=1, target_dir=self.server_path):
            return None, "Not enough disk space to create backup (>1GB required)."

        timestamp = datetime.datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
        filename = f"{timestamp}.zip" if reason == "manual" else f"{timestamp}__{reason}.zip"
        backup_path = self.backup_dir / filename
        abs_backup_dir = self.backup_dir.resolve()
        skipped_files = []

        try:
            with zipfile.ZipFile(backup_path, 'w', zipfile.ZIP_DEFLATED) as zipf:
                for root, dirs, files in os.walk(self.server_path):
                    root_path = os.path.abspath(root)
                    if "backups" in os.path.relpath(root_path, self.server_path).split(os.sep):
                        continue
                    for file in files:
                        file_path = os.path.join(root, file)
                        if os.path.abspath(file_path) == str(abs_backup_dir / filename):
                            continue
                        arcname = os.path.relpath(file_path, self.server_path)
                        try:
                            zipf.write(file_path, arcname)
                        except (PermissionError, OSError) as e:
                            if getattr(e, 'errno', None) == 13:
                                skipped_files.append(arcname)
                                logger.warning("Skipped locked file: %s", arcname)
                            else:
                                raise

            self._apply_retention(self._resolve_retention(retention_count, reason), reason=reason)
            if skipped_files:
                return backup_path, f"Backup created with warnings. Skipped {len(skipped_files)} locked files."
            return backup_path, None
        except Exception as e:
            if backup_path.exists():
                try:
                    backup_path.unlink()
                except OSError as unlink_err:
                    logger.warning("Failed to clean up failed backup: %s", unlink_err)
            return None, str(e)

    def _resolve_retention(self, retention_count: int | None, reason: str) -> int | None:
        """Tagged backups default to a bounded retention even when the
        caller doesn't pass one — otherwise repeated pre-update snapshots
        would grow the backup directory unbounded."""
        if retention_count is None and reason != "manual":
            return self._DEFAULT_TAGGED_RETENTION
        return retention_count

    def _apply_retention(self, retention_count: int | None, reason: str | None = None) -> None:
        """Prune old backups beyond retention_count.

        When `reason` is given, only backups sharing that reason are counted
        and pruned — a pre-update snapshot rotation must never delete a
        user's manual/scheduled backups, and vice versa.
        """
        if retention_count is None:
            return
        candidates = [f for f in self.backup_dir.iterdir() if f.is_file() and f.suffix == ".zip"]
        if reason is not None:
            candidates = [f for f in candidates if (f.stem.partition("__")[2] or "manual") == reason]
        backups = sorted(candidates, key=lambda x: x.name, reverse=True)
        if len(backups) > retention_count:
            for f in backups[retention_count:]:
                try:
                    f.unlink()
                    logger.info("Removed old backup: %s", f.name)
                except OSError as e:
                    logger.warning("Failed to remove old backup %s: %s", f.name, e)

    def list_backups(self) -> list[dict[str, Any]]:
        backups: list[dict[str, Any]] = []
        if not self.backup_dir.exists():
            return backups
        for f in self.backup_dir.iterdir():
            if f.is_file() and f.suffix == ".zip":
                timestamp_part, _, reason = f.stem.partition("__")
                try:
                    date_str = datetime.datetime.strptime(timestamp_part, "%Y-%m-%d_%H-%M-%S").strftime("%d %b %Y %H:%M")
                except ValueError:
                    logger.warning("Skipping non-timestamp backup file: %s", f.name)
                    continue
                size_mb = f.stat().st_size / (1024 * 1024)
                backups.append({
                    "name": f.name,
                    "path": str(f),
                    "size": f"{size_mb:.2f} MB",
                    "date": date_str,
                    "reason": reason or "manual",
                })
        backups.sort(key=lambda x: x["name"], reverse=True)
        return backups

    def delete_backup(self, backup_path_str: str) -> tuple[bool, str | None]:
        """Delete one backup archive of this server. Refuses anything that
        isn't a .zip directly inside this server's backup directory."""
        backup_path = Path(backup_path_str)
        try:
            inside = backup_path.resolve().parent == self.backup_dir.resolve()
        except OSError:
            inside = False
        if not inside or backup_path.suffix != ".zip":
            return False, "Not a backup of this server."
        try:
            backup_path.unlink()
        except FileNotFoundError:
            return True, None
        except OSError as e:
            logger.warning("Failed to delete backup %s: %s", backup_path.name, e)
            return False, str(e)
        logger.info("Deleted backup: %s", backup_path.name)
        return True, None

    def get_latest_backup(self) -> dict[str, Any] | None:
        if not self.backup_dir.exists():
            return None
        backups = []
        for f in self.backup_dir.iterdir():
            if f.is_file() and f.suffix == ".zip":
                timestamp_part = f.stem.partition("__")[0]
                try:
                    datetime.datetime.strptime(timestamp_part, "%Y-%m-%d_%H-%M-%S")
                except ValueError:
                    continue
                backups.append(f)
        if not backups:
            return None
        backups.sort(key=lambda x: x.name, reverse=True)
        latest = backups[0]
        latest_timestamp = latest.stem.partition("__")[0]
        return {
            "name": latest.name,
            "path": str(latest),
            "date": datetime.datetime.strptime(latest_timestamp, "%Y-%m-%d_%H-%M-%S").strftime("%d %b %Y %H:%M"),
        }

    def restore_backup(self, backup_path_str: str) -> bool:
        backup_path = Path(backup_path_str)
        if not backup_path.exists():
            return False

        # dir= pins the temp dir to the same volume as server_path — mkdtemp()'s
        # default (system TEMP) can be a different drive, which makes the
        # rename() below raise OSError (cross-device rename) on every restore.
        tmp_extract = Path(tempfile.mkdtemp(prefix="zbb_restore_", dir=self.server_path.parent))
        bak_path = self.server_path.with_name(self.server_path.name + "_bak")
        try:
            # Extract to temp dir first — server_path untouched until this succeeds
            tmp_extract_real = os.path.realpath(tmp_extract)
            with zipfile.ZipFile(backup_path, 'r') as zipf:
                for member in zipf.namelist():
                    member_path = os.path.realpath(os.path.join(tmp_extract, member))
                    if not member_path.startswith(tmp_extract_real + os.sep):
                        raise ValueError(f"Unsafe path in backup archive: {member}")
                zipf.extractall(tmp_extract)

            # Atomic swap: rename current → _bak, extracted → server_path
            if bak_path.exists():
                shutil.rmtree(bak_path)
            self.server_path.rename(bak_path)
            try:
                tmp_extract.rename(self.server_path)
            except Exception as e:
                # Rename of extracted dir failed — restore original
                logger.error("Atomic swap failed, restoring original: %s", e)
                bak_path.rename(self.server_path)
                raise

            shutil.rmtree(bak_path, ignore_errors=True)
            return True
        except Exception as e:
            logger.error("Backup restore failed: %s", e)
            return False
        finally:
            if tmp_extract.exists():
                shutil.rmtree(tmp_extract, ignore_errors=True)
