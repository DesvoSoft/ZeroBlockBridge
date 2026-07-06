"""Antialiased icon set drawn with PIL — replaces emoji glyphs.

Tk renders emoji with inconsistent size/baseline and no tinting.
Icons here are drawn at 4x supersampling and downsampled with LANCZOS,
so edges are smooth (unlike CTk's own corner rendering). Each icon is
cached per (name, size, colors) and returned as a CTkImage with light
and dark variants.

Usage:
    from app.ui.icons import icon
    btn = ctk.CTkButton(parent, image=icon("play"), text="")
"""

import logging

import customtkinter as ctk
from PIL import Image, ImageDraw

logger = logging.getLogger(__name__)

# Default tint: dark slate for light mode, light slate for dark mode
DEFAULT_LIGHT = "#334155"
DEFAULT_DARK = "#e2e8f0"

_SS = 4  # supersampling factor
_cache: dict = {}


def _canvas(size):
    s = size * _SS
    img = Image.new("RGBA", (s, s), (0, 0, 0, 0))
    return img, ImageDraw.Draw(img), s


def _stroke(size):
    """Stroke width scaled to icon size (2px at 16px)."""
    return max(2, round(size / 8)) * _SS


class _Painters:
    """Each painter draws one icon on a supersampled canvas.

    Coordinates are fractions of the canvas edge (0.0-1.0) scaled by `s`.
    """

    @staticmethod
    def play(d, s, c, w):
        d.polygon([(0.30 * s, 0.18 * s), (0.30 * s, 0.82 * s), (0.85 * s, 0.50 * s)], fill=c)

    @staticmethod
    def stop(d, s, c, w):
        d.rounded_rectangle([0.24 * s, 0.24 * s, 0.76 * s, 0.76 * s], radius=0.10 * s, fill=c)

    @staticmethod
    def plus(d, s, c, w):
        d.line([(0.5 * s, 0.15 * s), (0.5 * s, 0.85 * s)], fill=c, width=w)
        d.line([(0.15 * s, 0.5 * s), (0.85 * s, 0.5 * s)], fill=c, width=w)

    @staticmethod
    def check(d, s, c, w):
        d.line([(0.18 * s, 0.55 * s), (0.42 * s, 0.78 * s), (0.84 * s, 0.25 * s)],
               fill=c, width=w, joint="curve")

    @staticmethod
    def close(d, s, c, w):
        d.line([(0.22 * s, 0.22 * s), (0.78 * s, 0.78 * s)], fill=c, width=w)
        d.line([(0.78 * s, 0.22 * s), (0.22 * s, 0.78 * s)], fill=c, width=w)

    @staticmethod
    def folder(d, s, c, w):
        # Tab + body, outline style
        d.rounded_rectangle([0.10 * s, 0.28 * s, 0.90 * s, 0.80 * s], radius=0.08 * s,
                            outline=c, width=w)
        d.line([(0.10 * s, 0.30 * s), (0.10 * s, 0.22 * s)], fill=c, width=w)
        d.arc([0.10 * s, 0.16 * s, 0.22 * s, 0.28 * s], 180, 270, fill=c, width=w)
        d.line([(0.16 * s, 0.16 * s), (0.40 * s, 0.16 * s)], fill=c, width=w)
        d.line([(0.40 * s, 0.16 * s), (0.48 * s, 0.28 * s)], fill=c, width=w)

    @staticmethod
    def gear(d, s, c, w):
        import math
        cx = cy = 0.5 * s
        r_out = 0.42 * s
        r_in = 0.30 * s
        tooth_w = 0.14 * s
        for i in range(8):
            a = math.radians(i * 45)
            x1 = cx + r_in * math.cos(a)
            y1 = cy + r_in * math.sin(a)
            x2 = cx + r_out * math.cos(a)
            y2 = cy + r_out * math.sin(a)
            d.line([(x1, y1), (x2, y2)], fill=c, width=int(tooth_w))
        d.ellipse([cx - r_in, cy - r_in, cx + r_in, cy + r_in], fill=c)
        r_hole = 0.14 * s
        d.ellipse([cx - r_hole, cy - r_hole, cx + r_hole, cy + r_hole], fill=(0, 0, 0, 0))

    @staticmethod
    def refresh(d, s, c, w):
        d.arc([0.16 * s, 0.16 * s, 0.84 * s, 0.84 * s], start=-40, end=230, fill=c, width=w)
        # Arrowhead at the arc start (right side, pointing up-right)
        d.polygon([(0.90 * s, 0.10 * s), (0.94 * s, 0.42 * s), (0.64 * s, 0.26 * s)], fill=c)

    @staticmethod
    def reset(d, s, c, w):
        # Ouroboros: one open ring with a visible gap, single arrowhead
        # biting toward the tail end — clearly not a closed loop.
        d.arc([0.14 * s, 0.14 * s, 0.86 * s, 0.86 * s], start=15, end=300, fill=c, width=w)
        # Arrowhead at the head end (start=15deg, upper-right)
        d.polygon([(0.86 * s, 0.42 * s), (0.78 * s, 0.20 * s), (0.62 * s, 0.34 * s)], fill=c)
        # Tapered tail at the other end (end=300deg, lower-right) so the
        # ring visibly doesn't close — the head just falls short of it.
        d.ellipse([0.55 * s, 0.76 * s, 0.65 * s, 0.86 * s], fill=c)

    @staticmethod
    def copy(d, s, c, w):
        d.rounded_rectangle([0.32 * s, 0.32 * s, 0.86 * s, 0.86 * s], radius=0.08 * s,
                            outline=c, width=w)
        d.line([(0.20 * s, 0.66 * s), (0.14 * s, 0.66 * s), (0.14 * s, 0.14 * s),
                (0.66 * s, 0.14 * s), (0.66 * s, 0.20 * s)], fill=c, width=w, joint="curve")

    @staticmethod
    def user(d, s, c, w):
        d.ellipse([0.34 * s, 0.10 * s, 0.66 * s, 0.42 * s], fill=c)
        d.pieslice([0.16 * s, 0.48 * s, 0.84 * s, 1.16 * s], 180, 360, fill=c)

    @staticmethod
    def search(d, s, c, w):
        d.ellipse([0.14 * s, 0.14 * s, 0.64 * s, 0.64 * s], outline=c, width=w)
        d.line([(0.60 * s, 0.60 * s), (0.86 * s, 0.86 * s)], fill=c, width=w)

    @staticmethod
    def package(d, s, c, w):
        d.rounded_rectangle([0.14 * s, 0.26 * s, 0.86 * s, 0.86 * s], radius=0.06 * s,
                            outline=c, width=w)
        d.line([(0.14 * s, 0.46 * s), (0.86 * s, 0.46 * s)], fill=c, width=w)
        d.line([(0.42 * s, 0.46 * s), (0.42 * s, 0.62 * s), (0.58 * s, 0.62 * s),
                (0.58 * s, 0.46 * s)], fill=c, width=w)
        d.line([(0.14 * s, 0.28 * s), (0.24 * s, 0.14 * s), (0.76 * s, 0.14 * s),
                (0.86 * s, 0.28 * s)], fill=c, width=w, joint="curve")

    @staticmethod
    def bolt(d, s, c, w):
        d.polygon([(0.58 * s, 0.08 * s), (0.24 * s, 0.56 * s), (0.46 * s, 0.56 * s),
                   (0.40 * s, 0.92 * s), (0.76 * s, 0.42 * s), (0.53 * s, 0.42 * s)], fill=c)

    @staticmethod
    def trash(d, s, c, w):
        d.line([(0.16 * s, 0.26 * s), (0.84 * s, 0.26 * s)], fill=c, width=w)
        d.line([(0.38 * s, 0.26 * s), (0.38 * s, 0.14 * s), (0.62 * s, 0.14 * s),
                (0.62 * s, 0.26 * s)], fill=c, width=w, joint="curve")
        d.line([(0.24 * s, 0.26 * s), (0.30 * s, 0.88 * s)], fill=c, width=w)
        d.line([(0.76 * s, 0.26 * s), (0.70 * s, 0.88 * s)], fill=c, width=w)
        d.line([(0.30 * s, 0.88 * s), (0.70 * s, 0.88 * s)], fill=c, width=w)
        d.line([(0.42 * s, 0.40 * s), (0.44 * s, 0.74 * s)], fill=c, width=w)
        d.line([(0.58 * s, 0.40 * s), (0.56 * s, 0.74 * s)], fill=c, width=w)

    @staticmethod
    def dot(d, s, c, w):
        d.ellipse([0.22 * s, 0.22 * s, 0.78 * s, 0.78 * s], fill=c)

    @staticmethod
    def chevron_left(d, s, c, w):
        d.line([(0.62 * s, 0.18 * s), (0.34 * s, 0.50 * s), (0.62 * s, 0.82 * s)],
               fill=c, width=w, joint="curve")

    @staticmethod
    def chevron_right(d, s, c, w):
        d.line([(0.38 * s, 0.18 * s), (0.66 * s, 0.50 * s), (0.38 * s, 0.82 * s)],
               fill=c, width=w, joint="curve")

    @staticmethod
    def download(d, s, c, w):
        d.line([(0.5 * s, 0.10 * s), (0.5 * s, 0.60 * s)], fill=c, width=w)
        d.line([(0.28 * s, 0.42 * s), (0.5 * s, 0.64 * s), (0.72 * s, 0.42 * s)],
               fill=c, width=w, joint="curve")
        d.line([(0.16 * s, 0.80 * s), (0.84 * s, 0.80 * s)], fill=c, width=w)

    @staticmethod
    def link(d, s, c, w):
        d.arc([0.10 * s, 0.30 * s, 0.54 * s, 0.70 * s], 90, 270, fill=c, width=w)
        d.arc([0.46 * s, 0.30 * s, 0.90 * s, 0.70 * s], 270, 90, fill=c, width=w)
        d.line([(0.34 * s, 0.50 * s), (0.66 * s, 0.50 * s)], fill=c, width=w)


def _render(name: str, size: int, color: str) -> Image.Image:
    img, draw, s = _canvas(size)
    painter = getattr(_Painters, name)
    painter(draw, s, color, _stroke(size))
    return img.resize((size, size), Image.LANCZOS)


def icon(name: str, size: int = 16, color=None) -> ctk.CTkImage:
    """Return a cached CTkImage for `name`.

    `color` is either a single hex string (both modes) or a
    (light_mode_color, dark_mode_color) tuple.
    """
    if color is None:
        color = (DEFAULT_LIGHT, DEFAULT_DARK)
    if isinstance(color, str):
        color = (color, color)
    key = (name, size, color)
    if key not in _cache:
        _cache[key] = ctk.CTkImage(
            light_image=_render(name, size, color[0]),
            dark_image=_render(name, size, color[1]),
            size=(size, size),
        )
    return _cache[key]
