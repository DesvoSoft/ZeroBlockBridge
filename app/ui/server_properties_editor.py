import customtkinter as ctk
from tkinter import filedialog
import logging
import os
import threading
from app.api.areas import dropdown_labels
from app.api.mods import MrpackCompatibilityError
from app.api.property_catalog import (  # noqa: F401  (TAB_LAYOUTS, property_label: also used by tests)
    IMPACT_LABELS as _IMPACT_LABELS, SETTINGS_METADATA, TAB_LAYOUTS, property_control, property_label,
)
from app.api.server_config import LaunchSettings
from app.api.servers import MigrationError
from app.core.app_config import AppConfig
from app.core import i18n
from app.core.i18n import _, N_

logger = logging.getLogger(__name__)
from app.ui.ui_components import ToolTip, center_on_parent, ZBBDialog, dialog_buttons, dialog_header, ScrollableFrame, StackedTabview, ZBBToplevel
from app.ui.win_effects import apply_rounded_corners
from app.ui.formatting import engine_name
from app.ui.icons import icon


# (restart schedule "type", label shown in the Schedule Mode menu)
_SCHEDULE_MODES = (("interval", N_("Interval")), ("time", N_("Daily Time")))


# Control column: every settings row right-aligns its control in a column of
# this width, so help icons, impact dots and controls line up across cards.
_CONTROL_WIDTH = 200
_CONTROL_PADX = 12


def _bare_switch(parent, **kwargs) -> ctk.CTkSwitch:
    """Text-less switch whose toggle sits flush with its right edge.

    CTkSwitch keeps a label column (plus a 6px spacer) even with text="",
    which left the toggle ~10px short of the entries above and below it.
    """
    switch = ctk.CTkSwitch(parent, text="", width=0, **kwargs)
    switch._text_label.grid_remove()
    switch.grid_columnconfigure(1, minsize=0)
    return switch


