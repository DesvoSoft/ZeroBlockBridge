"""Tests for tools/extract_changelog_section.py (release-notes extraction)."""
import importlib.util
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
MODULE_PATH = ROOT / "tools" / "extract_changelog_section.py"

_spec = importlib.util.spec_from_file_location("extract_changelog_section", MODULE_PATH)
extract_changelog_section = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(extract_changelog_section)

extract_section = extract_changelog_section.extract_section

CHANGELOG = """\
# Changelog

---

## [2.0.0] - 2026-07-10

### Added
- Feature A
- Feature B

### Fixed
- Bug X

## [1.9.0] - 2026-06-01

### Added
- Older feature
"""


def test_extracts_first_section_body_only():
    section = extract_section(CHANGELOG, "2.0.0")
    assert section is not None
    # Regression: DOTALL used to let `.*$` swallow the file and return "".
    assert "Feature A" in section
    assert "Bug X" in section


def test_stops_at_next_version_heading():
    section = extract_section(CHANGELOG, "2.0.0")
    assert "Older feature" not in section
    assert "[1.9.0]" not in section


def test_heading_itself_is_excluded():
    section = extract_section(CHANGELOG, "2.0.0")
    assert not section.startswith("## [2.0.0]")


def test_last_section_runs_to_end_of_file():
    section = extract_section(CHANGELOG, "1.9.0")
    assert section == "### Added\n- Older feature"


def test_missing_version_returns_none():
    assert extract_section(CHANGELOG, "9.9.9") is None


def test_empty_section_returns_none():
    text = "## [3.0.0] - 2026-08-01\n\n## [2.0.0] - 2026-07-10\n\n- real content\n"
    assert extract_section(text, "3.0.0") is None


def test_em_dash_heading_separator_matches():
    text = "## [2.1.0] — 2026-08-01\n\n- Unicode heading\n"
    assert extract_section(text, "2.1.0") == "- Unicode heading"


@pytest.mark.parametrize("argv_version", ["v2.0.0", "2.0.0"])
def test_cli_strips_leading_v(monkeypatch, capsys, tmp_path, argv_version):
    changelog = tmp_path / "docs" / "changelog.md"
    changelog.parent.mkdir(parents=True)
    changelog.write_text(CHANGELOG, encoding="utf-8")
    monkeypatch.setattr(extract_changelog_section, "CHANGELOG_PATH", changelog)
    monkeypatch.setattr(sys, "argv", ["extract_changelog_section.py", argv_version])

    assert extract_changelog_section.main() == 0
    assert "Feature A" in capsys.readouterr().out


def test_cli_prerelease_falls_back_to_base_version(monkeypatch, capsys, tmp_path):
    changelog = tmp_path / "docs" / "changelog.md"
    changelog.parent.mkdir(parents=True)
    changelog.write_text(CHANGELOG, encoding="utf-8")
    monkeypatch.setattr(extract_changelog_section, "CHANGELOG_PATH", changelog)
    monkeypatch.setattr(sys, "argv", ["extract_changelog_section.py", "v2.0.0-rc1"])

    assert extract_changelog_section.main() == 0
    assert "Feature A" in capsys.readouterr().out


def test_cli_strict_fails_on_missing_section(monkeypatch, tmp_path):
    changelog = tmp_path / "docs" / "changelog.md"
    changelog.parent.mkdir(parents=True)
    changelog.write_text(CHANGELOG, encoding="utf-8")
    monkeypatch.setattr(extract_changelog_section, "CHANGELOG_PATH", changelog)
    monkeypatch.setattr(sys, "argv", ["extract_changelog_section.py", "v9.9.9", "--strict"])

    assert extract_changelog_section.main() == 1


def test_cli_non_strict_emits_placeholder(monkeypatch, capsys, tmp_path):
    changelog = tmp_path / "docs" / "changelog.md"
    changelog.parent.mkdir(parents=True)
    changelog.write_text(CHANGELOG, encoding="utf-8")
    monkeypatch.setattr(extract_changelog_section, "CHANGELOG_PATH", changelog)
    monkeypatch.setattr(sys, "argv", ["extract_changelog_section.py", "v9.9.9"])

    assert extract_changelog_section.main() == 0
    assert "No changelog entry found" in capsys.readouterr().out


def test_real_changelog_current_version_is_not_empty():
    """Guards the actual shipped changelog against the empty-body regression."""
    text = (ROOT / "docs" / "changelog.md").read_text(encoding="utf-8")
    app_config = (ROOT / "app" / "core" / "app_config.py").read_text(encoding="utf-8")
    version = app_config.split('APP_VERSION = "')[1].split('"')[0]

    section = extract_section(text, version)
    assert section is not None, f"docs/changelog.md has no section for {version}"
    assert len(section) > 50
