"""Tests for app/ui/icons.py (PIL-drawn icon set)."""

import pytest

from app.ui import icons
from app.ui.icons import _Painters, _render, icon

PAINTER_NAMES = sorted(n for n, v in vars(_Painters).items() if isinstance(v, staticmethod))


@pytest.mark.parametrize("name", PAINTER_NAMES)
@pytest.mark.parametrize("size", [12, 16, 48])
def test_every_icon_renders_visible_pixels(name, size):
    img = _render(name, size, "#ff0000")
    assert img.size == (size, size)
    assert img.getchannel("A").getbbox() is not None, f"{name} rendered empty"


def test_icon_is_cached_per_name_size_and_color():
    a = icon("play", 16, "#ffffff")
    assert icon("play", 16, "#ffffff") is a
    assert icon("play", 16, ("#000000", "#ffffff")) is not a
    assert icon("play", 20, "#ffffff") is not a


def test_default_color_uses_theme_pair():
    img = icon("check", 14)
    key = ("check", 14, (icons.DEFAULT_LIGHT, icons.DEFAULT_DARK))
    assert icons._cache[key] is img


def test_unknown_icon_name_raises():
    with pytest.raises(AttributeError):
        _render("does-not-exist", 16, "#000000")
