"""Windows 11 native window effects (best-effort, no-op elsewhere).

CTk cannot draw drop shadows or antialiased window corners; DWM can.
`apply_rounded_corners` asks the compositor to round a toplevel's corners
(DWMWA_WINDOW_CORNER_PREFERENCE, Win11+). Silently does nothing on
Win10/other platforms.
"""

import logging
import sys

logger = logging.getLogger(__name__)

_DWMWA_WINDOW_CORNER_PREFERENCE = 33
_DWMWCP_ROUND = 2
_DWMWCP_ROUNDSMALL = 3
_DWMWA_USE_IMMERSIVE_DARK_MODE = 20
_DWMWA_USE_IMMERSIVE_DARK_MODE_BEFORE_20H1 = 19


def _hwnd(window):
    import ctypes
    return ctypes.windll.user32.GetParent(window.winfo_id()) or window.winfo_id()


def apply_titlebar_theme(window) -> None:
    """Match the Win11 titlebar to the active CTk appearance mode.

    CTkToplevel tries this itself at creation, but before the window is
    realized the DWM call can silently fail and the titlebar stays white
    in dark mode. Call after update_idletasks for a valid hwnd; safe to
    re-call on live theme switches. No-op off Windows.
    """
    if sys.platform != "win32":
        return
    try:
        import ctypes
        import customtkinter as ctk
        value = ctypes.c_int(0 if ctk.get_appearance_mode() == "Light" else 1)
        hwnd = _hwnd(window)
        if ctypes.windll.dwmapi.DwmSetWindowAttribute(
            hwnd, _DWMWA_USE_IMMERSIVE_DARK_MODE, ctypes.byref(value), ctypes.sizeof(value)
        ) != 0:
            ctypes.windll.dwmapi.DwmSetWindowAttribute(
                hwnd, _DWMWA_USE_IMMERSIVE_DARK_MODE_BEFORE_20H1,
                ctypes.byref(value), ctypes.sizeof(value)
            )
    except (OSError, AttributeError) as e:
        logger.debug("DWM titlebar theme unavailable: %s", e)


def apply_rounded_corners(window, small: bool = False) -> None:
    """Round a Tk toplevel's corners via DWM. Win11 only; no-op elsewhere.

    Also themes the titlebar (dark/light) to match the app.
    """
    if sys.platform != "win32":
        return
    try:
        import ctypes
        window.update_idletasks()
        hwnd = _hwnd(window)
        pref = ctypes.c_int(_DWMWCP_ROUNDSMALL if small else _DWMWCP_ROUND)
        ctypes.windll.dwmapi.DwmSetWindowAttribute(
            hwnd, _DWMWA_WINDOW_CORNER_PREFERENCE, ctypes.byref(pref), ctypes.sizeof(pref)
        )
    except (OSError, AttributeError) as e:
        logger.debug("DWM rounded corners unavailable: %s", e)
    apply_titlebar_theme(window)
