"""Tests for app.services.bytecode_analyzer and app.services.scaffolder."""

import os
import struct
import tempfile
import zipfile

import pytest

from app.services.bytecode_analyzer import (
    CLASS_VERSION_MAP,
    _extract_class_major,
    _read_manifest_main_class,
    analyze_jar_bytecode,
)
from app.services.scaffolder import pre_boot_scaffold


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _make_class_bytes(major: int, minor: int = 0) -> bytes:
    """Build a minimal .class file header with the given major version."""
    return b"\xCA\xFE\xBA\xBE" + struct.pack(">HH", minor, major)


def _make_jar(tmp_path, manifest_text: str = "", classes: dict = None) -> str:
    """Create a temporary .jar with optional manifest and .class entries.

    Args:
        tmp_path:       pytest tmp_path fixture.
        manifest_text:  Raw MANIFEST.MF content.
        classes:        Dict of {internal_path: raw_major_version (int)}.

    Returns:
        Absolute path to the created .jar file.
    """
    jar_path = os.path.join(str(tmp_path), "server.jar")
    with zipfile.ZipFile(jar_path, "w") as zf:
        if manifest_text:
            zf.writestr("META-INF/MANIFEST.MF", manifest_text)
        for path, major in (classes or {}).items():
            zf.writestr(path, _make_class_bytes(major))
    return jar_path


# ============================================================================
# bytecode_analyzer tests
# ============================================================================
class TestExtractClassMajor:
    """Unit tests for the low-level _extract_class_major helper."""

    def test_valid_java17(self):
        assert _extract_class_major(_make_class_bytes(61)) == 61

    def test_valid_java8(self):
        assert _extract_class_major(_make_class_bytes(52)) == 52

    def test_too_short(self):
        assert _extract_class_major(b"\xCA\xFE\xBA") is None

    def test_bad_magic(self):
        assert _extract_class_major(b"\x00\x00\x00\x00\x00\x00\x00\x3D") is None

    def test_empty(self):
        assert _extract_class_major(b"") is None


class TestReadManifestMainClass:
    """Tests for MANIFEST.MF parsing."""

    def test_normal_manifest(self, tmp_path):
        manifest = "Manifest-Version: 1.0\nMain-Class: net.minecraft.server.Main\n"
        jar_path = _make_jar(tmp_path, manifest_text=manifest)
        with zipfile.ZipFile(jar_path) as zf:
            assert _read_manifest_main_class(zf) == "net.minecraft.server.Main"

    def test_continuation_lines(self, tmp_path):
        # Long Main-Class that wraps onto a continuation line
        manifest = (
            "Manifest-Version: 1.0\n"
            "Main-Class: net.minecraft.bundler.Mai\n"
            " n\n"
        )
        jar_path = _make_jar(tmp_path, manifest_text=manifest)
        with zipfile.ZipFile(jar_path) as zf:
            assert _read_manifest_main_class(zf) == "net.minecraft.bundler.Main"

    def test_no_manifest(self, tmp_path):
        jar_path = _make_jar(tmp_path)
        with zipfile.ZipFile(jar_path) as zf:
            assert _read_manifest_main_class(zf) is None

    def test_manifest_without_main_class(self, tmp_path):
        manifest = "Manifest-Version: 1.0\nCreated-By: 17.0.1\n"
        jar_path = _make_jar(tmp_path, manifest_text=manifest)
        with zipfile.ZipFile(jar_path) as zf:
            assert _read_manifest_main_class(zf) is None


