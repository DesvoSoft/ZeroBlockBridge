"""AppApi and its areas with a fake manager: no Tk, no network, no server."""

import ast
import concurrent.futures
import io
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest
from PIL import Image

from app.api import AppApi, NoServerJarError, ServerRunningError
from app.api.areas import ConsoleApi, JavaApi, SettingsApi, TunnelApi
from app.api.mods import ModsApi
from app.api.storage import StorageApi, open_in_file_manager
from app.core.provisioning import ProvisionResult
from app.core.server_events import EventBus, ServerEvent
from app.services import mod_icons
from app.services.server_paths import UnsafePathError

ROOT = Path(__file__).resolve().parent.parent


class FakeManager:
    def __init__(self, running=False, current=None):
        self.running = running
        self.current_server = current
        self.players = object()
        self.selected = []
        self.calls = []
        self.server_runner = None
        self.playit_manager = None

    def is_running(self):
        return self.running

    def select_server(self, name):
        self.selected.append(name)
        self.current_server = name

    def start_server(self):
        self.calls.append(("start", self.current_server))
        return True

    def stop_server(self):
        self.calls.append(("stop",))

    def send_command(self, cmd):
        self.calls.append(("cmd", cmd))

    def server_memory_usage(self):
        return 1024 if self.running else None

    def load_server_manually(self, folder):
        self.calls.append(("import", folder))
        return True

    def provision_server(self, config, progress, cancel_event):
        progress(0.5, "half")
        return ProvisionResult(ok=True, name=config["name"])

    def create_pre_update_snapshot(self, name):
        return Path("snap.zip"), None

    def delete_backup(self, name, path):
        return True, None

    def bootstrap(self):
        self.calls.append(("bootstrap",))

    def shutdown(self):
        self.calls.append(("shutdown",))


@pytest.fixture
def servers_dir(tmp_path):
    root = tmp_path / "servers"
    with patch("app.api.servers.SERVERS_DIR", str(root)), \
            patch("app.api.storage.SERVERS_DIR", str(root)), \
            patch("app.core.logic.SERVERS_DIR", str(root)):
        yield root


def make_api(manager=None, **kw):
    executor = concurrent.futures.ThreadPoolExecutor(max_workers=2)
    api = AppApi(EventBus(), manager or FakeManager(), executor=executor,
                 mods=kw.pop("mods", MagicMock()), java=kw.pop("java", MagicMock()),
                 settings=kw.pop("settings", MagicMock()), **kw)
    return api, executor


