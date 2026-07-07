"""Application-wide settings dialog (gear button in the sidebar).

Currently hosts the Notifications section (Discord webhook). New global
sections (theme, paths, ...) belong here, not in the per-server editor.
"""
import logging
import threading

import customtkinter as ctk

from app.core.app_config import AppConfig
from app.services.discord_webhook import DiscordWebhookService
from app.services.settings_manager import SettingsManager
from app.ui.icons import icon
from app.ui.toast import Toast
from app.ui.ui_components import ZBBDialog, center_on_parent
from app.ui.win_effects import apply_rounded_corners

logger = logging.getLogger(__name__)

_WEBHOOK_PREFIXES = (
    "https://discord.com/api/webhooks/",
    "https://discordapp.com/api/webhooks/",
)


class AppSettingsDialog(ctk.CTkToplevel):
    def __init__(self, master, zbb_manager, **kwargs):
        super().__init__(master, **kwargs)
        self.title("Settings")
        self.geometry("560x340")
        center_on_parent(self, master, 560, 340)
        self.minsize(480, 300)
        self.transient(master)
        self.lift()
        self.focus_force()
        apply_rounded_corners(self)

        self.zbb_manager = zbb_manager
        self._settings = SettingsManager()

        self.grid_columnconfigure(0, weight=1)

        header = ctk.CTkLabel(self, text="Application Settings", font=AppConfig.FONT_HEADING, anchor="w")
        header.grid(row=0, column=0, sticky="ew", padx=20, pady=(18, 8))

        self._build_notifications_section()

    def _build_notifications_section(self):
        lbl_section = ctk.CTkLabel(
            self, text="NOTIFICATIONS",
            font=(AppConfig.FONT_FAMILY_DISPLAY, 11, "bold"),
            text_color=AppConfig.COLOR_TEXT_GRAY, anchor="w",
        )
        lbl_section.grid(row=1, column=0, sticky="ew", padx=20, pady=(8, 2))

        card = ctk.CTkFrame(
            self, corner_radius=AppConfig.RADIUS_CARD, border_width=0,
            fg_color=(AppConfig.COLOR_BG_CARD_LIGHT, AppConfig.COLOR_BG_CARD_DARK),
        )
        card.grid(row=2, column=0, sticky="ew", padx=20, pady=(2, 10))
        card.grid_columnconfigure(0, weight=1)

        lbl_title = ctk.CTkLabel(card, text="Discord Webhook", font=AppConfig.FONT_BODY, anchor="w")
        lbl_title.grid(row=0, column=0, sticky="ew", padx=15, pady=(12, 0))

        lbl_hint = ctk.CTkLabel(
            card,
            text="Posts crash, ready and backup events to a Discord channel.\n"
                 "Server Settings > Integrations > Webhooks > Copy Webhook URL. Leave empty to disable.",
            font=AppConfig.FONT_BODY_SMALL, text_color=AppConfig.COLOR_TEXT_GRAY,
            anchor="w", justify="left",
        )
        lbl_hint.grid(row=1, column=0, sticky="ew", padx=15, pady=(2, 8))

        self.entry_webhook = ctk.CTkEntry(
            card, placeholder_text="https://discord.com/api/webhooks/...",
            corner_radius=AppConfig.RADIUS_BTN, height=32,
        )
        self.entry_webhook.grid(row=2, column=0, sticky="ew", padx=15, pady=(0, 10))
        current = self._settings.get("discord_webhook_url", "")
        if current:
            self.entry_webhook.insert(0, current)

        btn_row = ctk.CTkFrame(card, fg_color="transparent")
        btn_row.grid(row=3, column=0, sticky="ew", padx=15, pady=(0, 12))

        self.btn_test = ctk.CTkButton(
            btn_row, text="Send Test", image=icon("bolt", 13),
            command=self._send_test, corner_radius=AppConfig.RADIUS_BTN, height=32, width=110,
            fg_color="transparent", border_width=1,
            border_color=(AppConfig.COLOR_BORDER_LIGHT, AppConfig.COLOR_BORDER_DARK),
            text_color=("#0f172a", AppConfig.COLOR_TEXT_PRIMARY),
            hover_color=(AppConfig.COLOR_BG_SIDEBAR_LIGHT, AppConfig.COLOR_BTN_GHOST),
            font=(AppConfig.FONT_FAMILY, 12),
        )
        self.btn_test.pack(side="left")

        self.btn_save = ctk.CTkButton(
            btn_row, text="Save", image=icon("check", 13, "#ffffff"),
            command=self._save, corner_radius=AppConfig.RADIUS_BTN, height=32, width=110,
            fg_color=AppConfig.COLOR_BTN_PRIMARY, hover_color=AppConfig.COLOR_BTN_PRIMARY_HOVER,
            font=(AppConfig.FONT_FAMILY_DISPLAY, 12, "bold"),
        )
        self.btn_save.pack(side="right")

    def _current_url(self) -> str:
        return self.entry_webhook.get().strip()

    def _validate(self, url: str) -> bool:
        if url and not url.startswith(_WEBHOOK_PREFIXES):
            ZBBDialog.info(
                self, "Invalid Webhook URL",
                "That does not look like a Discord webhook URL.\n"
                "It must start with:\nhttps://discord.com/api/webhooks/...",
                kind="error",
            )
            return False
        return True

    def _save(self):
        url = self._current_url()
        if not self._validate(url):
            return
        self._settings.set("discord_webhook_url", url)
        self.zbb_manager.reload_discord_webhook()
        if url:
            Toast.show(self, "Discord notifications enabled.", toast_type="success")
        else:
            Toast.show(self, "Discord notifications disabled.", toast_type="info")

    def _send_test(self):
        url = self._current_url()
        if not url:
            ZBBDialog.info(self, "No URL", "Enter a webhook URL first.", kind="warning")
            return
        if not self._validate(url):
            return
        self.btn_test.configure(state="disabled", text="Sending...")

        def _worker():
            ok, error = DiscordWebhookService.send_test(url)
            def _apply():
                if not self.winfo_exists():
                    return
                self.btn_test.configure(state="normal", text="Send Test")
                if ok:
                    Toast.show(self, "Test message sent. Check your Discord channel.", toast_type="success")
                else:
                    ZBBDialog.info(self, "Test Failed", f"Could not post to the webhook:\n{error}", kind="error")
            self.after(0, _apply)

        threading.Thread(target=_worker, daemon=True, name="WebhookTest").start()
