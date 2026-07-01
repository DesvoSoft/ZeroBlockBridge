import customtkinter as ctk
from tkinter import filedialog, messagebox
import logging
import os
import subprocess
import sys
import threading
from app.core.app_config import AppConfig
from app.core.constants import SERVERS_DIR

logger = logging.getLogger(__name__)
from app.ui.ui_components import ToolTip
from app.services.backup_manager import BackupManager
from app.services.server_properties import load_server_properties, save_server_properties
from app.core.logic import BackupScheduler


SETTINGS_METADATA = {
    # General
    "max-players": {"desc": "Maximum number of players allowed online.", "impact": "Low"},
    "gamemode": {"desc": "The default game mode for new players.", "impact": "Low"},
    "force-gamemode": {"desc": "Forces players to join in the default game mode.", "impact": "Low"},
    "difficulty": {"desc": "Overall game difficulty. Affects damage and mob behavior.", "impact": "Low"},
    "hardcore": {"desc": "Players are banned upon death. One life only.", "impact": "Medium"},
    "enable-command-block": {"desc": "Allows the use of command blocks in-game.", "impact": "Low"},
    
    # World
    "level-seed": {"desc": "The unique code used to generate the world. Leave empty for random.", "impact": "Low"},
    "level-name": {"desc": "The name of the world folder on disk.", "impact": "Low"},
    "level-type": {"desc": "The type of world generation (Flat, Large Biomes, etc).", "impact": "Medium"},
    "generate-structures": {"desc": "Whether to generate villages, dungeons, etc.", "impact": "Medium"},
    "spawn-npcs": {"desc": "Whether to spawn villagers.", "impact": "Low"},
    "spawn-animals": {"desc": "Whether to spawn passive mobs like cows and sheep.", "impact": "Medium"},
    "spawn-monsters": {"desc": "Whether to spawn hostile mobs.", "impact": "Medium"},
    "view-distance": {"desc": "How many chunks are visible to players. Higher = More RAM usage.", "impact": "High"},
    "simulation-distance": {"desc": "How many chunks process active ticks (crops, mobs).", "impact": "High"},
    
    # Network
    "server-port": {"desc": "The port the server listens on (Default: 25565).", "impact": "Low"},
    "white-list": {"desc": "Only allowed players can join the server.", "impact": "Low"},
    "online-mode": {"desc": "Checks players against Mojang accounts. Disable for 'cracked' servers.", "impact": "Medium"},
    "network-compression-threshold": {"desc": "Size at which packets are compressed. Lower = More CPU usage.", "impact": "Medium"},
    
    # Advanced
    "sync-chunk-writes": {"desc": "Ensures world data is saved safely. Disabling can boost performance but risks corruption.", "impact": "High"},
    "op-permission-level": {"desc": "Default power level for operators (1-4).", "impact": "Medium"},
    "prevent-proxy-connections": {"desc": "Blocks players using VPNs or Proxies.", "impact": "Low"},
    "enforce-secure-profile": {"desc": "Requires Mojang-signed public keys for players.", "impact": "Low"},
    "enable-rcon": {"desc": "Allows remote console access (for bots/panels).", "impact": "Medium"},
    "enable-query": {"desc": "Allows external tools to see server status.", "impact": "Low"},
}

# Define the layout for the complex tabs
TAB_LAYOUTS = {
    "World": {
        "🌿 Environment & Generation": [
            "level-seed", "level-name", "level-type", "generate-structures"
        ],
        "🐾 Entities & Spawning": [
            "spawn-npcs", "spawn-animals", "spawn-monsters"
        ],
        "⚙️ Performance": [
            "view-distance", "simulation-distance"
        ]
    },
    "Network": {
        "Connectivity": ["server-port", "server-ip"],
        "Access Control": ["white-list", "enforce-whitelist", "online-mode"],
        "Optimization": ["network-compression-threshold"],
        "Remote Access": ["enable-rcon", "rcon.password", "rcon.port"]
    },
    "Advanced": {
        "🚀 System Performance": ["sync-chunk-writes"],
        "🛡️ Security & Permissions": [
            "op-permission-level", "prevent-proxy-connections", "enforce-secure-profile"
        ]
    }
}