class TestServers:
    def test_valid_name_lets_the_ui_ask_again_instead_of_crashing(self):
        api, _ = make_api()
        assert api.servers.valid_name("Survival 2")
        assert not api.servers.valid_name("a/b")
        assert not api.servers.valid_name("x.")

    def test_list_creates_the_folder_and_lists_only_folders(self, servers_dir):
        api, _ = make_api()
        assert api.servers.list() == []
        (servers_dir / "alpha").mkdir()
        (servers_dir / "stray.txt").write_text("x", encoding="utf-8")
        assert api.servers.list() == ["alpha"]
        assert api.servers.exists("alpha") and not api.servers.exists("beta")

    def test_info_reads_metadata_and_properties(self, servers_dir):
        api, _ = make_api()
        with patch("app.core.logic.get_server_meta", return_value={"type": "Fabric", "version": "1.21"}), \
                patch("app.api.servers.load_server_properties", return_value={"max-players": "8"}):
            info = api.servers.info("alpha")
        assert (info.engine, info.mc_version, info.loader, info.max_players) == ("Fabric", "1.21", "fabric", 8)
        assert info.mod_context == ("alpha", "1.21", "fabric")

    def test_info_defaults_match_the_old_screens(self, servers_dir):
        api, _ = make_api()
        with patch("app.core.logic.get_server_meta", return_value={}), \
                patch("app.api.servers.load_server_properties", return_value={"max-players": "lots"}):
            info = api.servers.info("alpha")
        assert info.engine is None and info.mc_version is None and info.max_players is None
        assert info.mod_context == ("alpha", "1.20.1", None)  # vanilla: no loader

    def test_select_and_start(self, servers_dir):
        manager = FakeManager()
        api, _ = make_api(manager)
        assert api.servers.select("alpha") is True
        assert api.servers.start("beta") is True
        assert manager.calls == [("start", "beta")]
        assert api.servers.active == "beta"

    def test_nothing_changes_while_a_server_runs(self, servers_dir):
        manager = FakeManager(running=True, current="alpha")
        api, _ = make_api(manager)
        assert api.servers.select("beta") is False
        assert api.servers.start("beta") is False
        assert manager.selected == [] and manager.calls == []
        assert api.servers.running_server() == "alpha"

    def test_delete_refuses_the_running_server(self, servers_dir):
        (servers_dir / "alpha").mkdir(parents=True)
        api, _ = make_api(FakeManager(running=True, current="alpha"))
        with pytest.raises(ServerRunningError):
            api.servers.delete("alpha")
        assert (servers_dir / "alpha").exists()

    def test_delete_removes_folder_and_clears_the_active_server(self, servers_dir):
        (servers_dir / "alpha" / "world").mkdir(parents=True)
        manager = FakeManager(current="alpha")
        api, _ = make_api(manager)
        api.servers.delete("alpha")
        assert not (servers_dir / "alpha").exists()
        assert manager.current_server is None

    @pytest.mark.parametrize("name", ["..", ".", "", "../servers", "a/b"])
    def test_delete_never_leaves_the_servers_folder(self, servers_dir, name):
        (servers_dir / "keep").mkdir(parents=True)
        api, _ = make_api()
        with pytest.raises(UnsafePathError):
            api.servers.delete(name)
        assert (servers_dir / "keep").exists()

    def test_import_folder_needs_a_jar(self, servers_dir, tmp_path):
        manager = FakeManager()
        api, _ = make_api(manager)
        empty = tmp_path / "empty"
        empty.mkdir()
        with pytest.raises(NoServerJarError):
            api.servers.import_folder(str(empty))
        (empty / "server.jar").write_bytes(b"x")
        assert api.servers.import_folder(str(empty)) is True
        assert manager.calls == [("import", str(empty))]

    def test_export_and_import_pack_delegate(self, servers_dir):
        api, _ = make_api()
        with patch("app.api.servers.migration") as migration:
            api.servers.export("alpha", "out.zbbpack")
            api.servers.import_pack("in.zbbpack", "beta")
        migration.export_server.assert_called_once_with("alpha", "out.zbbpack", progress_callback=None)
        migration.import_server.assert_called_once_with("in.zbbpack", "beta")
        with pytest.raises(UnsafePathError):
            api.servers.import_pack("in.zbbpack", "../beta")

    def test_memory_sample(self, servers_dir):
        api, _ = make_api(FakeManager(running=True, current="alpha"))
        with patch("app.core.logic.get_server_ram", return_value=4096):
            sample = api.servers.memory()
        assert (sample.used_bytes, sample.limit_mb) == (1024, 4096)
        api, _ = make_api(FakeManager())
        assert api.servers.memory().limit_mb is None

    def test_update_meta_and_mod_install_request(self, servers_dir):
        api, _ = make_api()
        got = []
        api.bus.subscribe(ServerEvent.REQUEST_MOD_INSTALL, got.append)
        with patch("app.core.logic.update_server_meta", return_value=True) as update:
            assert api.servers.update_meta("alpha", {"ram": 2048})
        update.assert_called_once_with("alpha", {"ram": 2048})
        api.servers.request_mod_install("alpha", ("fabric-api",))
        assert got == [{"missing_mod_ids": ["fabric-api"], "server_name": "alpha"}]

    def test_create_reports_progress_and_result(self, servers_dir):
        api, executor = make_api()
        progress = []
        task = api.servers.create({"name": "new"}).on_progress(lambda *a: progress.append(a))
        result = task.result(timeout=5)
        executor.shutdown(wait=True)
        assert result.ok and result.name == "new"
        assert api.servers.creations() == []

    def test_create_turns_a_crash_into_a_failed_result(self, servers_dir):
        manager = FakeManager()
        manager.provision_server = MagicMock(side_effect=RuntimeError("disk gone"))
        api, executor = make_api(manager)
        result = api.servers.create({"name": "new"}).result(timeout=5)
        executor.shutdown(wait=True)
        assert not result.ok and result.error == "disk gone" and result.name == "new"

    def test_create_passes_the_cancel_event(self, servers_dir):
        manager = FakeManager()
        seen = []

        def provision(config, progress, cancel_event):
            cancel_event.wait(timeout=5)
            seen.append(cancel_event.is_set())
            return ProvisionResult(ok=False, name="new", cancelled=True)
        manager.provision_server = provision
        api, executor = make_api(manager)
        task = api.servers.create({"name": "new"})
        api.tasks.cancel_all()
        assert task.result(timeout=5).cancelled
        executor.shutdown(wait=True)
        assert seen == [True]


