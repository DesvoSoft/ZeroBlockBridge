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
                    mock_ret.assert_called_once_with(7, reason="manual")

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

    def test_create_backup_manual_reason_untagged_filename(self, tmp_path):
        bm = BackupManager("test_server")
        with patch.object(bm, "backup_dir", tmp_path), patch.object(bm, "server_path", tmp_path):
            (tmp_path / "dummy.txt").write_text("data")
            path, error = bm.create_backup(reason="manual")
            assert error is None
            assert "__" not in path.name

    def test_create_backup_tags_reason_in_filename(self, tmp_path):
        bm = BackupManager("test_server")
        with patch.object(bm, "backup_dir", tmp_path), patch.object(bm, "server_path", tmp_path):
            (tmp_path / "dummy.txt").write_text("data")
            path, error = bm.create_backup(reason="pre_update")
            assert error is None
            assert path.name.endswith("__pre_update.zip")

    def test_list_backups_reports_reason(self, tmp_path):
        bm = BackupManager("test_server")
        with patch.object(bm, "backup_dir", tmp_path):
            (tmp_path / "2025-05-01_00-00-00.zip").touch()
            (tmp_path / "2025-05-02_00-00-00__pre_update.zip").touch()
            backups = {b["name"]: b for b in bm.list_backups()}
            assert backups["2025-05-01_00-00-00.zip"]["reason"] == "manual"
            assert backups["2025-05-02_00-00-00__pre_update.zip"]["reason"] == "pre_update"

    def test_apply_retention_reason_scoped_does_not_touch_other_reason(self, tmp_path):
        bm = BackupManager("test_server")
        with patch.object(bm, "backup_dir", tmp_path):
            for i in range(3):
                (tmp_path / f"2025-06-0{i+1}_00-00-00.zip").touch()
            for i in range(3):
                (tmp_path / f"2025-06-0{i+1}_00-00-00__pre_update.zip").touch()

            bm._apply_retention(1, reason="pre_update")

            remaining = sorted(f.name for f in tmp_path.iterdir())
            manual = [n for n in remaining if "__" not in n]
            tagged = [n for n in remaining if "__pre_update" in n]
            assert len(manual) == 3
            assert tagged == ["2025-06-03_00-00-00__pre_update.zip"]

    def test_create_backup_default_retention_caps_tagged_backups(self, tmp_path):
        bm = BackupManager("test_server")
        with patch.object(bm, "backup_dir", tmp_path), patch.object(bm, "server_path", tmp_path):
            (tmp_path / "dummy.txt").write_text("data")
            for i in range(5):
                (tmp_path / f"2025-06-0{i+1}_00-00-00__pre_update.zip").touch()

            path, error = bm.create_backup(reason="pre_update")

            assert error is None
            tagged = [f for f in tmp_path.iterdir() if f.suffix == ".zip" and "__pre_update" in f.stem]
            assert len(tagged) == 5

    def test_get_latest_backup_handles_tagged_filename(self, tmp_path):
        bm = BackupManager("test_server")
        with patch.object(bm, "backup_dir", tmp_path):
            (tmp_path / "2025-05-01_00-00-00.zip").touch()
            (tmp_path / "2025-05-02_00-00-00__pre_update.zip").touch()
            latest = bm.get_latest_backup()
            assert latest is not None
            assert latest["name"] == "2025-05-02_00-00-00__pre_update.zip"
            assert latest["date"] == "02 May 2025 00:00"

    def test_pre_update_snapshot_restore_round_trip(self, tmp_path):
        """Snapshot -> mod update -> restore brings back the exact pre-update mods."""
        server = tmp_path / "servers" / "srv"
        backups = tmp_path / "backups"
        (server / "mods").mkdir(parents=True)
        backups.mkdir()
        (server / "mods" / "sodium-0.5.jar").write_text("old")
        (server / "server.properties").write_text("motd=§aHello", encoding="utf-8")

        bm = BackupManager("test_server")
        with patch.object(bm, "backup_dir", backups), patch.object(bm, "server_path", server):
            snapshot, error = bm.create_backup(reason="pre_update")
            assert error is None

            # Simulate the mod update replacing the jar.
            (server / "mods" / "sodium-0.5.jar").unlink()
            (server / "mods" / "sodium-0.6.jar").write_text("new")

            assert bm.restore_backup(str(snapshot)) is True

            assert sorted(p.name for p in (server / "mods").iterdir()) == ["sodium-0.5.jar"]
            assert (server / "mods" / "sodium-0.5.jar").read_text() == "old"
            assert (server / "server.properties").read_text(encoding="utf-8") == "motd=§aHello"
            assert snapshot.exists()  # rollback must not destroy the snapshot itself
