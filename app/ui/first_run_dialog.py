"""First-run modal: pick where ZBB stores its data (servers/config/etc.).

Runs from `app.core.bootstrap.resolve_data_dir()`, BEFORE `app.ui.main` (and
therefore `app.core.constants`) is ever imported -- see bootstrap.py. This
module and everything it imports must stay free of any `app.core.constants`
dependency, directly or transitively (that rules out `app.ui.ui_components`,
which imports SERVERS_DIR at module level).

No app window exists yet at this point, so the dialog is its own `ctk.CTk`
root rather than a `CTkToplevel` (contrast with `EulaDialog`, which is a
Toplevel over the already-running `MCTunnelApp`).
"""

import logging
import os
import sys
import tkinter.filedialog
from pathlib import Path

import customtkinter as ctk

from app.core.app_config import AppConfig
from app.core.bootstrap import is_writable_dir
from app.ui.icons import icon
from app.ui.win_effects import apply_rounded_corners

logger = logging.getLogger(__name__)


def _resource_dir() -> Path:
    """Mirrors constants.py's _RESOURCE_DIR without importing it."""
    if getattr(sys, "frozen", False):
        return Path(getattr(sys, "_MEIPASS", Path(sys.executable).resolve().parent))
    return Path(__file__).resolve().parent.parent.parent


def _standard_dir() -> Path:
    local_appdata = os.environ.get("LOCALAPPDATA")
    base = Path(local_appdata) if local_appdata else Path.home()
    return base / "ZeroBlockBridge"


class _FirstRunDialog(ctk.CTk):
    def __init__(self, exe_dir: Path):
        super().__init__()
        self.result: Path | None = None
        self._exe_dir = exe_dir
        self._standard = _standard_dir()
        self._custom_dir: Path | None = None
        self._choice = ctk.StringVar(value="standard")

        self.title("Zero Block Bridge - Setup")
        self.resizable(False, False)
        self.configure(fg_color=(AppConfig.COLOR_BG_CARD_LIGHT, AppConfig.COLOR_BG_CARD_DARK))
        self.protocol("WM_DELETE_WINDOW", self._use_standard_and_close)

        frame = ctk.CTkFrame(self, fg_color="transparent")
        frame.pack(padx=30, pady=25, fill="both", expand=True)

        ctk.CTkLabel(
            frame, text="", image=icon("folder", 28, AppConfig.COLOR_BTN_PRIMARY),
        ).pack(anchor="w", pady=(0, 8))
        ctk.CTkLabel(
            frame, text="Where should ZBB store your data?",
            font=AppConfig.FONT_HEADING,
        ).pack(anchor="w", pady=(0, 6))
        ctk.CTkLabel(
            frame,
            text="Servers, backups, config and downloaded Java runtimes\nwill live here.",
            font=AppConfig.FONT_BODY, justify="left", text_color=AppConfig.COLOR_TEXT_GRAY,
        ).pack(anchor="w", pady=(0, 18))

        self._custom_path_label = self._build_option(
            frame, "standard", "Standard (recommended)", str(self._standard),
        )
        self._build_option(frame, "portable", "Portable (next to the app)", str(exe_dir))
        self._custom_path_label = self._build_option(
            frame, "custom", "Choose folder...", "No folder selected yet", browse=True,
        )

        self._error_label = ctk.CTkLabel(
            frame, text="", font=AppConfig.FONT_BODY_SMALL,
            text_color=AppConfig.COLOR_STATUS_ERROR,
        )
        self._error_label.pack(anchor="w", pady=(6, 0))

        buttons = ctk.CTkFrame(frame, fg_color="transparent")
        buttons.pack(fill="x", pady=(14, 0))
        ctk.CTkButton(
            buttons, text="Continue", corner_radius=AppConfig.RADIUS_BTN, width=160,
            fg_color=AppConfig.COLOR_BTN_PRIMARY, hover_color=AppConfig.COLOR_BTN_PRIMARY_HOVER,
            command=self._confirm,
        ).pack(side="right")

        apply_rounded_corners(self)
        self.update_idletasks()
        self._center()
        self.focus_force()

    def _build_option(self, parent, value, title, subtitle, browse=False):
        row = ctk.CTkFrame(parent, fg_color="transparent")
        row.pack(fill="x", pady=4)
        ctk.CTkRadioButton(
            row, text=title, variable=self._choice, value=value,
            font=AppConfig.FONT_BODY, fg_color=AppConfig.COLOR_BTN_PRIMARY,
            command=lambda: self._on_pick(value, browse),
        ).pack(anchor="w")
        sub = ctk.CTkLabel(
            row, text=subtitle, font=AppConfig.FONT_BODY_SMALL,
            text_color=AppConfig.COLOR_TEXT_MUTED, anchor="w",
        )
        sub.pack(anchor="w", padx=(28, 0))
        return sub

    def _on_pick(self, value, browse):
        self._error_label.configure(text="")
        if value != "custom":
            return
        if browse:
            chosen = tkinter.filedialog.askdirectory(
                title="Choose data folder", mustexist=False,
            )
            if chosen:
                self._custom_dir = Path(chosen)
                self._custom_path_label.configure(text=str(self._custom_dir))
            elif self._custom_dir is None:
                # No prior selection and dialog was cancelled -- fall back
                # so "custom" isn't left pointing at nothing.
                self._choice.set("standard")

    def _center(self):
        try:
            self.update_idletasks()
            w, h = self.winfo_reqwidth(), self.winfo_reqheight()
            sw, sh = self.winfo_screenwidth(), self.winfo_screenheight()
            self.geometry(f"+{max((sw - w) // 2, 0)}+{max((sh - h) // 2, 0)}")
        except Exception as e:
            logger.debug("First-run dialog centering failed: %s", e)

    def _target_dir(self) -> Path | None:
        choice = self._choice.get()
        if choice == "standard":
            return self._standard
        if choice == "portable":
            return self._exe_dir
        return self._custom_dir

    def _confirm(self):
        target = self._target_dir()
        if target is None:
            self._error_label.configure(text="Pick a folder first.")
            return
        if not is_writable_dir(target):
            self._error_label.configure(text=f"Can't write to {target} -- pick another folder.")
            return
        self.result = target
        self.destroy()

    def _use_standard_and_close(self):
        self.result = self._standard
        self.destroy()


def ask_data_dir(exe_dir: Path) -> Path:
    """Blocks until the user picks (or the window is closed, defaulting
    to Standard) a data directory. Sets up the ctk theme/appearance
    fresh since no app window has run yet."""
    theme_path = _resource_dir() / "assets" / "zbb_theme.json"
    ctk.set_appearance_mode("dark")
    ctk.set_default_color_theme(str(theme_path) if theme_path.exists() else "green")

    dialog = _FirstRunDialog(exe_dir)
    dialog.mainloop()
    return dialog.result if dialog.result is not None else dialog._standard