class TestSmallAreas:
    def test_console_only_sends_to_a_running_server(self):
        manager = FakeManager()
        console = ConsoleApi(manager)
        assert console.send("say hi") is False
        manager.running = True
        assert console.send("") is False
        assert console.send("say hi") is True
        assert manager.calls == [("cmd", "say hi")]

    def test_tunnel(self):
        manager = MagicMock()
        manager.link_playit_manually.return_value = 1
        manager.playit_manager = SimpleNamespace(is_linked=True, running=False)
        tunnel = TunnelApi(manager)
        tunnel.start()
        tunnel.stop()
        tunnel.reset()
        assert tunnel.link("code") is True
        assert tunnel.is_linked and not tunnel.is_running
        manager.reset_tunnel.assert_called_once_with(mode="soft")
        assert not TunnelApi(SimpleNamespace(playit_manager=None)).is_linked
        assert not TunnelApi(SimpleNamespace(playit_manager=None)).is_running

    def test_java_best(self):
        found = SimpleNamespace(major=21, source="PORTABLE", version_string="21.0.4")
        java = JavaApi(lambda: SimpleNamespace(detect_all=lambda force_refresh=False: [found]))
        best = java.best()
        assert (best.major, best.portable, best.version_string) == (21, True, "21.0.4")
        assert JavaApi(lambda: SimpleNamespace(detect_all=lambda force_refresh=False: [])).best() is None

    def test_settings(self):
        store = MagicMock()
        store.get.return_value = "Dark"
        settings = SettingsApi(store)
        assert settings.get("theme", "Light") == "Dark"
        settings.set("theme", "Light")
        settings.save()
        store.set.assert_called_once_with("theme", "Light")
        store.save.assert_called_once()

    def test_backups_delegate(self):
        api, _ = make_api()
        assert api.backups.create_snapshot("alpha") == (Path("snap.zip"), None)
        assert api.backups.delete("alpha", "x.zip") == (True, None)


class TestStorage:
    @pytest.mark.parametrize("platform, command", [
        ("win32", "explorer"), ("darwin", "open"), ("linux", "xdg-open")])
    def test_one_opener_per_platform(self, tmp_path, platform, command):
        calls = []
        assert open_in_file_manager(tmp_path, platform=platform, run=lambda c, check: calls.append(c))
        assert calls == [[command, str(tmp_path)]]

    def test_missing_folder_is_not_opened_unless_created(self, tmp_path):
        calls = []
        target = tmp_path / "new"
        assert not open_in_file_manager(target, run=lambda c, check: calls.append(c))
        assert calls == []
        assert open_in_file_manager(target, create=True, run=lambda c, check: calls.append(c))
        assert target.is_dir() and len(calls) == 1

    def test_launch_failure_is_reported(self, tmp_path):
        def boom(cmd, check):
            raise FileNotFoundError(cmd[0])
        assert open_in_file_manager(tmp_path, run=boom) is False

    def test_cannot_create(self, tmp_path):
        blocker = tmp_path / "file"
        blocker.write_text("x", encoding="utf-8")
        assert open_in_file_manager(blocker / "sub", create=True, run=lambda c, check: None) is False

    def test_server_paths(self, servers_dir):
        storage = StorageApi()
        assert storage.server_dir("alpha") == servers_dir / "alpha"
        assert storage.server_dir("alpha", "backups") == servers_dir / "alpha" / "backups"
        assert storage.ensure_servers_dir() == servers_dir and servers_dir.is_dir()
        assert storage.servers_dir == servers_dir
        assert storage.data_dir and storage.logs_dir
        with pytest.raises(UnsafePathError):
            storage.server_dir("..")
        with patch("app.api.storage.open_in_file_manager", return_value=True) as opener:
            assert storage.open_folder(servers_dir)
        opener.assert_called_once_with(servers_dir, create=False)


class TestAppApi:
    def test_dispatcher_reaches_events_and_tasks(self):
        api, executor = make_api()
        queued = []
        api.set_dispatcher(queued.append)
        got = []
        api.events.subscribe(ServerEvent.READY, got.append)
        api.bus.emit(ServerEvent.READY, 1)
        task = api.servers.create({"name": "x"}).on_progress(lambda *a: got.append(a))
        task.result(timeout=5)
        executor.shutdown(wait=True)
        assert got == []
        for fn in queued:
            fn()
        assert 1 in got

    def test_lifecycle_and_orphan_kill(self):
        manager = FakeManager()
        alive, dead, stubborn = MagicMock(), MagicMock(), MagicMock()
        alive.poll.return_value = None
        dead.poll.return_value = 0
        stubborn.poll.return_value = None
        stubborn.kill.side_effect = OSError("access denied")
        manager.server_runner = SimpleNamespace(process=alive)
        manager.playit_manager = SimpleNamespace(process=stubborn)
        api, _ = make_api(manager)
        assert not hasattr(api, "legacy_manager")
        api.start_background_services()
        api.shutdown()  # the stubborn process doesn't stop the shutdown
        assert manager.calls == [("bootstrap",), ("shutdown",)]
        alive.kill.assert_called_once()
        dead.kill.assert_not_called()

    def test_default_construction_builds_the_real_manager(self):
        with patch("app.core.core.ZBBManager") as manager_cls:
            api = AppApi()
        manager_cls.assert_called_once_with(api.bus)
        assert isinstance(api.mods, ModsApi)


