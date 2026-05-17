"""Unit tests for Phase 4 — Provisioning services."""

import os
import hashlib
import tempfile
from unittest.mock import patch, MagicMock


# =====================================================================
# PROV-01 / INTEG-03 — Java Detection & Version Matching
# =====================================================================
from app.services.java_detector import (
    parse_java_version,
    get_required_java,
    check_java_compatibility,
    JavaInstallation,
    JavaDetector,
    _detect_vendor,
    _parse_mc_version,
)


class TestJavaVersionParsing:
    def test_parse_java_17(self):
        output = 'openjdk version "17.0.8" 2023-07-18\nOpenJDK Runtime Environment'
        assert parse_java_version(output) == (17, 0, 8)

    def test_parse_java_21(self):
        output = 'openjdk version "21.0.1" 2023-10-17\nOpenJDK Runtime Environment'
        assert parse_java_version(output) == (21, 0, 1)

    def test_parse_java_8_legacy(self):
        output = 'java version "1.8.0_381"\nJava(TM) SE Runtime Environment'
        major, minor, patch = parse_java_version(output)
        assert major == 8

    def test_parse_java_16(self):
        output = 'openjdk version "16.0.2" 2021-07-20'
        assert parse_java_version(output) == (16, 0, 2)

    def test_parse_empty_returns_zero(self):
        assert parse_java_version("") == (0, 0, 0)

    def test_parse_garbage_returns_zero(self):
        assert parse_java_version("not a java version") == (0, 0, 0)


class TestMCJavaMapping:
    def test_mc_1_12_requires_java_8(self):
        assert get_required_java("1.12.2") == 8

    def test_mc_1_16_requires_java_8(self):
        assert get_required_java("1.16.5") == 8

    def test_mc_1_17_requires_java_16(self):
        assert get_required_java("1.17") == 16

    def test_mc_1_17_1_requires_java_16(self):
        assert get_required_java("1.17.1") == 16

    def test_mc_1_18_requires_java_17(self):
        assert get_required_java("1.18") == 17

    def test_mc_1_20_1_requires_java_17(self):
        assert get_required_java("1.20.1") == 17

    def test_mc_1_20_4_requires_java_17(self):
        assert get_required_java("1.20.4") == 17

    def test_mc_1_20_5_requires_java_21(self):
        assert get_required_java("1.20.5") == 21

    def test_mc_1_21_requires_java_21(self):
        assert get_required_java("1.21") == 21

    def test_unknown_version_defaults_17(self):
        assert get_required_java("99.99.99") == 17


class TestJavaCompatibility:
    def test_compatible(self):
        ok, req, msg = check_java_compatibility("1.20.1", 17)
        assert ok is True
        assert req == 17

    def test_higher_java_is_incompatible(self):
        ok, req, msg = check_java_compatibility("1.20.1", 21)
        assert ok is False

    def test_incompatible(self):
        ok, req, msg = check_java_compatibility("1.20.5", 17)
        assert ok is False
        assert req == 21

    def test_legacy_mc_with_java_8(self):
        ok, req, msg = check_java_compatibility("1.12.2", 8)
        assert ok is True
        assert req == 8


class TestVendorDetection:
    def test_adoptium(self):
        assert _detect_vendor("Eclipse Adoptium") == "Eclipse Adoptium"

    def test_oracle(self):
        assert _detect_vendor("Java(TM) SE Runtime") == "Oracle"

    def test_graalvm(self):
        assert _detect_vendor("GraalVM CE 21") == "GraalVM"

    def test_corretto(self):
        assert _detect_vendor("Amazon Corretto 17") == "Amazon Corretto"


class TestMCVersionParsing:
    def test_basic(self):
        assert _parse_mc_version("1.20.4") == (1, 20, 4)

    def test_two_part(self):
        assert _parse_mc_version("1.21") == (1, 21, 0)


class TestJavaDetector:
    @patch("app.services.java_detector._probe_java")
    def test_scan_path_finds_java(self, mock_probe):
        mock_probe.return_value = JavaInstallation(
            path="/usr/bin/java", version_string='openjdk "17"',
            major=17, minor=0, patch=0, source="PATH",
        )
        detector = JavaDetector()
        with patch.dict(os.environ, {"PATH": "/usr/bin"}):
            with patch("os.path.isfile", return_value=True):
                results = detector._scan_path()
                assert len(results) >= 1

    def test_find_best_for_mc_returns_none_when_empty(self):
        detector = JavaDetector()
        detector._cache = []
        result = detector.find_best_for_mc("1.20.1")
        assert result is None

    def test_find_best_for_mc_selects_compatible(self):
        detector = JavaDetector()
        detector._cache = [
            JavaInstallation(path="/j21", version_string="", major=21, source="TEST"),
            JavaInstallation(path="/j17", version_string="", major=17, source="TEST"),
            JavaInstallation(path="/j8", version_string="", major=8, source="TEST"),
        ]
        best = detector.find_best_for_mc("1.20.1")  # requires Java 17
        assert best is not None
        assert best.major >= 17


# =====================================================================
# PROV-04 — SHA1 Validation
# =====================================================================
from app.services.sha1_validator import compute_sha1, verify_sha1, download_with_verification


