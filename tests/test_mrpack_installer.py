"""Unit tests for the .mrpack modpack installer (app/services/mrpack_installer.py)."""

import json
import zipfile

import pytest

from app.services.mrpack_installer import (
    MrpackCompatibilityError,
    _check_compatibility,
    _safe_dest,
    _validate_manifest,
    install_mrpack,
)


def _make_mrpack(path, manifest, overrides=None):
    with zipfile.ZipFile(path, "w") as zf:
        zf.writestr("modrinth.index.json", json.dumps(manifest))
        for rel, content in (overrides or {}).items():
            zf.writestr(f"overrides/{rel}", content)


def _fabric_manifest(mc_version="1.20.1", files=None):
    return {
        "formatVersion": 1,
        "game": "minecraft",
        "dependencies": {"minecraft": mc_version, "fabric-loader": "0.15.0"},
        "files": files if files is not None else [],
    }


class TestValidateManifest:
    def test_rejects_wrong_format_version(self):
        with pytest.raises(ValueError, match="format version"):
            _validate_manifest({"formatVersion": 2, "files": []})

    def test_rejects_missing_files_key(self):
        with pytest.raises(ValueError, match="files"):
            _validate_manifest({"formatVersion": 1})

    def test_accepts_valid_manifest(self):
        _validate_manifest({"formatVersion": 1, "files": []})


class TestCheckCompatibility:
    def test_matching_loader_and_version_passes(self):
        manifest = _fabric_manifest()
        _check_compatibility(manifest, server_type="Fabric", mc_version="1.20.1")

    def test_wrong_loader_raises(self):
        manifest = _fabric_manifest()
        with pytest.raises(MrpackCompatibilityError, match="Fabric server"):
            _check_compatibility(manifest, server_type="Paper", mc_version="1.20.1")

    def test_wrong_mc_version_raises(self):
        manifest = _fabric_manifest(mc_version="1.20.1")
        with pytest.raises(MrpackCompatibilityError, match="Minecraft"):
            _check_compatibility(manifest, server_type="Fabric", mc_version="1.19.4")

    def test_unsupported_engine_raises(self):
        manifest = {
            "formatVersion": 1,
            "dependencies": {"minecraft": "1.20.1", "quilt-loader": "0.20.0"},
            "files": [],
        }
        with pytest.raises(MrpackCompatibilityError, match="Quilt"):
            _check_compatibility(manifest, server_type="Quilt", mc_version="1.20.1")

    def test_no_server_type_skips_loader_check(self):
        manifest = _fabric_manifest()
        _check_compatibility(manifest, server_type=None, mc_version="1.20.1")

    def test_no_loader_dependency_skips_check(self):
        manifest = {"formatVersion": 1, "dependencies": {"minecraft": "1.20.1"}, "files": []}
        _check_compatibility(manifest, server_type="Paper", mc_version="1.20.1")


class TestSafeDest:
    def test_rejects_path_traversal(self, tmp_path):
        with pytest.raises(ValueError, match="Unsafe path"):
            _safe_dest(str(tmp_path), "../../evil.jar")

    def test_allows_nested_path(self, tmp_path):
        dest = _safe_dest(str(tmp_path), "mods/sub/ok.jar")
        assert dest.startswith(str(tmp_path))


class TestInstallMrpack:
    def test_raises_for_missing_server_dir(self, tmp_path, monkeypatch):
        monkeypatch.setattr("app.services.mrpack_installer.SERVERS_DIR", str(tmp_path))
        pack_path = tmp_path / "pack.mrpack"
        _make_mrpack(str(pack_path), _fabric_manifest())
        with pytest.raises(ValueError, match="does not exist"):
            install_mrpack(str(pack_path), "nosuchserver")

    def test_raises_compatibility_error_before_download(self, tmp_path, monkeypatch):
        monkeypatch.setattr("app.services.mrpack_installer.SERVERS_DIR", str(tmp_path))
        server_dir = tmp_path / "myserver"
        server_dir.mkdir()
        pack_path = tmp_path / "pack.mrpack"
        _make_mrpack(str(pack_path), _fabric_manifest(files=[
            {"path": "mods/foo.jar", "downloads": ["https://example.invalid/foo.jar"],
             "hashes": {"sha1": "x"}, "env": {"server": "required"}},
        ]))
        with pytest.raises(MrpackCompatibilityError):
            install_mrpack(str(pack_path), "myserver", server_type="Paper", mc_version="1.20.1")
        assert not (server_dir / "mods").exists()

    def test_skips_client_only_files(self, tmp_path, monkeypatch):
        monkeypatch.setattr("app.services.mrpack_installer.SERVERS_DIR", str(tmp_path))
        server_dir = tmp_path / "myserver"
        server_dir.mkdir()
        pack_path = tmp_path / "pack.mrpack"
        _make_mrpack(str(pack_path), _fabric_manifest(files=[
            {"path": "mods/client-only.jar", "downloads": [], "hashes": {},
             "env": {"server": "unsupported"}},
        ]))
        summary = install_mrpack(str(pack_path), "myserver", server_type="Fabric", mc_version="1.20.1")
        assert summary == {"installed": 0, "skipped_client": 1, "failed": 0}

    def test_copies_overrides(self, tmp_path, monkeypatch):
        monkeypatch.setattr("app.services.mrpack_installer.SERVERS_DIR", str(tmp_path))
        server_dir = tmp_path / "myserver"
        server_dir.mkdir()
        pack_path = tmp_path / "pack.mrpack"
        _make_mrpack(
            str(pack_path), _fabric_manifest(),
            overrides={"config/mod.toml": "setting=1"},
        )
        install_mrpack(str(pack_path), "myserver", server_type="Fabric", mc_version="1.20.1")
        copied = server_dir / "config" / "mod.toml"
        assert copied.exists()
        assert copied.read_text(encoding="utf-8") == "setting=1"

    def test_rejects_non_zip_file(self, tmp_path, monkeypatch):
        monkeypatch.setattr("app.services.mrpack_installer.SERVERS_DIR", str(tmp_path))
        server_dir = tmp_path / "myserver"
        server_dir.mkdir()
        bad_path = tmp_path / "notazip.mrpack"
        bad_path.write_text("not a zip", encoding="utf-8")
        with pytest.raises(ValueError, match="Not a valid ZIP"):
            install_mrpack(str(bad_path), "myserver")
