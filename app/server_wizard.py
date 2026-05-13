import customtkinter as ctk
import os
import psutil
from app.constants import SERVERS_DIR
from app.version_manager import VersionManager
from PIL import Image

class ServerWizard(ctk.CTkToplevel):
    def __init__(self, parent, on_complete_callback):
        super().__init__(parent)
        self.title("Create New Server - Zero Block Bridge")
        self.geometry("650x650")
        self.resizable(False, False)
        
        self.on_complete_callback = on_complete_callback
        self.current_step = 1
        self.total_steps = 4
        
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
            "icon_path": None
        }
        
        # Layout
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(0, weight=0) # Header
        self.grid_rowconfigure(1, weight=1) # Content
        self.grid_rowconfigure(2, weight=0) # Footer
        
        # Header
        self.header_frame = ctk.CTkFrame(self, height=50, corner_radius=0)
        self.header_frame.grid(row=0, column=0, sticky="ew")
        self.lbl_step = ctk.CTkLabel(self.header_frame, text="Paso 1 de 4", font=ctk.CTkFont(size=14))
        self.lbl_step.pack(side="left", padx=20, pady=10)
        self.lbl_title = ctk.CTkLabel(self.header_frame, text="Identidad", font=ctk.CTkFont(size=16, weight="bold"))
        self.lbl_title.pack(side="right", padx=20, pady=10)
        
        # Content Frame
        self.content_frame = ctk.CTkFrame(self, fg_color="transparent")
        self.content_frame.grid(row=1, column=0, sticky="nsew", padx=20, pady=20)
        
        # Footer
        self.footer_frame = ctk.CTkFrame(self, height=60, corner_radius=0)
        self.footer_frame.grid(row=2, column=0, sticky="ew")
        
        self.btn_back = ctk.CTkButton(self.footer_frame, text="Atrás", command=self.go_back, state="disabled", corner_radius=12)
        self.btn_back.pack(side="left", padx=20, pady=15)
        
        self.btn_next = ctk.CTkButton(self.footer_frame, text="Siguiente", command=self.go_next, corner_radius=12)
        self.btn_next.pack(side="right", padx=20, pady=15)
        
        self.vm = VersionManager()
        self.vm.add_callback(self.on_versions_refreshed)
        
        self.show_step_1()
        
        self.transient(parent)
        self.wait_visibility()
        self.grab_set()

    def update_header(self, title):
        self.lbl_step.configure(text=f"Paso {self.current_step} de {self.total_steps}")
        self.lbl_title.configure(text=title)
        
        if self.current_step == 1:
            self.btn_back.configure(state="disabled")
        else:
            self.btn_back.configure(state="normal")
            
        if self.current_step == self.total_steps:
            self.btn_next.configure(text="Crear Servidor", fg_color="green", hover_color="darkgreen")
        else:
            self.btn_next.configure(text="Siguiente", fg_color=["#3a7ebf", "#1f538d"], hover_color=["#325882", "#14375e"])

    def clear_content(self):
        for widget in self.content_frame.winfo_children():
            widget.destroy()

    def on_versions_refreshed(self):
        if self.current_step == 2:
            self.after(0, self._render_versions)

    # --- Step 1: Identidad ---
    def show_step_1(self):
        self.clear_content()
        self.update_header("Identidad del Servidor")
        
        ctk.CTkLabel(self.content_frame, text="Nombre del Servidor:", font=ctk.CTkFont(weight="bold")).pack(anchor="w", pady=(0, 5))
        self.entry_name = ctk.CTkEntry(self.content_frame, placeholder_text="my-awesome-server", corner_radius=12, height=36)
        self.entry_name.pack(fill="x", pady=(0, 15))
        if self.wizard_data["name"]:
            self.entry_name.insert(0, self.wizard_data["name"])
            
        ctk.CTkLabel(self.content_frame, text="Ubicación Personalizada:", font=ctk.CTkFont(weight="bold")).pack(anchor="w", pady=(0, 5))
        loc_frame = ctk.CTkFrame(self.content_frame, fg_color="transparent")
        loc_frame.pack(fill="x", pady=(0, 15))
        
        self.entry_location = ctk.CTkEntry(loc_frame, corner_radius=12, height=36)
        self.entry_location.pack(side="left", fill="x", expand=True, padx=(0, 10))
        self.entry_location.insert(0, self.wizard_data["location"])
        
        btn_browse_loc = ctk.CTkButton(loc_frame, text="Explorar...", command=self.browse_location, corner_radius=12, width=80, fg_color="gray", hover_color="gray30")
        btn_browse_loc.pack(side="right")
            
        ctk.CTkLabel(self.content_frame, text="Icono del Servidor (Opcional):", font=ctk.CTkFont(weight="bold")).pack(anchor="w", pady=(0, 10))
        
        self.icon_preview = ctk.CTkLabel(self.content_frame, text="Sin Icono", width=100, height=100, fg_color="gray30", corner_radius=12)
        self.icon_preview.pack(pady=10)
        
        if self.wizard_data["icon_path"]:
            self._update_icon_preview(self.wizard_data["icon_path"])
            
        btn_browse = ctk.CTkButton(self.content_frame, text="Buscar Imagen...", command=self.browse_icon, corner_radius=12, fg_color="gray", hover_color="gray30")
        btn_browse.pack(pady=10)

    def browse_location(self):
        from tkinter import filedialog
        dir_path = filedialog.askdirectory(title="Seleccionar Carpeta Raíz")
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

    # --- Step 2: Motor ---
    def show_step_2(self):
        self.clear_content()
        self.update_header("Motor & Versión")
        
        # Engine Selection
        engines_frame = ctk.CTkFrame(self.content_frame, fg_color="transparent")
        engines_frame.pack(fill="x", pady=(0, 15))
        
        self.engine_var = ctk.StringVar(value=self.wizard_data["type"])
        engines = [("Vanilla", "🌿 Vanilla"), ("Forge", "🔨 Forge"), ("Fabric", "🧶 Fabric"), ("Paper", "🧻 Paper")]
        
        # 2 rows for radio buttons
        row1 = ctk.CTkFrame(engines_frame, fg_color="transparent")
        row1.pack(fill="x", pady=5)
        
        for val, name in engines:
            rb = ctk.CTkRadioButton(row1, text=name, variable=self.engine_var, value=val, command=self._on_engine_change, font=ctk.CTkFont(size=14))
            rb.pack(side="left", padx=(0, 15))
            
        # Version Search
        ctk.CTkLabel(self.content_frame, text="Buscar Versión:", font=ctk.CTkFont(weight="bold")).pack(anchor="w", pady=(0, 5))
        self.entry_search = ctk.CTkEntry(self.content_frame, placeholder_text="Ej. 1.20.1", corner_radius=12, height=36)
        self.entry_search.pack(fill="x", pady=(0, 10))
        self.entry_search.bind("<KeyRelease>", lambda e: self._render_versions())
        
        # Versions List
        self.scroll_versions = ctk.CTkScrollableFrame(self.content_frame, corner_radius=12, fg_color=("gray90", "gray15"))
        self.scroll_versions.pack(fill="both", expand=True)
        
        self.version_var = ctk.StringVar(value=self.wizard_data["version"])
        self._render_versions()
        
    def _on_engine_change(self):
        self.wizard_data["type"] = self.engine_var.get()
        self._render_versions()
        
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
            except:
                return (0, 0, 0)

        versions.sort(key=version_key, reverse=True)
        filtered = [v for v in versions if search_q in v.lower()]
        
        if not filtered:
            ctk.CTkLabel(self.scroll_versions, text="No se encontraron versiones.").pack(pady=20)
            return
            
        for v in filtered[:100]: # Allow more versions to be shown
            rb = ctk.CTkRadioButton(self.scroll_versions, text=v, variable=self.version_var, value=v)
            rb.pack(anchor="w", padx=10, pady=5)
            
        if self.wizard_data["version"] in filtered:
            self.version_var.set(self.wizard_data["version"])
        elif filtered:
            self.version_var.set(filtered[0])

    # --- Step 3: Hardware ---
    def show_step_3(self):
        self.clear_content()
        self.update_header("Hardware (RAM & Red)")
        
        total_ram = psutil.virtual_memory().total / (1024 * 1024)
        max_slider = min(16384, total_ram - 1024)
        
        ctk.CTkLabel(self.content_frame, text="Memoria RAM (MB):", font=ctk.CTkFont(weight="bold")).pack(anchor="w", pady=(0, 5))
        
        input_frame = ctk.CTkFrame(self.content_frame, fg_color="transparent")
        input_frame.pack(fill="x", pady=(0, 10))
        
        self.entry_ram = ctk.CTkEntry(input_frame, width=100, corner_radius=12, height=36)
        self.entry_ram.pack(side="left", padx=(0, 10))
        self.entry_ram.insert(0, str(self.wizard_data['ram']))
        self.entry_ram.bind("<KeyRelease>", self.update_ram_from_entry)
        
        self.slider_ram = ctk.CTkSlider(self.content_frame, from_=512, to=max_slider, number_of_steps=100, command=self.update_ram_label)
        self.slider_ram.set(self.wizard_data["ram"])
        self.slider_ram.pack(fill="x", pady=(0, 20))
        
        self.lbl_ram_error = ctk.CTkLabel(self.content_frame, text="", text_color="red")
        self.lbl_ram_error.pack(anchor="w")

    def update_ram_from_entry(self, event=None):
        try:
            val = int(self.entry_ram.get())
            if 512 <= val <= 32768:
                self.slider_ram.set(val)
                self.wizard_data["ram"] = val
                self.lbl_ram_error.configure(text="")
        except ValueError:
            pass
            
    def update_ram_label(self, value):
        self.wizard_data["ram"] = int(value)
        self.entry_ram.delete(0, "end")
        self.entry_ram.insert(0, str(int(value)))

    # --- Step 4: Reglas y Mundo ---
    def show_step_4(self):
        self.clear_content()
        self.update_header("Reglas y Mundo")
        
        # Game Mode
        ctk.CTkLabel(self.content_frame, text="Modo de Juego:", font=ctk.CTkFont(weight="bold")).pack(anchor="w", pady=(0, 5))
        self.combo_gamemode = ctk.CTkComboBox(self.content_frame, values=["survival", "creative", "adventure", "spectator"], corner_radius=12, height=36)
        self.combo_gamemode.pack(fill="x", pady=(0, 10))
        self.combo_gamemode.set(self.wizard_data["game_mode"])
        
        # Difficulty
        ctk.CTkLabel(self.content_frame, text="Dificultad:", font=ctk.CTkFont(weight="bold")).pack(anchor="w", pady=(0, 5))
        self.combo_difficulty = ctk.CTkComboBox(self.content_frame, values=["peaceful", "easy", "normal", "hard"], corner_radius=12, height=36)
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
        
        # Seed
        ctk.CTkLabel(self.content_frame, text="Semilla (Seed) (Opcional):", font=ctk.CTkFont(weight="bold")).pack(anchor="w", pady=(0, 5))
        self.entry_seed = ctk.CTkEntry(self.content_frame, placeholder_text="Dejar vacío para aleatoria", corner_radius=12, height=36)
        self.entry_seed.pack(fill="x", pady=(0, 10))
        if self.wizard_data["seed"]:
            self.entry_seed.insert(0, self.wizard_data["seed"])
            
        # Distances
        dist_frame = ctk.CTkFrame(self.content_frame, fg_color="transparent")
        dist_frame.pack(fill="x", pady=(0, 10))
        
        ctk.CTkLabel(dist_frame, text="View Distance:", font=ctk.CTkFont(weight="bold")).grid(row=0, column=0, sticky="w", pady=(0, 5))
        self.entry_view = ctk.CTkEntry(dist_frame, width=60, corner_radius=12, height=36)
        self.entry_view.grid(row=1, column=0, sticky="w", padx=(0, 20))
        self.entry_view.insert(0, str(self.wizard_data["view_distance"]))
        
        ctk.CTkLabel(dist_frame, text="Simulation Distance:", font=ctk.CTkFont(weight="bold")).grid(row=0, column=1, sticky="w", pady=(0, 5))
        self.entry_sim = ctk.CTkEntry(dist_frame, width=60, corner_radius=12, height=36)
        self.entry_sim.grid(row=1, column=1, sticky="w")
        self.entry_sim.insert(0, str(self.wizard_data["simulation_distance"]))

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
            pass # RAM is saved automatically via events
                
        elif self.current_step == 4:
            self.wizard_data["game_mode"] = self.combo_gamemode.get()
            self.wizard_data["difficulty"] = self.combo_difficulty.get()
            self.wizard_data["hardcore"] = self.var_hardcore.get()
            self.wizard_data["whitelist"] = self.var_whitelist.get()
            self.wizard_data["seed"] = self.entry_seed.get().strip()
            self.wizard_data["view_distance"] = self.entry_view.get().strip()
            self.wizard_data["simulation_distance"] = self.entry_sim.get().strip()
            
            self.on_complete_callback(self.wizard_data)
            self.destroy()
            return

        self.current_step += 1
        self.show_step()
        
    def go_back(self):
        if self.current_step == 4:
            self.wizard_data["game_mode"] = self.combo_gamemode.get()
            self.wizard_data["difficulty"] = self.combo_difficulty.get()
            self.wizard_data["hardcore"] = self.var_hardcore.get()
            self.wizard_data["whitelist"] = self.var_whitelist.get()
            self.wizard_data["seed"] = self.entry_seed.get().strip()
            self.wizard_data["view_distance"] = self.entry_view.get().strip()
            self.wizard_data["simulation_distance"] = self.entry_sim.get().strip()
            
        self.current_step -= 1
        self.show_step()
        
    def show_step(self):
        if self.current_step == 1: self.show_step_1()
        elif self.current_step == 2: self.show_step_2()
        elif self.current_step == 3: self.show_step_3()
        elif self.current_step == 4: self.show_step_4()
