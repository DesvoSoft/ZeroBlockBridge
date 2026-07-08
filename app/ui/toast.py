"""
REND-02 — Neo-Modern Toast Notification System.

Non-blocking, animated notification overlay that renders in the
bottom-right corner of the parent window. Supports INFO, WARNING,
and ERROR types with distinct color schemes from the Slate palette.

Integrated with the EventBus via ServerEvent.NOTIFICATION payloads.
"""

import customtkinter as ctk
import logging
from typing import Any

from app.core.app_config import AppConfig
from app.ui.icons import icon
from app.ui.win_effects import apply_rounded_corners

logger = logging.getLogger(__name__)

# Toast type -> (bg_color, border_color, badge)
# bg_color uses AppConfig card tokens to adapt to light/dark mode.
# badge is a letter for info/warning (no matching PIL icon) and an
# icons.py name for success/error.
_CARD_BG = (AppConfig.COLOR_BG_CARD_LIGHT, AppConfig.COLOR_BG_CARD_DARK)
_TOAST_STYLES = {
    "info":    (_CARD_BG, AppConfig.COLOR_BTN_PRIMARY, "i"),
    "success": (_CARD_BG, AppConfig.COLOR_BTN_SUCCESS, ("icon", "check")),
    "warning": (_CARD_BG, AppConfig.COLOR_ACCENT_AMBER, "!"),
    "error":   (_CARD_BG, AppConfig.COLOR_BTN_DANGER, ("icon", "close")),
}

# Fallback color mapping from raw color names to toast types
_COLOR_TYPE_MAP = {
    "red": "error",
    "#ef4444": "error",
    "orange": "warning",
    "#f97316": "warning",
    "blue": "info",
    "#3b82f6": "info",
    "green": "success",
    "white": "info",
}


class ToastNotification:
    """Manages a queue of floating toast notifications with fade animations.
    
    Now supports multiple concurrent toasts to prevent window orphans
    and race conditions.
    """
    def __init__(self) -> None:
        self._active_toasts: list = []

    def show(self, parent: Any, message: str, toast_type: str = "info",
              duration: int = 4000) -> None:
        """Display a toast notification."""
        style = _TOAST_STYLES.get(toast_type, _TOAST_STYLES["info"])
        bg_color, border_color, icon_char = style

        toast = ctk.CTkToplevel(parent)
        toast.overrideredirect(True)
        toast.attributes("-topmost", True)
        toast.attributes("-alpha", 0.0)
        toast.configure(fg_color=(AppConfig.COLOR_BG_CARD_LIGHT, AppConfig.COLOR_BG_CARD_DARK))

        # Outer frame with border accent
        outer = ctk.CTkFrame(
            toast, fg_color=bg_color, corner_radius=0,
            border_width=2, border_color=border_color,
        )
        outer.pack(fill="both", expand=True, padx=2, pady=2)

        inner = ctk.CTkFrame(outer, fg_color="transparent")
        inner.pack(fill="both", expand=True, padx=12, pady=10)

        # Icon badge: PIL icon when one exists, letter fallback otherwise
        if isinstance(icon_char, tuple):
            badge = ctk.CTkLabel(
                inner, text="", image=icon(icon_char[1], 12, "#ffffff"),
                width=24, height=24, fg_color=border_color, corner_radius=12,
            )
        else:
            badge = ctk.CTkLabel(
                inner, text=icon_char, width=24, height=24,
                font=(AppConfig.FONT_FAMILY_DISPLAY, 13, "bold"), text_color="white",
                fg_color=border_color, corner_radius=12,
            )
        badge.pack(side="left", padx=(0, 10))

        # Message
        ctk.CTkLabel(
            inner, text=message, text_color=AppConfig.COLOR_TEXT_PRIMARY,
            font=(AppConfig.FONT_FAMILY, 12), wraplength=320, justify="left",
        ).pack(side="left", fill="x", expand=True)

        # Position: bottom-right, stacked vertically
        parent.update_idletasks()
        toast.update_idletasks()
        tw = max(toast.winfo_reqwidth(), 280)
        th = toast.winfo_reqheight()
        pw = parent.winfo_width()
        ph = parent.winfo_height()
        
        # Offset based on current active toasts
        offset_y = len(self._active_toasts) * (th + 10)
        x = parent.winfo_rootx() + pw - tw - 20
        y = parent.winfo_rooty() + ph - th - 20 - offset_y
        y = max(y, parent.winfo_rooty() + 10)
        toast.geometry(f"{tw}x{th}+{x}+{y}")
        apply_rounded_corners(toast, small=True)

        toast._zbb_parent = parent
        toast._zbb_height = th
        self._active_toasts.append(toast)

        # Fade-in
        self._animate_alpha(toast, 0.0, 0.95, steps=8, delay=25)

        # Schedule fade-out then destroy
        toast.after(duration, lambda: self._fade_out(toast))

    def _fade_out(self, toast):
        """Animate fade-out, then destroy."""
        self._animate_alpha(toast, 0.95, 0.0, steps=8, delay=25,
                            on_complete=lambda: self._destroy_toast(toast))

    def _animate_alpha(self, toast, start, end, steps, delay,
                       on_complete=None):
        """Smooth alpha transition."""
        if not toast or not toast.winfo_exists():
            return
        delta = (end - start) / steps

        def _step(i, current):
            if not toast.winfo_exists():
                return
            try:
                toast.attributes("-alpha", current)
            except Exception as e:
                logger.debug("Toast animate error: %s", e)
                return
            if i < steps:
                toast.after(delay, _step, i + 1, current + delta)
            elif on_complete:
                on_complete()

        _step(0, start)

    def _destroy_toast(self, toast):
        """Safe destruction and removal from tracking list."""
        if toast in self._active_toasts:
            self._active_toasts.remove(toast)
        try:
            toast.destroy()
        except Exception as e:
            logger.debug("Toast hide error: %s", e)
        self._reflow_toasts()

    def _reflow_toasts(self):
        """Recompute vertical position of remaining active toasts to close gaps."""
        for i, toast in enumerate(self._active_toasts):
            if not toast.winfo_exists():
                continue
            parent = getattr(toast, "_zbb_parent", None)
            th = getattr(toast, "_zbb_height", None)
            if parent is None or th is None:
                continue
            try:
                tw = toast.winfo_width()
                pw = parent.winfo_width()
                ph = parent.winfo_height()
                offset_y = i * (th + 10)
                x = parent.winfo_rootx() + pw - tw - 20
                y = parent.winfo_rooty() + ph - th - 20 - offset_y
                y = max(y, parent.winfo_rooty() + 10)
                toast.geometry(f"{tw}x{th}+{x}+{y}")
            except Exception as e:
                logger.debug("Toast reflow error: %s", e)

    def dismiss(self) -> None:
        """Clear all active toasts immediately."""
        for toast in list(self._active_toasts):
            self._destroy_toast(toast)


    @staticmethod
    def resolve_type(data: dict) -> str:
        """Extract toast type from a NOTIFICATION event payload.

        Supports both new {"type": "warning"} and legacy {"color": "red"} formats.
        """
        if "type" in data:
            return data["type"] if data["type"] in _TOAST_STYLES else "info"
        color = data.get("color", "")
        return _COLOR_TYPE_MAP.get(color, "info")


# Module-level singleton
Toast = ToastNotification()
