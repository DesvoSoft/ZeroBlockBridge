"""API areas added for the players panel, Settings, wizard and properties
editor (8b part B): fakes only, no Tk, no network."""

from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest
from PIL import Image

from app.api.areas import BackupsApi, JavaApi, SettingsApi, TunnelApi
from app.api.creation import CreationApi
from app.api.events import direct
from app.api.players import PlayersApi
from app.api.property_catalog import (IMPACT_LABELS, SETTINGS_METADATA, TAB_LAYOUTS, property_control,
                                      property_label)
from app.api.server_config import LaunchSettings, ServerConfigApi
from app.api.storage import StorageApi
from app.services.server_paths import UnsafePathError


class TestPlayers:
    def test_snapshot_reads_everything_the_panel_shows(self):
        orch = MagicMock()
        orch.roster.return_value = [{"name": "Steve"}]
        orch.online_mode.return_value = False
        orch.whitelist_enabled.return_value = True
        orch.is_live.return_value = True
        orch.default_op_level.return_value = 2
        snap = PlayersApi(orch).snapshot("srv")
        assert (snap.roster, snap.online_mode, snap.whitelist_enabled, snap.live, snap.default_op_level) == \
            ([{"name": "Steve"}], False, True, True, 2)

    @pytest.mark.parametrize("method, args", [
        ("set_whitelist_enabled", (True,)), ("whitelist_add", ("Alex",)), ("whitelist_remove", ("Alex",)),
        ("op", ("Alex", 3)), ("deop", ("Alex",)), ("ban", ("Alex", "griefing")), ("pardon", ("Alex",)),
        ("kick", ("Alex", "afk")),
    ])
    def test_actions_delegate(self, method, args):
        orch = MagicMock()
        getattr(orch, method).return_value = "result"
        assert getattr(PlayersApi(orch), method)("srv", *args) == "result"
        getattr(orch, method).assert_called_once_with("srv", *args)

    def test_head_image_scaled_with_nearest_neighbour(self, tmp_path):
        png = tmp_path / "head.png"
        img = Image.new("RGBA", (8, 8), (0, 0, 0, 255))
        img.putpixel((0, 0), (255, 0, 0, 255))
        img.save(png)
        with patch("app.api.players.fetch_head", return_value=png):
            head = PlayersApi.head_image("uuid", 32)
        assert head.size == (32, 32)
        assert head.getpixel((3, 3)) == (255, 0, 0, 255)  # a 4x4 block, not blurred

    def test_no_or_unreadable_head(self, tmp_path):
        with patch("app.api.players.fetch_head", return_value=None):
            assert PlayersApi.head_image("uuid", 32) is None
        bad = tmp_path / "bad.png"
        bad.write_bytes(b"nope")
        with patch("app.api.players.fetch_head", return_value=bad):
            assert PlayersApi.head_image("uuid", 32) is None


class TestBackups:
    def _api(self):
        bm, sched = MagicMock(), MagicMock()
        bm.list_backups.return_value = [{"path": "a.zip"}]
        bm.create_backup.return_value = ("b.zip", None)
        bm.restore_backup.return_value = 1
        bm.backup_dir = "C:/data/backups/srv"
        sched.get_config.return_value = {"enabled": True}
        sched.seconds_until_next.return_value = 60.0
        manager = MagicMock()
        api = BackupsApi(manager, manager_factory=lambda name: bm, scheduler_factory=lambda name: sched)
        return api, bm, sched, manager

    def test_one_servers_backups(self):
        api, bm, sched, manager = self._api()
        assert api.list("srv") == [{"path": "a.zip"}]
        assert api.create("srv") == ("b.zip", None)
        assert api.restore("srv", "a.zip") is True
        bm.restore_backup.assert_called_once_with("a.zip")
        assert api.folder("srv") == Path("C:/data/backups/srv")
        api.delete("srv", "a.zip")
        manager.delete_backup.assert_called_once_with("srv", "a.zip")

    def test_auto_backup_schedule(self):
        api, _, sched, _ = self._api()
        assert api.auto_config("srv") == {"enabled": True}
        api.set_auto_config("srv", False, 12, 5)
        sched.set_config.assert_called_once_with(False, interval_hours=12, retention_count=5)
        assert api.seconds_until_auto("srv") == 60.0

    @pytest.mark.parametrize("call", ["list", "create", "folder", "auto_config", "seconds_until_auto"])
    def test_refuses_names_that_are_paths(self, call):
        api, bm, _, _ = self._api()
        with pytest.raises(UnsafePathError):
            getattr(api, call)("../other")


