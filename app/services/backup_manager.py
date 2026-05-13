import os
import zipfile
import datetime
import threading
import logging
from typing import Callable, Optional

logger = logging.getLogger(__name__)

class BackupManager:
    """Service to create zip backups of Minecraft servers."""
    
    def __init__(self, servers_dir: str, backups_dir: str):
        self.servers_dir = servers_dir
        self.backups_dir = backups_dir
        if not os.path.exists(self.backups_dir):
            os.makedirs(self.backups_dir, exist_ok=True)

    def create_backup(self, server_name: str, on_complete: Optional[Callable[[bool, str], None]] = None) -> threading.Thread:
        """
        Creates a zip backup in the background.
        Fires on_complete(success: bool, filepath: str) when done.
        """
        def _backup_task():
            success = False
            filepath = ""
            try:
                server_path = os.path.join(self.servers_dir, server_name)
                if not os.path.exists(server_path):
                    logger.error(f"Cannot backup. Server path does not exist: {server_path}")
                    if on_complete: on_complete(False, "Server not found")
                    return
                
                timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
                filename = f"backup_{server_name}_{timestamp}.zip"
                filepath = os.path.join(self.backups_dir, filename)
                
                with zipfile.ZipFile(filepath, 'w', zipfile.ZIP_DEFLATED) as zipf:
                    for root, dirs, files in os.walk(server_path):
                        for file in files:
                            abs_file_path = os.path.join(root, file)
                            rel_path = os.path.relpath(abs_file_path, server_path)
                            zipf.write(abs_file_path, arcname=rel_path)
                            
                success = True
                logger.info(f"Backup created successfully: {filepath}")
            except Exception as e:
                logger.error(f"Backup creation failed: {e}")
            finally:
                if on_complete:
                    on_complete(success, filepath)
                    
        thread = threading.Thread(target=_backup_task, daemon=True)
        thread.start()
        return thread
