from unittest.mock import patch

from app.services import mod_install_tracker


def _with_servers_dir(tmp_path):
    return patch("app.services.mod_install_tracker.SERVERS_DIR", str(tmp_path))


class TestRemoveInstallByFilename:
    def test_removes_matching_entry(self, tmp_path):
        with _with_servers_dir(tmp_path):
            mod_install_tracker.record_install("TestServer", "sodium", "sodium-0.5.jar")
            mod_install_tracker.record_install("TestServer", "lithium", "lithium-0.11.jar")

            mod_install_tracker.remove_install_by_filename("TestServer", "sodium-0.5.jar")

            slugs = mod_install_tracker.get_installed_slugs("TestServer")
            assert slugs == {"lithium"}

    def test_filename_not_found_is_noop(self, tmp_path):
        with _with_servers_dir(tmp_path):
            mod_install_tracker.record_install("TestServer", "sodium", "sodium-0.5.jar")

            mod_install_tracker.remove_install_by_filename("TestServer", "does-not-exist.jar")

            slugs = mod_install_tracker.get_installed_slugs("TestServer")
            assert slugs == {"sodium"}

    def test_noop_when_no_metadata_file(self, tmp_path):
        with _with_servers_dir(tmp_path):
            mod_install_tracker.remove_install_by_filename("TestServer", "sodium-0.5.jar")

            assert mod_install_tracker.get_installed_slugs("TestServer") == set()
