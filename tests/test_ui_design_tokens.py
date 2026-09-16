"""Source-level guards for the UI design system (docs: CLAUDE.md > UI components).

These run without a display: they scan app/ui/*.py text so a literal font,
raw hex color or glyph marker can't creep back in unnoticed.
"""

import re
from pathlib import Path

import pytest

from app.core.app_config import AppConfig

UI_DIR = Path(__file__).resolve().parent.parent / "app" / "ui"
# icons.py owns its default stroke colors; everything else must use tokens.
_EXEMPT_HEX = {"icons.py"}


def _ui_sources():
    for path in sorted(UI_DIR.glob("*.py")):
        yield path, path.read_text(encoding="utf-8")


def _code_lines(text):
    """Lines outside comments/docstrings are what matter; a cheap filter is
    enough here: drop full-line comments and lines inside triple-quoted blocks."""
    in_doc = False
    for lineno, line in enumerate(text.splitlines(), 1):
        stripped = line.strip()
        if stripped.count('"""') == 1:
            in_doc = not in_doc
            continue
        if in_doc or stripped.startswith("#"):
            continue
        yield lineno, line


@pytest.mark.parametrize("path,text", list(_ui_sources()), ids=lambda v: getattr(v, "name", ""))
def test_no_literal_fonts(path, text):
    offenders = [
        f"{path.name}:{n}: {line.strip()}"
        for n, line in _code_lines(text)
        if "CTkFont(" in line or re.search(r"font=\((AppConfig\.FONT_FAMILY|\")", line)
    ]
    assert not offenders, "use AppConfig.FONT_* tokens:\n" + "\n".join(offenders)


@pytest.mark.parametrize("path,text", list(_ui_sources()), ids=lambda v: getattr(v, "name", ""))
def test_no_raw_hex_colors(path, text):
    if path.name in _EXEMPT_HEX:
        return
    offenders = [
        f"{path.name}:{n}: {line.strip()}"
        for n, line in _code_lines(text)
        if re.search(r'"#[0-9a-fA-F]{6}"', line)
    ]
    assert not offenders, "use AppConfig.COLOR_* tokens:\n" + "\n".join(offenders)


@pytest.mark.parametrize("path,text", list(_ui_sources()), ids=lambda v: getattr(v, "name", ""))
def test_no_glyph_markers_in_strings(path, text):
    # Check/cross/warning/play glyphs render misaligned and can't be tinted;
    # use icons.icon() and explicit status kinds instead.
    offenders = [
        f"{path.name}:{n}: {line.strip()}"
        for n, line in _code_lines(text)
        if re.search("[✓✔✗✘⚠▶]", line)
    ]
    assert not offenders, "glyph markers in UI strings:\n" + "\n".join(offenders)


def test_font_tokens_are_well_formed():
    fonts = {k: v for k, v in vars(AppConfig).items() if k.startswith("FONT_") and not k.startswith("FONT_FAMILY")}
    assert fonts, "no FONT_* tokens found"
    for name, value in fonts.items():
        assert isinstance(value, tuple) and 2 <= len(value) <= 3, name
        assert isinstance(value[0], str) and isinstance(value[1], int), name