class TestModsApi:
    def test_delegates_to_the_client(self):
        client = MagicMock()
        mods = ModsApi(client_factory=lambda: client)
        mods.search("sodium", limit=5)
        mods.get_versions("sodium", mc_version="1.21", loader="fabric")
        mods.required_dependencies({"id": "v"}, "1.21", "fabric", {"x"})
        mods.check_updates("srv", "1.21", "fabric")
        client.search.assert_called_once_with("sodium", limit=5)
        client.get_versions.assert_called_once_with("sodium", mc_version="1.21", loader="fabric")
        client.get_required_dependencies.assert_called_once_with({"id": "v"}, "1.21", "fabric", {"x"})
        client.check_updates.assert_called_once_with("srv", "1.21", "fabric")
        assert mods.client is client  # created once

    def test_apply_updates_snapshots_first(self):
        client, order = MagicMock(), []
        client.apply_update.side_effect = lambda u, s, l: order.append(("apply", u["filename"])) or True

        def snapshot(name):
            order.append(("snapshot", name))
            return Path("s.zip"), None
        mods = ModsApi(client_factory=lambda: client, create_snapshot=snapshot)
        seen = []
        assert mods.apply_updates("srv", "fabric", [{"filename": "a.jar"}], on_update=seen.append) == (None, 1, 0)
        assert order == [("snapshot", "srv"), ("apply", "a.jar")]
        assert seen == [{"filename": "a.jar"}]

    def test_without_a_snapshot_nothing_is_updated(self):
        client = MagicMock()
        error, updated, _ = ModsApi(client_factory=lambda: client).apply_updates("srv", "fabric", [{"filename": "a"}])
        assert error and updated == 0
        client.apply_update.assert_not_called()

    def test_file_operations_delegate_to_the_service(self):
        mods = ModsApi(client_factory=MagicMock)
        with patch("app.api.mods.mod_content") as content, patch("app.api.mods.mod_install_tracker") as tracker:
            mods.installed_files("srv")
            mods.installed_slugs("srv")
            mods.installed_filename("srv", "x")
            mods.uninstall("srv", "x")
            mods.delete_files("srv", ["p"])
            mods.install_version({"id": 1}, "srv", "fabric", "x")
            mods.install_latest("x", "srv", "1.21", "fabric")
            mods.install_modpack({"id": 1}, "srv")
        content.installed_jar_files.assert_called_once_with("srv")
        content.uninstall.assert_called_once_with("srv", "x")
        content.delete_content_files.assert_called_once_with("srv", ["p"])
        assert content.install_version.called and content.install_latest.called and content.install_modpack.called
        tracker.get_installed_slugs.assert_called_once_with("srv")
        tracker.get_installed_filename.assert_called_once_with("srv", "x")


class TestModsApiDeleteFile:
    """Regression: a single delete must report the slug it forgot, or the
    browser keeps showing the mod as installed (and Uninstall does nothing)."""

    def test_returns_the_forgotten_slug(self, tmp_path):
        root = tmp_path / "servers"
        mods_dir = root / "srv" / "mods"
        mods_dir.mkdir(parents=True)
        (mods_dir / "sodium.jar").write_bytes(b"x")
        (mods_dir / "manual.jar").write_bytes(b"x")
        with patch("app.services.mod_content.SERVERS_DIR", str(root)),                 patch("app.services.mod_install_tracker.SERVERS_DIR", str(root)):
            from app.services import mod_install_tracker
            mod_install_tracker.record_install("srv", "sodium", "sodium.jar")
            assert ModsApi.delete_file("srv", str(mods_dir / "sodium.jar")) == "sodium"
            assert ModsApi.delete_file("srv", str(mods_dir / "manual.jar")) is None
            assert mod_install_tracker.get_installed_slugs("srv") == set()
            with pytest.raises(UnsafePathError):
                ModsApi.delete_file("srv", str(root / "srv" / "server.properties"))
        assert not list(mods_dir.iterdir())


