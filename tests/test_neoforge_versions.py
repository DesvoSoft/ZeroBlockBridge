import pytest

from app.core import neoforge

# A slice of the real maven listing (2026-10-14).
BUILDS = [
    "0.25w14craftmine.5-beta", "20.2.93", "20.3.8-beta", "20.4.250", "20.4.251", "20.5.21-beta",
    "21.0.167", "21.1.258", "21.1.259", "21.2.1-beta", "21.6.20-beta",
    "26.1.0.19-beta", "26.1.2.116", "26.1.2.117", "26.2.0.90", "26.3.0.75-beta", "26.3.0.76", "26.3.0.77",
]


@pytest.mark.parametrize("build, mc", [
    ("21.1.77", "1.21.1"),
    ("21.0.167", "1.21"),
    ("20.4.251", "1.20.4"),
    ("21.10.64", "1.21.10"),
    ("20.5.21-beta", "1.20.5"),
    ("26.1.2.117", "26.1.2"),
    ("26.3.0.77", "26.3"),
    ("26.1.0.19-beta", "26.1"),
    ("0.25w14craftmine.5-beta", None),
    ("not-a-version", None),
    ("", None),
])
def test_mc_version(build, mc):
    assert neoforge.mc_version(build) == mc


def test_best_build_prefers_newest_stable():
    assert neoforge.best_build(BUILDS, "1.21.1") == "21.1.259"
    assert neoforge.best_build(BUILDS, "26.3") == "26.3.0.77"
    assert neoforge.best_build(BUILDS, "26.1.2") == "26.1.2.117"


def test_best_build_falls_back_to_beta_and_none():
    assert neoforge.best_build(BUILDS, "1.21.6") == "21.6.20-beta"
    assert neoforge.best_build(BUILDS, "1.20.1") is None  # NeoForge 1.20.1 isn't this artifact


def test_build_numbers_compare_numerically():
    builds = ["21.1.9", "21.1.10", "21.1.100"]
    assert neoforge.best_build(builds, "1.21.1") == "21.1.100"


def test_supported_versions_newest_first_and_skip_junk():
    versions = neoforge.supported_mc_versions(BUILDS)
    assert versions[:3] == ["26.3", "26.2", "26.1.2"]
    assert "1.20.2" in versions and "1.21" in versions
    assert all(v[0].isdigit() for v in versions)


def test_installer_url():
    assert neoforge.installer_url("21.1.77") == (
        "https://maven.neoforged.net/releases/net/neoforged/neoforge/21.1.77/neoforge-21.1.77-installer.jar")
