import customtkinter as ctk
from tkinter import filedialog, messagebox
import os
import threading
from app.app_config import AppConfig

class ToolTip:
    def __init__(self, widget, text):
        self.widget = widget
        self.text = text
        self.tooltip = None
        self.schedule_id = None
        self.widget.bind("<Enter>", self.on_enter)
        self.widget.bind("<Leave>", self.hide)
        self.widget.bind("<ButtonPress>", self.hide)

    def on_enter(self, event=None):
        self.unschedule()
        self.schedule_id = self.widget.after(500, self.show)

    def unschedule(self):
        if self.schedule_id:
            self.widget.after_cancel(self.schedule_id)
            self.schedule_id = None

    def show(self, event=None):
        self.unschedule()
        if self.tooltip or not self.widget.winfo_exists():
            return
            
        # Final check: is the mouse still over the widget?
        try:
            x, y = self.widget.winfo_pointerxy()
            widget_x1 = self.widget.winfo_rootx()
            widget_y1 = self.widget.winfo_rooty()
            widget_x2 = widget_x1 + self.widget.winfo_width()
            widget_y2 = widget_y1 + self.widget.winfo_height()
            
            if not (widget_x1 <= x <= widget_x2 and widget_y1 <= y <= widget_y2):
                return
        except:
            return

        # Position relative to mouse
        tip_x = x + 15
        tip_y = y + 15
        
        self.tooltip = ctk.CTkToplevel(self.widget)
        self.tooltip.wm_overrideredirect(True)
        self.tooltip.wm_geometry(f"+{tip_x}+{tip_y}")
        self.tooltip.attributes("-topmost", True)
        self.tooltip.configure(fg_color=("#ebebeb", "#2b2b2b"))
        
        # Ensure it doesn't steal focus
        self.tooltip.bind("<Enter>", lambda e: self.hide())
        
        label = ctk.CTkLabel(self.tooltip, text=self.text, fg_color=("#ebebeb", "#2b2b2b"), 
                             text_color=("black", "white"), corner_radius=6, padx=10, pady=5,
                             font=ctk.CTkFont(size=12))
        label.pack()
        
        # Force update to ensure visibility
        self.tooltip.update_idletasks()
        self.tooltip.lift()

    def hide(self, event=None):
        self.unschedule()
        if self.tooltip:
            try:
                self.tooltip.destroy()
            except:
                pass
            self.tooltip = None

