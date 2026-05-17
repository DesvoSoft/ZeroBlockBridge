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

logger = logging.getLogger(__name__)

# Toast type -> (bg_color, border_color, icon)
_TOAST_STYLES = {
    "info":    ("#1e293b", "#3b82f6", "i"),       # Slate-800 + Blue-500
    "success": ("#1e293b", "#22c55e", "\u2713"),   # Slate-800 + Green-500
    "warning": ("#1e293b", "#f97316", "!"),        # Slate-800 + Orange-500
    "error":   ("#1e293b", "#ef4444", "x"),        # Slate-800 + Red-500
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
        toast.configure(fg_color="#1e293b")

        # Outer frame with border accent
        outer = ctk.CTkFrame(
            toast, fg_color=bg_color, corner_radius=0,
            border_width=2, border_color=border_color,
        )
        outer.pack(fill="both", expand=True, padx=2, pady=2)

        inner = ctk.CTkFrame(outer, fg_color="transparent")
        inner.pack(fill="both", expand=True, padx=12, pady=10)

        # Icon badge
        ctk.CTkLabel(
            inner, text=icon_char, width=24, height=24,
            font=("Roboto Medium", 13), text_color="white",
            fg_color=border_color, corner_radius=12,
        ).pack(side="left", padx=(0, 10))

        # Message
        ctk.CTkLabel(
            inner, text=message, text_color="#e2e8f0",
            font=("Roboto", 12), wraplength=320, justify="left",
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
        toast.geometry(f"{tw}x{th}+{x}+{y}")

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
            except Exception:
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
        except Exception:
            pass

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