class ServerPropertiesEditor(ZBBToplevel):
    def __init__(self, parent, server_name, api):
        super().__init__(parent)
        self.title(f"Edit Properties - {server_name}")
        self.geometry("700x600")
        center_on_parent(self, parent, 700, 600)
        self.resizable(True, True)

        self.server_name = server_name
        self.api = api
        self.server_config = api.config
        self.properties = self.server_config.properties(server_name)
        
        # Shared Fonts
        self.font_bold = AppConfig.FONT_LABEL
        self.font_small = AppConfig.FONT_BODY_SMALL
        self.font_header = AppConfig.FONT_HEADING_SMALL
        
        # Layout: header / [running banner] / tabs / buttons
        self.grid_columnconfigure(0, weight=1)
        meta = self.server_config.meta(server_name)
        engine = f"{engine_name(meta.get('type'))} {meta.get('version', '')}".strip()
        header, _, _ = dialog_header(self, "Server Properties", f"{server_name} · {engine}")
        header.grid(row=0, column=0, sticky="ew", padx=20, pady=(14, 0))
        
        self._running_locked = api.servers.running_server() == server_name

        if self._running_locked:
            banner = ctk.CTkLabel(
                self, text="Server is running — settings that require a restart are locked. "
                           "Backups and Automation can still be changed live.",
                font=self.font_small, text_color=AppConfig.COLOR_STATUS_STARTING,
                anchor="w", wraplength=660,
            )
            banner.grid(row=1, column=0, sticky="ew", padx=15, pady=(10, 0))
            tabview_row = 2
        else:
            tabview_row = 1
        self.btn_frame_row = tabview_row + 1
        self.grid_rowconfigure(tabview_row, weight=1)

        # Tabview
        self.tabview = StackedTabview(self)
        self.tabview.grid(row=tabview_row, column=0, sticky="nsew", padx=10, pady=10)
        
        self.tab_general = self.tabview.add("General")
        self.tab_world = self.tabview.add("World")
        self.tab_network = self.tabview.add("Network")
        self.tab_advanced = self.tabview.add("Advanced")
        self.tab_backups = self.tabview.add("Backups")
        self.tab_automation = self.tabview.add("Automation")
        self.tab_launch = self.tabview.add("Launch")

        self._locked_tab_names = ("General", "World", "Network", "Advanced", "Launch")
        if self._running_locked:
            for name in self._locked_tab_names:
                btn = self.tabview._segmented_button._buttons_dict.get(name)
                if btn is not None:
                    btn.configure(state="disabled")
                    ToolTip(btn, "Stop the server to edit this — it only takes effect on next start.")
            self.tabview.set("Automation")
        
        # Set tab change command for optimization
        self.tabview.configure(command=self._on_tab_changed)
        
        # Scrollable frames for tabs
        self.frame_general = ScrollableFrame(self.tab_general)
        self.frame_general.pack(fill="both", expand=True)
        
        self.frame_world = ScrollableFrame(self.tab_world)
        self.frame_world.pack(fill="both", expand=True)
        
        self.frame_network = ScrollableFrame(self.tab_network)
        self.frame_network.pack(fill="both", expand=True)
        
        self.frame_advanced = ScrollableFrame(self.tab_advanced)
        self.frame_advanced.pack(fill="both", expand=True)

        self.frame_backups = ctk.CTkFrame(self.tab_backups, fg_color="transparent")
        self.frame_backups.pack(fill="both", expand=True)

        self.frame_automation = ScrollableFrame(self.tab_automation)
        self.frame_automation.pack(fill="both", expand=True)

        self.frame_launch = ScrollableFrame(self.tab_launch)
        self.frame_launch.pack(fill="both", expand=True)
        
        # Tracking
        self.widgets = {}
        self.loaded_tabs = set()
        
        # UI Variables for validation (initialized for lazy loading safety)
        self.entry_ram = None
        self.var_auto_restart = None
        self.entry_interval = None
        
        # Load initial tab
        self._on_tab_changed()
        
        # Footer Buttons
        self.btn_frame, self.btn_save, self.btn_cancel = dialog_buttons(
            self, "Save", self.save_properties, "Cancel", self.destroy,
            height=36, primary_width=140, secondary_width=140,
        )
        self.btn_frame.grid(row=self.btn_frame_row, column=0, sticky="ew", padx=10, pady=(0, 10))

        apply_rounded_corners(self)

        # Make modal
        self.transient(parent)
        self.wait_visibility()
        self.grab_set()

    def _on_tab_changed(self):
        """Lazy load tabs when selected."""
        tab = self.tabview.get()
        if tab in self.loaded_tabs:
            return
            
        if tab == "General":
            self.setup_general_tab()
        elif tab == "World":
            self.setup_world_tab()
        elif tab == "Network":
            self.setup_network_tab()
        elif tab == "Advanced":
            self.setup_advanced_tab()
        elif tab == "Automation":
            self.setup_automation_tab()
        elif tab == "Backups":
            self.setup_backups_tab()
            self.refresh_backups()
        elif tab == "Launch":
            self.setup_launch_tab()
            
        self.loaded_tabs.add(tab)

    def setup_backups_tab(self):
        # Toolbar — flush with the list's edges, one button height
        toolbar = ctk.CTkFrame(self.frame_backups, fg_color="transparent")
        toolbar.pack(fill="x", pady=(0, 8))
        _btn = dict(corner_radius=AppConfig.RADIUS_BTN, height=32)

        self.btn_create_backup = ctk.CTkButton(
            toolbar, text="Create Backup", command=self.create_backup,
            fg_color=AppConfig.COLOR_BTN_PRIMARY, hover_color=AppConfig.COLOR_BTN_PRIMARY_HOVER,
            width=120, **_btn)
        self.btn_create_backup.pack(side="left")
        btn_folder = ctk.CTkButton(
            toolbar, text="Open Folder", image=icon("folder", 14), command=self._open_backups_folder,
            fg_color=AppConfig.COLOR_BTN_GHOST, text_color=AppConfig.COLOR_TEXT_PRIMARY, hover_color=AppConfig.COLOR_BTN_GHOST_HOVER,
            width=120, **_btn)
        btn_folder.pack(side="left", padx=(8, 0))
        ctk.CTkButton(toolbar, text="Refresh", command=self.refresh_backups,
                      fg_color=AppConfig.COLOR_BTN_GHOST, text_color=AppConfig.COLOR_TEXT_PRIMARY, hover_color=AppConfig.COLOR_BTN_GHOST_HOVER,
                      width=80, **_btn).pack(side="right")
        self.btn_export_pack = ctk.CTkButton(
            toolbar, text="Export as .zbbpack", command=self.export_zbbpack,
            fg_color=AppConfig.COLOR_BTN_GHOST, text_color=AppConfig.COLOR_TEXT_PRIMARY, hover_color=AppConfig.COLOR_BTN_GHOST_HOVER,
            width=150, **_btn)
        self.btn_export_pack.pack(side="right", padx=(0, 8))

        # List
        self.backup_list_frame = ScrollableFrame(self.frame_backups)
        self.backup_list_frame.pack(fill="both", expand=True)
        
        self.backups = self.api.backups
        self._next_backup_lbl = ctk.CTkLabel(
            self.frame_backups, text="", anchor="w",
            text_color=AppConfig.COLOR_TEXT_GRAY, font=AppConfig.FONT_CAPTION
        )
        self._next_backup_lbl.pack(fill="x", padx=12, pady=(6, 0))
        self._refresh_backup_countdown()

    def refresh_backups(self):
        # Clear current list
        for widget in self.backup_list_frame.winfo_children():
            widget.destroy()
            
        # Show loading state
        loading_lbl = ctk.CTkLabel(self.backup_list_frame, text="Scanning backups...")
        loading_lbl.pack(pady=20)
        
        def load():
            backups = self.backups.list(self.server_name)
            if self.winfo_exists():
                self.after(0, lambda: self._populate_backups(backups, loading_lbl))
            
        threading.Thread(target=load, daemon=True).start()

    def _populate_backups(self, backups, loading_lbl):
        if loading_lbl.winfo_exists():
            loading_lbl.destroy()
            
        if not backups:
            ctk.CTkLabel(self.backup_list_frame, text="", image=icon("package", 36, AppConfig.COLOR_TEXT_MUTED)).pack(pady=(24, 4))
            ctk.CTkLabel(
                self.backup_list_frame, text="No backups found.",
                text_color=AppConfig.COLOR_TEXT_MUTED
            ).pack(pady=(0, 10))
            ctk.CTkButton(
                self.backup_list_frame, text="Create Backup",
                command=self.create_backup,
                fg_color=AppConfig.COLOR_BTN_PRIMARY,
                hover_color=AppConfig.COLOR_BTN_PRIMARY_HOVER,
                corner_radius=AppConfig.RADIUS_BTN, height=32
            ).pack(pady=(0, 20))
            return
            
        for backup in backups:
            self._backup_row(backup)

    # reason -> (chip label, bg, text)
    _BACKUP_REASONS = {
        "manual": ("Manual", AppConfig.COLOR_BADGE_NEUTRAL_BG, AppConfig.COLOR_BADGE_NEUTRAL_TEXT),
        "auto": ("Auto", AppConfig.COLOR_BADGE_BG, AppConfig.COLOR_BADGE_TEXT),
        "pre_update": ("Pre-update", AppConfig.COLOR_BADGE_WARNING_BG, AppConfig.COLOR_BADGE_WARNING_TEXT),
    }

    def _backup_row(self, backup: dict):
        row = ctk.CTkFrame(self.backup_list_frame, corner_radius=AppConfig.RADIUS_CARD,
                           fg_color=(AppConfig.COLOR_BG_SIDEBAR_LIGHT, AppConfig.COLOR_BG_DARK))
        row.pack(fill="x", padx=2, pady=3)
        row.grid_columnconfigure(3, weight=1)

        ctk.CTkLabel(row, text=backup["date"], font=AppConfig.FONT_LABEL, anchor="w").grid(
            row=0, column=0, sticky="w", padx=(12, 10), pady=10)
        reason = backup.get("reason", "manual")
        text, bg, fg = self._BACKUP_REASONS.get(
            reason, (reason.replace("_", " ").title(), AppConfig.COLOR_BADGE_NEUTRAL_BG, AppConfig.COLOR_BADGE_NEUTRAL_TEXT))
        for col, (chip, chip_bg, chip_fg) in enumerate(
                ((text, bg, fg), (backup["size"], AppConfig.COLOR_BADGE_NEUTRAL_BG, AppConfig.COLOR_BADGE_NEUTRAL_TEXT)), start=1):
            ctk.CTkLabel(row, text=chip, font=AppConfig.FONT_MICRO, fg_color=chip_bg, text_color=chip_fg,
                         corner_radius=AppConfig.RADIUS_BADGE, padx=8, pady=2).grid(
                row=0, column=col, sticky="w", padx=(0, 6))

        btn_delete = ctk.CTkButton(
            row, text="", image=icon("trash", 14, AppConfig.COLOR_TEXT_ON_ACCENT), width=32, height=28,
            corner_radius=AppConfig.RADIUS_BTN,
            fg_color=AppConfig.COLOR_BTN_DANGER, hover_color=AppConfig.COLOR_BTN_DANGER_HOVER,
            command=lambda p=backup["path"], n=backup["date"]: self.delete_backup(p, n),
        )
        btn_delete.grid(row=0, column=5, padx=(0, 12), pady=10)
        ToolTip(btn_delete, "Delete this backup")
        ctk.CTkButton(
            row, text="Restore", width=90, height=28, corner_radius=AppConfig.RADIUS_BTN,
            fg_color="transparent", border_width=AppConfig.BORDER_BTN, border_color=AppConfig.COLOR_ACCENT_AMBER,
            text_color=AppConfig.COLOR_TEXT_PRIMARY, hover_color=AppConfig.COLOR_BTN_WARNING_GHOST_HOVER,
            command=lambda p=backup["path"]: self.restore_backup(p),
        ).grid(row=0, column=4, padx=(0, 8), pady=10)

    def _open_backups_folder(self):
        self._open_path(self.backups.folder(self.server_name))

    def delete_backup(self, path: str, label: str):
        if not ZBBDialog.confirm(self, "Delete Backup", f"Delete the backup from {label}?\n\nThis can't be undone.",
                                 confirm_text="Delete", danger=True):
            return

        def worker():
            ok, error = self.backups.delete(self.server_name, path)
            if self.winfo_exists():
                self.after(0, lambda: self._on_backup_deleted(ok, error))

        threading.Thread(target=worker, daemon=True).start()

    def _on_backup_deleted(self, ok: bool, error):
        if not ok:
            ZBBDialog.info(self, "Error", f"Failed to delete backup.\n\n{error}", kind="error")
        self.refresh_backups()

    def create_backup(self):
        def worker():
            path, error = self.backups.create(self.server_name)
            if self.winfo_exists():
                self.after(0, lambda: self._on_backup_created(path, error))

        threading.Thread(target=worker, daemon=True).start()

    def _on_backup_created(self, path, error):
        if error and not path:
            ZBBDialog.info(self, "Error", f"Failed to create backup.\n\n{error}", kind="error")
        elif error:
            ZBBDialog.info(self, "Backup Created", error, kind="warning")
        self.refresh_backups()

    def export_zbbpack(self):
        dest_path = filedialog.asksaveasfilename(
            defaultextension=".zbbpack",
            initialfile=f"{self.server_name}.zbbpack",
            filetypes=[("ZeroBlockBridge Pack", "*.zbbpack")],
        )
        if not dest_path:
            return

        self.btn_export_pack.configure(state="disabled", text="Exporting…")

        def _export():
            try:
                self.api.servers.export(
                    self.server_name, dest_path,
                    progress=lambda msg: self.after(
                        0, lambda m=msg: self.btn_export_pack.configure(text=m[:28])),
                )
            except (MigrationError, OSError, ValueError) as e:
                self.after(0, lambda e=e: ZBBDialog.info(self, "Export Failed", str(e), kind="error"))
                return
            finally:
                self.after(0, lambda: self.btn_export_pack.configure(state="normal", text="Export as .zbbpack"))
            self.after(0, lambda: ZBBDialog.info(
                self, "Export Complete", f"Server '{self.server_name}' exported to:\n\n{dest_path}"))

        threading.Thread(target=_export, daemon=True).start()

    def _server_is_running(self) -> bool:
        return self.api.servers.is_running()

    def restore_backup(self, path: str):

        if self._server_is_running():
            ZBBDialog.info(
                self, "Server Running",
                "Stop the server before restoring a backup.", kind="error"
            )
            return

        confirm = ZBBDialog.confirm(
            self, "Confirm Restore",
            f"Are you sure you want to restore this backup?\n\n{os.path.basename(path)}\n\nCurrent world data will be overwritten.",
            confirm_text="Restore", danger=True,
        )
        if not confirm:
            return

        def worker():
            success = self.backups.restore(self.server_name, path)
            if self.winfo_exists():
                self.after(0, lambda: self._on_backup_restored(success))

        threading.Thread(target=worker, daemon=True).start()

    def _on_backup_restored(self, success):
        if success:
            ZBBDialog.info(self, "Success", "Server restored successfully.")
            self.refresh_backups()
        else:
            ZBBDialog.info(self, "Error", "Failed to restore backup.", kind="error")

    def _refresh_backup_countdown(self):
        if not self.winfo_exists():
            return
        secs = self.backups.seconds_until_auto(self.server_name)
        if secs is None:
            self._next_backup_lbl.configure(text="Auto-backup: disabled")
        elif secs == 0.0:
            self._next_backup_lbl.configure(text="Next auto-backup: overdue")
        else:
            h = int(secs // 3600)
            m = int((secs % 3600) // 60)
            self._next_backup_lbl.configure(text=f"Next auto-backup in: {h}h {m}m")
        self.after(60_000, self._refresh_backup_countdown)

    def setup_automation_tab(self):
        schedule = self.server_config.restart_schedule(self.server_name)
        
        card = self.create_section_frame(self.frame_automation, "Automated Restarts")

        self.var_auto_restart = ctk.BooleanVar(value=bool(schedule))
        self._start_row(card, "Enable Automated Restarts")
        self.chk_auto_restart = _bare_switch(card, variable=self.var_auto_restart,
                                             command=self.toggle_automation_inputs)
        self._grid_control(card, self.chk_auto_restart)

        self.var_backup_restart = ctk.BooleanVar(value=schedule.get("backup_on_restart", False) if schedule else False)
        _, self.lbl_backup_restart = self._start_row(card, "Backup before Restart")
        self.chk_backup_restart = _bare_switch(card, variable=self.var_backup_restart)
        self._grid_control(card, self.chk_backup_restart)

        mode = "time" if schedule and schedule.get("type") == "time" else "interval"
        self.var_schedule_mode = ctk.StringVar(value=i18n.choice_label(_SCHEDULE_MODES, mode))
        _, self.lbl_schedule_mode = self._start_row(card, "Schedule Mode")
        self.combo_mode = ctk.CTkOptionMenu(card, values=i18n.choice_labels(_SCHEDULE_MODES), variable=self.var_schedule_mode,
                                            command=self.toggle_automation_inputs, height=28, width=_CONTROL_WIDTH)
        self._grid_control(card, self.combo_mode)

        vcmd = (self.register(self.validate_int), '%P')
        _, self.lbl_interval = self._start_row(card, "Interval (hours)")
        self.entry_interval = ctk.CTkEntry(card, height=28, width=_CONTROL_WIDTH, validate="key", validatecommand=vcmd)
        self.entry_interval.insert(0, str(schedule.get("interval_hours", 6)) if schedule else "6")
        self._grid_control(card, self.entry_interval)

        _, self.lbl_time = self._start_row(card, "Daily Time (HH:MM)")
        self.entry_time = ctk.CTkEntry(card, height=28, width=_CONTROL_WIDTH)
        self.entry_time.insert(0, schedule.get("restart_time", "03:00") if schedule else "03:00")
        self._grid_control(card, self.entry_time)

        # Auto-Backups card (P0.2)
        bk_cfg = self.backups.auto_config(self.server_name)

        card_bk = self.create_section_frame(self.frame_automation, "Auto-Backups")

        self.var_auto_backup = ctk.BooleanVar(value=bk_cfg.get("enabled", False))
        self._start_row(card_bk, "Enable Auto-Backups")
        self._grid_control(card_bk, _bare_switch(card_bk, variable=self.var_auto_backup))

        vcmd2 = (self.register(self.validate_int), '%P')
        self._start_row(card_bk, "Interval (hours)")
        self.entry_bk_interval = ctk.CTkEntry(card_bk, height=28, width=_CONTROL_WIDTH, validate="key", validatecommand=vcmd2)
        self.entry_bk_interval.insert(0, str(bk_cfg.get("interval_hours", 24)))
        self._grid_control(card_bk, self.entry_bk_interval)

        self._start_row(card_bk, "Keep (last N backups)")
        self.entry_bk_retention = ctk.CTkEntry(card_bk, height=28, width=_CONTROL_WIDTH, validate="key", validatecommand=vcmd2)
        self.entry_bk_retention.insert(0, str(bk_cfg.get("retention_count", 10)))
        self._grid_control(card_bk, self.entry_bk_retention)

        self.toggle_automation_inputs()

    def toggle_automation_inputs(self, *args):
        enabled = self.var_auto_restart.get()
        interval = self._schedule_mode() == "interval"
        on, off = AppConfig.COLOR_TEXT_PRIMARY, AppConfig.COLOR_TEXT_GRAY
        self.combo_mode.configure(state="normal" if enabled else "disabled")
        self.chk_backup_restart.configure(state="normal" if enabled else "disabled")
        self.entry_interval.configure(state="normal" if enabled and interval else "disabled")
        self.entry_time.configure(state="normal" if enabled and not interval else "disabled")
        self.lbl_backup_restart.configure(text_color=on if enabled else off)
        self.lbl_schedule_mode.configure(text_color=on if enabled else off)
        self.lbl_interval.configure(text_color=on if enabled and interval else off)
        self.lbl_time.configure(text_color=on if enabled and not interval else off)

    def _schedule_mode(self) -> str:
        return i18n.choice_key(_SCHEDULE_MODES, self.var_schedule_mode.get(), "interval")

    def save_automation(self):
        if not self.var_auto_restart: return

        enabled = self.var_auto_restart.get()
        backup = self.var_backup_restart.get()
        if self._schedule_mode() == "interval":
            interval = 6
            try:
                interval = int(self.entry_interval.get())
            except ValueError:
                logger.warning("Invalid interval input, using default 6")
            self.server_config.set_restart_schedule(self.server_name, enabled, interval_hours=interval,
                                             backup_on_restart=backup)
        else:
            time_val = self.entry_time.get()
            self.server_config.set_restart_schedule(self.server_name, enabled, restart_time=time_val,
                                             backup_on_restart=backup)

        # Save auto-backup config
        if hasattr(self, "var_auto_backup"):
            bk_enabled = self.var_auto_backup.get()
            try:
                bk_interval = int(self.entry_bk_interval.get())
            except (ValueError, AttributeError):
                bk_interval = 24
            try:
                bk_retention = int(self.entry_bk_retention.get())
            except (ValueError, AttributeError):
                bk_retention = 10
            self.backups.set_auto_config(self.server_name, bk_enabled, bk_interval, bk_retention)

    def validate_int(self, P):
        """Callback to allow only digits."""
        if P == "" or P.isdigit():
            return True
        return False

    def _create_widget(self, parent, widget_type, val, options=None):
        compact_height = 28
        vcmd = (self.register(self.validate_int), '%P')
        
        if widget_type == "entry":
            widget = ctk.CTkEntry(parent, height=compact_height)
            if str(val).isdigit() or val == "":
                widget.configure(validate="key", validatecommand=vcmd)
            widget.insert(0, str(val))
            widget.pack(fill="x", expand=True, pady=0)
        elif widget_type == "checkbox":
            widget = _bare_switch(parent, height=compact_height)
            if str(val).lower() == "true":
                widget.select()
            widget.pack(anchor="e", pady=0)
        elif widget_type == "dropdown":
            widget = ctk.CTkOptionMenu(parent, values=options, height=compact_height)
            if val in options:
                widget.set(val)
            widget.pack(fill="x", expand=True, pady=0)
        return widget

    def create_section_frame(self, parent, title):
        """Creates a modern 'Card' container for a group of settings."""
        if title:
            lbl = ctk.CTkLabel(parent, text=title, font=self.font_header, 
                               text_color=AppConfig.COLOR_LINK, anchor="w")
            lbl.pack(fill="x", padx=15, pady=(15, 5))

        card = ctk.CTkFrame(parent, fg_color=(AppConfig.COLOR_BG_CARD_LIGHT, AppConfig.COLOR_BG_CARD_DARK), corner_radius=AppConfig.RADIUS_CARD)
        card.pack(fill="x", padx=10, pady=(0, 5))
        
        # Fixed widths for the help/impact/control columns: every card lines
        # them up at the same x, whether or not a card has any "?" or dot.
        card.grid_columnconfigure(0, weight=1) # Label
        card.grid_columnconfigure(1, weight=0, minsize=22) # Help Icon
        card.grid_columnconfigure(2, weight=0, minsize=12) # Impact Dot
        card.grid_columnconfigure(3, weight=0, minsize=_CONTROL_WIDTH + 2 * _CONTROL_PADX) # Control

        return card

    def _start_row(self, card, label_text: str, sticky: str = "w"):
        """Separator (after the first row) + label; returns (row, label)."""
        row = card.grid_size()[1]
        if row > 0:
            sep = ctk.CTkFrame(card, height=1, fg_color=(AppConfig.COLOR_BORDER_LIGHT, AppConfig.COLOR_BORDER_DARK))
            sep.grid(row=row, column=0, columnspan=4, sticky="ew", padx=10, pady=2)
            row += 1
        lbl = ctk.CTkLabel(card, text=label_text, font=self.font_bold, anchor="w")
        lbl.grid(row=row, column=0, sticky=sticky, padx=(12, 5), pady=8)
        return row, lbl

    @staticmethod
    def _grid_control(card, widget, row=None, **grid_kwargs):
        """Right-align a control in the shared control column of the last row."""
        if row is None:
            row = card.grid_size()[1] - 1
        opts = dict(row=row, column=3, sticky="e", padx=_CONTROL_PADX, pady=5)
        opts.update(grid_kwargs)
        widget.grid(**opts)

    def add_field_to_section(self, parent_card, key, label_text, widget_type="entry", options=None, default_val=None):
        """Adds a row to an existing section card using Grid."""
        meta = SETTINGS_METADATA.get(key, {})
        description = meta.get("desc")
        impact = meta.get("impact")
        
        # 1-2. Separator + label
        current_row, _label = self._start_row(parent_card, label_text)

        # 3. Help Icon (?)
        if description:
            help_icon = ctk.CTkLabel(parent_card, text="?", font=self.font_small, 
                                     width=18, height=18, corner_radius=9,
                                     fg_color=AppConfig.COLOR_BTN_GHOST, text_color=AppConfig.COLOR_TEXT_GRAY)
            help_icon.grid(row=current_row, column=1, sticky="w", padx=2)
            help_icon.tooltip_ref = ToolTip(help_icon, text=description)
            
        # 4. Impact Dot
        if impact and impact != "Low":
            colors = {"Medium": AppConfig.COLOR_STATUS_STARTING, "High": AppConfig.COLOR_STATUS_ERROR}
            dot = ctk.CTkFrame(parent_card, width=8, height=8, corner_radius=4, fg_color=colors[impact])
            dot.grid(row=current_row, column=2, sticky="w", padx=2)
            dot.tooltip_ref = ToolTip(dot, _("Impact: {level}").format(level=_(_IMPACT_LABELS[impact])))

        # 5. Control Frame (for alignment)
        ctrl_frame = ctk.CTkFrame(parent_card, fg_color="transparent", width=_CONTROL_WIDTH, height=28)
        self._grid_control(parent_card, ctrl_frame, row=current_row, pady=3)
        ctrl_frame.pack_propagate(False)
        
        val = self.properties.get(key)
        if val is None:
            val = default_val if default_val is not None else ""
            
        widget = self._create_widget(ctrl_frame, widget_type, val, options)
        self.widgets[key] = (widget, widget_type)

    # Keys where the enable/spawn/white-list/... substring heuristic below
    # doesn't apply but the value is still a vanilla true/false toggle.
    def _build_tab_from_config(self, parent_frame, tab_name):
        """Generates UI sections dynamically based on TAB_LAYOUTS config."""
        layout = TAB_LAYOUTS.get(tab_name, {})

        for section_title, keys in layout.items():
            card = self.create_section_frame(parent_frame, section_title)
            for key in keys:
                label = property_label(key)

                widget_type, options = property_control(key)
                if key == "level-name":
                    worlds = self.api.config.worlds(self.server_name)
                    current = self.properties.get("level-name", "world")
                    if worlds:
                        widget_type = "dropdown"
                        options = worlds if current in worlds else worlds + [current]
                    else:
                        widget_type = "entry"

                self.add_field_to_section(card, key, label, widget_type, options)

    def setup_general_tab(self):
        # 1. Identity Section
        card_identity = self.create_section_frame(self.frame_general, "Identity & Appearance")
        
        self._start_row(card_identity, "Server Icon")
        btn = ctk.CTkButton(card_identity, text="Change Icon", command=self.change_icon,
                            width=100, height=28, fg_color="transparent", border_width=AppConfig.BORDER_BTN,
                            border_color=(AppConfig.COLOR_BORDER_LIGHT, AppConfig.COLOR_BORDER_DARK),
                            hover_color=AppConfig.COLOR_BTN_GHOST_HOVER,
                            text_color=AppConfig.COLOR_TEXT_PRIMARY)
        self._grid_control(card_identity, btn)

        current_row, _ = self._start_row(card_identity, "Message of the Day", sticky="nw")

        motd_help_icon = ctk.CTkLabel(card_identity, text="?", font=self.font_small,
                                 width=18, height=18, corner_radius=9,
                                 fg_color=AppConfig.COLOR_BTN_GHOST, text_color=AppConfig.COLOR_TEXT_GRAY)
        motd_help_icon.grid(row=current_row, column=1, sticky="nw", padx=2, pady=13)
        motd_help_icon.tooltip_ref = ToolTip(motd_help_icon, text="Message shown in the multiplayer server list. Supports § color codes - the preview below shows the result.")

        motd_frame = ctk.CTkFrame(card_identity, fg_color="transparent")
        self._grid_control(card_identity, motd_frame, row=current_row)

        self.entry_motd = ctk.CTkEntry(motd_frame, width=_CONTROL_WIDTH, height=28)
        self.entry_motd.pack(fill="x", pady=(0, 5))
        self.entry_motd.insert(0, self.properties.get("motd", "A Minecraft Server"))
        self.entry_motd.bind("<KeyRelease>", self._update_motd_preview)

        self.preview_motd_frame = ctk.CTkFrame(motd_frame, fg_color=(AppConfig.COLOR_CONSOLE_LIGHT, AppConfig.COLOR_CONSOLE_DARK), corner_radius=0, border_width=2, border_color=(AppConfig.COLOR_BORDER_LIGHT, AppConfig.COLOR_BORDER_DARK))
        self.preview_motd_frame.pack(fill="x", pady=(0, 0))
        
        self.motd_preview = ctk.CTkTextbox(self.preview_motd_frame, height=45, width=_CONTROL_WIDTH - 4, fg_color=(AppConfig.COLOR_CONSOLE_LIGHT, AppConfig.COLOR_CONSOLE_DARK), text_color=AppConfig.COLOR_TEXT_GRAY, font=AppConfig.FONT_MONO, wrap="word")
        self.motd_preview.pack(fill="both", expand=True, padx=2, pady=2)
        
        mc_colors = {
            '0': '#000000', '1': '#0000AA', '2': '#00AA00', '3': '#00AAAA',
            '4': '#AA0000', '5': '#AA00AA', '6': '#FFAA00', '7': '#AAAAAA',
            '8': '#555555', '9': '#5555FF', 'a': '#55FF55', 'b': '#55FFFF',
            'c': '#FF5555', 'd': '#FF55FF', 'e': '#FFFF55', 'f': '#FFFFFF'
        }
        for code, hex_color in mc_colors.items():
            self.motd_preview.tag_config(f"mc_{code}", foreground=hex_color)
        # Removed font argument from mc_l due to CTk scaling limitations
            
        self.widgets["motd"] = (self.entry_motd, "entry")
        self._update_motd_preview()

        # 2. Resources Section
        card_res = self.create_section_frame(self.frame_general, "Resources")
        
        self._start_row(card_res, "RAM Allocation")
        ram_ctrl = ctk.CTkFrame(card_res, fg_color="transparent", width=_CONTROL_WIDTH, height=28)
        self._grid_control(card_res, ram_ctrl, pady=3)
        ram_ctrl.pack_propagate(False)
        
        vcmd = (self.register(self.validate_int), '%P')
        self.entry_ram = ctk.CTkEntry(ram_ctrl, height=28, validate="key", validatecommand=vcmd)
        self.entry_ram.insert(0, str(self.server_config.ram_mb(self.server_name)))
        self.entry_ram.pack(fill="x")

        # 3. Gameplay Section
        card_game = self.create_section_frame(self.frame_general, "Gameplay Rules")
        self.add_field_to_section(card_game, "max-players", "Max Players", default_val="20")
        self.add_field_to_section(card_game, "gamemode", "Game Mode", "dropdown", ["survival", "creative", "adventure", "spectator"])
        self.add_field_to_section(card_game, "force-gamemode", "Force Game Mode", "checkbox")
        self.add_field_to_section(card_game, "difficulty", "Difficulty", "dropdown", ["peaceful", "easy", "normal", "hard"])
        self.add_field_to_section(card_game, "hardcore", "Hardcore Mode", "checkbox")
        self.add_field_to_section(card_game, "enable-command-block", "Command Blocks", "checkbox")

        # 4. Modpack Import Section
        card_mrpack = self.create_section_frame(self.frame_general, "Modpack Import")
        self._start_row(card_mrpack, "Import from .mrpack")

        self.btn_mrpack = ctk.CTkButton(
            card_mrpack, text="Import .mrpack", image=icon("download", 13, AppConfig.COLOR_TEXT_ON_ACCENT), width=150, height=28,
            corner_radius=AppConfig.RADIUS_BTN,
            fg_color=AppConfig.COLOR_ACCENT_BROWN, hover_color=AppConfig.COLOR_ACCENT_BROWN_HOVER,
            text_color=AppConfig.COLOR_TEXT_ON_ACCENT, font=AppConfig.FONT_BADGE,
            command=self._on_import_mrpack,
        )
        self._grid_control(card_mrpack, self.btn_mrpack, row=0)

        self.lbl_mrpack_status = ctk.CTkLabel(
            card_mrpack, text="", font=self.font_small, anchor="w",
            text_color=AppConfig.COLOR_TEXT_GRAY,
        )
        self.lbl_mrpack_status.grid(row=1, column=0, columnspan=4, sticky="w", padx=12, pady=(0, 8))

    def _set_mrpack_status(self, text: str, kind: str = "info"):
        colors = {
            "success": AppConfig.COLOR_STATUS_ONLINE,
            "error": AppConfig.COLOR_STATUS_ERROR,
        }
        if self.lbl_mrpack_status.winfo_exists():
            self.lbl_mrpack_status.configure(
                text=text, text_color=colors.get(kind, AppConfig.COLOR_TEXT_GRAY))

    def _on_import_mrpack(self):
        meta = self.server_config.meta(self.server_name)
        loader = meta.get("type", "vanilla")
        if loader in (None, "vanilla"):
            ZBBDialog.info(
                self, "Vanilla Server",
                "Vanilla servers can't load mods or plugins.\n\n"
                "Create a Fabric, Forge or NeoForge server for mods, or Paper/Purpur for plugins.",
            )
            return

        if self._server_is_running():
            ZBBDialog.info(
                self, "Server Running",
                "Stop the server before importing a modpack.", kind="error"
            )
            return

        mrpack_path = filedialog.askopenfilename(
            title="Select Modpack File",
            filetypes=[("Modrinth Modpack", "*.mrpack"), ("All files", "*.*")],
        )
        if not mrpack_path:
            return

        self._set_mrpack_status("Importing modpack…")
        self.btn_mrpack.configure(state="disabled")

        def _import():
            try:
                summary = self.server_config.import_modpack(
                    self.server_name, mrpack_path,
                    on_status=lambda msg: self.after(0, lambda m=msg: self._set_mrpack_status(m)),
                )
                parts = [f"{summary['installed']} mods installed"]
                if summary.get("skipped_client"):
                    parts.append(f"{summary['skipped_client']} client-only skipped")
                if summary.get("failed"):
                    parts.append(f"{summary['failed']} failed")
                text = ", ".join(parts)
                self.after(0, lambda t=text: self._set_mrpack_status(t, kind="success"))
            except MrpackCompatibilityError as exc:
                self.after(0, lambda e=exc: self._set_mrpack_status(f"Incompatible: {e}", kind="error"))
                self.after(0, lambda e=exc: ZBBDialog.info(
                    self, "Incompatible Modpack", str(e), kind="warning"))
            except Exception as exc:
                logger.error("mrpack import failed: %s", exc)
                self.after(0, lambda e=exc: self._set_mrpack_status(f"Import failed: {e}", kind="error"))
            finally:
                self.after(0, lambda: self.btn_mrpack.configure(state="normal"))

        threading.Thread(target=_import, daemon=True).start()

    def setup_world_tab(self):
        ctk.CTkLabel(
            self.frame_world,
            text="Changing the active world requires the server to be stopped for the change to take effect.",
            font=self.font_small, text_color=AppConfig.COLOR_TEXT_GRAY, anchor="w", wraplength=600,
        ).pack(fill="x", padx=15, pady=(4, 0))
        self._build_tab_from_config(self.frame_world, "World")

    def setup_network_tab(self):
        self._build_tab_from_config(self.frame_network, "Network")

    def setup_advanced_tab(self):
        self._build_tab_from_config(self.frame_advanced, "Advanced")
        
        # Dynamic "Other Properties"
        card_other = self.create_section_frame(self.frame_advanced, "Other Properties")
        
        used_keys = set(self.widgets.keys())
        used_keys.update(["motd", "server-ip", "server-port", "white-list", "enforce-whitelist"]) 
        
        for key, val in self.properties.items():
            if key not in used_keys and "rcon" not in key and "query" not in key:
                self.add_field_to_section(card_other, key, key, "entry")

    def change_icon(self):
        file_path = filedialog.askopenfilename(
            title="Select Server Icon",
            filetypes=[("Images", "*.png;*.jpg;*.jpeg")]
        )
        if file_path:
            self.server_config.set_icon(self.server_name, file_path)

    def _update_motd_preview(self, event=None):
        text = self.entry_motd.get()
        self.motd_preview.configure(state="normal")
        self.motd_preview.delete("1.0", "end")
        
        import re
        parts = re.split(r'([§&][0-9a-fk-or])', text)
        current_tag = "mc_7" # default gray
        for p in parts:
            if re.match(r'^[§&][0-9a-fk-or]$', p):
                code = p[1].lower()
                if code in '0123456789abcdef':
                    current_tag = f"mc_{code}"
            else:
                self.motd_preview.insert("end", p, current_tag)
        self.motd_preview.configure(state="disabled")

    def save_properties(self):
        # 1. Validate RAM (General Tab)
        if self.entry_ram:
            ram_input = self.entry_ram.get()
            if not ram_input.isdigit():
                self.entry_ram.configure(border_color=AppConfig.COLOR_BTN_DANGER)
                self.tabview.set("General")
                ZBBDialog.info(self, "Invalid Input", "RAM Allocation must be a whole number (MB).", kind="error")
                return
            self.entry_ram.configure(border_color=(AppConfig.COLOR_BORDER_LIGHT, AppConfig.COLOR_BORDER_DARK))
            
            try:
                ram = int(ram_input)
                self.server_config.set_ram_mb(self.server_name, ram)
            except ValueError:
                logger.warning("Invalid RAM input: %s", ram_input)

        # 2. Validate Automation Interval (Automation Tab)
        if self.var_auto_restart and self.var_auto_restart.get():
            interval_input = self.entry_interval.get()
            if not interval_input.isdigit():
                self.entry_interval.configure(border_color=AppConfig.COLOR_BTN_DANGER)
                self.tabview.set("Automation")
                ZBBDialog.info(self, "Invalid Input", "Restart Interval must be a whole number (Hours).", kind="error")
                return
            self.entry_interval.configure(border_color=(AppConfig.COLOR_BORDER_LIGHT, AppConfig.COLOR_BORDER_DARK))

        self.save_automation()

        new_props = {}
        for key, (widget, w_type) in self.widgets.items():
            if w_type == "entry":
                new_props[key] = widget.get()
            elif w_type == "checkbox":
                new_props[key] = "true" if widget.get() == 1 else "false"
            elif w_type == "dropdown":
                new_props[key] = widget.get()
                
        self.server_config.save_properties(self.server_name, new_props)
        if "Launch" in self.loaded_tabs:
            self.save_launch_settings()
        self.destroy()
    def _grid_help_icon(self, parent, row, text):
        """Small '?' badge with a tooltip, in the help column of a section card."""
        help_icon = ctk.CTkLabel(parent, text="?", font=self.font_small,
                                 width=18, height=18, corner_radius=9,
                                 fg_color=AppConfig.COLOR_BTN_GHOST, text_color=AppConfig.COLOR_TEXT_GRAY)
        help_icon.grid(row=row, column=1, sticky="w", padx=2, pady=8)
        help_icon.tooltip_ref = ToolTip(help_icon, text=text)
        return help_icon

    def setup_launch_tab(self):
        """Setup Java and Launch arguments tab."""
        card = self.create_section_frame(self.frame_launch, "Java & Runtime")

        # Java Path
        self._start_row(card, "Java Version")
        self._grid_help_icon(card, 0, (
            "Which Java runtime launches the server.\n"
            "Auto-Detect picks the version your Minecraft version requires\n"
            "(Java 25 for 26.1+, 21 for 1.20.5-1.21.x, 17 for 1.18-1.20.4,\n"
            "8 for older) and "
            "downloads it automatically if it's not installed."
        ))
        
        self._java_label_to_path = {"Auto-Detect": "auto"}
        self._java_path_to_label = {"auto": "Auto-Detect"}

        launch = self.server_config.launch_settings(self.server_name)

        saved_path = launch.java_path
        # Placeholder mapping so a previously saved path stays selectable
        # (and saveable) while detection runs in the background
        if saved_path != "auto":
            self._java_label_to_path[saved_path] = saved_path
            self._java_path_to_label[saved_path] = saved_path
        self.var_java_path = ctk.StringVar(value=self._java_path_to_label.get(saved_path, "Auto-Detect"))

        self.combo_java = ctk.CTkOptionMenu(card, values=list(self._java_label_to_path.keys()),
                                            variable=self.var_java_path, height=28, width=_CONTROL_WIDTH,
                                            dynamic_resizing=False)
        self._grid_control(card, self.combo_java, row=0)

        # detect_all() scans registry + filesystem — keep it off the UI thread
        def _load_javas():
            javas = self.api.java.installations()

            def _apply():
                if not self.combo_java.winfo_exists():
                    return
                for j, label in zip(javas, dropdown_labels(javas)):
                    self._java_label_to_path[label] = j.path
                    self._java_path_to_label[j.path] = label
                if saved_path != "auto" and self._java_path_to_label.get(saved_path) != saved_path:
                    # Real label now known — replace the raw-path placeholder
                    self._java_label_to_path.pop(saved_path, None)
                    if self.var_java_path.get() == saved_path:
                        self.var_java_path.set(self._java_path_to_label[saved_path])
                self.combo_java.configure(values=list(self._java_label_to_path.keys()))

            self.after(0, _apply)

        threading.Thread(target=_load_javas, daemon=True).start()

        # Aikar's Flags
        row, _ = self._start_row(card, "Use Aikar's Flags")
        self._grid_help_icon(card, row, (
            "Community-tuned JVM garbage collector flags (from PaperMC)\n"
            "that reduce lag spikes on Minecraft servers. Recommended: on.\n"
            "When off, only the basic memory flags (-Xms/-Xmx) are used."
        ))
        self.var_use_aikars = ctk.BooleanVar(value=launch.use_aikars)
        self.chk_aikars = _bare_switch(card, variable=self.var_use_aikars)
        self._grid_control(card, self.chk_aikars, row=row)

        # Custom JVM Flags
        row, _ = self._start_row(card, "Custom JVM Flags")
        self._grid_help_icon(card, row, (
            "Extra arguments appended to the Java command line, after the\n"
            "memory and GC flags. Space-separated. Leave empty unless a mod\n"
            "or guide asks for a specific flag - a wrong flag can prevent\n"
            "the server from starting."
        ))
        self.entry_jvm_flags = ctk.CTkEntry(card, height=28, width=_CONTROL_WIDTH)
        self.entry_jvm_flags.insert(0, launch.jvm_custom_flags)
        self._grid_control(card, self.entry_jvm_flags, row=row)
        ctk.CTkLabel(card, text="e.g. -XX:+UseG1GC -Dfoo=bar", font=self.font_small,
                     text_color=AppConfig.COLOR_TEXT_GRAY,
                     anchor="e").grid(row=row + 1, column=3, sticky="e", padx=_CONTROL_PADX, pady=(0, 8))

        # Tools
        card_tools = self.create_section_frame(self.frame_launch, "Utilities")
        tools_row = ctk.CTkFrame(card_tools, fg_color="transparent")
        tools_row.pack(fill="x", padx=12, pady=12)
        tools_row.grid_columnconfigure((0, 1, 2), weight=1, uniform="tools")
        buttons = (
            ("Open Server Folder", "folder", None,
             "The server's root folder (world, mods, configs)."),
            ("Open Logs", "folder", "logs",
             "Full server logs, including sessions older than the console buffer."),
            ("Open Crash Reports", "folder", "crash_reports",
             "JSON diagnostics ZBB writes every time the server crashes."),
        )
        for col, (label, icon_name, subpath, tip) in enumerate(buttons):
            btn = ctk.CTkButton(
                tools_row, text=label, image=icon(icon_name, 14),
                command=lambda s=subpath: self.open_folder(s),
                fg_color=AppConfig.COLOR_BTN_GHOST, text_color=AppConfig.COLOR_TEXT_PRIMARY, hover_color=AppConfig.COLOR_BTN_GHOST_HOVER,
                corner_radius=AppConfig.RADIUS_BTN, height=36,
            )
            btn.grid(row=0, column=col, sticky="ew", padx=(0 if col == 0 else 8, 0))
            btn.tooltip_ref = ToolTip(btn, tip)

    def open_folder(self, subpath=None):
        self._open_path(self.api.storage.server_dir(self.server_name, subpath or ""))

    def _open_path(self, server_path):
        if not os.path.exists(server_path):
            ZBBDialog.info(self, "Nothing Here Yet",
                           "That folder does not exist yet - it is created the first time it is needed.",
                           kind="info")
            return
        self.api.storage.open_folder(server_path)

    def save_launch_settings(self):
        label = self.var_java_path.get()
        path = getattr(self, "_java_label_to_path", {}).get(label, "auto")
        self.server_config.save_launch_settings(self.server_name, LaunchSettings(
            path, self.var_use_aikars.get(), self.entry_jvm_flags.get().strip()))
