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
    def __init__(self, server_name: str):
        self.server_name = server_name
        self.server_path = SERVERS_DIR / server_name
        self.backup_dir = BASE_DIR / "backups" / server_name
        if not self.backup_dir.exists():
            self.backup_dir.mkdir(parents=True, exist_ok=True)

    def create_backup(self, retention_count: int | None = None) -> tuple[Path | None, str | None]:
        from app.core.constants import check_disk_space
        if not check_disk_space(min_gb=1, target_dir=self.server_path):
            return None, "Not enough disk space to create backup (>1GB required)."

        timestamp = datetime.datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
        backup_path = self.backup_dir / f"{timestamp}.zip"
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
                        if os.path.abspath(file_path) == str(abs_backup_dir / f"{timestamp}.zip"):
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

            self._apply_retention(retention_count)
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

    def _apply_retention(self, retention_count: int | None) -> None:
        if retention_count is None:
            return
        backups = sorted(
            [f for f in self.backup_dir.iterdir() if f.is_file() and f.suffix == ".zip"],
            key=lambda x: x.name, reverse=True
        )
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
                try:
                    date_str = datetime.datetime.strptime(f.stem, "%Y-%m-%d_%H-%M-%S").strftime("%d %b %Y %H:%M")
                except ValueError:
                    logger.warning("Skipping non-timestamp backup file: %s", f.name)
                    continue
                size_mb = f.stat().st_size / (1024 * 1024)
                backups.append({
                    "name": f.name,
                    "path": str(f),
                    "size": f"{size_mb:.2f} MB",
                    "date": date_str,
                })
        backups.sort(key=lambda x: x["name"], reverse=True)
        return backups

    def get_latest_backup(self) -> dict[str, Any] | None:
        if not self.backup_dir.exists():
            return None
        backups = []
        for f in self.backup_dir.iterdir():
            if f.is_file() and f.suffix == ".zip":
                try:
                    datetime.datetime.strptime(f.stem, "%Y-%m-%d_%H-%M-%S")
                except ValueError:
                    continue
                backups.append(f)
        if not backups:
            return None
        backups.sort(key=lambda x: x.name, reverse=True)
        latest = backups[0]
        return {
            "name": latest.name,
            "path": str(latest),
            "date": datetime.datetime.strptime(latest.stem, "%Y-%m-%d_%H-%M-%S").strftime("%d %b %Y %H:%M"),
        }

    def restore_backup(self, backup_path_str: str) -> bool:
        backup_path = Path(backup_path_str)
        if not backup_path.exists():
            return False

        tmp_extract = Path(tempfile.mkdtemp(prefix="zbb_restore_"))
        bak_path = self.server_path.with_name(self.server_path.name + "_bak")
        try:
            # Extract to temp dir first — server_path untouched until this succeeds
            with zipfile.ZipFile(backup_path, 'r') as zipf:
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
