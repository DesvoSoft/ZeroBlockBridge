import customtkinter as ctk
import os
import psutil
from app.core.constants import SERVERS_DIR
from app.core.version_manager import VersionManager
from PIL import Image

class ServerWizard(ctk.CTkToplevel):
    def __init__(self, parent, on_complete_callback):
        super().__init__(parent)
        self.title("Create New Server - Zero Block Bridge")
        self.geometry("650x650")
        self.resizable(False, False)
        
        self.on_complete_callback = on_complete_callback
        self.current_step = 1
        self.total_steps = 3
        
        # Data storage
        self.wizard_data = {
            "name": "",
            "type": "Vanilla",
            "version": "",
            "ram": 2048,
            "seed": "",
            "game_mode": "survival",
            "difficulty": "normal",
            "hardcore": False,
            "whitelist": False,
            "view_distance": "10",
            "simulation_distance": "10",
            "location": str(SERVERS_DIR),
            "icon_path": None,
            "auto_install_jdk": True,
        }
        
        # Layout
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(0, weight=0) # Header
        self.grid_rowconfigure(1, weight=1) # Content
        self.grid_rowconfigure(2, weight=0) # Footer
        
        # Header
        self.header_frame = ctk.CTkFrame(self, height=50, corner_radius=0)
        self.header_frame.grid(row=0, column=0, sticky="ew")
        self.lbl_step = ctk.CTkLabel(self.header_frame, text="Step 1 of 3", font=ctk.CTkFont(size=14))
        self.lbl_step.pack(side="left", padx=20, pady=10)
        self.lbl_title = ctk.CTkLabel(self.header_frame, text="Identity", font=ctk.CTkFont(size=16, weight="bold"))
        self.lbl_title.pack(side="right", padx=20, pady=10)
        
        # Content Frame
        self.content_frame = ctk.CTkFrame(self, fg_color="transparent")
        self.content_frame.grid(row=1, column=0, sticky="nsew", padx=20, pady=20)
        
        # Footer
        self.footer_frame = ctk.CTkFrame(self, height=60, corner_radius=0)
        self.footer_frame.grid(row=2, column=0, sticky="ew")
        
        self.btn_back = ctk.CTkButton(self.footer_frame, text="Back", command=self.go_back, state="disabled", corner_radius=12)
        self.btn_back.pack(side="left", padx=20, pady=15)
        
        self.btn_next = ctk.CTkButton(self.footer_frame, text="Next", command=self.go_next, corner_radius=12)
        self.btn_next.pack(side="right", padx=20, pady=15)
        
        self.vm = VersionManager()
        self.vm.add_callback(self.on_versions_refreshed)
        
        self.show_step_1()
        
        self.transient(parent)
        self.wait_visibility()
        self.grab_set()

    def update_header(self, title):
        self.lbl_step.configure(text=f"Step {self.current_step} of {self.total_steps}")
        self.lbl_title.configure(text=title)
        
        if self.current_step == 1:
            self.btn_back.configure(state="disabled")
        else:
            self.btn_back.configure(state="normal")
            
        if self.current_step == self.total_steps:
            self.btn_next.configure(text="Create Server", fg_color="green", hover_color="darkgreen")
        else:
            self.btn_next.configure(text="Next", fg_color=["#3a7ebf", "#1f538d"], hover_color=["#325882", "#14375e"])

    def clear_content(self):
        for widget in self.content_frame.winfo_children():
            widget.destroy()

    def on_versions_refreshed(self):
        if self.current_step == 2:
            self.after(0, self._render_versions)

    # --- Step 1: Identidad ---
    def show_step_1(self):
        self.clear_content()
        self.update_header("Server Identity")
        
        ctk.CTkLabel(self.content_frame, text="Server Name:", font=ctk.CTkFont(weight="bold")).pack(anchor="w", pady=(0, 5))
        self.entry_name = ctk.CTkEntry(self.content_frame, placeholder_text="my-awesome-server", corner_radius=12, height=36)
        self.entry_name.pack(fill="x", pady=(0, 15))
        if self.wizard_data["name"]:
            self.entry_name.insert(0, self.wizard_data["name"])
            
        ctk.CTkLabel(self.content_frame, text="Custom Location:", font=ctk.CTkFont(weight="bold")).pack(anchor="w", pady=(0, 5))
        loc_frame = ctk.CTkFrame(self.content_frame, fg_color="transparent")
        loc_frame.pack(fill="x", pady=(0, 15))
        
        self.entry_location = ctk.CTkEntry(loc_frame, corner_radius=12, height=36)
        self.entry_location.pack(side="left", fill="x", expand=True, padx=(0, 10))
        self.entry_location.insert(0, self.wizard_data["location"])
        
        btn_browse_loc = ctk.CTkButton(loc_frame, text="Browse...", command=self.browse_location, corner_radius=12, width=80, fg_color="gray", hover_color="gray30")
        btn_browse_loc.pack(side="right")
            
        ctk.CTkLabel(self.content_frame, text="Server Icon (Optional):", font=ctk.CTkFont(weight="bold")).pack(anchor="w", pady=(0, 10))
        
        self.icon_preview = ctk.CTkLabel(self.content_frame, text="No Icon", width=100, height=100, fg_color="gray30", corner_radius=12)
        self.icon_preview.pack(pady=10)
        
        if self.wizard_data["icon_path"]:
            self._update_icon_preview(self.wizard_data["icon_path"])
            
        btn_browse = ctk.CTkButton(self.content_frame, text="Select Image...", command=self.browse_icon, corner_radius=12, fg_color="gray", hover_color="gray30")
        btn_browse.pack(pady=10)

    def browse_location(self):
        from tkinter import filedialog
        dir_path = filedialog.askdirectory(title="Select Root Folder")
        if dir_path:
            self.wizard_data["location"] = dir_path
            self.entry_location.delete(0, "end")
            self.entry_location.insert(0, dir_path)

    def browse_icon(self):
        from tkinter import filedialog
        file_path = filedialog.askopenfilename(title="Seleccionar Icono", filetypes=[("Images", "*.png;*.jpg;*.jpeg")])
        if file_path:
            self.wizard_data["icon_path"] = file_path
            self._update_icon_preview(file_path)
            
    def _update_icon_preview(self, path):
        try:
            img = ctk.CTkImage(Image.open(path), size=(100, 100))
            self.icon_preview.configure(image=img, text="")
        except Exception:
            self.icon_preview.configure(text="Error")

    # --- Step 2: Engine & Resources ---
    def show_step_2(self):
        self.clear_content()
        self.update_header("Engine & Resources")

        engine_res_frame = ctk.CTkFrame(self.content_frame, fg_color="transparent")
        engine_res_frame.pack(fill="both", expand=True)

        # Engine Selection
        ctk.CTkLabel(engine_res_frame, text="Server Engine:", font=ctk.CTkFont(weight="bold")).pack(anchor="w", pady=(0, 5))

        self.engine_var = ctk.StringVar(value=self.wizard_data["type"])
        engines = [("Vanilla", "Vanilla"), ("Paper", "Paper"), ("Purpur", "Purpur"), ("Fabric", "Fabric"), ("Forge", "Forge")]

        engine_row = ctk.CTkFrame(engine_res_frame, fg_color="transparent")
        engine_row.pack(fill="x", pady=(0, 15))

        for val, name in engines:
            rb = ctk.CTkRadioButton(engine_row, text=name, variable=self.engine_var, value=val, command=self._on_engine_change, font=ctk.CTkFont(size=14))
            rb.pack(side="left", padx=(0, 12))

        self.lbl_ram_hint = ctk.CTkLabel(engine_res_frame, text="", text_color="gray", font=ctk.CTkFont(size=12))
        self.lbl_ram_hint.pack(anchor="w", pady=(0, 5))

        # Version Search
        ctk.CTkLabel(engine_res_frame, text="Version:", font=ctk.CTkFont(weight="bold")).pack(anchor="w", pady=(0, 5))
        self.entry_search = ctk.CTkEntry(engine_res_frame, placeholder_text="e.g. 1.20.1", corner_radius=12, height=36)
        self.entry_search.pack(fill="x", pady=(0, 10))
        self.entry_search.bind("<KeyRelease>", lambda e: self._render_versions())

        # Versions List
        self.scroll_versions = ctk.CTkScrollableFrame(engine_res_frame, corner_radius=12, fg_color=("gray90", "gray15"), height=120)
        self.scroll_versions.pack(fill="x", pady=(0, 15))

        self.version_var = ctk.StringVar(value=self.wizard_data["version"])
        self._render_versions()

        # RAM Memory
        total_ram = psutil.virtual_memory().total / (1024 * 1024)
        max_slider = min(16384, total_ram - 1024)
        min_ram = 512

        ram_label_frame = ctk.CTkFrame(engine_res_frame, fg_color="transparent")
        ram_label_frame.pack(fill="x", pady=(0, 5))

        ctk.CTkLabel(ram_label_frame, text="RAM:", font=ctk.CTkFont(weight="bold")).pack(side="left")
        self.lbl_ram_value = ctk.CTkLabel(ram_label_frame, text=f"{self.wizard_data['ram']} MB ({self.wizard_data['ram']//1024} GB)", font=ctk.CTkFont(size=13))
        self.lbl_ram_value.pack(side="left", padx=(10, 0))

        ram_input_frame = ctk.CTkFrame(engine_res_frame, fg_color="transparent")
        ram_input_frame.pack(fill="x", pady=(0, 2))

        self.entry_ram = ctk.CTkEntry(ram_input_frame, width=90, corner_radius=12, height=32)
        self.entry_ram.pack(side="left", padx=(0, 10))
        self.entry_ram.insert(0, str(self.wizard_data['ram']))
        self.entry_ram.bind("<KeyRelease>", self.update_ram_from_entry)

        self.slider_ram = ctk.CTkSlider(engine_res_frame, from_=min_ram, to=max_slider, number_of_steps=100, command=self.update_ram_label, height=16, border_width=1)
        self.slider_ram.set(self.wizard_data["ram"])
        self.slider_ram.pack(fill="x", pady=(2, 2))

        slider_range = ctk.CTkFrame(engine_res_frame, fg_color="transparent")
        slider_range.pack(fill="x")
        ctk.CTkLabel(slider_range, text=f"{min_ram} MB", font=ctk.CTkFont(size=10), text_color="gray").pack(side="left")
        self.lbl_ram_util = ctk.CTkLabel(slider_range, text="", font=ctk.CTkFont(size=10), text_color="gray")
        self.lbl_ram_util.pack(side="right")

        self.lbl_ram_error = ctk.CTkLabel(engine_res_frame, text="", text_color="red", font=ctk.CTkFont(size=12))
        self.lbl_ram_error.pack(anchor="w")

        self._update_ram_hint()
        
    def _on_engine_change(self):
        self.wizard_data["type"] = self.engine_var.get()
        self._render_versions()
        self._update_ram_hint()

    def _update_ram_hint(self):
        engine = self.engine_var.get()
        hints = {"Vanilla": "512 MB min", "Paper": "1 GB min", "Purpur": "1 GB min", "Fabric": "1 GB min", "Forge": "2 GB min"}
        hint = hints.get(engine, "1 GB min")
        self.lbl_ram_hint.configure(text=f"Recommended: {hint}")

    def update_ram_from_entry(self, event=None):
        try:
            val = int(self.entry_ram.get())
            if 512 <= val <= 32768:
                self.slider_ram.set(val)
                self.wizard_data["ram"] = val
                self.lbl_ram_value.configure(text=f"{val} MB ({val//1024} GB)")
                total = psutil.virtual_memory().total / (1024 * 1024)
                pct = val / total
                self.lbl_ram_util.configure(text=f"{pct*100:.0f}% of system RAM")
                self.lbl_ram_error.configure(text="")
        except ValueError:
            pass

    def update_ram_label(self, value):
        ram = int(value)
        self.wizard_data["ram"] = ram
        self.entry_ram.delete(0, "end")
        self.entry_ram.insert(0, str(ram))
        self.lbl_ram_value.configure(text=f"{ram} MB ({ram//1024} GB)")
        total = psutil.virtual_memory().total / (1024 * 1024)
        pct = ram / total
        self.lbl_ram_util.configure(text=f"{pct*100:.0f}% of system RAM")

    def _render_versions(self):
        for widget in self.scroll_versions.winfo_children():
            widget.destroy()
            
        engine = self.engine_var.get()
        versions = self.vm.get_versions(engine)
        search_q = self.entry_search.get().lower()
        
        def version_key(v):
            try:
                import re
                parts = []
                for part in v.split('.'):
                    if part.isdigit():
                        parts.append(int(part))
                    else:
                        match = re.match(r"(\d+)", part)
                        parts.append(int(match.group(1)) if match else 0)
                return tuple(parts)
            except (ValueError, TypeError) as e:
                logger.debug("Wizard version_key parse failed: %s", e)
                return (0, 0, 0)

        versions.sort(key=version_key, reverse=True)
        filtered = [v for v in versions if search_q in v.lower()]
        
        if not filtered:
            ctk.CTkLabel(self.scroll_versions, text="No versions found.").pack(pady=20)
            return
            
        for v in filtered[:100]: # Allow more versions to be shown
            rb = ctk.CTkRadioButton(self.scroll_versions, text=v, variable=self.version_var, value=v)
            rb.pack(anchor="w", padx=10, pady=5)
            
        if self.wizard_data["version"] in filtered:
            self.version_var.set(self.wizard_data["version"])
        elif filtered:
            self.version_var.set(filtered[0])

    # --- Step 3: Rules & World ---
    def show_step_3(self):
        self.clear_content()
        self.update_header("Rules & World")
        
        # Game Mode
        ctk.CTkLabel(self.content_frame, text="Game Mode:", font=ctk.CTkFont(weight="bold")).pack(anchor="w", pady=(0, 5))
        self.combo_gamemode = ctk.CTkOptionMenu(self.content_frame, values=["survival", "creative", "adventure", "spectator"], corner_radius=12, height=36)
        self.combo_gamemode.pack(fill="x", pady=(0, 10))
        self.combo_gamemode.set(self.wizard_data["game_mode"])
        
        # Difficulty
        ctk.CTkLabel(self.content_frame, text="Difficulty:", font=ctk.CTkFont(weight="bold")).pack(anchor="w", pady=(0, 5))
        self.combo_difficulty = ctk.CTkOptionMenu(self.content_frame, values=["peaceful", "easy", "normal", "hard"], corner_radius=12, height=36)
        self.combo_difficulty.pack(fill="x", pady=(0, 10))
        self.combo_difficulty.set(self.wizard_data["difficulty"])
        
        # Toggles Frame
        toggles_frame = ctk.CTkFrame(self.content_frame, fg_color="transparent")
        toggles_frame.pack(fill="x", pady=(0, 15))
        
        self.var_hardcore = ctk.BooleanVar(value=self.wizard_data["hardcore"])
        self.chk_hardcore = ctk.CTkSwitch(toggles_frame, text="Hardcore", variable=self.var_hardcore)
        self.chk_hardcore.pack(side="left", padx=(0, 20))
        
        self.var_whitelist = ctk.BooleanVar(value=self.wizard_data["whitelist"])
        self.chk_whitelist = ctk.CTkSwitch(toggles_frame, text="White-list", variable=self.var_whitelist)
        self.chk_whitelist.pack(side="left")

        self.var_auto_jdk = ctk.BooleanVar(value=self.wizard_data["auto_install_jdk"])
        self.chk_auto_jdk = ctk.CTkSwitch(toggles_frame, text="Auto-install JDK if missing", variable=self.var_auto_jdk)
        self.chk_auto_jdk.pack(side="left", padx=(20, 0))
        
        # Seed
        ctk.CTkLabel(self.content_frame, text="Seed (Optional):", font=ctk.CTkFont(weight="bold")).pack(anchor="w", pady=(0, 5))
        self.entry_seed = ctk.CTkEntry(self.content_frame, placeholder_text="Leave blank for random", corner_radius=12, height=36)
        self.entry_seed.pack(fill="x", pady=(0, 10))
        if self.wizard_data["seed"]:
            self.entry_seed.insert(0, self.wizard_data["seed"])
            
        # Distances (Sliders)
        dist_frame = ctk.CTkFrame(self.content_frame, fg_color="transparent")
        dist_frame.pack(fill="x", pady=(0, 10))
        
        # View Distance
        ctk.CTkLabel(dist_frame, text="View Distance:", font=ctk.CTkFont(weight="bold")).grid(row=0, column=0, sticky="w", pady=(0, 5))
        self.lbl_view_val = ctk.CTkLabel(dist_frame, text=str(self.wizard_data["view_distance"]))
        self.lbl_view_val.grid(row=0, column=1, sticky="w", padx=(10, 20))
        
        self.slider_view = ctk.CTkSlider(dist_frame, from_=2, to=32, number_of_steps=30, command=self.update_view_label)
        self.slider_view.set(int(self.wizard_data["view_distance"]))
        self.slider_view.grid(row=1, column=0, columnspan=2, sticky="ew", padx=(0, 20))
        
        # Simulation Distance
        ctk.CTkLabel(dist_frame, text="Simulation Distance:", font=ctk.CTkFont(weight="bold")).grid(row=2, column=0, sticky="w", pady=(10, 5))
        self.lbl_sim_val = ctk.CTkLabel(dist_frame, text=str(self.wizard_data["simulation_distance"]))
        self.lbl_sim_val.grid(row=2, column=1, sticky="w", padx=10)
        
        self.slider_sim = ctk.CTkSlider(dist_frame, from_=2, to=32, number_of_steps=30, command=self.update_sim_label)
        self.slider_sim.set(int(self.wizard_data["simulation_distance"]))
        self.slider_sim.grid(row=3, column=0, columnspan=2, sticky="ew", padx=(0, 20))

    def update_view_label(self, value):
        self.wizard_data["view_distance"] = str(int(value))
        self.lbl_view_val.configure(text=str(int(value)))

    def update_sim_label(self, value):
        self.wizard_data["simulation_distance"] = str(int(value))
        self.lbl_sim_val.configure(text=str(int(value)))

    # --- Navigation ---
    def go_next(self):
        if self.current_step == 1:
            name = self.entry_name.get().strip()
            loc = self.entry_location.get().strip()
            if not name:
                self.entry_name.configure(border_color="red")
                return
            self.wizard_data["name"] = name
            self.wizard_data["location"] = loc
            
        elif self.current_step == 2:
            self.wizard_data["type"] = self.engine_var.get()
            self.wizard_data["version"] = self.version_var.get()
            if not self.wizard_data["version"]:
                return

        elif self.current_step == 3:
            self.wizard_data["game_mode"] = self.combo_gamemode.get()
            self.wizard_data["difficulty"] = self.combo_difficulty.get()
            self.wizard_data["hardcore"] = self.var_hardcore.get()
            self.wizard_data["whitelist"] = self.var_whitelist.get()
            self.wizard_data["auto_install_jdk"] = self.var_auto_jdk.get()
            self.wizard_data["seed"] = self.entry_seed.get().strip()
            
            self.on_complete_callback(self.wizard_data)
            self.destroy()
            return

        self.current_step += 1
        self.show_step()
        
    def go_back(self):
        if self.current_step == 3:
            self.wizard_data["game_mode"] = self.combo_gamemode.get()
            self.wizard_data["difficulty"] = self.combo_difficulty.get()
            self.wizard_data["hardcore"] = self.var_hardcore.get()
            self.wizard_data["whitelist"] = self.var_whitelist.get()
            self.wizard_data["auto_install_jdk"] = self.var_auto_jdk.get()
            self.wizard_data["seed"] = self.entry_seed.get().strip()
            
        self.current_step -= 1
        self.show_step()
        
    def show_step(self):
        if self.current_step == 1: self.show_step_1()
        elif self.current_step == 2: self.show_step_2()
        elif self.current_step == 3: self.show_step_3()
