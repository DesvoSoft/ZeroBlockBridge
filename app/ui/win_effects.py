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
_DWMWA_CAPTION_COLOR = 35
_DWMWA_TEXT_COLOR = 36


def _colorref(hex_color: str) -> int:
    """'#RRGGBB' -> Windows COLORREF (0x00BBGGRR — reversed byte order)."""
    hex_color = hex_color.lstrip("#")
    r, g, b = (int(hex_color[i:i + 2], 16) for i in (0, 2, 4))
    return (b << 16) | (g << 8) | r


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


def apply_titlebar_brand_color(window, bg_hex: str, text_hex: str) -> None:
    """Tint a Win11 native titlebar with the app's own colors (DWMWA_CAPTION_COLOR
    / DWMWA_TEXT_COLOR, build 22000+ only). Keeps the OS-native titlebar — and
    with it every bit of native window behavior (taskbar entry, Aero Snap,
    Alt-Tab thumbnail, minimize/restore, resize borders) — while still giving
    the window a branded look instead of default Windows gray/black. No-op
    on Win10 or older Win11 builds (DwmSetWindowAttribute just fails, silently).

    A fully custom (frameless) titlebar was considered instead but rejected:
    overrideredirect() on Windows is notorious for losing the taskbar entry
    and breaking iconify/restore, which is a real regression for an app whose
    whole point is glanceable "is my server still up" status.
    """
    if sys.platform != "win32":
        return
    try:
        import ctypes
        window.update_idletasks()
        hwnd = _hwnd(window)
        caption = ctypes.c_int(_colorref(bg_hex))
        text = ctypes.c_int(_colorref(text_hex))
        ctypes.windll.dwmapi.DwmSetWindowAttribute(
            hwnd, _DWMWA_CAPTION_COLOR, ctypes.byref(caption), ctypes.sizeof(caption)
        )
        ctypes.windll.dwmapi.DwmSetWindowAttribute(
            hwnd, _DWMWA_TEXT_COLOR, ctypes.byref(text), ctypes.sizeof(text)
        )
    except (OSError, AttributeError) as e:
        logger.debug("DWM titlebar brand color unavailable: %s", e)


_WTA_NONCLIENT = 1
_WTNCA_NODRAWCAPTION = 0x1
_WTNCA_NODRAWICON = 0x2


def hide_titlebar_caption(window) -> None:
    """Minimal titlebar: don't draw the icon or the title text in it.

    SetWindowThemeAttribute only affects what the non-client area paints — the
    window keeps its title and icon for the taskbar, Alt-Tab and the system
    menu. Every window shows its own title in its body instead.
    """
    if sys.platform != "win32":
        return
    try:
        import ctypes
        from ctypes import wintypes

        class _WtaOptions(ctypes.Structure):
            _fields_ = [("dwFlags", wintypes.DWORD), ("dwMask", wintypes.DWORD)]

        flags = _WTNCA_NODRAWCAPTION | _WTNCA_NODRAWICON
        opts = _WtaOptions(flags, flags)
        window.update_idletasks()
        ctypes.windll.uxtheme.SetWindowThemeAttribute(
            _hwnd(window), _WTA_NONCLIENT, ctypes.byref(opts), ctypes.sizeof(opts))
    except (OSError, AttributeError) as e:
        logger.debug("Titlebar caption hiding unavailable: %s", e)


def _apply_app_icon(window) -> None:
    """Give a dialog the app's titlebar icon.

    CTkToplevel replaces the inherited default icon with CustomTkinter's own
    blue logo ~200ms after creation unless iconbitmap() was called on it.
    """
    import tkinter
    from app.core.constants import ASSETS_DIR
    try:
        window.iconbitmap(str(ASSETS_DIR / "logo.ico"))
    except tkinter.TclError as e:
        logger.debug("Window icon unavailable: %s", e)


def _brand_titlebar(window, caption_color=None) -> None:
    """Tint the titlebar like the window body and keep it in sync with
    Dark/Light switches (CTk only flips immersive dark mode, which leaves a
    default gray bar — or a stale brand color — behind).

    caption_color: (light, dark) hex pair; defaults to the window's fg_color.
    """
    import customtkinter as ctk
    from app.core.app_config import AppConfig

    if caption_color is None:
        caption_color = getattr(window, "_zbb_caption_color", None) or window.cget("fg_color")
    window._zbb_caption_color = caption_color
    light = ctk.get_appearance_mode() == "Light"
    if isinstance(caption_color, str):
        bg = caption_color
    else:
        bg = caption_color[0] if light else caption_color[1]
    text = AppConfig.COLOR_TEXT_PRIMARY[0] if light else AppConfig.COLOR_TEXT_PRIMARY[1]
    apply_titlebar_brand_color(window, bg, text)

    if getattr(window, "_zbb_caption_tracked", False):
        return
    window._zbb_caption_tracked = True

    def _on_mode_change(_mode):
        # Let CTk's own withdraw/deiconify titlebar refresh finish first.
        if window.winfo_exists():
            window.after(150, lambda: window.winfo_exists() and (
                _brand_titlebar(window), hide_titlebar_caption(window)))

    ctk.AppearanceModeTracker.add(_on_mode_change)
    window.bind("<Destroy>", lambda e: e.widget is window and ctk.AppearanceModeTracker.remove(_on_mode_change),
                add="+")


def apply_rounded_corners(window, small: bool = False, caption_color=None) -> None:
    """Round a Tk toplevel's corners via DWM. Win11 only; no-op elsewhere.

    Also themes and tints the titlebar to match the app (following live
    Dark/Light switches), keeps it minimal (no icon/title drawn in it) and
    sets the app icon for the taskbar — every window calls this, so it is the
    one shared hook.
    """
    if sys.platform != "win32":
        return
    if not window.winfo_ismapped() and not getattr(window, "_zbb_effects_on_map", False):
        # The native frame window only exists once Tk maps the toplevel; before
        # that the DWM/theme calls land on the inner child window and do
        # nothing (untinted bar, caption still drawn). Apply again on first map.
        window._zbb_effects_on_map = True

        def _on_map(event):
            if event.widget is window:
                window.unbind("<Map>", map_bind)
                apply_rounded_corners(window, small, caption_color)
        map_bind = window.bind("<Map>", _on_map, add="+")
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
    _brand_titlebar(window, caption_color)
    _apply_app_icon(window)
    hide_titlebar_caption(window)
    # CTkToplevel re-shows itself ~after creation to set its titlebar color,
    # which repaints the non-client area without the attribute.
    window.after(300, lambda: window.winfo_exists() and hide_titlebar_caption(window))