class TestJavaAndSettings:
    def test_installations_and_required(self):
        calls = []
        java = JavaApi(lambda: SimpleNamespace(detect_all=lambda force_refresh=False: calls.append(force_refresh) or []))
        assert java.installations(force_refresh=True) == []
        assert calls == [True]
        assert JavaApi.required("1.21.1") == 21
        assert JavaApi.required("1.16.5") == 8

    def test_managed_runtimes(self):
        manager = MagicMock()
        manager.list_managed_jdks.return_value = [{"version": 21, "size_bytes": 1}]
        manager.purge_jdk.return_value = 0
        manager.purge_unused_jdks.return_value = 1
        java = JavaApi(manager=manager)
        assert java.managed() == [{"version": 21, "size_bytes": 1}]
        assert java.purge(21) is False
        assert java.purge_unused() is True

    def test_language_is_saved_in_both_places(self, tmp_path):
        store = MagicMock()
        with patch("app.api.areas.remember_language") as remember, patch("app.api.areas.BASE_DIR", tmp_path):
            SettingsApi(store).set_language("es")
        store.set.assert_called_once_with("language", "es")
        remember.assert_called_once_with("es", tmp_path)

    def test_notifications(self):
        manager = MagicMock()
        SettingsApi(MagicMock(), manager=manager).reload_notifications()
        manager.reload_discord_webhook.assert_called_once()
        with patch("app.api.areas.DiscordWebhookService.send_test", return_value=(True, "")) as send:
            assert SettingsApi.send_test_notification("https://x", "ZBB", "") == (True, "")
        send.assert_called_once_with("https://x", username="ZBB", avatar_url="", language="auto")

    def test_default_store_is_the_settings_singleton(self):
        with patch("app.api.areas.SettingsManager") as sm:
            sm.return_value.get.return_value = "Light"
            assert SettingsApi().get("theme") == "Light"

    def test_tunnel_status_debounce(self):
        with patch("app.api.areas.statemanager.schedule_update", return_value=False) as debounce:
            assert TunnelApi.status_changed({"status": "Online"}) is False
        debounce.assert_called_once_with({"status": "Online"})


class TestStorage:
    def test_usage_by_category(self, tmp_path):
        servers = tmp_path / "servers"
        (servers / "a" / "crash_reports").mkdir(parents=True)
        (servers / "a" / "crash_reports" / "c.json").write_bytes(b"x" * 10)
        (servers / "a" / "world.dat").write_bytes(b"x" * 5)
        (tmp_path / "backups").mkdir()
        (tmp_path / "backups" / "b.zip").write_bytes(b"x" * 7)
        versions = tmp_path / "versions_cache.json"
        versions.write_bytes(b"x" * 3)
        with patch("app.api.storage.SERVERS_DIR", servers), patch("app.api.storage.BASE_DIR", tmp_path), \
                patch("app.api.storage.JDK_CACHE_DIR", tmp_path / "jdks"), \
                patch("app.api.storage.LOGS_DIR", tmp_path / "logs"), \
                patch("app.api.storage.VERSIONS_CACHE_FILE", versions):
            usage = dict(StorageApi.usage())
        assert usage == {"servers": 15, "backups": 7, "java": 0, "crash_reports": 10, "logs": 0,
                         "versions_cache": 3}

    def test_usage_without_any_data(self, tmp_path):
        with patch("app.api.storage.SERVERS_DIR", tmp_path / "none"), patch("app.api.storage.BASE_DIR", tmp_path), \
                patch("app.api.storage.VERSIONS_CACHE_FILE", tmp_path / "none.json"):
            assert dict(StorageApi.usage())["versions_cache"] == 0

    def test_crash_reports_and_shortcuts(self):
        manager = MagicMock()
        manager.purge_crash_reports.return_value = 2
        assert StorageApi(manager).purge_crash_reports() == 2
        with patch("app.api.storage.installer.add_shortcuts", return_value=[]) as add:
            assert StorageApi.add_shortcuts(Path("zbb.exe"), desktop=True) == []
        add.assert_called_once_with(Path("zbb.exe"), start_menu=False, desktop=True)

    @pytest.mark.parametrize("marker, flag, portable, installed", [
        ({"mode": "installed", "exe_path": "C:/Programs/zbb.exe"}, False, False, "C:/Programs/zbb.exe"),
        ({"mode": "manual"}, False, False, None),
        ({}, True, True, None),
    ])
    def test_install_info(self, tmp_path, marker, flag, portable, installed):
        exe = tmp_path / "ZeroBlockBridge.exe"
        exe.write_bytes(b"")
        if flag:
            (tmp_path / "ZeroBlockBridge-portable.txt").write_text("", encoding="utf-8")
        with patch("app.api.storage.bootstrap.read_marker", return_value=marker):
            info = StorageApi.install_info(exe)
        assert (info.portable, info.installed_at) == (portable, installed)
        assert info.shortcut_target == (Path(installed) if installed else exe.resolve())


