"""Application-wide settings dialog (gear button in the sidebar).

Tabbed layout (F14): General, Notifications, Java, Storage, About.
Global sections belong here, not in the per-server editor.

Mutating operations (JDK purge, crash-report cleanup) go through
ZBBManager; this dialog never touches services that change state directly.
Disk walks and Java probing run in daemon threads -- UI updates via
`self.after(0, ...)`.
"""
import logging
import subprocess
import sys
import threading
from pathlib import Path

import customtkinter as ctk

from app.core.app_config import AppConfig
from app.core.constants import BASE_DIR, JDK_CACHE_DIR, SERVERS_DIR, VERSIONS_CACHE_FILE
from app.services.discord_webhook import DiscordWebhookService, DEFAULT_EVENT_PREFS, TEMPLATE_PLACEHOLDERS
from app.services.disk_usage import dir_size, format_size
from app.services.settings_manager import SettingsManager
from app.ui.icons import icon
from app.ui.toast import Toast
from app.ui.ui_components import ToolTip, ZBBDialog, center_on_parent
from app.ui.win_effects import apply_rounded_corners, apply_titlebar_theme

logger = logging.getLogger(__name__)

_WEBHOOK_PREFIXES = (
    "https://discord.com/api/webhooks/",
    "https://discordapp.com/api/webhooks/",
)

_WEBHOOK_EVENT_LABELS = [
    ("crashed", "Server crashed"),
    ("ready", "Server ready"),
    ("stopped", "Server stopped"),
    ("restarted", "Server restarted"),
    ("zombie_detected", "Server unresponsive"),
    ("lag_spike", "Lag detected"),
    ("tunnel_online", "Tunnel address ready"),
    ("player_joins", "Player joins/leaves"),
    ("backup_completed", "Backup completed"),
    ("backup_failed", "Backup failed"),
]


