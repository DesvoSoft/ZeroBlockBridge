"""Mod/plugin file operations moved out of the Modrinth browser
(app/services/mod_content.py): the delete guard above all."""

import os
import subprocess
from unittest.mock import MagicMock, patch

import pytest

from app.core.fs_links import create_junction
from app.services import mod_content, mod_install_tracker
from app.services.mod_content import ModDownloadError, NoCompatibleVersionError, UnsafePathError
from app.services.server_paths import check_server_name


@pytest.fixture
def servers(tmp_path):
    root = tmp_path / "servers"
    root.mkdir()
    with patch("app.services.mod_content.SERVERS_DIR", str(root)), \
            patch("app.services.mod_install_tracker.SERVERS_DIR", str(root)):
        yield root


def _jar(folder, name, content=b"jar"):
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / name
    path.write_bytes(content)
    return path


class TestServerName:
    @pytest.mark.parametrize("name", ["", " ", ".", "..", "a/b", "a\\b", "../x", "C:x", None])
    def test_rejects_anything_but_one_folder_name(self, name):
        with pytest.raises(UnsafePathError):
            check_server_name(name)

    def test_accepts_plain_names(self):
        assert check_server_name("My Server 1.20") == "My Server 1.20"


class TestResolveContentFile:
    def test_file_in_mods_or_plugins_is_allowed(self, servers):
        mod = _jar(servers / "srv" / "mods", "a.jar")
        plugin = _jar(servers / "srv" / "plugins", "p.jar")
        assert mod_content.resolve_content_file("srv", str(mod)) == os.path.abspath(mod)
        assert mod_content.resolve_content_file("srv", str(plugin)) == os.path.abspath(plugin)

    @pytest.mark.parametrize("relative", [
        "server.properties",          # the server folder itself
        "world/level.dat",            # anywhere else in it
        "mods/../server.properties",  # traversal out of mods/
        "mods/sub/a.jar",             # nested below mods/
    ])
    def test_other_places_in_the_server_are_refused(self, servers, relative):
        target = servers / "srv" / relative
        _jar(target.parent, target.name)
        (servers / "srv" / "mods").mkdir(exist_ok=True)
        with pytest.raises(UnsafePathError):
            mod_content.resolve_content_file("srv", str(servers / "srv" / relative))

    def test_another_servers_mods_are_refused(self, servers):
        other = _jar(servers / "other" / "mods", "a.jar")
        (servers / "srv" / "mods").mkdir(parents=True)
        with pytest.raises(UnsafePathError):
            mod_content.resolve_content_file("srv", str(other))

    def test_a_folder_inside_mods_is_refused(self, servers):
        (servers / "srv" / "mods" / "config").mkdir(parents=True)
        with pytest.raises(UnsafePathError):
            mod_content.resolve_content_file("srv", str(servers / "srv" / "mods" / "config"))

    def test_server_reached_through_a_link_is_allowed(self, servers, tmp_path):
        real = tmp_path / "elsewhere"
        mod = _jar(real / "mods", "a.jar")
        try:
            create_junction(str(real), str(servers / "linked"))  # how imported servers are linked
        except (OSError, subprocess.SubprocessError) as exc:
            pytest.skip(f"directory links not available: {exc}")
        linked = servers / "linked" / "mods" / "a.jar"
        assert mod_content.resolve_content_file("linked", str(linked))
        mod_content.delete_content_file("linked", str(linked))
        assert not mod.exists()


class TestDelete:
    def test_delete_removes_file_and_record(self, servers):
        mod = _jar(servers / "srv" / "mods", "sodium.jar")
        mod_install_tracker.record_install("srv", "sodium", "sodium.jar")
        assert mod_content.delete_content_file("srv", str(mod)) == "sodium.jar"
        assert not mod.exists()
        assert mod_install_tracker.get_installed_slugs("srv") == set()

    def test_delete_outside_never_touches_the_file(self, servers):
        props = _jar(servers / "srv", "server.properties")
        (servers / "srv" / "mods").mkdir()
        with pytest.raises(UnsafePathError):
            mod_content.delete_content_file("srv", str(props))
        assert props.exists()

    def test_bulk_delete_reports_each_outcome(self, servers):
        a = _jar(servers / "srv" / "mods", "a.jar")
        b = _jar(servers / "srv" / "plugins", "b.jar")
        outside = _jar(servers / "srv", "eula.txt")
        mod_install_tracker.record_install("srv", "alpha", "a.jar")
        result = mod_content.delete_content_files(
            "srv", [str(a), str(outside), str(servers / "srv" / "mods" / "gone.jar"), str(b)])
        assert result.deleted == ["a.jar", "b.jar"]
        assert [p for p, _ in result.failed] == [str(outside), str(servers / "srv" / "mods" / "gone.jar")]
        assert result.removed_slugs == {"alpha"}
        assert outside.exists()


