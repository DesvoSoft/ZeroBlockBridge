"""Tests for disk_usage helpers and F14 settings defaults."""
from app.services.disk_usage import dir_size, format_size


class TestDirSize:
    def test_missing_path_is_zero(self, tmp_path):
        assert dir_size(tmp_path / "nope") == 0

    def test_empty_dir_is_zero(self, tmp_path):
        assert dir_size(tmp_path) == 0

    def test_sums_nested_files(self, tmp_path):
        (tmp_path / "a.bin").write_bytes(b"x" * 10)
        sub = tmp_path / "sub" / "deep"
        sub.mkdir(parents=True)
        (sub / "b.bin").write_bytes(b"y" * 32)
        assert dir_size(tmp_path) == 42


class TestFormatSize:
    def test_bytes(self):
        assert format_size(0) == "0 B"
        assert format_size(512) == "512 B"

    def test_kb_mb_gb(self):
        assert format_size(2048) == "2.0 KB"
        assert format_size(5 * 1024 * 1024) == "5.0 MB"
        assert format_size(3 * 1024 ** 3) == "3.0 GB"

    def test_over_a_terabyte_stays_gb(self):
        assert format_size(2 * 1024 ** 4) == "2048.0 GB"


class TestSettingsDefaults:
    def test_dead_keys_removed_and_webhook_events_present(self):
        from app.services.discord_webhook import DEFAULT_EVENT_PREFS
        from app.services.settings_manager import SettingsManager
        defaults = SettingsManager()._get_defaults()
        assert "servers_dir" not in defaults
        assert "java_preferences" not in defaults
        assert defaults["webhook_events"] == DEFAULT_EVENT_PREFS
        # Original four events stay opt-out; newer chatty ones are opt-in.
        for key in ("crashed", "ready", "backup_completed", "backup_failed"):
            assert defaults["webhook_events"][key] is True
        for key in ("stopped", "player_joins", "lag_spike"):
            assert defaults["webhook_events"][key] is False

    def test_webhook_event_keys_match_service_map(self):
        from app.services.discord_webhook import SETTING_EVENT_KEYS
        from app.services.settings_manager import SettingsManager
        defaults = SettingsManager()._get_defaults()
        assert set(defaults["webhook_events"]) == set(SETTING_EVENT_KEYS)
