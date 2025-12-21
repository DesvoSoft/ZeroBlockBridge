import customtkinter as ctk
import os
import psutil
from app.constants import MINECRAFT_VERSIONS, SERVERS_DIR

class ServerWizard(ctk.CTkToplevel):
    def __init__(self, parent, on_complete_callback):
        super().__init__(parent)
        self.title("Create New Server - Zero Block Bridge")
        self.geometry("600x500")
        self.resizable(False, False)
        
        self.on_complete_callback = on_complete_callback
        self.current_step = 1
        self.total_steps = 6
        
        # Data storage
        self.wizard_data = {
            "name": "",
            "type": "Vanilla",
            "version": "1.21.1",
            "ram": 2048,
            "seed": "",
            "game_mode": "survival",
            "difficulty": "normal",
            "view_distance": "10",
            "simulation_distance": "10",
            "location": "default",
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
        self.lbl_step = ctk.CTkLabel(self.header_frame, text="Step 1 of 5", font=ctk.CTkFont(size=14))
        self.lbl_step.pack(side="left", padx=20, pady=10)
        self.lbl_title = ctk.CTkLabel(self.header_frame, text="Server Details", font=ctk.CTkFont(size=16, weight="bold"))
        self.lbl_title.pack(side="right", padx=20, pady=10)
        
        # Content Frame
        self.content_frame = ctk.CTkFrame(self, fg_color="transparent")
        self.content_frame.grid(row=1, column=0, sticky="nsew", padx=20, pady=20)
        
        # Footer
        self.footer_frame = ctk.CTkFrame(self, height=60, corner_radius=0)
        self.footer_frame.grid(row=2, column=0, sticky="ew")
        
        self.btn_back = ctk.CTkButton(self.footer_frame, text="Back", command=self.go_back, state="disabled")
        self.btn_back.pack(side="left", padx=20, pady=15)
        
        self.btn_next = ctk.CTkButton(self.footer_frame, text="Next", command=self.go_next)
        self.btn_next.pack(side="right", padx=20, pady=15)
        
        # Initialize Step 1
        self.show_step_1()
        
        # Make modal
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

    # --- Steps ---
    
    def show_step_1(self):
        self.clear_content()
        self.update_header("Server Type & Name")
        
        # Name
        ctk.CTkLabel(self.content_frame, text="Server Name:").pack(anchor="w", pady=(0, 5))
        self.entry_name = ctk.CTkEntry(self.content_frame, placeholder_text="my-awesome-server")
        self.entry_name.pack(fill="x", pady=(0, 20))
        if self.wizard_data["name"]:
            self.entry_name.insert(0, self.wizard_data["name"])
            
        # Type
        ctk.CTkLabel(self.content_frame, text="Server Type:").pack(anchor="w", pady=(0, 5))
        self.combo_type = ctk.CTkComboBox(self.content_frame, values=list(MINECRAFT_VERSIONS.keys()), 
                                         command=self.update_version_list, state="readonly")
        self.combo_type.set(self.wizard_data["type"])
        self.combo_type.pack(fill="x", pady=(0, 20))
        # Fix: Make clickable anywhere and prevent text selection
        self.combo_type._entry.bind("<Button-1>", lambda e: self.combo_type._open_dropdown_menu())
        self.combo_type._entry.bind("<B1-Motion>", lambda e: "break")
        self.combo_type._entry.bind("<Double-Button-1>", lambda e: "break")
        self.combo_type._entry.configure(cursor="arrow")
        
        # Version
        ctk.CTkLabel(self.content_frame, text="Minecraft Version:").pack(anchor="w", pady=(0, 5))
        self.combo_version = ctk.CTkComboBox(self.content_frame, state="readonly")
        self.combo_version.pack(fill="x", pady=(0, 5))
        # Fix: Make clickable anywhere and prevent text selection
        self.combo_version._entry.bind("<Button-1>", lambda e: self.combo_version._open_dropdown_menu())
        self.combo_version._entry.bind("<B1-Motion>", lambda e: "break")
        self.combo_version._entry.bind("<Double-Button-1>", lambda e: "break")
        self.combo_version._entry.configure(cursor="arrow")
        
        # Initialize versions
        self.update_version_list(self.wizard_data["type"])
        
        # Pre-select version if available
        if self.wizard_data["version"] in self.combo_version.cget("values"):
             self.combo_version.set(self.wizard_data["version"])

    def update_version_list(self, server_type):
        versions = list(MINECRAFT_VERSIONS.get(server_type, {}).keys())
        # Sort versions if needed (they are usually dict keys, so insertion order or random)
        # For now, let's assume the dict in constants is ordered or we sort desc
        versions.sort(reverse=True) 
        self.combo_version.configure(values=versions)
        if versions:
            self.combo_version.set(versions[0])
        else:
            self.combo_version.set("No versions found")
        
    def show_step_2(self):
        self.clear_content()
        self.update_header("Performance (RAM)")
        
        # RAM Slider
        total_ram = psutil.virtual_memory().total / (1024 * 1024) # MB
        max_slider = min(16384, total_ram - 1024) # Leave 1GB for OS
        
        ctk.CTkLabel(self.content_frame, text=f"RAM Allocation (MB):").pack(anchor="w", pady=(0, 5))
        
        # Manual entry and slider in same row
        input_frame = ctk.CTkFrame(self.content_frame, fg_color="transparent")
        input_frame.pack(fill="x", pady=(0, 10))
        
        self.entry_ram = ctk.CTkEntry(input_frame, width=100, placeholder_text="MB")
        self.entry_ram.pack(side="left", padx=(0, 10))
        self.entry_ram.insert(0, str(self.wizard_data['ram']))
        self.entry_ram.bind("<KeyRelease>", self.update_ram_from_entry)
        
        self.lbl_ram_value = ctk.CTkLabel(input_frame, text=f"or use slider")
        self.lbl_ram_value.pack(side="left")
        
        self.slider_ram = ctk.CTkSlider(self.content_frame, from_=512, to=max_slider, number_of_steps=100,
                                       command=self.update_ram_label)
        self.slider_ram.set(self.wizard_data["ram"])
        self.slider_ram.pack(fill="x", pady=(0, 20))
        
        # Validation label
        self.lbl_ram_error = ctk.CTkLabel(self.content_frame, text="", text_color="red")
        self.lbl_ram_error.pack(anchor="w")
        
        # Recommendations
        rec_frame = ctk.CTkFrame(self.content_frame)
        rec_frame.pack(fill="x", pady=10)
        ctk.CTkLabel(rec_frame, text="Recommendations:", font=ctk.CTkFont(weight="bold")).pack(anchor="w", padx=10, pady=5)
        ctk.CTkLabel(rec_frame, text="• Vanilla: 2048 - 4096 MB").pack(anchor="w", padx=10)
        ctk.CTkLabel(rec_frame, text="• Modded (Fabric): 6144 - 8192 MB").pack(anchor="w", padx=10)
        
    def update_ram_from_entry(self, event=None):
        try:
            value = int(self.entry_ram.get())
            total_ram = psutil.virtual_memory().total / (1024 * 1024)
            max_ram = min(16384, total_ram - 1024)
            
            if value < 512:
                self.lbl_ram_error.configure(text="⚠ Minimum: 512 MB")
                return
            elif value > max_ram:
                self.lbl_ram_error.configure(text=f"⚠ Maximum: {int(max_ram)} MB")
                return
            else:
                self.lbl_ram_error.configure(text="")
                self.wizard_data["ram"] = value
                self.slider_ram.set(value)
        except ValueError:
            if self.entry_ram.get():  # Only show error if not empty
                self.lbl_ram_error.configure(text="⚠ Enter a valid number")
        
    def update_ram_label(self, value):
        self.wizard_data["ram"] = int(value)
        self.entry_ram.delete(0, "end")
        self.entry_ram.insert(0, str(int(value)))
        self.lbl_ram_error.configure(text="")

    def show_step_3(self):
        self.clear_content()
        self.update_header("World Settings")
        
        # --- Top Row: Seed & Gamemode ---
        top_frame = ctk.CTkFrame(self.content_frame, fg_color="transparent")
        top_frame.pack(fill="x", expand=True)
        top_frame.grid_columnconfigure((0, 1), weight=1)

        # Seed
        seed_frame = ctk.CTkFrame(top_frame, fg_color="transparent")
        seed_frame.grid(row=0, column=0, sticky="nsew", padx=(0, 10))
        ctk.CTkLabel(seed_frame, text="World Seed (Optional):").pack(anchor="w", pady=(0, 5))
        self.entry_seed = ctk.CTkEntry(seed_frame, placeholder_text="Leave empty for random")
        self.entry_seed.pack(fill="x")
        if self.wizard_data["seed"]: self.entry_seed.insert(0, self.wizard_data["seed"])
            
        # Game Mode
        gamemode_frame = ctk.CTkFrame(top_frame, fg_color="transparent")
        gamemode_frame.grid(row=0, column=1, sticky="nsew", padx=(10, 0))
        ctk.CTkLabel(gamemode_frame, text="Default Game Mode:").pack(anchor="w", pady=(0, 5))
        self.combo_gamemode = ctk.CTkComboBox(gamemode_frame, values=["survival", "creative", "adventure", "spectator"], state="readonly")
        self.combo_gamemode.set(self.wizard_data["game_mode"])
        self.combo_gamemode.pack(fill="x")
        # Fix: Make clickable anywhere and prevent text selection
        self.combo_gamemode._entry.bind("<Button-1>", lambda e: self.combo_gamemode._open_dropdown_menu())
        self.combo_gamemode._entry.bind("<B1-Motion>", lambda e: "break")
        self.combo_gamemode._entry.bind("<Double-Button-1>", lambda e: "break")
        self.combo_gamemode._entry.configure(cursor="arrow")

        # --- Middle Row: Difficulty, View, Sim ---
        middle_frame = ctk.CTkFrame(self.content_frame, fg_color="transparent")
        middle_frame.pack(fill="x", expand=True, pady=(20, 0))
        middle_frame.grid_columnconfigure((0, 1, 2), weight=1)
        
        # Difficulty
        difficulty_frame = ctk.CTkFrame(middle_frame, fg_color="transparent")
        difficulty_frame.grid(row=0, column=0, sticky="nsew", padx=(0, 10))
        ctk.CTkLabel(difficulty_frame, text="Difficulty:").pack(anchor="w", pady=(0, 5))
        self.combo_difficulty = ctk.CTkComboBox(difficulty_frame, values=["peaceful", "easy", "normal", "hard"], state="readonly")
        self.combo_difficulty.set(self.wizard_data["difficulty"])
        self.combo_difficulty.pack(fill="x")
        # Fix: Make clickable anywhere and prevent text selection
        self.combo_difficulty._entry.bind("<Button-1>", lambda e: self.combo_difficulty._open_dropdown_menu())
        self.combo_difficulty._entry.bind("<B1-Motion>", lambda e: "break")
        self.combo_difficulty._entry.bind("<Double-Button-1>", lambda e: "break")
        self.combo_difficulty._entry.configure(cursor="arrow")

        # View Distance
        view_dist_frame = ctk.CTkFrame(middle_frame, fg_color="transparent")
        view_dist_frame.grid(row=0, column=1, sticky="nsew", padx=(10, 10))
        ctk.CTkLabel(view_dist_frame, text="View Distance (chunks):").pack(anchor="w", pady=(0, 5))
        self.entry_view_distance = ctk.CTkEntry(view_dist_frame, placeholder_text="Default: 10")
        self.entry_view_distance.pack(fill="x")
        if self.wizard_data["view_distance"]: self.entry_view_distance.insert(0, self.wizard_data["view_distance"])

        # Simulation Distance
        sim_dist_frame = ctk.CTkFrame(middle_frame, fg_color="transparent")
        sim_dist_frame.grid(row=0, column=2, sticky="nsew", padx=(10, 0))
        ctk.CTkLabel(sim_dist_frame, text="Simulation Distance (chunks):").pack(anchor="w", pady=(0, 5))
        self.entry_sim_distance = ctk.CTkEntry(sim_dist_frame, placeholder_text="Default: 10")
        self.entry_sim_distance.pack(fill="x")
        if self.wizard_data["simulation_distance"]: self.entry_sim_distance.insert(0, self.wizard_data["simulation_distance"])



    def show_step_4(self):
        self.clear_content()
        self.update_header("Server Icon")
        
        ctk.CTkLabel(self.content_frame, text="Choose a server icon (Optional):").pack(anchor="w", pady=(0, 10))
        
        self.icon_preview = ctk.CTkLabel(self.content_frame, text="No Icon Selected", 
                                        width=100, height=100, fg_color="gray30", corner_radius=10)
        self.icon_preview.pack(pady=10)
        
        if self.wizard_data["icon_path"]:
            self._update_icon_preview(self.wizard_data["icon_path"])
            
        btn_browse = ctk.CTkButton(self.content_frame, text="Browse Image...", command=self.browse_icon)
        btn_browse.pack(pady=10)
        
        ctk.CTkLabel(self.content_frame, text="Supported formats: PNG, JPG (will be resized to 64x64)", 
                    text_color="gray", font=ctk.CTkFont(size=11)).pack(pady=5)

    def browse_icon(self):
        from tkinter import filedialog
        file_path = filedialog.askopenfilename(
            title="Select Server Icon",
            filetypes=[("Images", "*.png;*.jpg;*.jpeg")]
        )
        if file_path:
            self.wizard_data["icon_path"] = file_path
            self._update_icon_preview(file_path)
            
    def _update_icon_preview(self, path):
        try:
            from PIL import Image
            img = ctk.CTkImage(Image.open(path), size=(100, 100))
            self.icon_preview.configure(image=img, text="")
        except Exception as e:
            self.icon_preview.configure(text="Error loading image")

    def show_step_5(self):
        self.clear_content()
        self.update_header("Storage Location")
        
        ctk.CTkLabel(self.content_frame, text="Save Location:").pack(anchor="w", pady=(0, 5))
        
        server_path = SERVERS_DIR / self.wizard_data['name']
        self.lbl_location = ctk.CTkLabel(self.content_frame, text=str(server_path), 
                                        fg_color="gray20", corner_radius=6, padx=10, pady=5)
        self.lbl_location.pack(fill="x", pady=(0, 20))
        
        ctk.CTkLabel(self.content_frame, text="Note: Custom locations coming soon.", text_color="gray").pack(anchor="w")

    def show_step_6(self):
        self.clear_content()
        self.update_header("Review & Create")
        
        icon_status = "Default"
        if self.wizard_data["icon_path"]:
            icon_status = os.path.basename(self.wizard_data["icon_path"])
            
        summary = (
            f"Server Name: {self.wizard_data['name']}\n"
            f"Type: {self.wizard_data['type']} {self.wizard_data['version']}\n"
            f"RAM: {self.wizard_data['ram']} MB\n\n"
            f"World Seed: {self.wizard_data['seed'] or 'Random'}\n"
            f"Game Mode: {self.wizard_data['game_mode']}\n"
            f"Difficulty: {self.wizard_data['difficulty']}\n"
            f"View Distance: {self.wizard_data['view_distance']}\n"
            f"Simulation Distance: {self.wizard_data['simulation_distance']}\n\n"
            f"Icon: {icon_status}\n"
            f"Location: {SERVERS_DIR / self.wizard_data['name']}"
        )
        
        ctk.CTkLabel(self.content_frame, text="Please review your settings:", font=ctk.CTkFont(weight="bold")).pack(anchor="w", pady=(0, 10))
        
        lbl_summary = ctk.CTkLabel(self.content_frame, text=summary, justify="left", anchor="w", 
                                  fg_color="gray20", corner_radius=6, padx=15, pady=15)
        lbl_summary.pack(fill="x")

    # --- Navigation ---
    
    def go_next(self):
        # Save data from current step
        if self.current_step == 1:
            name = self.entry_name.get().strip()
            if not name:
                # Simple validation
                self.entry_name.configure(border_color="red")
                self.entry_name.focus()
                return
            else:
                self.entry_name.configure(border_color=["#979da2", "#565b5e"]) # Reset to default (light/dark)
            self.wizard_data["name"] = name
            self.wizard_data["type"] = self.combo_type.get()
            self.wizard_data["version"] = self.combo_version.get()
            
        elif self.current_step == 2:
            # RAM already updated via callback
            pass
            
        elif self.current_step == 3:
            self.wizard_data["seed"] = self.entry_seed.get().strip()
            self.wizard_data["game_mode"] = self.combo_gamemode.get()
            self.wizard_data["difficulty"] = self.combo_difficulty.get()
            # Validate distances
            v_dist = self.entry_view_distance.get().strip() or "10"
            s_dist = self.entry_sim_distance.get().strip() or "10"
            
            try:
                v_val = int(v_dist)
                s_val = int(s_dist)
                
                if not (2 <= v_val <= 32):
                    raise ValueError("View distance must be between 2 and 32")
                if not (2 <= s_val <= 32):
                    raise ValueError("Simulation distance must be between 2 and 32")
                    
                self.wizard_data["view_distance"] = str(v_val)
                self.wizard_data["simulation_distance"] = str(s_val)
                
                # Reset borders
                self.entry_view_distance.configure(border_color=["#979da2", "#565b5e"])
                self.entry_sim_distance.configure(border_color=["#979da2", "#565b5e"])
                
            except ValueError:
                # Show error visually (red borders)
                self.entry_view_distance.configure(border_color="red")
                self.entry_sim_distance.configure(border_color="red")
                return
            
            
        elif self.current_step == 6:
            # Finish
            self.on_complete_callback(self.wizard_data)
            self.destroy()
            return

        self.current_step += 1
        self.show_step()
        
    def go_back(self):
        self.current_step -= 1
        self.show_step()
        
    def show_step(self):
        if self.current_step == 1: self.show_step_1()
        elif self.current_step == 2: self.show_step_2()
        elif self.current_step == 3: self.show_step_3()
        elif self.current_step == 4: self.show_step_4()
        elif self.current_step == 5: self.show_step_5()
        elif self.current_step == 6: self.show_step_6()