SETTINGS_METADATA = {
    # General
    "motd": {"desc": "The message shown in the server list.", "impact": "Low"},
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
    def __init__(self, parent, server_name, logic_module):
        super().__init__(parent)
        self.title(f"Edit Properties - {server_name}")
        self.geometry("700x600")
        self.resizable(True, True)
        
        self.server_name = server_name
        self.logic = logic_module
        self.properties = self.logic.load_server_properties(server_name)
        
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
        
        self.btn_cancel = ctk.CTkButton(self.btn_frame, text="Cancel", command=self.destroy, fg_color="gray")
        self.btn_cancel.pack(side="right", padx=5)
        
        self.btn_save = ctk.CTkButton(self.btn_frame, text="Save", command=self.save_properties, fg_color="green")
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
        self.backup_manager = self.logic.BackupManager(self.server_name)

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
        self.backup_manager.create_backup()
        self.refresh_backups()

    def restore_backup(self):
        path = self.backup_var.get()
        if not path:
            return
        
        confirm = messagebox.askyesno(
            "Confirm Restore", 
            f"Are you sure you want to restore this backup?\n\n{os.path.basename(path)}\n\nCurrent world data will be overwritten."
        )
        
        if confirm:
            success = self.backup_manager.restore_backup(path)
            if success:
                messagebox.showinfo("Success", "Server restored successfully.")
                self.refresh_backups()
            else:
                messagebox.showerror("Error", "Failed to restore backup.")

    def setup_automation_tab(self):
        self.scheduler = self.logic.Scheduler(self.server_name)
        schedule = self.scheduler.get_schedule()
        
        card = self.create_section_frame(self.frame_automation, "Automated Restarts")
        
        # Enable Toggle
        self.var_auto_restart = ctk.BooleanVar(value=bool(schedule))
        self.chk_auto_restart = ctk.CTkSwitch(card, text="Enable Automated Restarts", 
                                                variable=self.var_auto_restart, command=self.toggle_automation_inputs)
        self.chk_auto_restart.grid(row=0, column=0, columnspan=2, sticky="w", padx=15, pady=10)
        
        # Separator
        ctk.CTkFrame(card, height=1, fg_color=("gray90", "gray25")).grid(row=1, column=0, columnspan=2, sticky="ew", padx=15)
        
        # Interval Input
        self.lbl_interval = ctk.CTkLabel(card, text="Restart Interval (Hours):", font=self.font_bold, anchor="w")
        self.lbl_interval.grid(row=2, column=0, sticky="w", padx=(12, 5), pady=8)
        
        # Column 1 is empty (no impact dot here)
        
        ctrl_frame = ctk.CTkFrame(card, fg_color="transparent", width=200, height=28)
        ctrl_frame.grid(row=2, column=2, sticky="e", padx=12, pady=3)
        ctrl_frame.pack_propagate(False)
        
        vcmd = (self.register(self.validate_int), '%P')
        self.entry_interval = ctk.CTkEntry(ctrl_frame, height=28, validate="key", validatecommand=vcmd)
        self.entry_interval.pack(fill="x")
        
        if schedule and schedule["type"] == "interval":
            self.entry_interval.insert(0, str(schedule["interval_hours"]))
        else:
            self.entry_interval.insert(0, "6") # Default
            
        self.toggle_automation_inputs()

    def toggle_automation_inputs(self):
        if self.var_auto_restart.get():
            self.entry_interval.configure(state="normal")
            self.lbl_interval.configure(text_color=("black", "white"))
        else:
            self.entry_interval.configure(state="disabled")
            self.lbl_interval.configure(text_color="gray")

    def save_automation(self):
        if not self.var_auto_restart:
            return
            
        enabled = self.var_auto_restart.get()
        interval = 6
        try:
            interval = int(self.entry_interval.get())
        except:
            pass
            
        self.scheduler.set_restart_schedule(enabled, interval)

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
            widget = ctk.CTkComboBox(parent, values=options, state="readonly", height=compact_height)
            if val in options:
                widget.set(val)
            widget.pack(fill="x", expand=True, pady=0)
            widget._entry.bind("<Button-1>", lambda e: widget._open_dropdown_menu())
            widget._entry.bind("<B1-Motion>", lambda e: "break")
            widget._entry.bind("<Double-Button-1>", lambda e: "break")
            widget._entry.configure(cursor="arrow")
        return widget

    def create_section_frame(self, parent, title):
        """Creates a modern 'Card' container for a group of settings."""
        if title:
            lbl = ctk.CTkLabel(parent, text=title, font=self.font_header, 
                               text_color="royalblue", anchor="w")
            lbl.pack(fill="x", padx=15, pady=(15, 5))

        card = ctk.CTkFrame(parent, fg_color=("white", "gray17"), corner_radius=8)
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
            sep = ctk.CTkFrame(parent_card, height=1, fg_color=("gray90", "gray25"))
            sep.grid(row=current_row, column=0, columnspan=4, sticky="ew", padx=10, pady=2)
            current_row += 1

        # 2. Label
        lbl = ctk.CTkLabel(parent_card, text=label_text, font=self.font_bold, anchor="w")
        lbl.grid(row=current_row, column=0, sticky="w", padx=(12, 5), pady=8)
        
        # 3. Help Icon (?)
        if description:
            help_icon = ctk.CTkLabel(parent_card, text="?", font=self.font_small, 
                                     width=18, height=18, corner_radius=9,
                                     fg_color=("gray85", "gray30"), text_color=("gray40", "gray70"))
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
                            width=100, height=28, fg_color="transparent", border_width=1, text_color=("gray10", "gray90"))
        btn.grid(row=0, column=2, sticky="e", padx=12, pady=8)
        
        self.add_field_to_section(card_identity, "motd", "Message of the Day")

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
            except:
                pass

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
                
        self.logic.save_server_properties(self.server_name, new_props)
        self.destroy()
