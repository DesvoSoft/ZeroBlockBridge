import customtkinter as ctk
import logging
import psutil
import threading
from app.core.constants import SERVERS_DIR
from app.core.version_manager import VersionManager
from app.core.app_config import AppConfig
from app.services.java_detector import JavaDetector, get_required_java
from app.services.template_manager import list_templates, load_template, save_template
from app.ui.ui_components import center_on_parent
from app.ui.win_effects import apply_rounded_corners
from app.ui.icons import icon
from PIL import Image

logger = logging.getLogger(__name__)

class ServerWizard(ctk.CTkToplevel):
    def __init__(self, parent, on_complete_callback):
        super().__init__(parent)
        self.title("Create New Server - Zero Block Bridge")
        self.geometry("650x650")
        center_on_parent(self, parent, 650, 650)
        self.resizable(True, True)
        self.minsize(650, 650)

        self.on_complete_callback = on_complete_callback
        self.current_step = 1
        self.total_steps = 5
        
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
            "enforce_whitelist": False,
            "pvp": True,
            "online_mode": True,
            "max_players": 20,
            "spawn_protection": 16,
            "enable_command_block": False,
            "allow_flight": False,
            "enforce_secure_profile": True,
            "view_distance": "10",
            "simulation_distance": "10",
            "location": str(SERVERS_DIR),
            "icon_path": None,
            "auto_install_jdk": True,
            "java_path": "auto",
            "playit_port": "25565",
        }
        
        # Layout
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(0, weight=0) # Header
        self.grid_rowconfigure(1, weight=1) # Content
        self.grid_rowconfigure(2, weight=0) # Footer
        
        # Header
        self.header_frame = ctk.CTkFrame(self, height=50, corner_radius=0,
                                         fg_color=(AppConfig.COLOR_BG_CARD_LIGHT, AppConfig.COLOR_BG_CARD_DARK))
        self.header_frame.grid(row=0, column=0, sticky="ew")
        self.lbl_step = ctk.CTkLabel(self.header_frame, text="Step 1 of 3",
                                     font=ctk.CTkFont(size=13), text_color=AppConfig.COLOR_TEXT_GRAY)
        self.lbl_step.pack(side="left", padx=20, pady=10)
        self.lbl_title = ctk.CTkLabel(self.header_frame, text="Identity",
                                      font=ctk.CTkFont(size=16, weight="bold"))
        self.lbl_title.pack(side="right", padx=20, pady=10)

        # Content Frame
        self.content_frame = ctk.CTkFrame(self, fg_color="transparent")
        self.content_frame.grid(row=1, column=0, sticky="nsew", padx=20, pady=20)

        # Footer
        self.footer_frame = ctk.CTkFrame(self, height=60, corner_radius=0,
                                         fg_color=(AppConfig.COLOR_BG_CARD_LIGHT, AppConfig.COLOR_BG_CARD_DARK))
        self.footer_frame.grid(row=2, column=0, sticky="ew")

        self.btn_back = ctk.CTkButton(
            self.footer_frame, text="← Back", command=self.go_back, state="disabled",
            corner_radius=AppConfig.RADIUS_BTN, height=36,
            fg_color=AppConfig.COLOR_BTN_GHOST, hover_color=AppConfig.COLOR_BTN_GHOST_HOVER,
        )
        self.btn_back.pack(side="left", padx=20, pady=12)

        self.btn_next = ctk.CTkButton(
            self.footer_frame, text="Next", command=self.go_next,
            image=icon("chevron_right", 13, "#ffffff"), compound="right",
            corner_radius=AppConfig.RADIUS_BTN, height=36,
            fg_color=AppConfig.COLOR_BTN_PRIMARY, hover_color=AppConfig.COLOR_BTN_PRIMARY_HOVER,
        )
        self.btn_next.pack(side="right", padx=20, pady=12)

        self.btn_save_template = ctk.CTkButton(
            self.footer_frame, text="Save as Template", command=self._save_as_template,
            corner_radius=AppConfig.RADIUS_BTN, height=36,
            fg_color=AppConfig.COLOR_BTN_GHOST, hover_color=AppConfig.COLOR_BTN_GHOST_HOVER,
        )
        # packed/unpacked per-step in _update_nav()

        self.vm = VersionManager()
        self.vm.add_callback(self.on_versions_refreshed)
        
        self.show_step_1()
        
        self.transient(parent)
        apply_rounded_corners(self)
        self.wait_visibility()
        self.grab_set()

    def destroy(self):
        self.vm.remove_callback(self.on_versions_refreshed)
        super().destroy()

    def update_header(self, title):
        self.lbl_step.configure(text=f"Step {self.current_step} of {self.total_steps}")
        self.lbl_title.configure(text=title)
        
        if self.current_step == 1:
            self.btn_back.configure(state="disabled")
        else:
            self.btn_back.configure(state="normal")
            
        if self.current_step == self.total_steps:
            self.btn_next.configure(text="Create Server", image=icon("check", 13, "#ffffff"),
                                    fg_color=AppConfig.COLOR_BTN_SUCCESS,
                                    hover_color=AppConfig.COLOR_BTN_SUCCESS_HOVER)
        else:
            self.btn_next.configure(text="Next", image=icon("chevron_right", 13, "#ffffff"),
                                    fg_color=AppConfig.COLOR_BTN_PRIMARY,
                                    hover_color=AppConfig.COLOR_BTN_PRIMARY_HOVER)

        if self.current_step == 5:
            self.btn_save_template.pack(side="left", padx=(0, 10), pady=12)
        else:
            self.btn_save_template.pack_forget()

    def clear_content(self):
        for widget in self.content_frame.winfo_children():
            widget.destroy()

    def on_versions_refreshed(self):
        if self.current_step == 2:
            self.after(0, self._render_versions)

    def _force_refresh_versions(self):
        self.btn_refresh.configure(state="disabled", text="...")
        threading.Thread(target=self._do_force_refresh, daemon=True).start()

    def _do_force_refresh(self):
        try:
            self.vm.refresh_versions()
        finally:
            self.after(0, lambda: self.btn_refresh.configure(state="normal", text="Refresh"))

    # --- Step 1: Identidad ---
    def show_step_1(self):
        self.clear_content()
        self.update_header("Server Identity")
        
        ctk.CTkLabel(self.content_frame, text="Server Name:", font=ctk.CTkFont(weight="bold")).pack(anchor="w", pady=(0, 5))
        self.entry_name = ctk.CTkEntry(self.content_frame, placeholder_text="my-awesome-server", corner_radius=AppConfig.RADIUS_BTN, height=36)
        self.entry_name.pack(fill="x", pady=(0, 15))
        if self.wizard_data["name"]:
            self.entry_name.insert(0, self.wizard_data["name"])
            
        ctk.CTkLabel(self.content_frame, text="Custom Location:", font=ctk.CTkFont(weight="bold")).pack(anchor="w", pady=(0, 5))
        loc_frame = ctk.CTkFrame(self.content_frame, fg_color="transparent")
        loc_frame.pack(fill="x", pady=(0, 15))
        
        self.entry_location = ctk.CTkEntry(loc_frame, corner_radius=AppConfig.RADIUS_BTN, height=36)
        self.entry_location.pack(side="left", fill="x", expand=True, padx=(0, 10))
        self.entry_location.insert(0, self.wizard_data["location"])
        
        btn_browse_loc = ctk.CTkButton(loc_frame, text="Browse...", command=self.browse_location,
                                        corner_radius=AppConfig.RADIUS_BTN, width=90, height=36,
                                        fg_color=AppConfig.COLOR_BTN_GHOST, hover_color=AppConfig.COLOR_BTN_GHOST_HOVER)
        btn_browse_loc.pack(side="right")
            
        ctk.CTkLabel(self.content_frame, text="Server Icon (Optional):", font=ctk.CTkFont(weight="bold")).pack(anchor="w", pady=(0, 10))
        
        self.icon_preview = ctk.CTkLabel(self.content_frame, text="No Icon", width=100, height=100,
                                          fg_color=AppConfig.COLOR_BTN_GHOST, corner_radius=AppConfig.RADIUS_CARD)
        self.icon_preview.pack(pady=10)

        if self.wizard_data["icon_path"]:
            self._update_icon_preview(self.wizard_data["icon_path"])

        btn_browse = ctk.CTkButton(self.content_frame, text="Select Image...", command=self.browse_icon,
                                    corner_radius=AppConfig.RADIUS_BTN, height=32,
                                    fg_color=AppConfig.COLOR_BTN_GHOST, hover_color=AppConfig.COLOR_BTN_GHOST_HOVER)
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
        file_path = filedialog.askopenfilename(title="Select Icon", filetypes=[("Images", "*.png;*.jpg;*.jpeg")])
        if file_path:
            self.wizard_data["icon_path"] = file_path
            self._update_icon_preview(file_path)
            
    def _update_icon_preview(self, path):
        try:
            img = ctk.CTkImage(Image.open(path), size=(100, 100))
            self.icon_preview.configure(image=img, text="")
        except Exception as e:
            logger.debug("Error loading image: %s", e)
            self.icon_preview.configure(text="Error")

    # --- Step 2: Engine & Version ---
    def show_step_2(self):
        self.clear_content()
        self.update_header("Engine & Version")

        p = self.content_frame

        # Start from template
        templates = list_templates()
        if templates:
            ctk.CTkLabel(p, text="Start from template (optional):", font=ctk.CTkFont(weight="bold")).pack(anchor="w", pady=(0, 5))
            template_row = ctk.CTkFrame(p, fg_color="transparent")
            template_row.pack(fill="x", pady=(0, 15))
            template_names = ["None"] + [t["name"] for t in templates]
            self.template_var = ctk.StringVar(value="None")
            template_menu = ctk.CTkOptionMenu(template_row, values=template_names, variable=self.template_var,
                                               command=self._on_template_selected, width=200)
            template_menu.pack(side="left")

        # Engine Selection
        ctk.CTkLabel(p, text="Server Engine:", font=ctk.CTkFont(weight="bold")).pack(anchor="w", pady=(0, 5))

        self.engine_var = ctk.StringVar(value=self.wizard_data["type"])
        engines = [("Vanilla", "Vanilla"), ("Paper", "Paper"), ("Purpur", "Purpur"), ("Fabric", "Fabric"), ("Forge", "Forge")]

        engine_row = ctk.CTkFrame(p, fg_color="transparent")
        engine_row.pack(fill="x", pady=(0, 15))

        for val, name in engines:
            rb = ctk.CTkRadioButton(engine_row, text=name, variable=self.engine_var, value=val, command=self._on_engine_change, font=ctk.CTkFont(size=14))
            rb.pack(side="left", padx=(0, 12))

        self.lbl_ram_hint = ctk.CTkLabel(p, text="", text_color=AppConfig.COLOR_TEXT_GRAY, font=ctk.CTkFont(size=12))
        self.lbl_ram_hint.pack(anchor="w", pady=(0, 5))
        self._update_ram_hint()

        # Version Search
        ctk.CTkLabel(p, text="Version:", font=ctk.CTkFont(weight="bold")).pack(anchor="w", pady=(0, 5))
        search_row = ctk.CTkFrame(p, fg_color="transparent")
        search_row.pack(fill="x", pady=(0, 10))
        self.entry_search = ctk.CTkEntry(search_row, placeholder_text="e.g. 1.20.1", corner_radius=AppConfig.RADIUS_BTN, height=36)
        self.entry_search.pack(side="left", fill="x", expand=True, padx=(0, 8))
        self.entry_search.bind("<KeyRelease>", lambda e: self._render_versions())
        self.btn_refresh = ctk.CTkButton(search_row, text="Refresh", image=icon("refresh", 13), width=100, height=36, corner_radius=AppConfig.RADIUS_BTN,
                                         fg_color=AppConfig.COLOR_BTN_GHOST, hover_color=AppConfig.COLOR_BTN_GHOST_HOVER,
                                         command=self._force_refresh_versions)
        self.btn_refresh.pack(side="right")

        # Versions List
        self.scroll_versions = ctk.CTkScrollableFrame(p, corner_radius=AppConfig.RADIUS_CARD,
                                                       fg_color=(AppConfig.COLOR_BG_CARD_LIGHT, AppConfig.COLOR_BG_CARD_DARK))
        self.scroll_versions.pack(fill="both", expand=True, pady=(0, 5))

        self.version_var = ctk.StringVar(value=self.wizard_data["version"])
        self._render_versions()

    def _on_engine_change(self):
        self.wizard_data["type"] = self.engine_var.get()
        self._render_versions()
        if hasattr(self, "lbl_ram_hint") and self.lbl_ram_hint.winfo_exists():
            self._update_ram_hint()
        if hasattr(self, "java_options_frame") and self.java_options_frame.winfo_exists():
            self._update_java_check()

    # --- Step 3: Resources (RAM + Java) ---
    def show_step_3(self):
        self.clear_content()
        self.update_header("Resources")

        p = self.content_frame

        # RAM Memory
        total_ram = psutil.virtual_memory().total / (1024 * 1024)
        max_slider = min(16384, total_ram - 1024)
        min_ram = 512

        ram_label_frame = ctk.CTkFrame(p, fg_color="transparent")
        ram_label_frame.pack(fill="x", pady=(0, 5))

        ctk.CTkLabel(ram_label_frame, text="RAM:", font=ctk.CTkFont(weight="bold")).pack(side="left")
        self.lbl_ram_value = ctk.CTkLabel(ram_label_frame, text=f"{self.wizard_data['ram']} MB ({self.wizard_data['ram']//1024} GB)", font=ctk.CTkFont(size=13))
        self.lbl_ram_value.pack(side="left", padx=(10, 0))

        ram_input_frame = ctk.CTkFrame(p, fg_color="transparent")
        ram_input_frame.pack(fill="x", pady=(0, 2))

        self.entry_ram = ctk.CTkEntry(ram_input_frame, width=90, corner_radius=AppConfig.RADIUS_BTN, height=32)
        self.entry_ram.pack(side="left", padx=(0, 10))
        self.entry_ram.insert(0, str(self.wizard_data['ram']))
        self.entry_ram.bind("<KeyRelease>", self.update_ram_from_entry)

        self.slider_ram = ctk.CTkSlider(p, from_=min_ram, to=max_slider, number_of_steps=100, command=self.update_ram_label, height=16, border_width=1)
        self.slider_ram.set(self.wizard_data["ram"])
        self.slider_ram.pack(fill="x", pady=(2, 2))

        slider_range = ctk.CTkFrame(p, fg_color="transparent")
        slider_range.pack(fill="x")
        ctk.CTkLabel(slider_range, text=f"{min_ram} MB", font=ctk.CTkFont(size=10), text_color=AppConfig.COLOR_TEXT_GRAY).pack(side="left")
        self.lbl_ram_util = ctk.CTkLabel(slider_range, text="", font=ctk.CTkFont(size=10), text_color=AppConfig.COLOR_TEXT_GRAY)
        self.lbl_ram_util.pack(side="right")

        self.lbl_ram_error = ctk.CTkLabel(p, text="", text_color=AppConfig.COLOR_STATUS_ERROR, font=ctk.CTkFont(size=12))
        self.lbl_ram_error.pack(anchor="w")
        self.update_ram_label(self.wizard_data["ram"])

        # --- Java Selection ---
        ctk.CTkLabel(p, text="Java:", font=ctk.CTkFont(weight="bold")).pack(anchor="w", pady=(20, 5))

        self.java_choice_var = ctk.StringVar(value="auto" if self.wizard_data.get("java_path", "auto") == "auto" else "detected")

        self.java_options_frame = ctk.CTkFrame(p, corner_radius=8,
                                                fg_color=(AppConfig.COLOR_BG_CARD_LIGHT, AppConfig.COLOR_BG_CARD_DARK))
        self.java_options_frame.pack(fill="x", pady=(0, 5))

        self._detected_java = []
        self.rb_java_auto = ctk.CTkRadioButton(
            self.java_options_frame, text="Auto-download recommended Java version", value="auto",
            variable=self.java_choice_var, command=self._on_java_choice_change,
        )
        self.rb_java_auto.pack(anchor="w", padx=10, pady=(10, 4))

        self.rb_java_detected = ctk.CTkRadioButton(
            self.java_options_frame, text="Use a Java already installed on this system", value="detected",
            variable=self.java_choice_var, command=self._on_java_choice_change,
        )
        self.rb_java_detected.pack(anchor="w", padx=10, pady=(0, 4))

        self.java_detected_menu = ctk.CTkOptionMenu(self.java_options_frame, values=["Detecting..."], width=280)
        self.java_detected_menu.pack(anchor="w", padx=(30, 10), pady=(0, 10))

        self.lbl_java_status = ctk.CTkLabel(p, text="Detecting Java...", font=ctk.CTkFont(size=12),
                                             text_color=AppConfig.COLOR_TEXT_GRAY, anchor="w")
        self.lbl_java_status.pack(fill="x", pady=(4, 0))

        self._update_java_check()

    def _save_as_template(self):
        self._collect_step5_fields()

        dialog = ctk.CTkInputDialog(text="Template name:", title="Save as Template")
        name = dialog.get_input()
        if not name:
            return
        name = name.strip().lower().replace(" ", "-")
        if not name:
            return
        save_template(name, self.wizard_data)

    def _on_template_selected(self, template_name):
        if template_name == "None":
            return
        template = load_template(template_name)
        if not template:
            return
        self.wizard_data.update({k: v for k, v in template.items() if not k.startswith("_")})
        self.engine_var.set(self.wizard_data["type"])
        self.version_var.set(self.wizard_data.get("version", ""))
        self._on_engine_change()

    def _update_ram_hint(self):
        engine = self.engine_var.get()
        hints = {"Vanilla": "512 MB min", "Paper": "1 GB min", "Purpur": "1 GB min", "Fabric": "1 GB min", "Forge": "2 GB min"}
        hint = hints.get(engine, "1 GB min")
        self.lbl_ram_hint.configure(text=f"Recommended: {hint}")

    def _update_java_check(self):
        if not hasattr(self, "java_options_frame") or not self.java_options_frame.winfo_exists():
            return
        version = self.version_var.get()
        if not version:
            self.lbl_java_status.configure(text="Select a version to check Java compatibility.", text_color=AppConfig.COLOR_TEXT_GRAY)
            return
        # detect_all() scans the Windows registry + filesystem — run off the UI
        # thread (NR-04). Sequence counter discards stale results from rapid
        # engine/version switches.
        self._java_check_seq = getattr(self, "_java_check_seq", 0) + 1
        seq = self._java_check_seq
        self.lbl_java_status.configure(text="Detecting Java...", text_color=AppConfig.COLOR_TEXT_GRAY)

        def _detect():
            installations = JavaDetector().detect_all()
            required = get_required_java(version)

            def _apply():
                if seq != self._java_check_seq or not self.lbl_java_status.winfo_exists():
                    return
                self._detected_java = installations
                required_str = str(required)

                if not installations:
                    self.rb_java_detected.configure(state="disabled")
                    self.java_detected_menu.configure(values=["No Java detected"], state="disabled")
                    self.java_detected_menu.set("No Java detected")
                    if self.java_choice_var.get() == "detected":
                        self.java_choice_var.set("auto")
                    self.lbl_java_status.configure(
                        text=f"No Java installations found on this system. MC {version} requires Java {required_str}.",
                        text_color=AppConfig.COLOR_STATUS_STARTING
                    )
                    return

                self.rb_java_detected.configure(state="normal")
                labels = [inst.label for inst in installations]
                self.java_detected_menu.configure(values=labels, state="normal")

                best_idx = next((i for i, inst in enumerate(installations) if inst.major == required), 0)
                self.java_detected_menu.set(labels[best_idx])

                best = installations[best_idx]
                compatible = best.major == required
                compat_text = "OK" if compatible else "Mismatch"
                color = AppConfig.COLOR_BTN_SUCCESS if compatible else AppConfig.COLOR_ACCENT_AMBER
                self.lbl_java_status.configure(
                    text=f"{compat_text}: MC {version} requires Java {required_str}. Detected {best.label}.",
                    text_color=color
                )
                self._on_java_choice_change()

            self.after(0, _apply)

        threading.Thread(target=_detect, daemon=True).start()

    def _on_java_choice_change(self):
        use_detected = self.java_choice_var.get() == "detected"
        self.java_detected_menu.configure(state="normal" if use_detected and self._detected_java else "disabled")
        if not use_detected:
            required = get_required_java(self.version_var.get())
            self.lbl_java_status.configure(
                text=f"Will auto-download Java {required} for this server.",
                text_color=AppConfig.COLOR_TEXT_GRAY
            )

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

        # Show loading indicator immediately — fetch happens in background
        loading_lbl = ctk.CTkLabel(self.scroll_versions, text="Loading versions...",
                                    text_color=AppConfig.COLOR_TEXT_GRAY)
        loading_lbl.pack(pady=20)
        self.scroll_versions.update_idletasks()

        def fetch_and_render():
            import re
            versions = self.vm.get_versions(engine)
            search_q = self.entry_search.get().lower()

            def version_key(v):
                try:
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

            def render_ui():
                if not self.winfo_exists():
                    return
                for widget in self.scroll_versions.winfo_children():
                    widget.destroy()

                if not filtered:
                    ctk.CTkLabel(self.scroll_versions, text="No versions found.",
                                  text_color=AppConfig.COLOR_TEXT_GRAY).pack(pady=20)
                    return

                for v in filtered[:100]:
                    rb = ctk.CTkRadioButton(self.scroll_versions, text=v, variable=self.version_var,
                                             value=v, command=self._update_java_check)
                    rb.pack(anchor="w", padx=10, pady=5)

                # Reset version selection when engine changes — each engine has its own list
                if self.wizard_data.get("_last_engine") != engine:
                    self.wizard_data["_last_engine"] = engine
                    self.wizard_data["version"] = filtered[0] if filtered else ""
                    self.version_var.set(self.wizard_data["version"])
                elif self.wizard_data["version"] in filtered:
                    self.version_var.set(self.wizard_data["version"])
                elif filtered:
                    self.version_var.set(filtered[0])
                    self.wizard_data["version"] = filtered[0]

                self._update_java_check()

            self.after(0, render_ui)

        threading.Thread(target=fetch_and_render, daemon=True).start()

    # --- Step 3: Rules & World ---
    def show_step_4(self):
        self.clear_content()
        self.update_header("Rules & Security")

        scroll = ctk.CTkScrollableFrame(self.content_frame, fg_color="transparent")
        scroll.pack(fill="both", expand=True)
        p = scroll

        # Game Mode
        ctk.CTkLabel(p, text="Game Mode:", font=ctk.CTkFont(weight="bold")).pack(anchor="w", pady=(0, 5))
        self.combo_gamemode = ctk.CTkOptionMenu(p, values=["survival", "creative", "adventure", "spectator"], corner_radius=AppConfig.RADIUS_BTN, height=36)
        self.combo_gamemode.pack(fill="x", pady=(0, 10))
        self.combo_gamemode.set(self.wizard_data["game_mode"])
        
        # Difficulty
        ctk.CTkLabel(p, text="Difficulty:", font=ctk.CTkFont(weight="bold")).pack(anchor="w", pady=(0, 5))
        self.combo_difficulty = ctk.CTkOptionMenu(p, values=["peaceful", "easy", "normal", "hard"], corner_radius=AppConfig.RADIUS_BTN, height=36)
        self.combo_difficulty.pack(fill="x", pady=(0, 10))
        self.combo_difficulty.set(self.wizard_data["difficulty"])
        
        # Toggles Frame
        toggles_frame = ctk.CTkFrame(p, fg_color="transparent")
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

        # Security section
        sec_frame = ctk.CTkFrame(p, fg_color="transparent")
        sec_frame.pack(fill="x", pady=(10, 10))

        ctk.CTkLabel(sec_frame, text="Security:", font=ctk.CTkFont(weight="bold")).pack(anchor="w", pady=(0, 5))

        sec_row1 = ctk.CTkFrame(sec_frame, fg_color="transparent")
        sec_row1.pack(fill="x", pady=(0, 6))

        self.var_online_mode = ctk.BooleanVar(value=self.wizard_data["online_mode"])
        self.chk_online_mode = ctk.CTkSwitch(sec_row1, text="Online Mode", variable=self.var_online_mode)
        self.chk_online_mode.pack(side="left", padx=(0, 20))

        self.var_enforce_whitelist = ctk.BooleanVar(value=self.wizard_data["enforce_whitelist"])
        self.chk_enforce_whitelist = ctk.CTkSwitch(sec_row1, text="Enforce Whitelist", variable=self.var_enforce_whitelist)
        self.chk_enforce_whitelist.pack(side="left", padx=(0, 20))

        self.var_pvp = ctk.BooleanVar(value=self.wizard_data["pvp"])
        self.chk_pvp = ctk.CTkSwitch(sec_row1, text="PvP", variable=self.var_pvp)
        self.chk_pvp.pack(side="left")

        sec_row2_sec = ctk.CTkFrame(sec_frame, fg_color="transparent")
        sec_row2_sec.pack(fill="x", pady=(0, 4))

        self.var_allow_flight = ctk.BooleanVar(value=self.wizard_data["allow_flight"])
        self.chk_allow_flight = ctk.CTkSwitch(sec_row2_sec, text="Allow Flight", variable=self.var_allow_flight)
        self.chk_allow_flight.pack(side="left", padx=(0, 20))

        self.var_enforce_secure_profile = ctk.BooleanVar(value=self.wizard_data["enforce_secure_profile"])
        self.chk_enforce_secure_profile = ctk.CTkSwitch(sec_row2_sec, text="Secure Profile", variable=self.var_enforce_secure_profile)
        self.chk_enforce_secure_profile.pack(side="left")

        sec_row2 = ctk.CTkFrame(p, fg_color="transparent")
        sec_row2.pack(fill="x", pady=(0, 10))

        ctk.CTkLabel(sec_row2, text="Max Players:", font=ctk.CTkFont(weight="bold")).pack(side="left", padx=(0, 10))
        self.entry_max_players = ctk.CTkEntry(sec_row2, width=60, corner_radius=AppConfig.RADIUS_BTN, height=32)
        self.entry_max_players.pack(side="left", padx=(0, 20))
        self.entry_max_players.insert(0, str(self.wizard_data["max_players"]))

        ctk.CTkLabel(sec_row2, text="Spawn Protection:", font=ctk.CTkFont(weight="bold")).pack(side="left", padx=(0, 10))
        self.entry_spawn_protection = ctk.CTkEntry(sec_row2, width=60, corner_radius=AppConfig.RADIUS_BTN, height=32)
        self.entry_spawn_protection.pack(side="left", padx=(0, 20))
        self.entry_spawn_protection.insert(0, str(self.wizard_data["spawn_protection"]))

        self.var_enable_command_block = ctk.BooleanVar(value=self.wizard_data["enable_command_block"])
        self.chk_enable_command_block = ctk.CTkSwitch(sec_row2, text="Command Blocks", variable=self.var_enable_command_block)
        self.chk_enable_command_block.pack(side="left")

    def show_step_5(self):
        self.clear_content()
        self.update_header("World & Network")

        scroll = ctk.CTkScrollableFrame(self.content_frame, fg_color="transparent")
        scroll.pack(fill="both", expand=True)
        p = scroll

        # Seed
        ctk.CTkLabel(p, text="Seed (Optional):", font=ctk.CTkFont(weight="bold")).pack(anchor="w", pady=(0, 5))
        self.entry_seed = ctk.CTkEntry(p, placeholder_text="Leave blank for random", corner_radius=AppConfig.RADIUS_BTN, height=36)
        self.entry_seed.pack(fill="x", pady=(0, 10))
        if self.wizard_data["seed"]:
            self.entry_seed.insert(0, self.wizard_data["seed"])

        # Playit.gg Port
        ctk.CTkLabel(p, text="Playit.gg Tunnel Port:", font=ctk.CTkFont(weight="bold")).pack(anchor="w", pady=(0, 5))
        self.entry_port = ctk.CTkEntry(p, placeholder_text="25565", corner_radius=AppConfig.RADIUS_BTN, height=36)
        self.entry_port.pack(fill="x", pady=(0, 10))
        if self.wizard_data.get("playit_port"):
            self.entry_port.insert(0, str(self.wizard_data["playit_port"]))

        # Distances (Sliders)
        dist_frame = ctk.CTkFrame(p, fg_color="transparent")
        dist_frame.pack(fill="x", pady=(0, 10))
        dist_frame.grid_columnconfigure(0, weight=1)

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
            self._collect_step3_fields()

        elif self.current_step == 4:
            self._collect_step4_fields()

        elif self.current_step == 5:
            self._collect_step5_fields()
            self.on_complete_callback(self.wizard_data)
            self.destroy()
            return

        self.current_step += 1
        self.show_step()

    def go_back(self):
        if self.current_step == 3:
            self._collect_step3_fields()
        elif self.current_step == 4:
            self._collect_step4_fields()
        elif self.current_step == 5:
            self._collect_step5_fields()

        self.current_step -= 1
        self.show_step()

    def _collect_step3_fields(self):
        if self.java_choice_var.get() == "detected" and self._detected_java:
            idx = self.java_detected_menu.cget("values").index(self.java_detected_menu.get())
            self.wizard_data["java_path"] = self._detected_java[idx].path
        else:
            self.wizard_data["java_path"] = "auto"

    def _collect_step4_fields(self):
        self.wizard_data["game_mode"] = self.combo_gamemode.get()
        self.wizard_data["difficulty"] = self.combo_difficulty.get()
        self.wizard_data["hardcore"] = self.var_hardcore.get()
        self.wizard_data["whitelist"] = self.var_whitelist.get()
        self.wizard_data["auto_install_jdk"] = self.var_auto_jdk.get()

        self.wizard_data["online_mode"] = self.var_online_mode.get()
        self.wizard_data["enforce_whitelist"] = self.var_enforce_whitelist.get()
        self.wizard_data["pvp"] = self.var_pvp.get()
        self.wizard_data["allow_flight"] = self.var_allow_flight.get()
        self.wizard_data["enforce_secure_profile"] = self.var_enforce_secure_profile.get()
        self.wizard_data["enable_command_block"] = self.var_enable_command_block.get()

        try:
            self.wizard_data["max_players"] = int(self.entry_max_players.get().strip())
        except ValueError:
            self.wizard_data["max_players"] = 20
        try:
            self.wizard_data["spawn_protection"] = int(self.entry_spawn_protection.get().strip())
        except ValueError:
            self.wizard_data["spawn_protection"] = 16

    def _collect_step5_fields(self):
        self.wizard_data["seed"] = self.entry_seed.get().strip()
        port_val = self.entry_port.get().strip()
        self.wizard_data["playit_port"] = port_val if port_val else "25565"

    def show_step(self):
        if self.current_step == 1: self.show_step_1()
        elif self.current_step == 2: self.show_step_2()
        elif self.current_step == 3: self.show_step_3()
        elif self.current_step == 4: self.show_step_4()
        elif self.current_step == 5: self.show_step_5()
