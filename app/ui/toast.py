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

# Cap concurrent toasts per window — a notification flood (e.g. a
# crash-restart loop) piling up past the top of the window is unreadable.
_MAX_TOASTS_PER_WINDOW = 4

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

        # Icon badge: PIL icon when one exists, letter fallback otherwise.
        # corner_radius is half the badge size (circle), not a card/button/badge token.
        badge_size = 24
        if isinstance(icon_char, tuple):
            badge = ctk.CTkLabel(
                inner, text="", image=icon(icon_char[1], 12, AppConfig.COLOR_TEXT_ON_ACCENT),
                width=badge_size, height=badge_size, fg_color=border_color, corner_radius=badge_size // 2,
            )
        else:
            badge = ctk.CTkLabel(
                inner, text=icon_char, width=badge_size, height=badge_size,
                font=AppConfig.FONT_SUBHEADING, text_color=AppConfig.COLOR_TEXT_ON_ACCENT,
                fg_color=border_color, corner_radius=badge_size // 2,
            )
        badge.pack(side="left", padx=(0, 10))

        # Message
        ctk.CTkLabel(
            inner, text=message, text_color=AppConfig.COLOR_TEXT_PRIMARY,
            font=AppConfig.FONT_CAPTION, wraplength=320, justify="left",
        ).pack(side="left", fill="x", expand=True)

        # Callers pass all sorts of widgets as "parent" (the main window, a
        # dialog, sometimes a plain frame) — anchor to the real containing
        # window so the toast lands at ITS bottom-right corner, and so
        # stacking below groups correctly by window instead of mixing
        # toasts from unrelated windows into one offset count.
        anchor = parent.winfo_toplevel()

        # A flood of toasts (e.g. a crash-restart loop) piling up past the
        # top of the window is unreadable — drop the oldest one for this
        # window before adding a new one.
        siblings = [t for t in self._active_toasts
                    if t.winfo_exists() and getattr(t, "_zbb_anchor", None) is anchor]
        while len(siblings) >= _MAX_TOASTS_PER_WINDOW:
            self._destroy_toast(siblings.pop(0))

        # Position: bottom-right of the anchor window, stacked vertically
        anchor.update_idletasks()
        toast.update_idletasks()
        tw = max(toast.winfo_reqwidth(), 280)
        th = toast.winfo_reqheight()
        pw = anchor.winfo_width()
        ph = anchor.winfo_height()

        # Cumulative height of this window's own still-live toasts — using a
        # per-toast real height (not "count * this toast's height", which
        # broke down as soon as two toasts had different wrapped-text heights).
        offset_y = sum(getattr(t, "_zbb_height", 0) + 10 for t in siblings)
        x = anchor.winfo_rootx() + pw - tw - 20
        y = anchor.winfo_rooty() + ph - th - 20 - offset_y
        y = max(y, anchor.winfo_rooty() + 10)
        # Start slightly below the resting spot — slide-up + fade-in reads as
        # the toast "arriving" instead of just popping into existence.
        slide_offset = 14
        toast.geometry(f"{tw}x{th}+{x}+{y + slide_offset}")
        apply_rounded_corners(toast, small=True)

        toast._zbb_anchor = anchor
        toast._zbb_height = th
        self._active_toasts.append(toast)

        # Fade-in + slide-up
        self._animate_alpha(toast, 0.0, 0.95, steps=8, delay=25)
        self._animate_slide(toast, x, y + slide_offset, y, steps=8, delay=25)

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

    def _animate_slide(self, toast, x, start_y, end_y, steps, delay):
        """Animate the toast's vertical position (paired with _animate_alpha
        for a slide-up-and-fade-in arrival instead of an instant pop-in)."""
        if not toast or not toast.winfo_exists():
            return
        delta = (end_y - start_y) / steps

        def _step(i, current_y):
            if not toast.winfo_exists():
                return
            try:
                toast.geometry(f"+{x}+{round(current_y)}")
            except Exception as e:
                logger.debug("Toast slide error: %s", e)
                return
            if i < steps:
                toast.after(delay, _step, i + 1, current_y + delta)

        _step(0, start_y)

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
        """Recompute vertical position of remaining active toasts to close gaps.

        Grouped per anchor window and offset by each toast's own real height
        (not index * this-toast's-height) — two windows with toasts open at
        once, or two toasts of different wrapped-text heights, used to
        produce overlapping/misplaced positions.
        """
        seen_per_anchor: dict = {}
        for toast in self._active_toasts:
            if not toast.winfo_exists():
                continue
            anchor = getattr(toast, "_zbb_anchor", None)
            th = getattr(toast, "_zbb_height", None)
            if anchor is None or th is None:
                continue
            offset_y = seen_per_anchor.get(id(anchor), 0)
            seen_per_anchor[id(anchor)] = offset_y + th + 10
            try:
                tw = toast.winfo_width()
                pw = anchor.winfo_width()
                ph = anchor.winfo_height()
                x = anchor.winfo_rootx() + pw - tw - 20
                y = anchor.winfo_rooty() + ph - th - 20 - offset_y
                y = max(y, anchor.winfo_rooty() + 10)
                toast.geometry(f"{tw}x{th}+{x}+{y}")
            except Exception as e:
                logger.debug("Toast reflow error: %s", e)

    def dismiss(self) -> None:
        """Clear all active toasts immediately."""
        for toast in list(self._active_toasts):
            self._destroy_toast(toast)


    @staticmethod
    def resolve_type(data: dict) -> str:
        """Toast type from a NOTIFICATION payload ({"type": ...}); unknown or
        missing types fall back to "info"."""
        toast_type = data.get("type")
        return toast_type if toast_type in _TOAST_STYLES else "info"


# Module-level singleton
Toast = ToastNotification()
