import datetime
from pathlib import Path
from unittest.mock import patch, MagicMock
from app.services.backup_manager import BackupManager


class TestBackupManager:
    def test_retention_keeps_recent(self, tmp_path):
        bm = BackupManager("test_server")
        with patch.object(bm, "backup_dir", tmp_path):
            for i in range(5):
                (tmp_path / f"2025-01-0{i+1}_00-00-00.zip").touch()
            bm._apply_retention(3)
            remaining = sorted(tmp_path.iterdir())
            assert len(remaining) == 3
            assert all(f.name == f"2025-01-0{i}_00-00-00.zip" for i, f in zip([3, 4, 5], remaining))

    def test_retention_noop_when_under_limit(self, tmp_path):
        bm = BackupManager("test_server")
        with patch.object(bm, "backup_dir", tmp_path):
            for i in range(2):
                (tmp_path / f"backup_{i}.zip").touch()
            bm._apply_retention(5)
            assert len(list(tmp_path.iterdir())) == 2

    def test_retention_none_skips(self, tmp_path):
        bm = BackupManager("test_server")
        with patch.object(bm, "backup_dir", tmp_path):
            (tmp_path / "backup.zip").touch()
            bm._apply_retention(None)
            assert (tmp_path / "backup.zip").exists()

    def test_retention_only_counts_zip(self, tmp_path):
        bm = BackupManager("test_server")
        with patch.object(bm, "backup_dir", tmp_path):
            for i in range(3):
                (tmp_path / f"backup_{i}.zip").touch()
            (tmp_path / "readme.txt").write_text("")
            bm._apply_retention(2)
            remaining_zip = [f for f in tmp_path.iterdir() if f.suffix == ".zip"]
            assert len(remaining_zip) == 2
            assert (tmp_path / "readme.txt").exists()

    def test_create_backup_passes_retention(self, tmp_path):
        bm = BackupManager("test_server")
        with patch.object(bm, "backup_dir", tmp_path):
            with patch.object(bm, "_apply_retention") as mock_ret:
                with patch.object(bm, "server_path", tmp_path):
                    (tmp_path / "dummy.txt").write_text("data")
                    bm.create_backup(retention_count=7)
                    mock_ret.assert_called_once_with(7)

    def test_list_backups_sorted(self, tmp_path):
        bm = BackupManager("test_server")
        with patch.object(bm, "backup_dir", tmp_path):
            for name in ["2025-03-03_00-00-00.zip", "2025-03-01_00-00-00.zip", "2025-03-02_00-00-00.zip"]:
                (tmp_path / name).touch()
            backups = bm.list_backups()
            assert len(backups) == 3
            assert backups[0]["name"] == "2025-03-03_00-00-00.zip"

    def test_get_latest_backup(self, tmp_path):
        bm = BackupManager("test_server")
        with patch.object(bm, "backup_dir", tmp_path):
            (tmp_path / "2025-04-01_00-00-00.zip").touch()
            (tmp_path / "2025-04-02_00-00-00.zip").touch()
            latest = bm.get_latest_backup()
            assert latest is not None
            assert latest["name"] == "2025-04-02_00-00-00.zip"
