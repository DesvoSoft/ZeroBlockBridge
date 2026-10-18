"""Windows 11 system backdrop (Mica / acrylic) and dark title bar via DWM.

The window's client area must be transparent where the backdrop should
show (``WA_TranslucentBackground`` for Widgets, ``color: "transparent"``
for a QQuickWindow); the frame is extended over the whole client area.
No-op (returns False) before Windows 11 22H2 or off Windows.
"""

from __future__ import annotations

import ctypes
import logging
import sys

logger = logging.getLogger(__name__)

DWMWA_USE_IMMERSIVE_DARK_MODE = 20
DWMWA_SYSTEMBACKDROP_TYPE = 38
BACKDROP = {"none": 1, "mica": 2, "acrylic": 3, "tabbed": 4}


class _Margins(ctypes.Structure):
    _fields_ = [("left", ctypes.c_int), ("right", ctypes.c_int),
                ("top", ctypes.c_int), ("bottom", ctypes.c_int)]


def set_dark_frame(hwnd: int, dark: bool) -> None:
    """Dark or light window border and shadow tint, without a backdrop."""
    if sys.platform != "win32":
        return
    try:
        value = ctypes.c_int(1 if dark else 0)
        ctypes.windll.dwmapi.DwmSetWindowAttribute(ctypes.c_void_p(hwnd), DWMWA_USE_IMMERSIVE_DARK_MODE,
                                                   ctypes.byref(value), ctypes.sizeof(value))
    except (AttributeError, OSError) as exc:
        logger.debug("DWM dark mode failed: %s", exc)


def apply(hwnd: int, dark: bool, kind: str = "mica") -> bool:
    if sys.platform != "win32" or sys.getwindowsversion().build < 22621:
        return False
    try:
        dwm = ctypes.windll.dwmapi
        value = ctypes.c_int(1 if dark else 0)
        dwm.DwmSetWindowAttribute(ctypes.c_void_p(hwnd), DWMWA_USE_IMMERSIVE_DARK_MODE,
                                  ctypes.byref(value), ctypes.sizeof(value))
        margins = _Margins(-1, -1, -1, -1)
        dwm.DwmExtendFrameIntoClientArea(ctypes.c_void_p(hwnd), ctypes.byref(margins))
        backdrop = ctypes.c_int(BACKDROP[kind])
        hr = dwm.DwmSetWindowAttribute(ctypes.c_void_p(hwnd), DWMWA_SYSTEMBACKDROP_TYPE,
                                       ctypes.byref(backdrop), ctypes.sizeof(backdrop))
        return hr == 0
    except (AttributeError, OSError) as exc:
        logger.debug("DWM backdrop failed: %s", exc)
        return False
