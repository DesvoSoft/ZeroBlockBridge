import customtkinter as ctk
import os

class ServerPropertiesEditor(ctk.CTkToplevel):
    def __init__(self, parent, server_name, logic_module):
        super().__init__(parent)
        self.title(f"Edit Properties - {server_name}")
        self.geometry("700x600")
        self.resizable(True, True)
        
        self.server_name = server_name
        self.logic = logic_module
        self.properties = self.logic.load_server_properties(server_name)
        
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
        
        # Keep track of widgets to save values
        self.widgets = {}
        
        self.create_widgets()
        self.setup_backups_tab()
        self.setup_automation_tab()
        
        # Footer Buttons
        self.btn_frame = ctk.CTkFrame(self, fg_color="transparent")
        self.btn_frame.grid(row=1, column=0, sticky="ew", padx=10, pady=10)
        
        self.btn_cancel = ctk.CTkButton(self.btn_frame, text="Cancel", command=self.destroy, fg_color="gray")
        self.btn_cancel.pack(side="right", padx=5)
        
        self.btn_save = ctk.CTkButton(self.btn_frame, text="Save", command=self.save_properties, fg_color="green")
        self.btn_save.pack(side="right", padx=5)
        
        # Make modal
        self.transient(parent)
        self.grab_set()

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
        self.refresh_backups()

    def refresh_backups(self):
        for widget in self.backup_list_frame.winfo_children():
            widget.destroy()
            
        backups = self.backup_manager.list_backups()
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
        
        # TODO: Add confirmation dialog
        success = self.backup_manager.restore_backup(path)
        if success:
            # Show success message?
            self.refresh_backups() # Just refresh for now

    def setup_automation_tab(self):
        self.scheduler = self.logic.Scheduler(self.server_name)
        schedule = self.scheduler.get_schedule()
        
        # Enable Toggle
        self.var_auto_restart = ctk.BooleanVar(value=bool(schedule))
        self.chk_auto_restart = ctk.CTkCheckBox(self.frame_automation, text="Enable Automated Restarts", 
                                                variable=self.var_auto_restart, command=self.toggle_automation_inputs)
        self.chk_auto_restart.pack(anchor="w", pady=10, padx=10)
        
        # Interval Input
        self.lbl_interval = ctk.CTkLabel(self.frame_automation, text="Restart Interval (Hours):")
        self.lbl_interval.pack(anchor="w", padx=30)
        
        self.entry_interval = ctk.CTkEntry(self.frame_automation, width=100)
        self.entry_interval.pack(anchor="w", padx=30, pady=(0, 10))
        
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
        enabled = self.var_auto_restart.get()
        interval = 6
        try:
            interval = int(self.entry_interval.get())
        except:
            pass
            
        self.scheduler.set_restart_schedule(enabled, interval)

    def create_widgets(self):
        # Helper to create fields
        def add_field(parent, key, label_text, widget_type="entry", options=None):
            frame = ctk.CTkFrame(parent, fg_color="transparent")
            frame.pack(fill="x", pady=2)
            
            lbl = ctk.CTkLabel(frame, text=label_text, width=150, anchor="w")
            lbl.pack(side="left", padx=5)
            
            val = self.properties.get(key, "")
            
            if widget_type == "entry":
                widget = ctk.CTkEntry(frame)
                widget.insert(0, str(val))
                widget.pack(side="right", fill="x", expand=True, padx=5)
            elif widget_type == "checkbox":
                widget = ctk.CTkCheckBox(frame, text="")
                if str(val).lower() == "true":
                    widget.select()
                widget.pack(side="right", padx=5)
            elif widget_type == "dropdown":
                widget = ctk.CTkComboBox(frame, values=options)
                if val in options:
                    widget.set(val)
                widget.pack(side="right", fill="x", expand=True, padx=5)
                
            self.widgets[key] = (widget, widget_type)
        
        # --- General Tab ---
        add_field(self.frame_general, "motd", "MOTD")
        add_field(self.frame_general, "max-players", "Max Players")
        add_field(self.frame_general, "gamemode", "Game Mode", "dropdown", ["survival", "creative", "adventure", "spectator"])
        add_field(self.frame_general, "difficulty", "Difficulty", "dropdown", ["peaceful", "easy", "normal", "hard"])
        add_field(self.frame_general, "hardcore", "Hardcore", "checkbox")
        add_field(self.frame_general, "enable-command-block", "Command Blocks", "checkbox")

        # --- World Tab ---
        add_field(self.frame_world, "level-seed", "Level Seed")
        add_field(self.frame_world, "level-name", "Level Name")
        add_field(self.frame_world, "level-type", "Level Type", "dropdown", ["minecraft:normal", "minecraft:flat", "minecraft:large_biomes", "minecraft:amplified"])
        add_field(self.frame_world, "generate-structures", "Gen Structures", "checkbox")
        add_field(self.frame_world, "spawn-npcs", "Spawn NPCs", "checkbox")
        add_field(self.frame_world, "spawn-animals", "Spawn Animals", "checkbox")
        add_field(self.frame_world, "spawn-monsters", "Spawn Monsters", "checkbox")
        add_field(self.frame_world, "view-distance", "View Distance")
        add_field(self.frame_world, "simulation-distance", "Sim Distance")

        # --- Network Tab ---
        add_field(self.frame_network, "server-port", "Server Port")
        add_field(self.frame_network, "server-ip", "Server IP")
        add_field(self.frame_network, "white-list", "Whitelist", "checkbox")
        add_field(self.frame_network, "enforce-whitelist", "Enforce Whitelist", "checkbox")
        add_field(self.frame_network, "online-mode", "Online Mode", "checkbox")
        add_field(self.frame_network, "enable-rcon", "Enable RCON", "checkbox")
        add_field(self.frame_network, "rcon.password", "RCON Password")
        add_field(self.frame_network, "rcon.port", "RCON Port")

        # --- Advanced Tab ---
        # Add any other keys not already added
        defined_keys = [k for k in self.widgets.keys()]
        for key, val in self.properties.items():
            if key not in defined_keys:
                add_field(self.frame_advanced, key, key)

    def save_properties(self):
        # Save Automation
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