class TestServerConfig:
    def test_properties_worlds_ram_icon(self):
        config = ServerConfigApi()
        with patch("app.api.server_config.server_properties") as props, \
                patch("app.api.server_config.logic") as logic:
            props.load_server_properties.return_value = {"motd": "hi"}
            props.list_worlds.return_value = ["world"]
            logic.get_server_ram.return_value = 4096
            logic.save_server_icon.return_value = True
            logic.get_server_meta.return_value = None
            assert config.properties("srv") == {"motd": "hi"}
            config.save_properties("srv", {"motd": "yo"})
            assert config.worlds("srv") == ["world"]
            assert config.ram_mb("srv") == 4096
            config.set_ram_mb("srv", 2048)
            assert config.set_icon("srv", "icon.png") is True
            assert config.meta("srv") == {}
        props.save_server_properties.assert_called_once_with("srv", new_properties={"motd": "yo"})
        logic.set_server_ram.assert_called_once_with("srv", 2048)

    def test_launch_settings_round_trip(self, tmp_path):
        (tmp_path / "srv").mkdir()
        (tmp_path / "srv" / "metadata.json").write_text("{}", encoding="utf-8")
        config = ServerConfigApi()
        with patch("app.api.server_config.SERVERS_DIR", tmp_path), \
                patch("app.api.server_config.logic") as logic:
            logic.get_server_meta.return_value = {"java_path": "C:/java.exe", "use_aikars": False}
            assert config.launch_settings("srv") == LaunchSettings("C:/java.exe", False, "")
            logic.update_server_meta.return_value = True
            assert config.save_launch_settings("srv", LaunchSettings("auto", True, "  -Dx=1 "))
            assert not config.save_launch_settings("missing", LaunchSettings("auto", True, ""))
        logic.update_server_meta.assert_called_once_with(
            "srv", {"java_path": "auto", "use_aikars": True, "jvm_custom_flags": "-Dx=1"})

    def test_restart_schedule(self):
        with patch("app.api.server_config.logic.Scheduler") as scheduler:
            scheduler.return_value.get_schedule.return_value = {"type": "time"}
            assert ServerConfigApi.restart_schedule("srv") == {"type": "time"}
            ServerConfigApi.set_restart_schedule("srv", True, restart_time="03:00", backup_on_restart=True)
        scheduler.return_value.set_restart_schedule.assert_called_once_with(
            True, interval_hours=None, restart_time="03:00", backup_on_restart=True)

    def test_modpack_import_uses_the_servers_engine(self):
        config = ServerConfigApi()
        with patch("app.api.server_config.logic.get_server_meta", return_value={"type": "Fabric", "version": "1.21"}), \
                patch("app.api.server_config.install_mrpack", return_value={"installed": 2}) as install:
            assert config.import_modpack("srv", "pack.mrpack", on_status=print) == {"installed": 2}
        install.assert_called_once_with(mrpack_path="pack.mrpack", server_name="srv", progress_callback=print,
                                        server_type="Fabric", mc_version="1.21")

    @pytest.mark.parametrize("call, args", [
        ("properties", ()), ("worlds", ()), ("ram_mb", ()), ("set_icon", ("x.png",)), ("meta", ()),
        ("restart_schedule", ()),
    ])
    def test_refuses_names_that_are_paths(self, call, args):
        with pytest.raises(UnsafePathError):
            getattr(ServerConfigApi(), call)("..", *args)


class FakeVersions:
    def __init__(self):
        self.callbacks = []
        self.refreshed = 0

    def add_callback(self, cb):
        self.callbacks.append(cb)

    def remove_callback(self, cb):
        self.callbacks.remove(cb)

    def get_versions(self, engine):
        return ["1.21.1", "1.20.4"] if engine == "Paper" else []

    def refresh_versions(self):
        self.refreshed += 1
        for cb in list(self.callbacks):
            cb()