class TestAnalyzeJarBytecode:
    """Integration tests for the full analyze_jar_bytecode function."""

    def test_main_class_java17(self, tmp_path):
        manifest = "Main-Class: net.minecraft.server.Main\n"
        classes = {"net/minecraft/server/Main.class": 61}
        jar = _make_jar(tmp_path, manifest, classes)
        assert analyze_jar_bytecode(jar) == 17

    def test_main_class_java21(self, tmp_path):
        manifest = "Main-Class: net.minecraft.server.Main\n"
        classes = {"net/minecraft/server/Main.class": 65}
        jar = _make_jar(tmp_path, manifest, classes)
        assert analyze_jar_bytecode(jar) == 21

    def test_main_class_java8(self, tmp_path):
        manifest = "Main-Class: org.bukkit.Main\n"
        classes = {"org/bukkit/Main.class": 52}
        jar = _make_jar(tmp_path, manifest, classes)
        assert analyze_jar_bytecode(jar) == 8

    def test_fallback_scan(self, tmp_path):
        """When Main-Class is missing, use highest .class in jar."""
        classes = {
            "com/example/A.class": 52,   # Java 8
            "com/example/B.class": 61,   # Java 17
        }
        jar = _make_jar(tmp_path, classes=classes)
        assert analyze_jar_bytecode(jar) == 17

    def test_fallback_scan_highest_wins(self, tmp_path):
        classes = {
            "a.class": 52,
            "b.class": 65,
            "c.class": 61,
        }
        jar = _make_jar(tmp_path, classes=classes)
        assert analyze_jar_bytecode(jar) == 21

    def test_main_class_not_found_in_jar(self, tmp_path):
        """Manifest declares a Main-Class that doesn't exist as a .class entry."""
        manifest = "Main-Class: com.ghost.NotHere\n"
        classes = {"com/real/Present.class": 61}
        jar = _make_jar(tmp_path, manifest, classes)
        # Should fall back to scan and find 61 -> Java 17
        assert analyze_jar_bytecode(jar) == 17

    def test_empty_jar(self, tmp_path):
        jar = _make_jar(tmp_path)
        assert analyze_jar_bytecode(jar) is None

    def test_nonexistent_file(self):
        assert analyze_jar_bytecode("/nonexistent/path/server.jar") is None

    def test_corrupt_file(self, tmp_path):
        bad_file = os.path.join(str(tmp_path), "corrupt.jar")
        with open(bad_file, "wb") as f:
            f.write(b"this is not a jar")
        assert analyze_jar_bytecode(bad_file) is None

    def test_class_version_map_coverage(self):
        """Ensure the map covers all Java versions we care about."""
        assert CLASS_VERSION_MAP[52] == 8
        assert CLASS_VERSION_MAP[61] == 17
        assert CLASS_VERSION_MAP[65] == 21
        assert CLASS_VERSION_MAP[70] == 26