class ServerPropertiesEditor(ctk.CTkToplevel):
    def __init__(self, parent, server_name, logic_module, zbb_manager=None):
        super().__init__(parent)
        self.title(f"Edit Properties - {server_name}")
        self.geometry("700x600")
        self.resizable(True, True)

        self.server_name = server_name
        self.logic = logic_module
        self.zbb_manager = zbb_manager
        self.properties = load_server_properties(server_name)
        
        # Shared Fonts
        self.font_bold = ctk.CTkFont(family=AppConfig.FONT_BODY[0], size=13, weight="bold")
        self.font_small = ctk.CTkFont(family=AppConfig.FONT_BODY[0], size=11)
        self.font_header = ctk.CTkFont(family=AppConfig.FONT_BODY[0], size=14, weight="bold")
        
        # Layout
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(0, weight=1) # Content
        self.grid_rowconfigure(1, weight=0) # Buttons
        
        # Tabview
        self.tabview = ctk.CTkTabview(self)
        self.tabview.grid(row=0, column=0, sticky="nsew", padx=10, pady=10)
        
        self.tab_general = self.tabview.add("General")
        self.tab_world = self.tabview.add("World")
        self.tab_network = self.tabview.add("Network")
        self.tab_advanced = self.tabview.add("Advanced")
        self.tab_backups = self.tabview.add("Backups")
        self.tab_automation = self.tabview.add("Automation")
        self.tab_launch = self.tabview.add("Launch")
        
        # Set tab change command for optimization
        self.tabview.configure(command=self._on_tab_changed)
        
        # Scrollable frames for tabs
        self.frame_general = ctk.CTkScrollableFrame(self.tab_general)
        self.frame_general.pack(fill="both", expand=True)
        
        self.frame_world = ctk.CTkScrollableFrame(self.tab_world)
        self.frame_world.pack(fill="both", expand=True)
        
        self.frame_network = ctk.CTkScrollableFrame(self.tab_network)
        self.frame_network.pack(fill="both", expand=True)
        
        self.frame_advanced = ctk.CTkScrollableFrame(self.tab_advanced)
        self.frame_advanced.pack(fill="both", expand=True)

        self.frame_backups = ctk.CTkFrame(self.tab_backups, fg_color="transparent")
        self.frame_backups.pack(fill="both", expand=True)

        self.frame_automation = ctk.CTkFrame(self.tab_automation, fg_color="transparent")
        self.frame_automation.pack(fill="both", expand=True)

        self.frame_launch = ctk.CTkScrollableFrame(self.tab_launch)
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
        self.btn_frame = ctk.CTkFrame(self, fg_color="transparent")
        self.btn_frame.grid(row=1, column=0, sticky="ew", padx=10, pady=10)
        
        self.btn_cancel = ctk.CTkButton(self.btn_frame, text="Cancel", command=self.destroy,
                                         fg_color=AppConfig.COLOR_BTN_GHOST, hover_color=AppConfig.COLOR_BTN_GHOST_HOVER,
                                         corner_radius=12, height=36)
        self.btn_cancel.pack(side="right", padx=5)

        self.btn_save = ctk.CTkButton(self.btn_frame, text="Save", command=self.save_properties,
                                      fg_color=AppConfig.COLOR_BTN_SUCCESS, hover_color=AppConfig.COLOR_BTN_SUCCESS_HOVER,
                                      corner_radius=12, height=36)
        self.btn_save.pack(side="right", padx=5)
        
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
        # Toolbar
        toolbar = ctk.CTkFrame(self.frame_backups)
        toolbar.pack(fill="x", pady=5)
        
        ctk.CTkButton(toolbar, text="Create Backup", command=self.create_backup, fg_color="green", width=120).pack(side="left", padx=5)
        ctk.CTkButton(toolbar, text="Restore Selected", command=self.restore_backup, fg_color="orange", width=120).pack(side="left", padx=5)
        ctk.CTkButton(toolbar, text="Refresh", command=self.refresh_backups, width=80).pack(side="right", padx=5)
        
        # List
        self.backup_list_frame = ctk.CTkScrollableFrame(self.frame_backups)
        self.backup_list_frame.pack(fill="both", expand=True, pady=5)
        
        self.backup_var = ctk.StringVar()
        self.backup_manager = BackupManager(self.server_name)
        self._backup_scheduler_ui = BackupScheduler(self.server_name)
        self._next_backup_lbl = ctk.CTkLabel(
            self.frame_backups, text="", anchor="w",
            text_color=(AppConfig.COLOR_TEXT_MUTED, AppConfig.COLOR_TEXT_GRAY), font=("Roboto", 12)
        )
        self._next_backup_lbl.pack(fill="x", padx=15, pady=(0, 4))
        self._refresh_backup_countdown()

    def refresh_backups(self):
        # Clear current list
        for widget in self.backup_list_frame.winfo_children():
            widget.destroy()
            
        # Show loading state
        loading_lbl = ctk.CTkLabel(self.backup_list_frame, text="Scanning backups...")
        loading_lbl.pack(pady=20)
        
        def load():
            backups = self.backup_manager.list_backups()
            if self.winfo_exists():
                self.after(0, lambda: self._populate_backups(backups, loading_lbl))
            
        threading.Thread(target=load, daemon=True).start()

    def _populate_backups(self, backups, loading_lbl):
        if loading_lbl.winfo_exists():
            loading_lbl.destroy()
            
        if not backups:
            ctk.CTkLabel(self.backup_list_frame, text="No backups found.").pack(pady=20)
            return
            
        for backup in backups:
            row = ctk.CTkFrame(self.backup_list_frame)
            row.pack(fill="x", pady=2)
            
            rb = ctk.CTkRadioButton(row, text=f"{backup['date']} ({backup['size']})", variable=self.backup_var, value=backup['path'])
            rb.pack(side="left", padx=10, pady=5)

    def create_backup(self):
        def worker():
            path, error = self.backup_manager.create_backup()
            if self.winfo_exists():
                self.after(0, lambda: self._on_backup_created(path, error))

        threading.Thread(target=worker, daemon=True).start()

    def _on_backup_created(self, path, error):
        if error and not path:
            messagebox.showerror("Error", f"Failed to create backup.\n\n{error}")
        elif error:
            messagebox.showwarning("Backup Created", error)
        self.refresh_backups()

    def _server_is_running(self) -> bool:
        runner = getattr(self.zbb_manager, "server_runner", None) if self.zbb_manager else None
        return bool(runner and runner.running)

    def restore_backup(self):
        path = self.backup_var.get()
        if not path:
            return

        if self._server_is_running():
            messagebox.showerror(
                "Server Running",
                "Stop the server before restoring a backup."
            )
            return

        confirm = messagebox.askyesno(
            "Confirm Restore",
            f"Are you sure you want to restore this backup?\n\n{os.path.basename(path)}\n\nCurrent world data will be overwritten."
        )
        if not confirm:
            return

        def worker():
            success = self.backup_manager.restore_backup(path)
            if self.winfo_exists():
                self.after(0, lambda: self._on_backup_restored(success))

        threading.Thread(target=worker, daemon=True).start()

    def _on_backup_restored(self, success):
        if success:
            messagebox.showinfo("Success", "Server restored successfully.")
            self.refresh_backups()
        else:
            messagebox.showerror("Error", "Failed to restore backup.")

    def _refresh_backup_countdown(self):
        if not self.winfo_exists():
            return
        secs = self._backup_scheduler_ui.seconds_until_next()
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
        self.scheduler = self.logic.Scheduler(self.server_name)
        schedule = self.scheduler.get_schedule()
        
        card = self.create_section_frame(self.frame_automation, "Automated Restarts")
        
        # Enable Toggle
        self.var_auto_restart = ctk.BooleanVar(value=bool(schedule))
        self.chk_auto_restart = ctk.CTkSwitch(card, text="Enable Automated Restarts", 
                                                variable=self.var_auto_restart, command=self.toggle_automation_inputs)
        self.chk_auto_restart.grid(row=0, column=0, columnspan=2, sticky="w", padx=15, pady=10)
        
        # Backup on Restart Toggle
        self.var_backup_restart = ctk.BooleanVar(value=schedule.get("backup_on_restart", False) if schedule else False)
        self.chk_backup_restart = ctk.CTkSwitch(card, text="Backup before Restart", variable=self.var_backup_restart)
        self.chk_backup_restart.grid(row=1, column=0, columnspan=2, sticky="w", padx=15, pady=(0, 10))

        # Separator
        ctk.CTkFrame(card, height=1, fg_color=(AppConfig.COLOR_BORDER_LIGHT, AppConfig.COLOR_BORDER_DARK)).grid(row=2, column=0, columnspan=4, sticky="ew", padx=15, pady=5)
        
        # Mode Selection
        ctk.CTkLabel(card, text="Schedule Mode:", font=self.font_bold, anchor="w").grid(row=3, column=0, sticky="w", padx=(12, 5), pady=8)
        self.var_schedule_mode = ctk.StringVar(value="Interval")
        if schedule and schedule.get("type") == "time":
            self.var_schedule_mode.set("Daily Time")
            
        self.combo_mode = ctk.CTkOptionMenu(card, values=["Interval", "Daily Time"], variable=self.var_schedule_mode, command=self.toggle_automation_inputs, height=28)
        self.combo_mode.grid(row=3, column=2, sticky="e", padx=12, pady=5)

        # Interval Input
        self.lbl_interval = ctk.CTkLabel(card, text="Interval (Hours):", font=self.font_bold, anchor="w")
        self.lbl_interval.grid(row=4, column=0, sticky="w", padx=(12, 5), pady=8)
        
        vcmd = (self.register(self.validate_int), '%P')
        self.entry_interval = ctk.CTkEntry(card, height=28, validate="key", validatecommand=vcmd, width=100)
        self.entry_interval.grid(row=4, column=2, sticky="e", padx=12, pady=5)
        self.entry_interval.insert(0, str(schedule.get("interval_hours", 6)) if schedule else "6")
        
        # Time Input
        self.lbl_time = ctk.CTkLabel(card, text="Daily Time (HH:MM):", font=self.font_bold, anchor="w")
        self.lbl_time.grid(row=5, column=0, sticky="w", padx=(12, 5), pady=8)
        
        self.entry_time = ctk.CTkEntry(card, height=28, width=100)
        self.entry_time.grid(row=5, column=2, sticky="e", padx=12, pady=5)
        self.entry_time.insert(0, schedule.get("restart_time", "03:00") if schedule else "03:00")

        # Auto-Backups card (P0.2)
        backup_sched = BackupScheduler(self.server_name)
        bk_cfg = backup_sched.get_config()

        card_bk = self.create_section_frame(self.frame_automation, "Auto-Backups")

        self.var_auto_backup = ctk.BooleanVar(value=bk_cfg.get("enabled", False))
        ctk.CTkSwitch(card_bk, text="Enable Auto-Backups", variable=self.var_auto_backup).grid(
            row=0, column=0, columnspan=4, sticky="w", padx=15, pady=10
        )

        ctk.CTkFrame(card_bk, height=1, fg_color=(AppConfig.COLOR_BORDER_LIGHT, AppConfig.COLOR_BORDER_DARK)).grid(
            row=1, column=0, columnspan=4, sticky="ew", padx=15, pady=2
        )

        ctk.CTkLabel(card_bk, text="Interval (Hours):", font=self.font_bold, anchor="w").grid(
            row=2, column=0, sticky="w", padx=(12, 5), pady=8
        )
        vcmd2 = (self.register(self.validate_int), '%P')
        self.entry_bk_interval = ctk.CTkEntry(card_bk, height=28, width=80, validate="key", validatecommand=vcmd2)
        self.entry_bk_interval.insert(0, str(bk_cfg.get("interval_hours", 24)))
        self.entry_bk_interval.grid(row=2, column=3, sticky="e", padx=12, pady=5)

        ctk.CTkLabel(card_bk, text="Keep (last N backups):", font=self.font_bold, anchor="w").grid(
            row=3, column=0, sticky="w", padx=(12, 5), pady=8
        )
        self.entry_bk_retention = ctk.CTkEntry(card_bk, height=28, width=80, validate="key", validatecommand=vcmd2)
        self.entry_bk_retention.insert(0, str(bk_cfg.get("retention_count", 10)))
        self.entry_bk_retention.grid(row=3, column=3, sticky="e", padx=12, pady=5)

        self.toggle_automation_inputs()

    def toggle_automation_inputs(self, *args):
        if self.var_auto_restart.get():
            self.combo_mode.configure(state="normal")
            self.chk_backup_restart.configure(state="normal")
            if self.var_schedule_mode.get() == "Interval":
                self.entry_interval.configure(state="normal")
                self.lbl_interval.configure(text_color=("black", "white"))
                self.entry_time.configure(state="disabled")
                self.lbl_time.configure(text_color=AppConfig.COLOR_TEXT_GRAY)
            else:
                self.entry_interval.configure(state="disabled")
                self.lbl_interval.configure(text_color=AppConfig.COLOR_TEXT_GRAY)
                self.entry_time.configure(state="normal")
                self.lbl_time.configure(text_color=("black", "white"))
        else:
            self.combo_mode.configure(state="disabled")
            self.chk_backup_restart.configure(state="disabled")
            self.entry_interval.configure(state="disabled")
            self.lbl_interval.configure(text_color=AppConfig.COLOR_TEXT_GRAY)
            self.entry_time.configure(state="disabled")
            self.lbl_time.configure(text_color=AppConfig.COLOR_TEXT_GRAY)

    def save_automation(self):
        if not self.var_auto_restart: return

        enabled = self.var_auto_restart.get()
        backup = self.var_backup_restart.get()
        mode = self.var_schedule_mode.get()

        if mode == "Interval":
            interval = 6
            try:
                interval = int(self.entry_interval.get())
            except ValueError:
                logger.warning("Invalid interval input, using default 6")
            self.scheduler.set_restart_schedule(enabled, interval_hours=interval, backup_on_restart=backup)
        else:
            time_val = self.entry_time.get()
            self.scheduler.set_restart_schedule(enabled, restart_time=time_val, backup_on_restart=backup)

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
            BackupScheduler(self.server_name).set_config(bk_enabled, interval_hours=bk_interval, retention_count=bk_retention)

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
            widget = ctk.CTkSwitch(parent, text="", height=compact_height, width=50)
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
                               text_color="royalblue", anchor="w")
            lbl.pack(fill="x", padx=15, pady=(15, 5))

        card = ctk.CTkFrame(parent, fg_color=(AppConfig.COLOR_BG_CARD_LIGHT, AppConfig.COLOR_BG_CARD_DARK), corner_radius=12)
        card.pack(fill="x", padx=10, pady=(0, 5))
        
        card.grid_columnconfigure(0, weight=1) # Label
        card.grid_columnconfigure(1, weight=0) # Help Icon
        card.grid_columnconfigure(2, weight=0) # Impact Dot
        card.grid_columnconfigure(3, weight=0) # Control
        
        return card

    def add_field_to_section(self, parent_card, key, label_text, widget_type="entry", options=None, default_val=None):
        """Adds a row to an existing section card using Grid."""
        meta = SETTINGS_METADATA.get(key, {})
        description = meta.get("desc")
        impact = meta.get("impact")
        
        current_row = parent_card.grid_size()[1]
        
        # 1. Separator
        if current_row > 0:
            sep = ctk.CTkFrame(parent_card, height=1, fg_color=(AppConfig.COLOR_BORDER_LIGHT, AppConfig.COLOR_BORDER_DARK))
            sep.grid(row=current_row, column=0, columnspan=4, sticky="ew", padx=10, pady=2)
            current_row += 1

        # 2. Label
        lbl = ctk.CTkLabel(parent_card, text=label_text, font=self.font_bold, anchor="w")
        lbl.grid(row=current_row, column=0, sticky="w", padx=(12, 5), pady=8)
        
        # 3. Help Icon (?)
        if description:
            help_icon = ctk.CTkLabel(parent_card, text="?", font=self.font_small, 
                                     width=18, height=18, corner_radius=12,
                                     fg_color=(AppConfig.COLOR_BG_CARD_LIGHT, AppConfig.COLOR_BTN_GHOST), text_color=(AppConfig.COLOR_TEXT_MUTED, AppConfig.COLOR_TEXT_GRAY))
            help_icon.grid(row=current_row, column=1, sticky="w", padx=2)
            help_icon.tooltip_ref = ToolTip(help_icon, text=description)
            
        # 4. Impact Dot
        if impact and impact != "Low":
            colors = {"Medium": "orange", "High": "#ff4d4d"}
            dot = ctk.CTkFrame(parent_card, width=8, height=8, corner_radius=4, fg_color=colors[impact])
            dot.grid(row=current_row, column=2, sticky="w", padx=2)
            dot.tooltip_ref = ToolTip(dot, f"Impact: {impact}")

        # 5. Control Frame (for alignment)
        ctrl_frame = ctk.CTkFrame(parent_card, fg_color="transparent", width=200, height=28)
        ctrl_frame.grid(row=current_row, column=3, sticky="e", padx=12, pady=3)
        ctrl_frame.pack_propagate(False)
        
        val = self.properties.get(key)
        if val is None:
            val = default_val if default_val is not None else ""
            
        widget = self._create_widget(ctrl_frame, widget_type, val, options)
        self.widgets[key] = (widget, widget_type)

    def _build_tab_from_config(self, parent_frame, tab_name):
        """Generates UI sections dynamically based on TAB_LAYOUTS config."""
        layout = TAB_LAYOUTS.get(tab_name, {})
        
        for section_title, keys in layout.items():
            card = self.create_section_frame(parent_frame, section_title)
            for key in keys:
                # Get the display name from metadata or generate from key
                label = key.replace("-", " ").replace(".", " ").title()
                
                # Determine widget type and options
                widget_type = "entry"
                options = None
                
                if any(x in key for x in ["enable", "spawn", "white-list", "hardcore", "enforce", "online"]):
                    widget_type = "checkbox"
                elif key in ["gamemode", "difficulty", "level-type", "op-permission-level"]:
                    widget_type = "dropdown"
                    if key == "gamemode": options = ["survival", "creative", "adventure", "spectator"]
                    elif key == "difficulty": options = ["peaceful", "easy", "normal", "hard"]
                    elif key == "level-type": options = ["minecraft:normal", "minecraft:flat", "minecraft:large_biomes"]
                    elif key == "op-permission-level": options = ["1", "2", "3", "4"]
                
                self.add_field_to_section(card, key, label, widget_type, options)

    def setup_general_tab(self):
        # 1. Identity Section
        card_identity = self.create_section_frame(self.frame_general, "Identity & Appearance")
        
        ctk.CTkLabel(card_identity, text="Server Icon", font=self.font_bold, anchor="w").grid(row=0, column=0, sticky="w", padx=(12, 5), pady=8)
        btn = ctk.CTkButton(card_identity, text="Change Icon", command=self.change_icon, 
                            width=100, height=28, fg_color="transparent", border_width=1,
                            border_color=AppConfig.COLOR_BORDER_DARK,
                            text_color=(AppConfig.COLOR_TEXT_MUTED, AppConfig.COLOR_TEXT_GRAY))
        btn.grid(row=0, column=2, sticky="e", padx=12, pady=8)
        
        current_row = card_identity.grid_size()[1]
        sep = ctk.CTkFrame(card_identity, height=1, fg_color=(AppConfig.COLOR_BORDER_LIGHT, AppConfig.COLOR_BORDER_DARK))
        sep.grid(row=current_row, column=0, columnspan=4, sticky="ew", padx=10, pady=2)
        current_row += 1

        ctk.CTkLabel(card_identity, text="Message of the Day", font=self.font_bold, anchor="w").grid(row=current_row, column=0, sticky="nw", padx=(12, 5), pady=8)
        
        motd_frame = ctk.CTkFrame(card_identity, fg_color="transparent")
        motd_frame.grid(row=current_row, column=2, columnspan=2, sticky="e", padx=12, pady=5)
        
        self.entry_motd = ctk.CTkEntry(motd_frame, width=200, height=28)
        self.entry_motd.pack(fill="x", pady=(0, 5))
        self.entry_motd.insert(0, self.properties.get("motd", "A Minecraft Server"))
        self.entry_motd.bind("<KeyRelease>", self._update_motd_preview)

        self.preview_motd_frame = ctk.CTkFrame(motd_frame, fg_color="#1d1d1d", corner_radius=0, border_width=2, border_color="#3e3e3e")
        self.preview_motd_frame.pack(fill="x", pady=(0, 0))
        
        self.motd_preview = ctk.CTkTextbox(self.preview_motd_frame, height=45, width=200, fg_color="#1d1d1d", text_color="#aaaaaa", font=("Consolas", 12), wrap="word")
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
        
        ctk.CTkLabel(card_res, text="RAM Allocation", font=self.font_bold, anchor="w").grid(row=0, column=0, sticky="w", padx=(12, 5), pady=8)
        
        ram_ctrl = ctk.CTkFrame(card_res, fg_color="transparent", width=200, height=28)
        ram_ctrl.grid(row=0, column=2, sticky="e", padx=12, pady=3)
        ram_ctrl.pack_propagate(False)
        
        vcmd = (self.register(self.validate_int), '%P')
        self.entry_ram = ctk.CTkEntry(ram_ctrl, height=28, validate="key", validatecommand=vcmd)
        self.entry_ram.insert(0, str(self.logic.get_server_ram(self.server_name)))
        self.entry_ram.pack(fill="x")

        # 3. Gameplay Section
        card_game = self.create_section_frame(self.frame_general, "Gameplay Rules")
        self.add_field_to_section(card_game, "max-players", "Max Players", default_val="20")
        self.add_field_to_section(card_game, "gamemode", "Game Mode", "dropdown", ["survival", "creative", "adventure", "spectator"])
        self.add_field_to_section(card_game, "force-gamemode", "Force Game Mode", "checkbox")
        self.add_field_to_section(card_game, "difficulty", "Difficulty", "dropdown", ["peaceful", "easy", "normal", "hard"])
        self.add_field_to_section(card_game, "hardcore", "Hardcore Mode", "checkbox")
        self.add_field_to_section(card_game, "enable-command-block", "Command Blocks", "checkbox")

    def setup_world_tab(self):
        self._build_tab_from_config(self.frame_world, "World")

    def setup_network_tab(self):
        self._build_tab_from_config(self.frame_network, "Network")

    def setup_advanced_tab(self):
        self._build_tab_from_config(self.frame_advanced, "Advanced")
        
        # Dynamic "Other Properties"
        card_other = self.create_section_frame(self.frame_advanced, "�️ Other Properties")
        
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
            if self.logic.save_server_icon(self.server_name, file_path):
                pass

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
                self.entry_ram.configure(border_color="red")
                self.tabview.set("General")
                messagebox.showerror("Invalid Input", "RAM Allocation must be a whole number (MB).")
                return
            self.entry_ram.configure(border_color=["#979da2", "#565b5e"]) # Reset color
            
            try:
                ram = int(ram_input)
                self.logic.set_server_ram(self.server_name, ram)
            except ValueError:
                logger.warning("Invalid RAM input: %s", ram_input)

        # 2. Validate Automation Interval (Automation Tab)
        if self.var_auto_restart and self.var_auto_restart.get():
            interval_input = self.entry_interval.get()
            if not interval_input.isdigit():
                self.entry_interval.configure(border_color="red")
                self.tabview.set("Automation")
                messagebox.showerror("Invalid Input", "Restart Interval must be a whole number (Hours).")
                return
            self.entry_interval.configure(border_color=["#979da2", "#565b5e"])

        self.save_automation()

        new_props = {}
        for key, (widget, w_type) in self.widgets.items():
            if w_type == "entry":
                new_props[key] = widget.get()
            elif w_type == "checkbox":
                new_props[key] = "true" if widget.get() == 1 else "false"
            elif w_type == "dropdown":
                new_props[key] = widget.get()
                
        save_server_properties(self.server_name, new_properties=new_props)
        if "Launch" in self.loaded_tabs:
            self.save_launch_settings()
        self.destroy()
    def setup_launch_tab(self):
        """Setup Java and Launch arguments tab."""
        from app.services.java_detector import JavaDetector
        
        card = self.create_section_frame(self.frame_launch, "Java & Runtime")
        
        # Java Path
        ctk.CTkLabel(card, text="Java Version:", font=self.font_bold, anchor="w").grid(row=0, column=0, sticky="w", padx=(12, 5), pady=8)
        
        detector = JavaDetector()
        javas = detector.detect_all()
        self._java_label_to_path = {"Auto-Detect": "auto"}
        self._java_path_to_label = {"auto": "Auto-Detect"}
        for j in javas:
            self._java_label_to_path[j.label] = j.path
            self._java_path_to_label[j.path] = j.label
            
        options = list(self._java_label_to_path.keys())
        
        meta_path = os.path.join(str(SERVERS_DIR), self.server_name, "metadata.json")
        meta = {}
        if os.path.exists(meta_path):
            import json
            with open(meta_path, "r") as f:
                meta = json.load(f)
        
        saved_path = meta.get("java_path", "auto")
        self.var_java_path = ctk.StringVar(value=self._java_path_to_label.get(saved_path, "Auto-Detect"))
        
        self.combo_java = ctk.CTkOptionMenu(card, values=options, variable=self.var_java_path, height=28)
        self.combo_java.grid(row=0, column=2, columnspan=2, sticky="e", padx=12, pady=5)

        # Aikar's Flags
        ctk.CTkFrame(card, height=1, fg_color=(AppConfig.COLOR_BORDER_LIGHT, AppConfig.COLOR_BORDER_DARK)).grid(row=1, column=0, columnspan=4, sticky="ew", padx=10, pady=2)
        
        ctk.CTkLabel(card, text="Use Aikar's Flags:", font=self.font_bold, anchor="w").grid(row=2, column=0, sticky="w", padx=(12, 5), pady=8)
        self.var_use_aikars = ctk.BooleanVar(value=meta.get("use_aikars", True))
        self.chk_aikars = ctk.CTkSwitch(card, text="", variable=self.var_use_aikars)
        self.chk_aikars.grid(row=2, column=2, columnspan=2, sticky="e", padx=12, pady=5)
        
        # Tools
        card_tools = self.create_section_frame(self.frame_launch, "Utilities")
        ctk.CTkButton(card_tools, text="📂 Open Server Folder", command=self.open_folder,
                          fg_color=AppConfig.COLOR_BTN_GHOST, hover_color=AppConfig.COLOR_BTN_GHOST_HOVER,
                          corner_radius=12, height=36).pack(fill="x", padx=15, pady=10)

    def open_folder(self):
        server_path = os.path.join(str(SERVERS_DIR), self.server_name)
        if os.path.exists(server_path):
            if sys.platform == "win32":
                os.startfile(server_path)
            elif sys.platform == "darwin":
                subprocess.run(["open", server_path], check=False)
            else:
                subprocess.run(["xdg-open", server_path], check=False)

    def save_launch_settings(self):
        meta_path = os.path.join(str(SERVERS_DIR), self.server_name, "metadata.json")
        if not os.path.exists(meta_path): return
        
        import json
        with open(meta_path, "r", encoding="utf-8") as f:
            meta = json.load(f)
            
        label = self.var_java_path.get()
        path = getattr(self, "_java_label_to_path", {}).get(label, "auto")
        meta["java_path"] = path
        meta["use_aikars"] = self.var_use_aikars.get()
        
        with open(meta_path, "w") as f:
            json.dump(meta, f, indent=4)
