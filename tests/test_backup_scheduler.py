import datetime
import json
from unittest.mock import patch
from app.core.logic import BackupScheduler


class TestBackupScheduler:
    def test_defaults_disabled(self):
        with patch("app.core.logic.get_server_meta", return_value={}):
            sched = BackupScheduler("test_server")
            config = sched.get_config()
            assert config["enabled"] is False
            assert config["interval_hours"] == 4
            assert config["retention_count"] == 10
            assert config["last_run"] is None

    def test_loads_persisted_config(self):
        persisted = {"auto_backup": {"enabled": True, "interval_hours": 6, "retention_count": 5, "last_run": "2025-01-01T00:00:00"}}
        with patch("app.core.logic.get_server_meta", return_value=persisted):
            sched = BackupScheduler("test_server")
            config = sched.get_config()
            assert config["enabled"] is True
            assert config["interval_hours"] == 6
            assert config["retention_count"] == 5

    def test_is_due_when_no_last_run(self):
        with patch("app.core.logic.get_server_meta", return_value={"auto_backup": {"enabled": True}}):
            sched = BackupScheduler("test_server")
            assert sched.is_due() is True

    def test_is_due_when_elapsed(self):
        past = (datetime.datetime.now() - datetime.timedelta(hours=5)).isoformat()
        persisted = {"auto_backup": {"enabled": True, "interval_hours": 4, "retention_count": 10, "last_run": past}}
        with patch("app.core.logic.get_server_meta", return_value=persisted):
            sched = BackupScheduler("test_server")
            assert sched.is_due() is True

    def test_not_due_when_recent(self):
        recent = datetime.datetime.now().isoformat()
        persisted = {"auto_backup": {"enabled": True, "interval_hours": 24, "retention_count": 10, "last_run": recent}}
        with patch("app.core.logic.get_server_meta", return_value=persisted):
            sched = BackupScheduler("test_server")
            assert sched.is_due() is False

    def test_not_due_when_disabled(self):
        with patch("app.core.logic.get_server_meta", return_value={}):
            sched = BackupScheduler("test_server")
            assert sched.is_due() is False

    def test_mark_run_updates_last_run(self):
        persisted = {"auto_backup": {"enabled": True, "interval_hours": 4, "retention_count": 10, "last_run": None}}
        with patch("app.core.logic.get_server_meta", return_value=persisted) as mock_get:
            with patch("app.core.logic.update_server_meta") as mock_update:
                sched = BackupScheduler("test_server")
                sched.mark_run()
                assert mock_update.called
                saved = mock_update.call_args[0][1]["auto_backup"]
                assert saved["last_run"] is not None

    def test_set_config_enables(self):
        with patch("app.core.logic.get_server_meta", return_value={}):
            with patch("app.core.logic.update_server_meta", return_value=True) as mock_update:
                sched = BackupScheduler("test_server")
                sched.set_config(enabled=True, interval_hours=8, retention_count=3)
                saved = mock_update.call_args[0][1]["auto_backup"]
                assert saved["enabled"] is True
                assert saved["interval_hours"] == 8
                assert saved["retention_count"] == 3

    def test_set_config_disables(self):
        with patch("app.core.logic.get_server_meta", return_value={}):
            with patch("app.core.logic.update_server_meta", return_value=True) as mock_update:
                sched = BackupScheduler("test_server")
                sched.set_config(enabled=False)
                saved = mock_update.call_args[0][1]["auto_backup"]
                assert saved["enabled"] is False

    def test_seconds_until_next(self):
        past = (datetime.datetime.now() - datetime.timedelta(hours=2)).isoformat()
        persisted = {"auto_backup": {"enabled": True, "interval_hours": 4, "retention_count": 10, "last_run": past}}
        with patch("app.core.logic.get_server_meta", return_value=persisted):
            sched = BackupScheduler("test_server")
            secs = sched.seconds_until_next()
            assert secs is not None
            assert secs > 0
            assert secs < 4 * 3600

    def test_seconds_until_next_disabled(self):
        with patch("app.core.logic.get_server_meta", return_value={}):
            sched = BackupScheduler("test_server")
            assert sched.seconds_until_next() is None
