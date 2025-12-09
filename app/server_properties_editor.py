import customtkinter as ctk
import os

class ServerPropertiesEditor(ctk.CTkToplevel):
    def __init__(self, parent, server_name, logic_module):
        super().__init__(parent)
        self.title(f"Edit Properties - {server_name}")
        self.geometry("600x500")
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
        
        # Scrollable frames for tabs
        self.frame_general = ctk.CTkScrollableFrame(self.tab_general)
        self.frame_general.pack(fill="both", expand=True)
        
        self.frame_world = ctk.CTkScrollableFrame(self.tab_world)
        self.frame_world.pack(fill="both", expand=True)
        
        self.frame_network = ctk.CTkScrollableFrame(self.tab_network)
        self.frame_network.pack(fill="both", expand=True)
        
        self.frame_advanced = ctk.CTkScrollableFrame(self.tab_advanced)
        self.frame_advanced.pack(fill="both", expand=True)
        
        # Keep track of widgets to save values
        self.widgets = {}
        
        self.create_widgets()
        
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