class AppSettingsDialog(ctk.CTkToplevel):
    def __init__(self, master, zbb_manager, **kwargs):
        super().__init__(master, **kwargs)
        self.title("Settings")
        self.geometry("720x540")
        center_on_parent(self, master, 720, 540)
        self.minsize(640, 460)
        self.transient(master)
        self.lift()
        self.focus_force()
        apply_rounded_corners(self)

        self.zbb_manager = zbb_manager
        self._settings = SettingsManager()

        # Init all data attributes before any thread can start.
        self._jdk_rows_frame = None
        self._detected_rows_frame = None
        self._storage_rows_frame = None
        self._java_note = None

        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(1, weight=1)

        header = ctk.CTkLabel(self, text="Application Settings", font=AppConfig.FONT_HEADING, anchor="w")
        header.grid(row=0, column=0, sticky="ew", padx=20, pady=(18, 6))

        self.tabview = ctk.CTkTabview(self, corner_radius=AppConfig.RADIUS_CARD)
        self.tabview.grid(row=1, column=0, sticky="nsew", padx=14, pady=(0, 14))
        for name in ("General", "Notifications", "Java", "Storage", "About"):
            self.tabview.add(name)

        self._build_general_tab(self.tabview.tab("General"))
        self._build_notifications_tab(self.tabview.tab("Notifications"))
        self._build_java_tab(self.tabview.tab("Java"))
        self._build_storage_tab(self.tabview.tab("Storage"))
        self._build_about_tab(self.tabview.tab("About"))

        self._refresh_jdks()
        self._refresh_detected_javas()
        self._refresh_storage()

    # ------------------------------------------------------------------
    # Shared card builder
    # ------------------------------------------------------------------
    def _card(self, parent, title: str, hint: str = ""):
        card = ctk.CTkFrame(
            parent, corner_radius=AppConfig.RADIUS_CARD, border_width=0,
            fg_color=(AppConfig.COLOR_BG_CARD_LIGHT, AppConfig.COLOR_BG_CARD_DARK),
        )
        card.pack(fill="x", padx=8, pady=(8, 4))
        card.grid_columnconfigure(0, weight=1)
        lbl = ctk.CTkLabel(card, text=title, font=AppConfig.FONT_BODY, anchor="w")
        lbl.grid(row=0, column=0, sticky="ew", padx=15, pady=(12, 0))
        if hint:
            lbl_hint = ctk.CTkLabel(
                card, text=hint, font=AppConfig.FONT_BODY_SMALL,
                text_color=AppConfig.COLOR_TEXT_GRAY, anchor="w", justify="left",
            )
            lbl_hint.grid(row=1, column=0, sticky="ew", padx=15, pady=(2, 4))
        return card

    def _ghost_button(self, parent, text, command, icon_name=None, width=110):
        return ctk.CTkButton(
            parent, text=text, command=command, width=width, height=30,
            image=icon(icon_name, 13) if icon_name else None,
            corner_radius=AppConfig.RADIUS_BTN, fg_color="transparent", border_width=1,
            border_color=(AppConfig.COLOR_BORDER_LIGHT, AppConfig.COLOR_BORDER_DARK),
            text_color=AppConfig.COLOR_TEXT_PRIMARY,
            hover_color=AppConfig.COLOR_BTN_GHOST,
            font=(AppConfig.FONT_FAMILY, 12),
        )

    # ------------------------------------------------------------------
    # Tab: General
    # ------------------------------------------------------------------
    def _build_general_tab(self, tab):
        card = self._card(
            tab, "Appearance",
            "Interface color mode — Dark, Light, or follow the system setting.",
        )
        self._theme_selector = ctk.CTkSegmentedButton(
            card, values=["Dark", "Light", "System"],
            command=self._on_theme_selected, height=32,
            font=(AppConfig.FONT_FAMILY, 12),
        )
        self._theme_selector.set(self._settings.get("theme", "Dark"))
        self._theme_selector.grid(row=2, column=0, sticky="w", padx=15, pady=(4, 14))

    def _on_theme_selected(self, choice: str):
        self._settings.set("theme", choice)
        ctk.set_appearance_mode(choice)
        # CTkToplevel reacts to the switch with a withdraw/deiconify dance to
        # recolor the titlebar; its revert can lose the race and leave this
        # dialog withdrawn forever. Re-show once the dust settles.
        self.after(80, self._ensure_visible)

    def _ensure_visible(self):
        if not self.winfo_exists():
            return
        if self.state() != "normal":
            self.deiconify()
            self.lift()
            self.focus_force()
        apply_titlebar_theme(self)

    # ------------------------------------------------------------------
    # Tab: Notifications
    # ------------------------------------------------------------------
    def _build_notifications_tab(self, tab):
        scroll = ctk.CTkScrollableFrame(tab, fg_color="transparent")
        scroll.pack(fill="both", expand=True, padx=0, pady=0)

        card = self._card(
            scroll, "Discord Webhook",
            "Posts server events to a Discord channel.\n"
            "Server Settings > Integrations > Webhooks > Copy Webhook URL. Leave empty to disable.",
        )
        self.entry_webhook = ctk.CTkEntry(
            card, placeholder_text="https://discord.com/api/webhooks/...",
            corner_radius=AppConfig.RADIUS_BTN, height=32,
        )
        self.entry_webhook.grid(row=2, column=0, sticky="ew", padx=15, pady=(0, 10))
        current = self._settings.get("discord_webhook_url", "")
        if current:
            self.entry_webhook.insert(0, current)

        events_card = self._card(scroll, "Events", "Which events get posted to the webhook.")
        prefs = self._settings.get("webhook_events", {}) or {}
        self._event_vars = {}
        checks_row = ctk.CTkFrame(events_card, fg_color="transparent")
        checks_row.grid(row=2, column=0, sticky="ew", padx=15, pady=(4, 12))
        for i, (key, label) in enumerate(_WEBHOOK_EVENT_LABELS):
            var = ctk.BooleanVar(value=bool(prefs.get(key, DEFAULT_EVENT_PREFS.get(key, False))))
            self._event_vars[key] = var
            chk = ctk.CTkCheckBox(
                checks_row, text=label, variable=var,
                font=(AppConfig.FONT_FAMILY, 12), checkbox_width=18, checkbox_height=18,
                corner_radius=AppConfig.RADIUS_BADGE,
            )
            chk.grid(row=i // 2, column=i % 2, sticky="w", padx=(0, 24), pady=3)

        templates_card = self._card(
            scroll, "Message Templates",
            "Optional. Override the message text for a specific event. Leave empty to use the default wording.",
        )
        self._webhook_templates = dict(self._settings.get("webhook_templates", {}) or {})
        tpl_select_row = ctk.CTkFrame(templates_card, fg_color="transparent")
        tpl_select_row.grid(row=2, column=0, sticky="ew", padx=15, pady=(0, 4))
        tpl_select_row.grid_columnconfigure(0, weight=1)
        self.opt_template_event = ctk.CTkOptionMenu(
            tpl_select_row, values=[label for _, label in _WEBHOOK_EVENT_LABELS],
            command=self._on_template_event_change, height=32,
            corner_radius=AppConfig.RADIUS_BTN, width=220,
        )
        self.opt_template_event.grid(row=0, column=0, sticky="w")

        self.lbl_template_placeholders = ctk.CTkLabel(
            templates_card, text="", font=AppConfig.FONT_BODY_SMALL,
            text_color=AppConfig.COLOR_TEXT_GRAY, anchor="w", justify="left",
        )
        self.lbl_template_placeholders.grid(row=3, column=0, sticky="ew", padx=15, pady=(2, 4))

        self.entry_template = ctk.CTkEntry(
            templates_card, placeholder_text="Custom message for this event...",
            corner_radius=AppConfig.RADIUS_BTN, height=32,
        )
        self.entry_template.grid(row=4, column=0, sticky="ew", padx=15, pady=(0, 4))

        tpl_btn_row = ctk.CTkFrame(templates_card, fg_color="transparent")
        tpl_btn_row.grid(row=5, column=0, sticky="ew", padx=15, pady=(0, 12))
        self._btn_template_apply = self._ghost_button(
            tpl_btn_row, "Apply", self._apply_template, icon_name="check", width=90,
        )
        self._btn_template_apply.pack(side="left")
        self._btn_template_clear = self._ghost_button(
            tpl_btn_row, "Clear", self._clear_template, icon_name="trash", width=90,
        )
        self._btn_template_clear.pack(side="left", padx=(8, 0))
        self._load_template_for_event(_WEBHOOK_EVENT_LABELS[0][0])

        identity_card = self._card(
            scroll, "Bot Identity",
            "Optional. Override the name and avatar shown on webhook messages.",
        )
        identity_row = ctk.CTkFrame(identity_card, fg_color="transparent")
        identity_row.grid(row=2, column=0, sticky="ew", padx=15, pady=(0, 10))
        identity_row.grid_columnconfigure(0, weight=1)
        identity_row.grid_columnconfigure(1, weight=2)
        self.entry_webhook_name = ctk.CTkEntry(
            identity_row, placeholder_text="Bot name (e.g. ZBB)",
            corner_radius=AppConfig.RADIUS_BTN, height=32,
        )
        self.entry_webhook_name.grid(row=0, column=0, sticky="ew", padx=(0, 8))
        self.entry_webhook_avatar = ctk.CTkEntry(
            identity_row, placeholder_text="Avatar image URL (https://...)",
            corner_radius=AppConfig.RADIUS_BTN, height=32,
        )
        self.entry_webhook_avatar.grid(row=0, column=1, sticky="ew")
        name = self._settings.get("webhook_username", "")
        if name:
            self.entry_webhook_name.insert(0, name)
        avatar = self._settings.get("webhook_avatar_url", "")
        if avatar:
            self.entry_webhook_avatar.insert(0, avatar)

        mention_card = self._card(
            scroll, "Crash Alert Mention",
            "Optional. Discord role ID to @mention when the server crashes.\n"
            "Right-click a role in Discord (Developer Mode on) > Copy Role ID.",
        )
        self.entry_webhook_role = ctk.CTkEntry(
            mention_card, placeholder_text="Role ID (numbers only)",
            corner_radius=AppConfig.RADIUS_BTN, height=32, width=260,
        )
        self.entry_webhook_role.grid(row=2, column=0, sticky="w", padx=15, pady=(0, 10))
        role = self._settings.get("webhook_crash_mention_role", "")
        if role:
            self.entry_webhook_role.insert(0, role)

        btn_row = ctk.CTkFrame(tab, fg_color="transparent")
        btn_row.pack(fill="x", padx=8, pady=(6, 4))

        self.btn_test = self._ghost_button(btn_row, "Send Test", self._send_test, icon_name="bolt")
        self.btn_test.pack(side="left")

        self.btn_save = ctk.CTkButton(
            btn_row, text="Save", image=icon("check", 13, "#ffffff"),
            command=self._save_notifications, corner_radius=AppConfig.RADIUS_BTN,
            height=30, width=110,
            fg_color=AppConfig.COLOR_BTN_PRIMARY, hover_color=AppConfig.COLOR_BTN_PRIMARY_HOVER,
            font=(AppConfig.FONT_FAMILY_DISPLAY, 12, "bold"),
        )
        self.btn_save.pack(side="right")

    def _current_template_key(self) -> str:
        label = self.opt_template_event.get()
        for key, lbl in _WEBHOOK_EVENT_LABELS:
            if lbl == label:
                return key
        return _WEBHOOK_EVENT_LABELS[0][0]

    def _load_template_for_event(self, key: str) -> None:
        placeholders = ", ".join("{" + p + "}" for p in TEMPLATE_PLACEHOLDERS.get(key, ["server"]))
        self.lbl_template_placeholders.configure(text=f"Available: {placeholders}")
        self.entry_template.delete(0, "end")
        existing = self._webhook_templates.get(key, "")
        if existing:
            self.entry_template.insert(0, existing)

    def _on_template_event_change(self, _label: str) -> None:
        self._load_template_for_event(self._current_template_key())

    def _apply_template(self) -> None:
        key = self._current_template_key()
        text = self.entry_template.get().strip()
        placeholders = set(TEMPLATE_PLACEHOLDERS.get(key, ["server"]))
        try:
            text.format(**{p: "" for p in placeholders})
        except (KeyError, IndexError, ValueError):
            ZBBDialog.info(
                self, "Invalid Template",
                "That template uses a placeholder that isn't available for this event.\n"
                f"Available: {', '.join('{' + p + '}' for p in placeholders)}",
                kind="error",
            )
            return
        if text:
            self._webhook_templates[key] = text
        else:
            self._webhook_templates.pop(key, None)
        Toast.show(self, "Template updated. Click Save to keep it.", toast_type="info")

    def _clear_template(self) -> None:
        key = self._current_template_key()
        self._webhook_templates.pop(key, None)
        self.entry_template.delete(0, "end")

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

    def _save_notifications(self):
        url = self._current_url()
        if not self._validate(url):
            return
        role = self.entry_webhook_role.get().strip()
        if role and not role.isdigit():
            ZBBDialog.info(
                self, "Invalid Role ID",
                "The role ID must be numbers only.\n"
                "In Discord: Settings > Advanced > Developer Mode, then right-click the role > Copy Role ID.",
                kind="error",
            )
            return
        self._settings.set("discord_webhook_url", url)
        self._settings.set(
            "webhook_events",
            {key: var.get() for key, var in self._event_vars.items()},
        )
        self._settings.set("webhook_username", self.entry_webhook_name.get().strip())
        self._settings.set("webhook_avatar_url", self.entry_webhook_avatar.get().strip())
        self._settings.set("webhook_crash_mention_role", role)
        self._settings.set("webhook_templates", dict(self._webhook_templates))
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
        username = self.entry_webhook_name.get().strip()
        avatar_url = self.entry_webhook_avatar.get().strip()

        def _worker():
            ok, error = DiscordWebhookService.send_test(url, username=username, avatar_url=avatar_url)
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

    # ------------------------------------------------------------------
    # Tab: Java
    # ------------------------------------------------------------------
    def _build_java_tab(self, tab):
        scroll = ctk.CTkScrollableFrame(tab, fg_color="transparent")
        scroll.pack(fill="both", expand=True)

        card = self._card(
            scroll, "Downloaded Java runtimes",
            "Runtimes ZBB downloaded automatically. Deleting one is safe --\n"
            "it re-downloads on the next launch of a server that needs it.",
        )
        self._jdk_rows_frame = ctk.CTkFrame(card, fg_color="transparent")
        self._jdk_rows_frame.grid(row=2, column=0, sticky="ew", padx=15, pady=(2, 6))
        self._jdk_rows_frame.grid_columnconfigure(0, weight=1)

        self._java_note = ctk.CTkLabel(
            card, text="", font=AppConfig.FONT_NOTE,
            text_color=AppConfig.COLOR_STATUS_STARTING, anchor="w",
        )
        self._java_note.grid(row=3, column=0, sticky="ew", padx=15, pady=(0, 2))

        jdk_btns = ctk.CTkFrame(card, fg_color="transparent")
        jdk_btns.grid(row=4, column=0, sticky="ew", padx=15, pady=(0, 12))
        self.btn_purge_unused = self._ghost_button(
            jdk_btns, "Purge Unused", self._purge_unused, icon_name="trash", width=120,
        )
        self.btn_purge_unused.pack(side="left")
        ToolTip(self.btn_purge_unused, "Delete runtimes no server uses")
        btn_refresh_jdks = self._ghost_button(
            jdk_btns, "Refresh", self._refresh_jdks, icon_name="refresh", width=100,
        )
        btn_refresh_jdks.pack(side="left", padx=(8, 0))

        detected_card = self._card(
            scroll, "Detected on this system",
            "Java installations found in PATH, JAVA_HOME, the Windows registry and well-known folders.",
        )
        self._detected_rows_frame = ctk.CTkFrame(detected_card, fg_color="transparent")
        self._detected_rows_frame.grid(row=2, column=0, sticky="ew", padx=15, pady=(2, 6))
        self._detected_rows_frame.grid_columnconfigure(0, weight=1)

        btn_rescan = self._ghost_button(
            detected_card, "Rescan", lambda: self._refresh_detected_javas(force=True),
            icon_name="refresh", width=100,
        )
        btn_rescan.grid(row=3, column=0, sticky="w", padx=15, pady=(0, 12))

    def _refresh_jdks(self):
        frame = self._jdk_rows_frame
        if frame is None or not frame.winfo_exists():
            return
        for child in frame.winfo_children():
            child.destroy()
        loading = ctk.CTkLabel(frame, text="Scanning...", font=AppConfig.FONT_BODY_SMALL,
                               text_color=AppConfig.COLOR_TEXT_GRAY, anchor="w")
        loading.grid(row=0, column=0, sticky="w")

        def _worker():
            jdks = self.zbb_manager.list_managed_jdks()
            running = self.zbb_manager.is_running()
            self.after(0, lambda: self._render_jdk_rows(jdks, running))

        threading.Thread(target=_worker, daemon=True, name="JdkListScan").start()

    def _render_jdk_rows(self, jdks: list, running: bool):
        frame = self._jdk_rows_frame
        if frame is None or not frame.winfo_exists():
            return
        for child in frame.winfo_children():
            child.destroy()

        if running:
            self._java_note.configure(text="Stop the server to manage runtimes.")
        else:
            self._java_note.configure(text="")
        self.btn_purge_unused.configure(state="disabled" if (running or not jdks) else "normal")

        if not jdks:
            empty = ctk.CTkLabel(frame, text="No runtimes downloaded yet.",
                                 font=AppConfig.FONT_BODY_SMALL,
                                 text_color=AppConfig.COLOR_TEXT_GRAY, anchor="w")
            empty.grid(row=0, column=0, sticky="w")
            return

        for i, jdk in enumerate(jdks):
            version, size = jdk["version"], jdk["size_bytes"]
            lbl = ctk.CTkLabel(
                frame, text=f"Java {version}", font=AppConfig.FONT_BODY, anchor="w",
            )
            lbl.grid(row=i, column=0, sticky="w", pady=2)
            lbl_size = ctk.CTkLabel(
                frame, text=format_size(size), font=AppConfig.FONT_BODY_SMALL,
                text_color=AppConfig.COLOR_TEXT_GRAY, anchor="e", width=80,
            )
            lbl_size.grid(row=i, column=1, sticky="e", padx=(10, 8))
            btn = ctk.CTkButton(
                frame, text="", image=icon("trash", 13), width=30, height=26,
                corner_radius=AppConfig.RADIUS_BTN, fg_color="transparent",
                hover_color=AppConfig.COLOR_BTN_GHOST,
                command=lambda v=version: self._delete_jdk(v),
                state="disabled" if running else "normal",
            )
            btn.grid(row=i, column=2, sticky="e")
            ToolTip(btn, f"Delete Java {version}")

    def _delete_jdk(self, version: int):
        if not ZBBDialog.confirm(
            self, "Delete Runtime",
            f"Delete the downloaded Java {version} runtime?\n"
            "It will re-download automatically if a server needs it.",
            confirm_text="Delete", danger=True,
        ):
            return
        if self.zbb_manager.purge_jdk(version):
            Toast.show(self, f"Java {version} deleted.", toast_type="success")
        else:
            Toast.show(self, "Cannot delete while the server is running.", toast_type="warning")
        self._refresh_jdks()
        self._refresh_storage()

    def _purge_unused(self):
        if not ZBBDialog.confirm(
            self, "Purge Unused Runtimes",
            "Delete every downloaded runtime that no server currently needs?",
            confirm_text="Purge", danger=True,
        ):
            return
        if self.zbb_manager.purge_unused_jdks():
            Toast.show(self, "Unused runtimes purged.", toast_type="success")
        else:
            Toast.show(self, "Cannot purge while the server is running.", toast_type="warning")
        self._refresh_jdks()
        self._refresh_storage()

    def _refresh_detected_javas(self, force: bool = False):
        frame = self._detected_rows_frame
        if frame is None or not frame.winfo_exists():
            return
        for child in frame.winfo_children():
            child.destroy()
        loading = ctk.CTkLabel(frame, text="Scanning...", font=AppConfig.FONT_BODY_SMALL,
                               text_color=AppConfig.COLOR_TEXT_GRAY, anchor="w")
        loading.grid(row=0, column=0, sticky="w")

        def _worker():
            from app.services.java_detector import JavaDetector
            try:
                installs = JavaDetector().detect_all(force_refresh=force)
            except Exception as exc:
                logger.warning("Java detection failed: %s", exc)
                installs = []
            self.after(0, lambda: self._render_detected_rows(installs))

        threading.Thread(target=_worker, daemon=True, name="JavaDetectScan").start()

    def _render_detected_rows(self, installs: list):
        frame = self._detected_rows_frame
        if frame is None or not frame.winfo_exists():
            return
        for child in frame.winfo_children():
            child.destroy()
        if not installs:
            empty = ctk.CTkLabel(frame, text="No system Java installations found.",
                                 font=AppConfig.FONT_BODY_SMALL,
                                 text_color=AppConfig.COLOR_TEXT_GRAY, anchor="w")
            empty.grid(row=0, column=0, sticky="w")
            return
        for i, inst in enumerate(installs):
            lbl = ctk.CTkLabel(frame, text=inst.label, font=AppConfig.FONT_BODY, anchor="w")
            lbl.grid(row=i * 2, column=0, sticky="w", pady=(4, 0))
            lbl_path = ctk.CTkLabel(
                frame, text=inst.path, font=AppConfig.FONT_BODY_SMALL,
                text_color=AppConfig.COLOR_TEXT_GRAY, anchor="w",
            )
            lbl_path.grid(row=i * 2 + 1, column=0, sticky="w")

    # ------------------------------------------------------------------
    # Tab: Storage
    # ------------------------------------------------------------------
    def _build_storage_tab(self, tab):
        scroll = ctk.CTkScrollableFrame(tab, fg_color="transparent")
        scroll.pack(fill="both", expand=True)

        loc_card = self._card(
            scroll, "Data Location",
            "Where servers, backups, config and Java runtimes are stored.",
        )
        loc_row = ctk.CTkFrame(loc_card, fg_color="transparent")
        loc_row.grid(row=2, column=0, sticky="ew", padx=15, pady=(2, 12))
        loc_row.grid_columnconfigure(0, weight=1)
        ctk.CTkLabel(
            loc_row, text=str(BASE_DIR), font=AppConfig.FONT_BODY_SMALL,
            text_color=AppConfig.COLOR_TEXT_GRAY, anchor="w",
        ).grid(row=0, column=0, sticky="ew", padx=(0, 8))
        self._ghost_button(
            loc_row, "Open Folder", self._open_data_dir, icon_name="folder", width=120,
        ).grid(row=0, column=1, sticky="e")

        card = self._card(
            scroll, "Disk usage",
            "Space used by ZBB data on this machine.",
        )
        self._storage_rows_frame = ctk.CTkFrame(card, fg_color="transparent")
        self._storage_rows_frame.grid(row=2, column=0, sticky="ew", padx=15, pady=(2, 6))
        self._storage_rows_frame.grid_columnconfigure(0, weight=1)

        btn_row = ctk.CTkFrame(card, fg_color="transparent")
        btn_row.grid(row=3, column=0, sticky="ew", padx=15, pady=(0, 12))
        btn_refresh = self._ghost_button(btn_row, "Refresh", self._refresh_storage,
                                         icon_name="refresh", width=100)
        btn_refresh.pack(side="left")
        self.btn_clear_reports = self._ghost_button(
            btn_row, "Clear Crash Reports", self._clear_crash_reports,
            icon_name="trash", width=160,
        )
        self.btn_clear_reports.pack(side="left", padx=(8, 0))

    def _open_data_dir(self):
        BASE_DIR.mkdir(parents=True, exist_ok=True)
        path = str(BASE_DIR)
        if sys.platform == "win32":
            subprocess.run(["explorer", path], check=False)
        elif sys.platform == "darwin":
            subprocess.run(["open", path], check=False)
        else:
            subprocess.run(["xdg-open", path], check=False)

    def _storage_categories(self) -> list:
        """(label, size_bytes) pairs -- runs on a worker thread."""
        backups_dir = BASE_DIR / "backups"
        crash_total = 0
        servers_dir = Path(SERVERS_DIR)
        if servers_dir.exists():
            for folder in servers_dir.iterdir():
                crash_total += dir_size(folder / "crash_reports")
        versions_size = VERSIONS_CACHE_FILE.stat().st_size if VERSIONS_CACHE_FILE.exists() else 0
        return [
            ("Servers", dir_size(servers_dir)),
            ("Backups", dir_size(backups_dir)),
            ("Java runtimes", dir_size(JDK_CACHE_DIR)),
            ("Crash reports", crash_total),
            ("Versions cache", versions_size),
        ]

    def _refresh_storage(self):
        frame = self._storage_rows_frame
        if frame is None or not frame.winfo_exists():
            return
        for child in frame.winfo_children():
            child.destroy()
        loading = ctk.CTkLabel(frame, text="Calculating...", font=AppConfig.FONT_BODY_SMALL,
                               text_color=AppConfig.COLOR_TEXT_GRAY, anchor="w")
        loading.grid(row=0, column=0, sticky="w")

        def _worker():
            rows = self._storage_categories()
            self.after(0, lambda: self._render_storage_rows(rows))

        threading.Thread(target=_worker, daemon=True, name="StorageScan").start()

    def _render_storage_rows(self, rows: list):
        frame = self._storage_rows_frame
        if frame is None or not frame.winfo_exists():
            return
        for child in frame.winfo_children():
            child.destroy()
        total = 0
        for i, (label, size) in enumerate(rows):
            total += size
            lbl = ctk.CTkLabel(frame, text=label, font=AppConfig.FONT_BODY, anchor="w")
            lbl.grid(row=i, column=0, sticky="w", pady=2)
            lbl_size = ctk.CTkLabel(
                frame, text=format_size(size), font=AppConfig.FONT_BODY,
                text_color=AppConfig.COLOR_TEXT_GRAY, anchor="e",
            )
            lbl_size.grid(row=i, column=1, sticky="e")
        lbl_total = ctk.CTkLabel(frame, text="Total", font=AppConfig.FONT_HEADING_SMALL, anchor="w")
        lbl_total.grid(row=len(rows), column=0, sticky="w", pady=(8, 2))
        lbl_total_size = ctk.CTkLabel(
            frame, text=format_size(total), font=AppConfig.FONT_HEADING_SMALL, anchor="e",
        )
        lbl_total_size.grid(row=len(rows), column=1, sticky="e", pady=(8, 2))

    def _clear_crash_reports(self):
        if not ZBBDialog.confirm(
            self, "Clear Crash Reports",
            "Delete all stored crash reports for every server?",
            confirm_text="Delete", danger=True,
        ):
            return
        removed = self.zbb_manager.purge_crash_reports()
        if removed:
            Toast.show(self, f"Crash reports cleared ({removed} server folders).", toast_type="success")
        else:
            Toast.show(self, "No crash reports to clear.", toast_type="info")
        self._refresh_storage()

    # ------------------------------------------------------------------
    # Tab: About
    # ------------------------------------------------------------------
    def _build_about_tab(self, tab):
        wrap = ctk.CTkFrame(tab, fg_color="transparent")
        wrap.pack(expand=True)

        lbl_icon = ctk.CTkLabel(wrap, text="", image=icon("package", 48))
        lbl_icon.pack(pady=(24, 8))
        lbl_name = ctk.CTkLabel(wrap, text=AppConfig.WINDOW_TITLE, font=AppConfig.FONT_TITLE)
        lbl_name.pack()
        lbl_version = ctk.CTkLabel(
            wrap, text=f"Version {AppConfig.APP_VERSION}",
            font=AppConfig.FONT_BODY, text_color=AppConfig.COLOR_TEXT_GRAY,
        )
        lbl_version.pack(pady=(2, 12))
        lbl_desc = ctk.CTkLabel(
            wrap,
            text="Minecraft server manager with auto-healing,\n"
                 "Playit.gg tunneling and one-click provisioning.",
            font=AppConfig.FONT_BODY_SMALL, text_color=AppConfig.COLOR_TEXT_GRAY,
            justify="center",
        )
        lbl_desc.pack()
        lbl_author = ctk.CTkLabel(
            wrap, text="By DesvoSoft",
            font=AppConfig.FONT_BODY_SMALL, text_color=AppConfig.COLOR_TEXT_GRAY,
        )
        lbl_author.pack(pady=(12, 2))

        import webbrowser
        repo_url = "https://github.com/DesvoSoft/ZeroBlockBridge"
        lbl_repo = ctk.CTkLabel(
            wrap, text=repo_url,
            font=AppConfig.FONT_BODY_SMALL, text_color=AppConfig.COLOR_LINK, cursor="hand2",
        )
        lbl_repo.pack(pady=(0, 24))
        lbl_repo.bind("<Button-1>", lambda e: webbrowser.open(repo_url))