def _png_bytes():
    buf = io.BytesIO()
    Image.new("RGBA", (128, 128), (255, 0, 0, 255)).save(buf, "PNG")
    return buf.getvalue()


class TestIcons:
    def test_downloads_scales_and_caches(self, tmp_path):
        session = MagicMock()
        session.get.return_value = SimpleNamespace(content=_png_bytes(), raise_for_status=lambda: None)
        with patch("app.services.mod_icons.BASE_DIR", tmp_path):
            mods = ModsApi(client_factory=lambda: SimpleNamespace(session=session))
            img = mods.fetch_icon("https://cdn.modrinth.com/a.png")
            assert img.size == (48, 48)
            again = mods.fetch_icon("https://cdn.modrinth.com/a.png")
            assert again.size == (48, 48)
            assert ModsApi.cached_icon("https://cdn.modrinth.com/a.png") is not None
        session.get.assert_called_once()  # the second came from disk

    def test_only_web_urls_are_fetched(self):
        session = MagicMock()
        assert mod_icons.fetch_icon("file:///C:/secret.png", session) is None
        session.get.assert_not_called()

    def test_unreadable_cache_entry_is_ignored(self, tmp_path):
        with patch("app.services.mod_icons.BASE_DIR", tmp_path):
            path = mod_icons.icon_disk_path("https://x/y.png")
            path.parent.mkdir(parents=True)
            path.write_bytes(b"not a png")
            assert mod_icons.cached_icon("https://x/y.png") is None

    def test_cache_write_failure_still_returns_the_icon(self, tmp_path):
        session = MagicMock()
        session.get.return_value = SimpleNamespace(content=_png_bytes(), raise_for_status=lambda: None)
        blocker = tmp_path / "file"
        blocker.write_text("x", encoding="utf-8")
        with patch("app.services.mod_icons.BASE_DIR", blocker):
            assert mod_icons.fetch_icon("https://x/z.png", session).size == (48, 48)


def _imports(path: Path) -> set:
    names = set()
    for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
        if isinstance(node, ast.Import):
            names.update(a.name for a in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            names.add(node.module)
            names.update(f"{node.module}.{a.name}" for a in node.names)
    return names


class TestBoundaries:
    def test_api_never_imports_a_gui_toolkit_or_the_ui(self):
        for path in (ROOT / "app" / "api").glob("*.py"):
            bad = {n for n in _imports(path)
                   if n.split(".")[0] in ("tkinter", "customtkinter", "PySide6", "pystray")
                   or n.startswith("app.ui")}
            assert not bad, f"{path.name} imports {bad}"

    # Presentation-only core modules a screen may use: UI tokens, translation,
    # bundled assets, Tk callback logging.
    ALLOWED_CORE = {"app.core.app_config", "app.core.i18n", "app.core.resources", "app.core.logging_setup"}
    SCREENS = ["main.py", "modrinth_browser.py", "players_panel.py", "app_settings.py",
               "server_wizard.py", "server_properties_editor.py"]

    @pytest.mark.parametrize("screen", SCREENS)
    def test_screens_reach_the_core_only_through_the_api(self, screen):
        """Every app.core / app.services import outside the allowed presentation
        modules is a leak. main() (startup glue before any window or API
        exists) is the one documented exception."""
        names = _screen_imports(ROOT / "app" / "ui" / screen)
        leaks = {n for n in names if n.startswith(("app.core", "app.services"))
                 and not any(n == a or n.startswith(a + ".") for a in self.ALLOWED_CORE)
                 and n != "app.core"}
        assert not leaks, f"{screen} imports {sorted(leaks)}"
        # `from app.core import i18n` names the package: only i18n is allowed from it.
        assert names & {"app.core." + x for x in ("logic", "core", "constants", "players")} == set()
        assert not names & {"subprocess", "shutil", "requests", "psutil"}
        source = (ROOT / "app" / "ui" / screen).read_text(encoding="utf-8")
        assert "os.remove(" not in source and "os.makedirs(" not in source


def _screen_imports(path: Path) -> set:
    """Imports of a screen module, leaving out its module-level main()."""
    tree = ast.parse(path.read_text(encoding="utf-8"))
    tree.body = [n for n in tree.body if not (isinstance(n, ast.FunctionDef) and n.name == "main")]
    names = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names.update(a.name for a in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            names.add(node.module)
            names.update(f"{node.module}.{a.name}" for a in node.names)
    return names
