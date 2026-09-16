"""Pure helpers for persisting the main window's geometry between sessions.

Kept free of Tk so the validation logic is unit-testable headless.
"""

import re
from typing import Optional

_GEOMETRY_RE = re.compile(r"^(\d+)x(\d+)([+-]-?\d+)([+-]-?\d+)$")

# How much of the titlebar must land on a screen for a restored position to
# count as reachable (a monitor that was unplugged leaves it off-screen).
_VISIBLE_MARGIN = 80


def parse_geometry(value) -> Optional[tuple[int, int, int, int]]:
    """'WxH+X+Y' -> (w, h, x, y), or None if it isn't a full geometry string."""
    if not isinstance(value, str):
        return None
    match = _GEOMETRY_RE.match(value.strip())
    if not match:
        return None
    w, h = int(match.group(1)), int(match.group(2))
    x, y = int(match.group(3).replace("+", "")), int(match.group(4).replace("+", ""))
    return w, h, x, y


def restorable_geometry(value, min_size: tuple[int, int],
                        screen: tuple[int, int, int, int]) -> Optional[str]:
    """Validate a saved geometry against the current screen area.

    screen is (left, top, width, height) of the virtual desktop. Returns a
    geometry string safe to apply (size clamped to min_size and to the
    screen), or None when nothing usable was saved or the window would open
    off-screen.
    """
    parsed = parse_geometry(value)
    if parsed is None:
        return None
    w, h, x, y = parsed
    left, top, screen_w, screen_h = screen
    w = max(min_size[0], min(w, screen_w))
    h = max(min_size[1], min(h, screen_h))
    if x + w < left + _VISIBLE_MARGIN or x > left + screen_w - _VISIBLE_MARGIN:
        return None
    if y < top or y > top + screen_h - _VISIBLE_MARGIN:
        return None
    return f"{w}x{h}+{x}+{y}"