class TestSHA1Compute:
    def test_compute_sha1_correct(self):
        with tempfile.NamedTemporaryFile(delete=False, suffix=".bin") as f:
            f.write(b"hello world")
            path = f.name
        try:
            expected = hashlib.sha1(b"hello world").hexdigest()
            assert compute_sha1(path) == expected
        finally:
            os.unlink(path)

    def test_verify_sha1_match(self):
        with tempfile.NamedTemporaryFile(delete=False, suffix=".bin") as f:
            f.write(b"test data")
            path = f.name
        try:
            expected = hashlib.sha1(b"test data").hexdigest()
            assert verify_sha1(path, expected) is True
        finally:
            os.unlink(path)

    def test_verify_sha1_mismatch(self):
        with tempfile.NamedTemporaryFile(delete=False, suffix=".bin") as f:
            f.write(b"actual data")
            path = f.name
        try:
            assert verify_sha1(path, "0000000000000000000000000000000000000000") is False
        finally:
            os.unlink(path)


class TestDownloadWithVerification:
    @patch("app.services.sha1_validator.requests.get")
    def test_successful_download(self, mock_get):
        content = b"server.jar contents"
        expected_sha1 = hashlib.sha1(content).hexdigest()

        mock_resp = MagicMock()
        mock_resp.headers = {"content-length": str(len(content))}
        mock_resp.iter_content.return_value = [content]
        mock_resp.raise_for_status = MagicMock()
        mock_get.return_value = mock_resp

        with tempfile.NamedTemporaryFile(delete=False, suffix=".jar") as f:
            path = f.name

        try:
            ok, result_path, error = download_with_verification(
                "https://example.com/server.jar", path, expected_sha1
            )
            assert ok is True
            assert error is None
            assert result_path == path
        finally:
            if os.path.exists(path):
                os.unlink(path)

    @patch("app.services.sha1_validator.requests.get")
    def test_sha1_mismatch_retries(self, mock_get):
        content = b"corrupt data"

        mock_resp = MagicMock()
        mock_resp.headers = {"content-length": str(len(content))}
        mock_resp.iter_content.return_value = [content]
        mock_resp.raise_for_status = MagicMock()
        mock_get.return_value = mock_resp

        with tempfile.NamedTemporaryFile(delete=False, suffix=".jar") as f:
            path = f.name

        try:
            ok, result_path, error = download_with_verification(
                "https://example.com/server.jar", path,
                "0000000000000000000000000000000000000000",
                max_retries=2,
            )
            assert ok is False
            assert "corruption" in error.lower() or "mismatch" in error.lower() or "sha1" in error.lower()
        finally:
            if os.path.exists(path):
                os.unlink(path)

    @patch("app.services.sha1_validator.requests.get")
    def test_no_sha1_still_succeeds(self, mock_get):
        content = b"no hash data"

        mock_resp = MagicMock()
        mock_resp.headers = {"content-length": str(len(content))}
        mock_resp.iter_content.return_value = [content]
        mock_resp.raise_for_status = MagicMock()
        mock_get.return_value = mock_resp

        with tempfile.NamedTemporaryFile(delete=False, suffix=".jar") as f:
            path = f.name

        try:
            ok, result_path, error = download_with_verification(
                "https://example.com/server.jar", path, None
            )
            assert ok is True
        finally:
            if os.path.exists(path):
                os.unlink(path)


# =====================================================================
# PROV-05 — Aikar's Flags
# =====================================================================
from app.services.aikars_flags import calculate_flags, build_java_command, flags_to_string


class TestAikarsFlags:
    def test_low_ram_flags(self):
        flags = calculate_flags(2048)
        assert "-Xms2048M" in flags
        assert "-Xmx2048M" in flags
        assert "-XX:+UseG1GC" in flags
        # Low RAM tier uses 30% new size
        assert "-XX:G1NewSizePercent=30" in flags
        assert "-XX:G1HeapRegionSize=8M" in flags

    def test_mid_ram_flags(self):
        flags = calculate_flags(8192)
        assert "-XX:G1NewSizePercent=35" in flags
        assert "-XX:G1HeapRegionSize=16M" in flags

    def test_high_ram_flags(self):
        flags = calculate_flags(12288)
        assert "-XX:G1NewSizePercent=40" in flags
        assert "-XX:G1MaxNewSizePercent=50" in flags
        assert "-XX:G1HeapRegionSize=16M" in flags

    def test_edge_case_4g(self):
        flags = calculate_flags(4096)
        # 4G is below 8G threshold → default tier
        assert "-XX:G1NewSizePercent=30" in flags

    def test_aikars_marker_present(self):
        flags = calculate_flags(4096)
        assert "-Dusing.aikars.flags=https://mcflags.emc.gs" in flags

    def test_flags_to_string(self):
        s = flags_to_string(2048)
        assert isinstance(s, str)
        assert "-Xms2048M" in s
        assert " " in s  # space-separated

    def test_build_command_with_aikars(self):
        cmd = build_java_command("java", 4096, "server.jar", use_aikars=True)
        assert cmd[0] == "java"
        assert "-jar" in cmd
        assert "server.jar" in cmd
        assert "nogui" in cmd
        assert "-XX:+UseG1GC" in cmd

    def test_build_command_without_aikars(self):
        cmd = build_java_command("java", 4096, "server.jar", use_aikars=False)
        assert "-Xms4096M" in cmd
        assert "-XX:+UseG1GC" not in cmd

    def test_build_command_custom_extra_args(self):
        cmd = build_java_command("java", 4096, "server.jar", extra_args=["-Dfoo=bar"])
        assert "-Dfoo=bar" in cmd