# ============================================================================
# scaffolder tests
# ============================================================================
class TestPreBootScaffold:
    """Tests for the pre_boot_scaffold function."""

    def test_creates_eula(self, tmp_path):
        pre_boot_scaffold(str(tmp_path), port=25565)
        eula_path = tmp_path / "eula.txt"
        assert eula_path.exists()
        content = eula_path.read_text()
        assert "eula=true" in content

    def test_creates_server_properties(self, tmp_path):
        pre_boot_scaffold(str(tmp_path), port=25577)
        props = tmp_path / "server.properties"
        assert props.exists()
        content = props.read_text()
        assert "server-port=25577" in content

    def test_creates_directories(self, tmp_path):
        pre_boot_scaffold(str(tmp_path))
        for d in ("mods", "plugins", "world", "logs"):
            assert (tmp_path / d).is_dir()

    def test_does_not_overwrite_existing_eula(self, tmp_path):
        eula_path = tmp_path / "eula.txt"
        eula_path.write_text("eula=false\n")
        pre_boot_scaffold(str(tmp_path))
        # Should NOT be overwritten
        assert "eula=false" in eula_path.read_text()

    def test_patches_port_in_existing_properties(self, tmp_path):
        props = tmp_path / "server.properties"
        props.write_text("server-port=25565\nmotd=Hello\n")
        pre_boot_scaffold(str(tmp_path), port=30000)
        content = props.read_text()
        assert "server-port=30000" in content
        assert "motd=Hello" in content

    def test_adds_port_if_missing_in_existing_properties(self, tmp_path):
        props = tmp_path / "server.properties"
        props.write_text("motd=Hello\n")
        pre_boot_scaffold(str(tmp_path), port=12345)
        content = props.read_text()
        assert "server-port=12345" in content
        assert "motd=Hello" in content

    def test_eula_false_when_not_accepted(self, tmp_path):
        pre_boot_scaffold(str(tmp_path), eula_accepted=False)
        content = (tmp_path / "eula.txt").read_text()
        assert "eula=false" in content

    def test_nonexistent_directory_no_crash(self):
        """Should log a warning and return silently."""
        pre_boot_scaffold("/nonexistent/path/xyz")

    def test_idempotent(self, tmp_path):
        """Calling twice should not corrupt files."""
        pre_boot_scaffold(str(tmp_path), port=25565)
        pre_boot_scaffold(str(tmp_path), port=25565)
        assert "eula=true" in (tmp_path / "eula.txt").read_text()
        assert "server-port=25565" in (tmp_path / "server.properties").read_text()

    def test_config_all_fields_written_on_fresh_properties(self, tmp_path):
        config = {
            "seed": "12345",
            "game_mode": "creative",
            "difficulty": "hard",
            "hardcore": True,
            "whitelist": True,
            "enforce_whitelist": False,
            "pvp": False,
            "online_mode": True,
            "max_players": 10,
            "spawn_protection": 0,
            "enable_command_block": True,
            "allow_flight": True,
            "enforce_secure_profile": False,
            "view_distance": 12,
            "simulation_distance": 8,
        }
        pre_boot_scaffold(str(tmp_path), port=25565, config=config)
        content = (tmp_path / "server.properties").read_text()
        assert "level-seed=12345" in content
        assert "gamemode=creative" in content
        assert "difficulty=hard" in content
        assert "hardcore=true" in content
        assert "white-list=true" in content
        assert "enforce-whitelist=false" in content
        assert "pvp=false" in content
        assert "online-mode=true" in content
        assert "max-players=10" in content
        assert "spawn-protection=0" in content
        assert "enable-command-block=true" in content
        assert "allow-flight=true" in content
        assert "enforce-secure-profile=false" in content
        assert "view-distance=12" in content
        assert "simulation-distance=8" in content

    def test_config_seed_omitted_when_falsy(self, tmp_path):
        pre_boot_scaffold(str(tmp_path), port=25565, config={"seed": ""})
        content = (tmp_path / "server.properties").read_text()
        assert "level-seed" not in content

    def test_config_empty_dict_uses_defaults_only(self, tmp_path):
        pre_boot_scaffold(str(tmp_path), port=25565, config={})
        content = (tmp_path / "server.properties").read_text()
        assert "server-port=25565" in content
        assert "motd=A ZeroBlockBridge Server" in content
        assert "enable-query=false" in content
        assert "enable-rcon=false" in content
        assert "gamemode" not in content

    def test_config_none_uses_defaults_only(self, tmp_path):
        pre_boot_scaffold(str(tmp_path), port=25565, config=None)
        content = (tmp_path / "server.properties").read_text()
        assert "server-port=25565" in content
        assert "gamemode" not in content

    def test_config_port_always_patched_even_if_present(self, tmp_path):
        """server-port must always be overwritten in-place, never skipped."""
        props = tmp_path / "server.properties"
        props.write_text("server-port=1111\n")
        pre_boot_scaffold(str(tmp_path), port=25565, config={"game_mode": "survival"})
        content = props.read_text()
        assert "server-port=25565" in content
        assert "server-port=1111" not in content

    def test_config_does_not_overwrite_existing_manual_value(self, tmp_path):
        """Non-port keys already present in the file must be left untouched."""
        props = tmp_path / "server.properties"
        props.write_text("server-port=25565\ngamemode=survival\n")
        pre_boot_scaffold(str(tmp_path), port=25565, config={"game_mode": "creative"})
        content = props.read_text()
        # user's manual value wins, scaffolder does not clobber it
        assert "gamemode=survival" in content
        assert "gamemode=creative" not in content

    def test_config_adds_new_key_to_existing_properties(self, tmp_path):
        props = tmp_path / "server.properties"
        props.write_text("server-port=25565\nmotd=Hello\n")
        pre_boot_scaffold(str(tmp_path), port=25565, config={"difficulty": "hard"})
        content = props.read_text()
        assert "difficulty=hard" in content
        assert "motd=Hello" in content