class TestUninstall:
    def test_removes_recorded_file(self, servers):
        mod = _jar(servers / "srv" / "plugins", "lp.jar")
        mod_install_tracker.record_install("srv", "luckperms", "lp.jar")
        assert mod_content.uninstall("srv", "luckperms") == "lp.jar"
        assert not mod.exists()
        assert mod_install_tracker.get_installed_slugs("srv") == set()

    def test_unknown_slug_is_a_no_op(self, servers):
        assert mod_content.uninstall("srv", "nothing") is None

    def test_missing_file_only_drops_the_record(self, servers):
        (servers / "srv" / "mods").mkdir(parents=True)
        mod_install_tracker.record_install("srv", "sodium", "sodium.jar")
        assert mod_content.uninstall("srv", "sodium") == "sodium.jar"
        assert mod_install_tracker.get_installed_slugs("srv") == set()

    def test_tampered_record_cannot_delete_outside(self, servers):
        props = _jar(servers / "srv", "server.properties")
        (servers / "srv" / "mods").mkdir()
        mod_install_tracker.record_install("srv", "evil", "../server.properties")
        with pytest.raises(UnsafePathError):
            mod_content.uninstall("srv", "evil")
        assert props.exists()


class TestInstalledFiles:
    def test_lists_jars_of_both_folders(self, servers):
        _jar(servers / "srv" / "mods", "b.jar")
        _jar(servers / "srv" / "mods", "a.jar")
        _jar(servers / "srv" / "mods", "notes.txt")
        _jar(servers / "srv" / "plugins", "p.jar")
        files = [os.path.relpath(f, servers / "srv") for f in mod_content.installed_jar_files("srv")]
        assert files == [os.path.join("mods", "a.jar"), os.path.join("mods", "b.jar"), os.path.join("plugins", "p.jar")]

    def test_no_folders_no_files(self, servers):
        assert mod_content.installed_jar_files("srv") == []


class TestInstalls:
    def test_install_version_records_slug(self, servers):
        client = MagicMock()
        client.download_version.return_value = str(servers / "srv" / "mods" / "sodium-1.jar")
        progress = MagicMock()
        path = mod_content.install_version(client, {"id": "v"}, "srv", "fabric", "sodium", progress)
        assert path.endswith("sodium-1.jar")
        client.download_version.assert_called_once_with({"id": "v"}, "srv", "fabric", progress_callback=progress)
        assert mod_install_tracker.get_installed_filename("srv", "sodium") == "sodium-1.jar"

    def test_failed_download_records_nothing(self, servers):
        client = MagicMock()
        client.download_version.return_value = None
        assert mod_content.install_version(client, {}, "srv", "fabric", "sodium") is None
        assert mod_install_tracker.get_installed_slugs("srv") == set()

    def test_install_version_rejects_bad_server_name(self, servers):
        with pytest.raises(UnsafePathError):
            mod_content.install_version(MagicMock(), {}, "..", "fabric", "x")

    def test_install_latest(self, servers):
        client = MagicMock()
        client.get_versions.return_value = [{"id": "1"}]
        client.download_mod.return_value = "/x/lithium.jar"
        assert mod_content.install_latest(client, "lithium", "srv", "1.21", "fabric") == "/x/lithium.jar"
        assert mod_install_tracker.get_installed_filename("srv", "lithium") == "lithium.jar"

    def test_install_latest_without_a_build(self, servers):
        client = MagicMock()
        client.get_versions.return_value = []
        with pytest.raises(NoCompatibleVersionError):
            mod_content.install_latest(client, "lithium", "srv", "1.21", "fabric")
        client.download_mod.assert_not_called()

    def test_install_latest_failed_download(self, servers):
        client = MagicMock()
        client.get_versions.return_value = [{"id": "1"}]
        client.download_mod.return_value = None
        assert mod_content.install_latest(client, "lithium", "srv", "1.21", "fabric") is None
        assert mod_install_tracker.get_installed_slugs("srv") == set()


class TestInstallModpack:
    def _client(self, tmp_dirs, ok=True):
        client = MagicMock()

        def download(version, dest, progress_callback=None):
            tmp_dirs.append(dest)
            if progress_callback:
                progress_callback(1.0)
            return os.path.join(dest, "pack.mrpack") if ok else None
        client.download_version_to.side_effect = download
        return client

    def test_installs_and_removes_temp_folder(self, servers):
        tmp_dirs, statuses, progress = [], [], []
        client = self._client(tmp_dirs)
        with patch("app.services.mod_content.get_server_meta", return_value={"type": "Fabric", "version": "1.21"}), \
                patch("app.services.mod_content.install_mrpack", return_value={"installed": 3}) as inst:
            summary = mod_content.install_modpack(client, {"id": "v"}, "srv", progress.append, statuses.append)
        assert summary == {"installed": 3}
        assert progress == [1.0]
        args, kwargs = inst.call_args
        assert args == (os.path.join(tmp_dirs[0], "pack.mrpack"), "srv")
        assert kwargs["server_type"] == "Fabric" and kwargs["mc_version"] == "1.21"
        assert kwargs["progress_callback"] == statuses.append
        assert not os.path.exists(tmp_dirs[0])

    def test_failed_download_raises_and_cleans_up(self, servers):
        tmp_dirs = []
        with pytest.raises(ModDownloadError):
            mod_content.install_modpack(self._client(tmp_dirs, ok=False), {"id": "v"}, "srv")
        assert not os.path.exists(tmp_dirs[0])

    def test_install_error_still_cleans_up(self, servers):
        tmp_dirs = []
        with patch("app.services.mod_content.get_server_meta", return_value={}), \
                patch("app.services.mod_content.install_mrpack", side_effect=ValueError("bad pack")):
            with pytest.raises(ValueError):
                mod_content.install_modpack(self._client(tmp_dirs), {"id": "v"}, "srv")
        assert not os.path.exists(tmp_dirs[0])
