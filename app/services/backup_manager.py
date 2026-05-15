import datetime
import logging
import os
import shutil
import zipfile
from pathlib import Path

from app.core.constants import SERVERS_DIR, BASE_DIR

logger = logging.getLogger(__name__)


class BackupManager:
    def __init__(self, server_name):
        self.server_name = server_name
        self.server_path = SERVERS_DIR / server_name
        self.backup_dir = BASE_DIR / "backups" / server_name
        if not self.backup_dir.exists():
            self.backup_dir.mkdir(parents=True, exist_ok=True)

    def create_backup(self):
        timestamp = datetime.datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
        backup_filename = f"{timestamp}.zip"
        backup_path = self.backup_dir / backup_filename
        abs_backup_dir = self.backup_dir.resolve()
        try:
            skipped_files = []
            with zipfile.ZipFile(backup_path, 'w', zipfile.ZIP_DEFLATED) as zipf:
                for root, dirs, files in os.walk(self.server_path):
                    root_path = os.path.abspath(root)
                    if "backups" in os.path.relpath(root_path, self.server_path).split(os.sep):
                        continue
                    for file in files:
                        file_path = os.path.join(root, file)
                        if os.path.abspath(file_path) == str(os.path.abspath(backup_path)):
                            continue
                        arcname = os.path.relpath(file_path, self.server_path)
                        try:
                            zipf.write(file_path, arcname)
                        except (PermissionError, OSError) as e:
                            if e.errno == 13:
                                skipped_files.append(arcname)
                                logger.warning("Skipped locked file: %s", arcname)
                            else:
                                raise e
            if skipped_files:
                return backup_path, f"Backup created with warnings. Skipped {len(skipped_files)} locked files."
            return backup_path, None
        except Exception as e:
            if backup_path.exists():
                try:
                    backup_path.unlink()
                except Exception:
                    pass
            return None, str(e)

    def list_backups(self):
        backups = []
        if not self.backup_dir.exists():
            return backups
        for f in self.backup_dir.iterdir():
            if f.is_file() and f.suffix == ".zip":
                size_mb = f.stat().st_size / (1024 * 1024)
                backups.append({
                    "name": f.name,
                    "path": str(f),
                    "size": f"{size_mb:.2f} MB",
                    "date": datetime.datetime.strptime(f.stem, "%Y-%m-%d_%H-%M-%S").strftime("%d %b %Y %H:%M")
                })
        backups.sort(key=lambda x: x["name"], reverse=True)
        return backups

    def get_latest_backup(self):
        if not self.backup_dir.exists():
            return None
        backups = [f for f in self.backup_dir.iterdir() if f.is_file() and f.suffix == ".zip"]
        if not backups:
            return None
        backups.sort(key=lambda x: x.name, reverse=True)
        latest = backups[0]
        return {
            "name": latest.name,
            "path": str(latest),
            "date": datetime.datetime.strptime(latest.stem, "%Y-%m-%d_%H-%M-%S").strftime("%d %b %Y %H:%M")
        }

    def restore_backup(self, backup_path_str):
        backup_path = Path(backup_path_str)
        if not backup_path.exists():
            return False
        try:
            for item in self.server_path.iterdir():
                if item.is_file() or item.is_symlink():
                    item.unlink()
                elif item.is_dir():
                    shutil.rmtree(item)
            with zipfile.ZipFile(backup_path, 'r') as zipf:
                zipf.extractall(self.server_path)
            return True
        except Exception:
            return False