class TestCreation:
    def test_versions_and_refresh_reach_the_listener_through_the_dispatcher(self):
        versions, queue, got = FakeVersions(), [], []
        creation = CreationApi(lambda: queue.append, versions_factory=lambda: versions)
        creation.on_versions_refreshed(lambda: got.append("refreshed"))
        assert creation.versions("Paper") == ["1.21.1", "1.20.4"]
        creation.refresh_versions()
        assert got == [] and len(queue) == 1
        queue.pop()()
        assert got == ["refreshed"]

    def test_cancelled_listener_drops_queued_and_later_calls(self):
        versions, queue, got = FakeVersions(), [], []
        creation = CreationApi(lambda: queue.append, versions_factory=lambda: versions)
        listener = creation.on_versions_refreshed(lambda: got.append(1))
        versions.refresh_versions()
        listener.cancel()
        versions.refresh_versions()
        for fn in queue:
            fn()
        assert got == [] and versions.callbacks == [] and not listener.active

    def test_defaults(self, tmp_path):
        with patch("app.api.creation.SERVERS_DIR", tmp_path):
            assert CreationApi.default_location() == str(tmp_path)
        defaults = CreationApi.property_defaults()
        defaults["game_mode"] = "changed"
        assert CreationApi.property_defaults()["game_mode"] != "changed"  # a copy
        assert CreationApi.system_ram_mb() > 0

    def test_templates_and_content_delegate(self):
        with patch("app.api.creation.template_manager") as tm, patch("app.api.creation.content_import") as ci:
            tm.list_templates.return_value = [{"name": "survival"}]
            assert CreationApi.templates() == [{"name": "survival"}]
            CreationApi.load_template("survival")
            CreationApi.normalize_template_name("My Template")
            CreationApi.template_exists("survival")
            CreationApi.save_template("survival", {"ram": 2048})
            CreationApi.inspect_modpack("p.mrpack")
            CreationApi.inspect_world("w.zip")
            CreationApi.world_version_check("world", "1.21")
        tm.save_template.assert_called_once_with("survival", {"ram": 2048})
        ci.inspect_modpack.assert_called_once_with("p.mrpack")
        ci.inspect_world.assert_called_once_with("w.zip")
        ci.world_version_check.assert_called_once_with("world", "1.21")

    def test_direct_dispatcher_runs_at_once(self):
        versions, got = FakeVersions(), []
        CreationApi(lambda: direct, versions_factory=lambda: versions).on_versions_refreshed(lambda: got.append(1))
        versions.refresh_versions()
        assert got == [1]


def _old_control(key):
    """The editor's rule before it moved into the catalog (8b part B)."""
    boolean_overrides = {
        "pvp", "allow-flight", "allow-nether", "hide-online-players", "log-ips",
        "broadcast-console-to-ops", "broadcast-rcon-to-ops", "require-resource-pack",
        "generate-structures", "sync-chunk-writes", "prevent-proxy-connections",
    }
    if key in boolean_overrides:
        return "checkbox", None
    if any(x in key for x in ["enable", "spawn-npcs", "spawn-animals", "spawn-monsters", "white-list",
                               "hardcore", "enforce", "online"]):
        return "checkbox", None
    options = {"gamemode": ["survival", "creative", "adventure", "spectator"],
               "difficulty": ["peaceful", "easy", "normal", "hard"],
               "level-type": ["minecraft:normal", "minecraft:flat", "minecraft:large_biomes"],
               "op-permission-level": ["1", "2", "3", "4"], "function-permission-level": ["1", "2", "3", "4"]}
    if key in options:
        return "dropdown", options[key]
    return "entry", None


class TestPropertyCatalog:
    @pytest.mark.parametrize("key", sorted(set(SETTINGS_METADATA) | {
        k for sections in TAB_LAYOUTS.values() for keys in sections.values() for k in keys}))
    def test_control_kind_is_unchanged(self, key):
        assert property_control(key) == _old_control(key)

    def test_options_are_copies(self):
        _, options = property_control("gamemode")
        options.append("hacked")
        assert "hacked" not in property_control("gamemode")[1]

    def test_every_impact_has_a_label_and_every_laid_out_key_a_description(self):
        assert {m["impact"] for m in SETTINGS_METADATA.values()} <= set(IMPACT_LABELS)
        for sections in TAB_LAYOUTS.values():
            for keys in sections.values():
                for key in keys:
                    assert SETTINGS_METADATA[key]["desc"]
                    assert property_label(key)


class TestAreasWithoutManager:
    """Review nit: an area built without the manager failed with
    AttributeError on None; it now says what is missing."""

    @pytest.mark.parametrize("call", [
        lambda: JavaApi().managed(), lambda: JavaApi().purge(21), lambda: JavaApi().purge_unused(),
        lambda: SettingsApi(MagicMock()).reload_notifications(), lambda: StorageApi().purge_crash_reports(),
    ])
    def test_clear_error(self, call):
        with pytest.raises(RuntimeError, match="needs the ZBBManager"):
            call()

    def test_snapshot_fields_by_name(self):
        orch = MagicMock()
        orch.online_mode.return_value, orch.whitelist_enabled.return_value = True, False
        snap = PlayersApi(orch).snapshot("srv")
        assert snap.online_mode is True and snap.whitelist_enabled is False
