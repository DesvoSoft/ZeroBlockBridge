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


def apply_rounded_corners(window, small: bool = False) -> None:
    """Round a Tk toplevel's corners via DWM. Win11 only; no-op elsewhere."""
    if sys.platform != "win32":
        return
    try:
        import ctypes
        window.update_idletasks()
        hwnd = ctypes.windll.user32.GetParent(window.winfo_id()) or window.winfo_id()
        pref = ctypes.c_int(_DWMWCP_ROUNDSMALL if small else _DWMWCP_ROUND)
        ctypes.windll.dwmapi.DwmSetWindowAttribute(
            hwnd, _DWMWA_WINDOW_CORNER_PREFERENCE, ctypes.byref(pref), ctypes.sizeof(pref)
        )
    except (OSError, AttributeError) as e:
        logger.debug("DWM rounded corners unavailable: %s", e)
