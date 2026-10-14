"""Asked when the main window's X is clicked: minimize to the tray or exit."""

import logging

import customtkinter as ctk

from app.core.app_config import AppConfig
from app.ui.icons import icon
from app.ui.tray import CLOSE_EXIT, CLOSE_TRAY
from app.ui.ui_components import ZBBToplevel, center_on_parent, dialog_buttons
from app.ui.win_effects import apply_rounded_corners

logger = logging.getLogger(__name__)


def close_message(running: list) -> str:
    """Body text; `running` names what exiting would stop (e.g. a server)."""
    text = ("Keep ZeroBlockBridge running in the system tray, or exit it completely?")
    if running:
        text += "\n\nExiting will stop: " + ", ".join(running) + "."
    return text


class CloseChoiceDialog(ZBBToplevel):
    def __init__(self, parent, running: list):
        super().__init__(parent)
        self.choice = None  # CLOSE_TRAY / CLOSE_EXIT, None when cancelled
        self.title("Close ZeroBlockBridge")
        self.resizable(False, False)
        self.configure(fg_color=(AppConfig.COLOR_BG_CARD_LIGHT, AppConfig.COLOR_BG_CARD_DARK))
        self.protocol("WM_DELETE_WINDOW", self._cancel)
        self.var_remember = ctk.BooleanVar(value=False)

        frame = ctk.CTkFrame(self, fg_color="transparent")
        frame.pack(padx=25, pady=20, fill="both", expand=True)
        header = ctk.CTkFrame(frame, fg_color="transparent")
        header.pack(fill="x", pady=(0, 8))
        ctk.CTkLabel(header, text="", image=icon("dot", 18, AppConfig.COLOR_BTN_PRIMARY), width=18
                     ).pack(side="left", padx=(0, 8))
        ctk.CTkLabel(header, text="Close ZeroBlockBridge?", font=AppConfig.FONT_HEADING_SMALL).pack(side="left")
        ctk.CTkLabel(frame, text=close_message(running), font=AppConfig.FONT_BODY, justify="left",
                     wraplength=400, anchor="w").pack(anchor="w", fill="x", pady=(0, 12))
        ctk.CTkCheckBox(frame, text="Don't ask again (change it in Settings > General)",
                        variable=self.var_remember, font=AppConfig.FONT_BODY_SMALL,
                        fg_color=AppConfig.COLOR_BTN_PRIMARY, corner_radius=AppConfig.RADIUS_BADGE,
                        ).pack(anchor="w", pady=(0, 16))

        buttons, btn_tray, _ = dialog_buttons(frame, "Minimize to tray", lambda: self._pick(CLOSE_TRAY),
                                              "Exit", lambda: self._pick(CLOSE_EXIT), primary_width=150)
        buttons.pack(fill="x")
        self.bind("<Escape>", lambda e: self._cancel())

        apply_rounded_corners(self)
        self.update_idletasks()
        center_on_parent(self, parent, self.winfo_reqwidth(), self.winfo_reqheight())
        self.transient(parent)
        try:
            self.wait_visibility()
            self.grab_set()
        except Exception as e:
            logger.debug("Close dialog grab failed: %s", e)
        btn_tray.focus_set()

    def _pick(self, choice):
        self.choice = choice
        self._close()

    def _cancel(self):
        self.choice = None
        self._close()

    def _close(self):
        try:
            self.grab_release()
        except Exception as e:
            logger.debug("Close dialog grab release failed: %s", e)
        self.destroy()

    @classmethod
    def ask(cls, parent, running: list):
        """(choice or None, remember)."""
        dialog = cls(parent, running)
        parent.wait_window(dialog)
        return dialog.choice, bool(dialog.var_remember.get())
