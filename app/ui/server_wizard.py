import customtkinter as ctk
import logging
import threading
import webbrowser
from app.api.areas import JavaApi, dropdown_labels
from app.api.creation import ContentImportError, CreationApi, WorldInfo
from app.core.app_config import AppConfig
from app.ui.ui_components import ZBBDialog, center_on_parent, dialog_header, ScrollableFrame, ZBBToplevel
from app.ui.win_effects import apply_rounded_corners
from app.ui.icons import icon
from PIL import Image

logger = logging.getLogger(__name__)

CURSEFORGE_WORLDS_URL = "https://www.curseforge.com/minecraft/worlds"

# Per-server imports: never saved into a template.
_CONTENT_KEYS = ("modpack_path", "modpack_label", "modpack_mc", "modpack_loader",
                 "loader_version", "world_path", "world_label", "world_mc", "world_snapshot")


def summary_value(value) -> str:
    """Display form of a wizard value on the Summary step (bools as Yes/No)."""
    if isinstance(value, bool):
        return "Yes" if value else "No"
    return str(value)


def java_summary(java_path: str, mc_version: str) -> str:
    """Summary text for the Java choice: a path, or what "auto" will fetch."""
    if java_path == "auto":
        return f"Auto (Java {JavaApi.required(mc_version)})"
    return java_path


def version_sort_key(v: str) -> tuple:
    """Numeric sort key for "1.20.1", "26.1", "1.21-pre1"..."""
    import re
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


# Engines that load mods (modpacks need one of these).
MODDED_ENGINES = ("Fabric", "Forge", "NeoForge")


def modpack_step_error(data: dict) -> str | None:
    """Why the Engine & Version choice can't run the imported modpack."""
    if not data.get("modpack_path"):
        return None
    engine, version = data.get("type"), data.get("version")
    loader, mc = data.get("modpack_loader"), data.get("modpack_mc")
    if engine not in MODDED_ENGINES:
        return "Modpacks need a Fabric, Forge or NeoForge server. Pick one below."
    if loader and engine != loader:
        return f"This modpack needs a {loader} server."
    if mc and version != mc:
        return f"This modpack needs Minecraft {mc}. Select {mc} below."
    return None


def world_step_error(mode: str, world_path: str | None, busy: bool,
                     version_check=None) -> str | None:
    """Why the World step can't continue with "Import existing world".
    `version_check` is content_import.world_version_check's result."""
    if mode != "import":
        return None
    if busy:
        return "Still reading the world, one moment..."
    if not world_path:
        return "Choose a world folder or .zip, or switch to New world."
    if version_check and version_check[0] == "error":
        return version_check[1]
    return None


def imported_world_check(wizard_data: dict):
    """world_version_check for the world chosen in the wizard, against the
    server version chosen in step 2."""
    if not wizard_data.get("world_path"):
        return None
    world = WorldInfo(path=wizard_data["world_path"], name=wizard_data.get("world_label", ""), is_zip=False,
                      root="", mc_version=wizard_data.get("world_mc"),
                      snapshot=bool(wizard_data.get("world_snapshot")))
    return CreationApi.world_version_check(world, wizard_data.get("version"))


def modpack_ram_mb(current: int, mod_count: int, system_mb: int) -> int:
    """RAM to suggest once a modpack is picked: modded servers need far more
    than the vanilla default. Never lowers a bigger choice, and leaves the
    system at least 2 GB."""
    wanted = 6144 if mod_count >= 100 else 4096
    return max(current, min(wanted, max(system_mb - 2048, 1024)))


class ServerWizard(ZBBToplevel):
    def __init__(self, parent, api, on_complete_callback):
        super().__init__(parent)
        self.title("Create New Server - Zero Block Bridge")
        self.geometry("650x650")
        center_on_parent(self, parent, 650, 650)
        self.resizable(True, True)
        self.minsize(650, 650)

        self.api = api
        self.creation = api.creation
        self.on_complete_callback = on_complete_callback
        self.current_step = 1
        self.total_steps = 6
        
        # Data storage
        self.wizard_data = {
            "name": "",
            "type": "Vanilla",
            "version": "",
            "ram": 2048,
            "seed": "",
            **self.creation.property_defaults(),
            "location": self.creation.default_location(),
            "icon_path": None,
            "auto_install_jdk": True,
            "java_path": "auto",
            "playit_port": "25565",
            "start_after_creation": False,
            # Imported content (see app.services.content_import)
            "modpack_path": None,
            "modpack_label": "",
            "modpack_mc": None,
            "modpack_loader": None,
            "loader_version": None,
            "world_path": None,
            "world_label": "",
            "world_mc": None,
            "world_snapshot": False,
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
        header, _, self.lbl_step = dialog_header(self.header_frame, "Create New Server", "")
        header.pack(fill="x", padx=20, pady=10)

        # Content Frame
        self.content_frame = ctk.CTkFrame(self, fg_color="transparent")
        self.content_frame.grid(row=1, column=0, sticky="nsew", padx=20, pady=20)

        # Footer
        self.footer_frame = ctk.CTkFrame(self, height=60, corner_radius=0,
                                         fg_color=(AppConfig.COLOR_BG_CARD_LIGHT, AppConfig.COLOR_BG_CARD_DARK))
        self.footer_frame.grid(row=2, column=0, sticky="ew")

        self.btn_back = ctk.CTkButton(
            self.footer_frame, text="Back", command=self.go_back, state="disabled",
            image=icon("chevron_left", 13, AppConfig.COLOR_TEXT_PRIMARY), compound="left",
            corner_radius=AppConfig.RADIUS_BTN, height=36,
            fg_color=AppConfig.COLOR_BTN_GHOST, text_color=AppConfig.COLOR_TEXT_PRIMARY, hover_color=AppConfig.COLOR_BTN_GHOST_HOVER,
        )
        self.btn_back.pack(side="left", padx=20, pady=12)

        self.btn_next = ctk.CTkButton(
            self.footer_frame, text="Next", command=self.go_next,
            image=icon("chevron_right", 13, AppConfig.COLOR_TEXT_ON_ACCENT), compound="right",
            corner_radius=AppConfig.RADIUS_BTN, height=36,
            fg_color=AppConfig.COLOR_BTN_PRIMARY, hover_color=AppConfig.COLOR_BTN_PRIMARY_HOVER,
        )
        self.btn_next.pack(side="right", padx=20, pady=12)

        self.btn_save_template = ctk.CTkButton(
            self.footer_frame, text="Save as Template", command=self._save_as_template,
            corner_radius=AppConfig.RADIUS_BTN, height=36,
            fg_color=AppConfig.COLOR_BTN_GHOST, text_color=AppConfig.COLOR_TEXT_PRIMARY, hover_color=AppConfig.COLOR_BTN_GHOST_HOVER,
        )
        # packed/unpacked per-step in _update_nav()

        self._versions_listener = self.creation.on_versions_refreshed(self.on_versions_refreshed)
        
        self.show_step_1()
        
        self.transient(parent)
        apply_rounded_corners(self)
        self.wait_visibility()
        self.grab_set()

    def destroy(self):
        listener = getattr(self, "_versions_listener", None)  # absent if __init__ failed early
        if listener is not None:
            listener.cancel()
        super().destroy()

    def update_header(self, title):
        self.lbl_step.configure(text=f"Step {self.current_step} of {self.total_steps} · {title}")
        
        if self.current_step == 1:
            self.btn_back.configure(state="disabled")
        else:
            self.btn_back.configure(state="normal")
            
        if self.current_step == self.total_steps:
            self.btn_next.configure(text="Create Server", image=icon("check", 13, AppConfig.COLOR_TEXT_ON_ACCENT),
                                    fg_color=AppConfig.COLOR_BTN_PRIMARY,
                                    hover_color=AppConfig.COLOR_BTN_PRIMARY_HOVER)
        else:
            self.btn_next.configure(text="Next", image=icon("chevron_right", 13, AppConfig.COLOR_TEXT_ON_ACCENT),
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
        if self.current_step == 2 and self.winfo_exists():
            self._render_versions()

    def _force_refresh_versions(self):
        self.btn_refresh.configure(state="disabled", text="...")
        threading.Thread(target=self._do_force_refresh, daemon=True).start()

    def _do_force_refresh(self):
        try:
            self.creation.refresh_versions()
        finally:
            self.after(0, lambda: self.btn_refresh.configure(state="normal", text="Refresh"))

    # --- Step 1: Identidad ---
    def show_step_1(self):
        self.clear_content()
        self.update_header("Server Identity")
        
        ctk.CTkLabel(self.content_frame, text="Server Name:", font=AppConfig.FONT_LABEL).pack(anchor="w", pady=(0, 5))
        self.entry_name = ctk.CTkEntry(self.content_frame, placeholder_text="my-awesome-server", corner_radius=AppConfig.RADIUS_BTN, height=36)
        self.entry_name.pack(fill="x", pady=(0, 15))
        if self.wizard_data["name"]:
            self.entry_name.insert(0, self.wizard_data["name"])
            
        ctk.CTkLabel(self.content_frame, text="Custom Location:", font=AppConfig.FONT_LABEL).pack(anchor="w", pady=(0, 5))
        loc_frame = ctk.CTkFrame(self.content_frame, fg_color="transparent")
        loc_frame.pack(fill="x", pady=(0, 15))
        
        self.entry_location = ctk.CTkEntry(loc_frame, corner_radius=AppConfig.RADIUS_BTN, height=36)
        self.entry_location.pack(side="left", fill="x", expand=True, padx=(0, 10))
        self.entry_location.insert(0, self.wizard_data["location"])
        
        btn_browse_loc = ctk.CTkButton(loc_frame, text="Browse...", command=self.browse_location,
                                        corner_radius=AppConfig.RADIUS_BTN, width=90, height=36,
                                        fg_color=AppConfig.COLOR_BTN_GHOST, text_color=AppConfig.COLOR_TEXT_PRIMARY, hover_color=AppConfig.COLOR_BTN_GHOST_HOVER)
        btn_browse_loc.pack(side="right")
            
        ctk.CTkLabel(self.content_frame, text="Server Icon (Optional):", font=AppConfig.FONT_LABEL).pack(anchor="w", pady=(0, 10))
        
        self.icon_preview = ctk.CTkLabel(self.content_frame, text="No Icon", width=100, height=100,
                                          fg_color=AppConfig.COLOR_BTN_GHOST, corner_radius=AppConfig.RADIUS_CARD)
        self.icon_preview.pack(pady=10)

        if self.wizard_data["icon_path"]:
            self._update_icon_preview(self.wizard_data["icon_path"])

        btn_browse = ctk.CTkButton(self.content_frame, text="Select Image...", command=self.browse_icon,
                                    corner_radius=AppConfig.RADIUS_BTN, height=32,
                                    fg_color=AppConfig.COLOR_BTN_GHOST, text_color=AppConfig.COLOR_TEXT_PRIMARY, hover_color=AppConfig.COLOR_BTN_GHOST_HOVER)
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

        self._build_modpack_card(p)

        # Start from template
        templates = self.creation.templates()
        if templates and not self.wizard_data["modpack_path"]:
            ctk.CTkLabel(p, text="Start from template (optional):", font=AppConfig.FONT_LABEL).pack(anchor="w", pady=(0, 5))
            template_row = ctk.CTkFrame(p, fg_color="transparent")
            template_row.pack(fill="x", pady=(0, 15))
            template_names = ["None"] + [t["name"] for t in templates]
            self.template_var = ctk.StringVar(value="None")
            template_menu = ctk.CTkOptionMenu(template_row, values=template_names, variable=self.template_var,
                                               command=self._on_template_selected, width=200)
            template_menu.pack(side="left")

        # Engine Selection
        ctk.CTkLabel(p, text="Server Engine:", font=AppConfig.FONT_LABEL).pack(anchor="w", pady=(0, 5))

        self.engine_var = ctk.StringVar(value=self.wizard_data["type"])
        engines = [("Vanilla", "Vanilla"), ("Paper", "Paper"), ("Purpur", "Purpur"), ("Fabric", "Fabric"),
                   ("Forge", "Forge"), ("NeoForge", "NeoForge")]

        # Six engines don't fit packed side by side at the wizard's 650px:
        # an even grid with compact radios keeps them on one row.
        engine_row = ctk.CTkFrame(p, fg_color="transparent")
        engine_row.pack(fill="x", pady=(0, 15))
        engine_row.grid_columnconfigure(tuple(range(len(engines))), weight=1, uniform="engines")

        self._engine_radios = []
        for column, (val, name) in enumerate(engines):
            rb = ctk.CTkRadioButton(engine_row, text=name, variable=self.engine_var, value=val, width=1,
                                    command=self._on_engine_change, font=AppConfig.FONT_BODY)
            rb.grid(row=0, column=column, sticky="w")
            self._engine_radios.append(rb)
        self._apply_modpack_lock()

        self.lbl_ram_hint = ctk.CTkLabel(p, text="", text_color=AppConfig.COLOR_TEXT_GRAY, font=AppConfig.FONT_CAPTION)
        self.lbl_ram_hint.pack(anchor="w", pady=(0, 5))
        self._update_ram_hint()

        # Version Search
        ctk.CTkLabel(p, text="Version:", font=AppConfig.FONT_LABEL).pack(anchor="w", pady=(0, 5))
        search_row = ctk.CTkFrame(p, fg_color="transparent")
        search_row.pack(fill="x", pady=(0, 10))
        self.entry_search = ctk.CTkEntry(search_row, placeholder_text="e.g. 1.20.1", corner_radius=AppConfig.RADIUS_BTN, height=36)
        self.entry_search.pack(side="left", fill="x", expand=True, padx=(0, 8))
        self.entry_search.bind("<KeyRelease>", lambda e: self._render_versions())
        self.btn_refresh = ctk.CTkButton(search_row, text="Refresh", image=icon("refresh", 13), width=100, height=36, corner_radius=AppConfig.RADIUS_BTN,
                                         fg_color=AppConfig.COLOR_BTN_GHOST, text_color=AppConfig.COLOR_TEXT_PRIMARY, hover_color=AppConfig.COLOR_BTN_GHOST_HOVER,
                                         command=self._force_refresh_versions)
        self.btn_refresh.pack(side="right")

        # Versions List
        if self.wizard_data["modpack_mc"]:
            self.entry_search.insert(0, self.wizard_data["modpack_mc"])
        self.scroll_versions = ScrollableFrame(p, corner_radius=AppConfig.RADIUS_CARD,
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

    # --- Imported content: modpack (step 2) and world (step 5) ---
    def _content_card(self, parent, title, hint):
        card = ctk.CTkFrame(parent, corner_radius=AppConfig.RADIUS_CARD,
                            fg_color=(AppConfig.COLOR_BG_CARD_LIGHT, AppConfig.COLOR_BG_CARD_DARK))
        card.pack(fill="x", pady=(0, 12))
        ctk.CTkLabel(card, text=title, font=AppConfig.FONT_LABEL, anchor="w").pack(fill="x", padx=12, pady=(10, 0))
        ctk.CTkLabel(card, text=hint, font=AppConfig.FONT_CAPTION, text_color=AppConfig.COLOR_TEXT_GRAY,
                     anchor="w", justify="left", wraplength=560).pack(fill="x", padx=12, pady=(2, 6))
        return card

    @staticmethod
    def _small_button(parent, text, command, primary=False, width=130):
        if primary:
            colors = dict(fg_color=AppConfig.COLOR_BTN_PRIMARY, hover_color=AppConfig.COLOR_BTN_PRIMARY_HOVER)
        else:
            colors = dict(fg_color=AppConfig.COLOR_BTN_GHOST, hover_color=AppConfig.COLOR_BTN_GHOST_HOVER,
                          text_color=AppConfig.COLOR_TEXT_PRIMARY)
        return ctk.CTkButton(parent, text=text, command=command, width=width, height=30,
                             corner_radius=AppConfig.RADIUS_BTN, **colors)

    def _build_modpack_card(self, parent):
        card = self._content_card(
            parent, "Modpack (optional)",
            "Import a Modrinth .mrpack or a modpack's Server Pack .zip. Engine and version are "
            "set for you. Rules you change in the next steps override the pack's; the rest keep its settings.")
        row = ctk.CTkFrame(card, fg_color="transparent")
        row.pack(fill="x", padx=12, pady=(0, 10))
        self.btn_modpack = self._small_button(row, "Import modpack...", self._browse_modpack,
                                              primary=True, width=150)
        self.btn_modpack.pack(side="left")
        if self.wizard_data["modpack_path"]:
            self._small_button(row, "Remove", self._clear_modpack, width=80).pack(side="right")
        self.lbl_modpack = ctk.CTkLabel(row, text="", font=AppConfig.FONT_CAPTION, anchor="w",
                                        justify="left", wraplength=340)
        self.lbl_modpack.pack(side="left", fill="x", expand=True, padx=(10, 0))
        if self._modpack_busy():
            self.btn_modpack.configure(state="disabled")
            self._set_modpack_status("Reading modpack...")
        elif self.wizard_data["modpack_path"]:
            self._set_modpack_status(self.wizard_data["modpack_label"])

    def _set_modpack_status(self, text, error=False):
        if hasattr(self, "lbl_modpack") and self.lbl_modpack.winfo_exists():
            self.lbl_modpack.configure(
                text=text, text_color=AppConfig.COLOR_STATUS_ERROR if error else AppConfig.COLOR_TEXT_PRIMARY)

    def _modpack_busy(self):
        return getattr(self, "_inspecting_modpack", False)

    def _browse_modpack(self):
        from tkinter import filedialog
        path = filedialog.askopenfilename(
            parent=self, title="Choose a modpack",
            filetypes=[("Modpacks", "*.mrpack *.zip"), ("Modrinth modpack", "*.mrpack"),
                       ("Server pack", "*.zip")])
        if not path:
            return
        # Sequence token: a slower earlier read (e.g. started before going
        # Back and choosing again) must never overwrite a newer choice.
        self._modpack_seq = getattr(self, "_modpack_seq", 0) + 1
        seq = self._modpack_seq
        self._inspecting_modpack = True
        self.btn_modpack.configure(state="disabled")
        self._set_modpack_status("Reading modpack...")

        def _work():
            try:
                info, error = self.creation.inspect_modpack(path), None
            except ContentImportError as e:
                info, error = None, str(e)
            except Exception as e:
                logger.exception("Modpack inspection failed")
                info, error = None, f"Couldn't read that modpack: {e}"
            self.after(0, lambda: self._on_modpack_inspected(info, error, seq))
        threading.Thread(target=_work, daemon=True).start()

    def _on_modpack_inspected(self, info, error, seq=None):
        if seq is not None and seq != getattr(self, "_modpack_seq", 0):
            return  # superseded by a newer choice
        self._inspecting_modpack = False
        if not self.winfo_exists():
            return
        on_step = self.current_step == 2
        if error:
            if not on_step:
                return
            self.btn_modpack.configure(state="normal")
            if self.wizard_data["modpack_path"]:
                # The earlier pack is still selected (and still locks engine/version).
                error += f"\nStill using: {self.wizard_data['modpack_label']}"
            self._set_modpack_status(error, error=True)
            return
        label = info.name + (f" ({info.describe()})" if info.describe() else "")
        self.wizard_data.update(
            modpack_path=info.path, modpack_label=label, modpack_mc=info.mc_version,
            modpack_loader=info.loader, loader_version=info.pinned_loader_version,
        )
        if info.loader:
            self.wizard_data["type"] = info.loader
        if info.mc_version:
            self.wizard_data["version"] = info.mc_version
        self.wizard_data["ram"] = modpack_ram_mb(
            self.wizard_data["ram"], info.mod_count, int(self.creation.system_ram_mb()))
        if not on_step:
            return  # kept in wizard_data; step 2 shows it when revisited
        self.show_step_2()  # re-render with engine/version locked
        if info.notes:
            self._set_modpack_status(label + "\n" + " ".join(info.notes))

    def _clear_modpack(self):
        self.wizard_data.update(modpack_path=None, modpack_label="", modpack_mc=None,
                                modpack_loader=None, loader_version=None)
        self.show_step_2()

    def _apply_modpack_lock(self):
        """Engine radios follow the modpack's loader and can't be changed."""
        loader = self.wizard_data["modpack_loader"]
        if not loader:
            return
        self.engine_var.set(loader)
        for rb in self._engine_radios:
            rb.configure(state="disabled")

    def _build_world_card(self, parent):
        card = self._content_card(
            parent, "World",
            "Start a new world, or bring one you already have: a world folder "
            "(e.g. from .minecraft/saves) or a .zip of it, like the ones you download from CurseForge.")
        self.var_world_mode = ctk.StringVar(value="import" if self.wizard_data["world_path"] else "new")
        body = ctk.CTkFrame(card, fg_color="transparent")
        body.pack(fill="x", padx=12, pady=(0, 10))

        self.rb_world_new = ctk.CTkRadioButton(body, text="New world", variable=self.var_world_mode, value="new",
                                               command=self._on_world_mode)
        self.rb_world_new.pack(anchor="w", pady=(0, 4))
        # Each option's details pack right after its own radio (never an
        # empty placeholder frame: a CTkFrame keeps its default height when
        # emptied, leaving a gap).
        self.world_new_frame = ctk.CTkFrame(body, fg_color="transparent")
        self.entry_seed = ctk.CTkEntry(self.world_new_frame, placeholder_text="Seed (optional, blank = random)",
                                       corner_radius=AppConfig.RADIUS_BTN, height=34)
        self.entry_seed.pack(fill="x", padx=(28, 0))
        if self.wizard_data["seed"]:
            self.entry_seed.insert(0, self.wizard_data["seed"])

        self.rb_world_import = ctk.CTkRadioButton(body, text="Import existing world", variable=self.var_world_mode,
                                                  value="import", command=self._on_world_mode)
        self.rb_world_import.pack(anchor="w", pady=(8, 4))
        self.world_import_frame = ctk.CTkFrame(body, fg_color="transparent")
        buttons = ctk.CTkFrame(self.world_import_frame, fg_color="transparent")
        buttons.pack(fill="x", padx=(28, 0))
        self._small_button(buttons, "Choose folder...", lambda: self._browse_world(folder=True),
                           primary=True).pack(side="left")
        self._small_button(buttons, "Choose .zip...", lambda: self._browse_world(folder=False)
                           ).pack(side="left", padx=(8, 0))
        # No CurseForge API here (it needs an approved key): open the site,
        # the user downloads a world .zip and picks it with "Choose .zip...".
        ctk.CTkButton(
            buttons, text="Browse worlds on CurseForge", image=icon("link", 12, AppConfig.COLOR_LINK),
            compound="left", command=lambda: webbrowser.open(CURSEFORGE_WORLDS_URL),
            fg_color="transparent", hover_color=AppConfig.COLOR_BTN_GHOST_HOVER, text_color=AppConfig.COLOR_LINK,
            height=30, width=10, corner_radius=AppConfig.RADIUS_BTN,
        ).pack(side="left", padx=(8, 0))
        self.lbl_world = ctk.CTkLabel(self.world_import_frame, text="", font=AppConfig.FONT_CAPTION,
                                      anchor="w", justify="left", wraplength=520)
        self.lbl_world.pack(fill="x", padx=(28, 0), pady=(6, 0))
        if getattr(self, "_inspecting_world", False):
            self.lbl_world.configure(text="Reading world...", text_color=AppConfig.COLOR_TEXT_GRAY)
        elif self.wizard_data["world_path"]:
            self._show_world(self.wizard_data["world_label"], self.wizard_data["world_path"])
        self._on_world_mode()

    def _on_world_mode(self):
        if self.var_world_mode.get() == "import":
            self.world_new_frame.pack_forget()
            self.world_import_frame.pack(fill="x", after=self.rb_world_import)
        else:
            self.world_import_frame.pack_forget()
            self.world_new_frame.pack(fill="x", after=self.rb_world_new)

    _CHECK_COLORS = {"error": AppConfig.COLOR_STATUS_ERROR, "warning": AppConfig.COLOR_ACCENT_AMBER}

    def _show_world(self, name, path):
        lines = [name, path]
        check = imported_world_check(self.wizard_data)
        color = AppConfig.COLOR_TEXT_PRIMARY
        if check:
            lines.append(check[1])
            color = self._CHECK_COLORS.get(check[0], color)
        self.lbl_world.configure(text="\n".join(lines), text_color=color)

    def _browse_world(self, folder):
        from tkinter import filedialog
        if folder:
            path = filedialog.askdirectory(parent=self, title="Choose the world folder")
        else:
            path = filedialog.askopenfilename(parent=self, title="Choose a world .zip",
                                              filetypes=[("World archive", "*.zip")])
        if not path:
            return
        self._world_seq = getattr(self, "_world_seq", 0) + 1
        seq = self._world_seq
        self._inspecting_world = True
        self.lbl_world.configure(text="Reading world...", text_color=AppConfig.COLOR_TEXT_GRAY)

        def _work():
            try:
                info, error = self.creation.inspect_world(path), None
            except ContentImportError as e:
                info, error = None, str(e)
            except Exception as e:
                logger.exception("World inspection failed")
                info, error = None, f"Couldn't read that world: {e}"
            self.after(0, lambda: self._on_world_inspected(info, error, seq))
        threading.Thread(target=_work, daemon=True).start()

    def _on_world_inspected(self, info, error, seq=None):
        if seq is not None and seq != getattr(self, "_world_seq", 0):
            return  # superseded by a newer choice
        self._inspecting_world = False
        if not self.winfo_exists():
            return
        if error:
            self.wizard_data.update(world_path=None, world_label="", world_mc=None, world_snapshot=False)
        else:
            self.wizard_data.update(world_path=info.path, world_label=info.name,
                                    world_mc=info.mc_version, world_snapshot=info.snapshot)
        if self.current_step != 5 or not self.lbl_world.winfo_exists():
            return  # kept in wizard_data; step 5 shows it when revisited
        if error:
            self.lbl_world.configure(text=error, text_color=AppConfig.COLOR_STATUS_ERROR)
        else:
            self._show_world(info.name, info.path)

    # --- Step 3: Resources (RAM + Java) ---
    def show_step_3(self):
        self.clear_content()
        self.update_header("Resources")

        p = self.content_frame

        # RAM Memory
        total_ram = self.creation.system_ram_mb()
        max_slider = min(16384, total_ram - 1024)
        min_ram = 512

        ram_label_frame = ctk.CTkFrame(p, fg_color="transparent")
        ram_label_frame.pack(fill="x", pady=(0, 5))

        ctk.CTkLabel(ram_label_frame, text="RAM:", font=AppConfig.FONT_LABEL).pack(side="left")
        self.lbl_ram_value = ctk.CTkLabel(ram_label_frame, text=f"{self.wizard_data['ram']} MB ({self.wizard_data['ram']//1024} GB)", font=AppConfig.FONT_BODY)
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
        ctk.CTkLabel(slider_range, text=f"{min_ram} MB", font=AppConfig.FONT_MICRO, text_color=AppConfig.COLOR_TEXT_GRAY).pack(side="left")
        self.lbl_ram_util = ctk.CTkLabel(slider_range, text="", font=AppConfig.FONT_MICRO, text_color=AppConfig.COLOR_TEXT_GRAY)
        self.lbl_ram_util.pack(side="right")

        self.lbl_ram_error = ctk.CTkLabel(p, text="", text_color=AppConfig.COLOR_STATUS_ERROR, font=AppConfig.FONT_CAPTION)
        self.lbl_ram_error.pack(anchor="w")
        self.update_ram_label(self.wizard_data["ram"])

        # --- Java Selection ---
        ctk.CTkLabel(p, text="Java:", font=AppConfig.FONT_LABEL).pack(anchor="w", pady=(20, 5))

        self.java_choice_var = ctk.StringVar(value="auto" if self.wizard_data.get("java_path", "auto") == "auto" else "detected")

        self.java_options_frame = ctk.CTkFrame(p, corner_radius=AppConfig.RADIUS_CARD,
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

        self.lbl_java_status = ctk.CTkLabel(p, text="Detecting Java...", font=AppConfig.FONT_CAPTION,
                                             text_color=AppConfig.COLOR_TEXT_GRAY, anchor="w")
        self.lbl_java_status.pack(fill="x", pady=(4, 0))

        self._update_java_check()

    def _save_as_template(self):
        self._collect_step5_fields()

        name = ZBBDialog.ask_string(
            self, "Save as Template", "Template name:",
            placeholder="my-template", confirm_text="Save",
        )
        if not name or not name.strip():
            return
        safe_name = self.creation.normalize_template_name(name)
        if safe_name is None:
            ZBBDialog.info(self, "Save as Template",
                           "Use letters, numbers, dashes, dots or underscores (up to 64), "
                           "starting with a letter or number.", kind="error")
            return
        if self.creation.template_exists(safe_name) and not ZBBDialog.confirm(
                self, "Save as Template",
                f"A template named \"{safe_name}\" already exists. Replace it?",
                confirm_text="Replace"):
            return
        try:
            self.creation.save_template(safe_name, {k: v for k, v in self.wizard_data.items() if k not in _CONTENT_KEYS})
        except OSError as e:
            ZBBDialog.info(self, "Save as Template", f"Couldn't save the template: {e}", kind="error")

    def _on_template_selected(self, template_name):
        if template_name == "None":
            return
        template = self.creation.load_template(template_name)
        if not template:
            return
        self.wizard_data.update({k: v for k, v in template.items() if not k.startswith("_")})
        self.engine_var.set(self.wizard_data["type"])
        self.version_var.set(self.wizard_data.get("version", ""))
        self._on_engine_change()

    def _update_ram_hint(self):
        engine = self.engine_var.get()
        hints = {"Vanilla": "512 MB min", "Paper": "1 GB min", "Purpur": "1 GB min", "Fabric": "1 GB min",
                 "Forge": "2 GB min", "NeoForge": "2 GB min"}
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
            installations = self.api.java.installations()
            required = self.api.java.required(version)

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
                labels = dropdown_labels(installations)
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
            required = self.api.java.required(self.version_var.get())
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
                total = self.creation.system_ram_mb()
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
        total = self.creation.system_ram_mb()
        pct = ram / total
        self.lbl_ram_util.configure(text=f"{pct*100:.0f}% of system RAM")

    def _render_versions(self):
        for widget in self.scroll_versions.winfo_children():
            widget.destroy()

        engine = self.engine_var.get()

        # Fetch happens in background — a fast search keystroke or engine
        # switch can spawn several overlapping fetches; sequence counter
        # discards a result if a newer call has started since (same pattern
        # as _update_java_check's _java_check_seq, same underlying hazard).
        self._version_render_seq = getattr(self, "_version_render_seq", 0) + 1
        seq = self._version_render_seq

        # Show loading indicator immediately — fetch happens in background
        loading_lbl = ctk.CTkLabel(self.scroll_versions, text="Loading versions...",
                                    text_color=AppConfig.COLOR_TEXT_GRAY)
        loading_lbl.pack(pady=20)
        self.scroll_versions.update_idletasks()

        def fetch_and_render():
            versions = sorted(self.creation.versions(engine), key=version_sort_key, reverse=True)
            search_q = self.entry_search.get().lower()
            filtered = [v for v in versions if search_q in v.lower()]

            def render_ui():
                if seq != self._version_render_seq or not self.winfo_exists():
                    return
                self._render_version_list(engine, filtered)

            self.after(0, render_ui)

        threading.Thread(target=fetch_and_render, daemon=True).start()

    def _render_version_list(self, engine, filtered):
        for widget in self.scroll_versions.winfo_children():
            widget.destroy()
        if not filtered:
            ctk.CTkLabel(self.scroll_versions, text="No versions found.",
                         text_color=AppConfig.COLOR_TEXT_GRAY).pack(pady=20)
            return
        locked = self.wizard_data["modpack_mc"]
        for v in filtered[:100]:
            rb = ctk.CTkRadioButton(self.scroll_versions, text=v, variable=self.version_var,
                                    value=v, command=self._update_java_check)
            if locked and v != locked:
                rb.configure(state="disabled")  # a modpack runs on one MC version only
            rb.pack(anchor="w", padx=10, pady=5)
        self._select_version(engine, filtered)
        self._update_java_check()

    def _select_version(self, engine, filtered):
        """Keep the chosen version when possible; each engine has its own list."""
        if self.wizard_data["modpack_mc"]:
            choice = self.wizard_data["modpack_mc"]
        elif self.wizard_data.get("_last_engine") != engine:
            choice = filtered[0]
        elif self.wizard_data["version"] in filtered:
            choice = self.wizard_data["version"]
        else:
            choice = filtered[0]
        self.wizard_data["_last_engine"] = engine
        self.wizard_data["version"] = choice
        self.version_var.set(choice)

    # --- Step 3: Rules & World ---
    def _scroll_body(self):
        # corner_radius=0: a rounded scrollable frame insets its content by the
        # radius, which shifted steps 4-6 right of steps 1-3.
        scroll = ScrollableFrame(self.content_frame, fg_color="transparent", corner_radius=0)
        scroll.pack(fill="both", expand=True)
        return scroll

    def show_step_4(self):
        self.clear_content()
        self.update_header("Rules & Security")

        scroll = self._scroll_body()
        p = scroll

        # Game Mode
        ctk.CTkLabel(p, text="Game Mode:", font=AppConfig.FONT_LABEL).pack(anchor="w", pady=(0, 5))
        self.combo_gamemode = ctk.CTkOptionMenu(p, values=["survival", "creative", "adventure", "spectator"], corner_radius=AppConfig.RADIUS_BTN, height=36)
        self.combo_gamemode.pack(fill="x", pady=(0, 10))
        self.combo_gamemode.set(self.wizard_data["game_mode"])
        
        # Difficulty
        ctk.CTkLabel(p, text="Difficulty:", font=AppConfig.FONT_LABEL).pack(anchor="w", pady=(0, 5))
        self.combo_difficulty = ctk.CTkOptionMenu(p, values=["peaceful", "easy", "normal", "hard"], corner_radius=AppConfig.RADIUS_BTN, height=36)
        self.combo_difficulty.pack(fill="x", pady=(0, 10))
        self.combo_difficulty.set(self.wizard_data["difficulty"])
        
        # Switches sit on a shared 3-column grid so every column lines up.
        def switch_grid(parent, items):
            grid = ctk.CTkFrame(parent, fg_color="transparent")
            grid.pack(fill="x", pady=(0, 10))
            grid.grid_columnconfigure((0, 1, 2), weight=1, uniform="switches")
            switches = []
            for n, (text, var) in enumerate(items):
                sw = ctk.CTkSwitch(grid, text=text, variable=var)
                sw.grid(row=n // 3, column=n % 3, sticky="w", pady=4)
                switches.append(sw)
            return switches

        self.var_hardcore = ctk.BooleanVar(value=self.wizard_data["hardcore"])
        self.var_whitelist = ctk.BooleanVar(value=self.wizard_data["whitelist"])
        self.var_auto_jdk = ctk.BooleanVar(value=self.wizard_data["auto_install_jdk"])
        self.chk_hardcore, self.chk_whitelist, self.chk_auto_jdk = switch_grid(p, [
            ("Hardcore", self.var_hardcore),
            ("White-list", self.var_whitelist),
            ("Auto-install JDK", self.var_auto_jdk),
        ])

        ctk.CTkLabel(p, text="Security:", font=AppConfig.FONT_LABEL).pack(anchor="w", pady=(0, 5))
        self.var_online_mode = ctk.BooleanVar(value=self.wizard_data["online_mode"])
        self.var_enforce_whitelist = ctk.BooleanVar(value=self.wizard_data["enforce_whitelist"])
        self.var_pvp = ctk.BooleanVar(value=self.wizard_data["pvp"])
        self.var_allow_flight = ctk.BooleanVar(value=self.wizard_data["allow_flight"])
        self.var_enforce_secure_profile = ctk.BooleanVar(value=self.wizard_data["enforce_secure_profile"])
        self.var_enable_command_block = ctk.BooleanVar(value=self.wizard_data["enable_command_block"])
        (self.chk_online_mode, self.chk_enforce_whitelist, self.chk_pvp,
         self.chk_allow_flight, self.chk_enforce_secure_profile, self.chk_enable_command_block) = switch_grid(p, [
            ("Online Mode", self.var_online_mode),
            ("Enforce Whitelist", self.var_enforce_whitelist),
            ("PvP", self.var_pvp),
            ("Allow Flight", self.var_allow_flight),
            ("Secure Profile", self.var_enforce_secure_profile),
            ("Command Blocks", self.var_enable_command_block),
        ])

        numbers = ctk.CTkFrame(p, fg_color="transparent")
        numbers.pack(fill="x", pady=(0, 10))
        numbers.grid_columnconfigure((0, 1), weight=1, uniform="numbers")
        ctk.CTkLabel(numbers, text="Max Players:", font=AppConfig.FONT_LABEL).grid(row=0, column=0, sticky="w", pady=(0, 5))
        ctk.CTkLabel(numbers, text="Spawn Protection:", font=AppConfig.FONT_LABEL).grid(
            row=0, column=1, sticky="w", padx=(10, 0), pady=(0, 5))
        self.entry_max_players = ctk.CTkEntry(numbers, corner_radius=AppConfig.RADIUS_BTN, height=36)
        self.entry_max_players.grid(row=1, column=0, sticky="ew", padx=(0, 10))
        self.entry_max_players.insert(0, str(self.wizard_data["max_players"]))
        self.entry_spawn_protection = ctk.CTkEntry(numbers, corner_radius=AppConfig.RADIUS_BTN, height=36)
        self.entry_spawn_protection.grid(row=1, column=1, sticky="ew", padx=(10, 0))
        self.entry_spawn_protection.insert(0, str(self.wizard_data["spawn_protection"]))

    def show_step_5(self):
        self.clear_content()
        self.update_header("World & Network")

        scroll = self._scroll_body()
        p = scroll

        self._build_world_card(p)

        # Playit.gg Port
        ctk.CTkLabel(p, text="Playit.gg Tunnel Port:", font=AppConfig.FONT_LABEL).pack(anchor="w", pady=(0, 5))
        self.entry_port = ctk.CTkEntry(p, placeholder_text="25565", corner_radius=AppConfig.RADIUS_BTN, height=36)
        self.entry_port.pack(fill="x", pady=(0, 10))
        if self.wizard_data.get("playit_port"):
            self.entry_port.insert(0, str(self.wizard_data["playit_port"]))

        # Distances (Sliders)
        dist_frame = ctk.CTkFrame(p, fg_color="transparent")
        dist_frame.pack(fill="x", pady=(0, 10))
        dist_frame.grid_columnconfigure(0, weight=1)

        # View Distance
        ctk.CTkLabel(dist_frame, text="View Distance:", font=AppConfig.FONT_LABEL).grid(row=0, column=0, sticky="w", pady=(0, 5))
        self.lbl_view_val = ctk.CTkLabel(dist_frame, text=str(self.wizard_data["view_distance"]), font=AppConfig.FONT_LABEL)
        self.lbl_view_val.grid(row=0, column=1, sticky="e", pady=(0, 5))

        self.slider_view = ctk.CTkSlider(dist_frame, from_=2, to=32, number_of_steps=30, command=self.update_view_label)
        self.slider_view.set(int(self.wizard_data["view_distance"]))
        self.slider_view.grid(row=1, column=0, columnspan=2, sticky="ew")

        # Simulation Distance
        ctk.CTkLabel(dist_frame, text="Simulation Distance:", font=AppConfig.FONT_LABEL).grid(row=2, column=0, sticky="w", pady=(10, 5))
        self.lbl_sim_val = ctk.CTkLabel(dist_frame, text=str(self.wizard_data["simulation_distance"]), font=AppConfig.FONT_LABEL)
        self.lbl_sim_val.grid(row=2, column=1, sticky="e", pady=(10, 5))

        self.slider_sim = ctk.CTkSlider(dist_frame, from_=2, to=32, number_of_steps=30, command=self.update_sim_label)
        self.slider_sim.set(int(self.wizard_data["simulation_distance"]))
        self.slider_sim.grid(row=3, column=0, columnspan=2, sticky="ew")

    def update_view_label(self, value):
        self.wizard_data["view_distance"] = str(int(value))
        self.lbl_view_val.configure(text=str(int(value)))

    def update_sim_label(self, value):
        self.wizard_data["simulation_distance"] = str(int(value))
        self.lbl_sim_val.configure(text=str(int(value)))

    # --- Step 6: Summary ---
    def show_step_6(self):
        self.clear_content()
        self.update_header("Summary")

        scroll = self._scroll_body()
        p = scroll

        d = self.wizard_data

        def section(title, rows):
            ctk.CTkLabel(p, text=title, font=AppConfig.FONT_LABEL).pack(anchor="w", pady=(10, 5))
            for label, value in rows:
                row = ctk.CTkFrame(p, fg_color="transparent")
                row.pack(fill="x", pady=1)
                ctk.CTkLabel(row, text=label, text_color=AppConfig.COLOR_TEXT_GRAY).pack(side="left")
                ctk.CTkLabel(row, text=summary_value(value)).pack(side="right")

        section("Identity", [
            ("Name", d["name"]),
            ("Location", d["location"]),
        ])
        section("Engine", [
            ("Type", d["type"]),
            ("Version", d["version"]),
        ])
        section("Resources", [
            ("RAM", f"{d['ram']} MB ({d['ram'] // 1024} GB)"),
            ("Java", java_summary(d["java_path"], d["version"])),
        ])
        section("Content", [
            ("Modpack", d["modpack_label"] or "None"),
            ("World", (f"{d['world_label']} (Minecraft {d['world_mc']})" if d.get("world_mc")
                       else d["world_label"]) or "New world"),
        ])
        section("Rules", [
            ("Game Mode", d["game_mode"]),
            ("Difficulty", d["difficulty"]),
            ("Hardcore", d["hardcore"]),
            ("Whitelist", d["whitelist"]),
            ("PvP", d["pvp"]),
            ("Max Players", d["max_players"]),
        ])
        section("World & Network", [
            ("Seed", "(imported world)" if d["world_path"] else (d["seed"] or "(random)")),
            ("Playit Port", d["playit_port"]),
            ("View Distance", d["view_distance"]),
            ("Simulation Distance", d["simulation_distance"]),
        ])

        self.var_start_after_creation = ctk.BooleanVar(value=d["start_after_creation"])
        ctk.CTkCheckBox(
            p, text="Start server after creation", variable=self.var_start_after_creation,
            corner_radius=AppConfig.RADIUS_BADGE,
        ).pack(anchor="w", pady=(15, 5))

    # --- Navigation ---
    def go_next(self):
        if self._leave_step(self.current_step) is False:
            return
        if self.current_step == self.total_steps:
            self.on_complete_callback(self.wizard_data)
            self.destroy()
            return
        self.current_step += 1
        self.show_step()

    def _leave_step(self, step):
        """Collect the step's fields; returns False to stay on the step."""
        return {
            1: self._leave_step_1,
            2: self._leave_step_2,
            3: self._collect_step3_fields,
            4: self._collect_step4_fields,
            5: self._leave_step_5,
            6: lambda: self.wizard_data.update(start_after_creation=self.var_start_after_creation.get()),
        }[step]()

    def _leave_step_1(self):
        name = self.entry_name.get().strip()
        if not name:
            self.entry_name.configure(border_color=AppConfig.COLOR_BTN_DANGER)
            return False
        self.wizard_data["name"] = name
        self.wizard_data["location"] = self.entry_location.get().strip()
        return True

    def _leave_step_2(self):
        if self._modpack_busy():
            return False
        self.wizard_data["type"] = self.engine_var.get()
        self.wizard_data["version"] = self.version_var.get()
        if not self.wizard_data["version"]:
            return False
        error = modpack_step_error(self.wizard_data)
        if error:
            self._set_modpack_status(error, error=True)
            return False
        return True

    def _leave_step_5(self):
        self._collect_step5_fields()
        check = imported_world_check(self.wizard_data)
        error = world_step_error(self.var_world_mode.get(), self.wizard_data["world_path"],
                                 getattr(self, "_inspecting_world", False), check)
        if error:
            if check and check[0] == "error":
                # Keep showing which world is selected; _show_world adds the red reason.
                self._show_world(self.wizard_data["world_label"], self.wizard_data["world_path"])
            else:
                self.lbl_world.configure(text=error, text_color=AppConfig.COLOR_STATUS_ERROR)
            return False
        return True

    def go_back(self):
        if self.current_step == 3:
            self._collect_step3_fields()
        elif self.current_step == 4:
            self._collect_step4_fields()
        elif self.current_step == 5:
            self._collect_step5_fields()
        elif self.current_step == 6:
            self.wizard_data["start_after_creation"] = self.var_start_after_creation.get()

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
        if self.var_world_mode.get() == "new":
            self.wizard_data.update(world_path=None, world_label="", world_mc=None, world_snapshot=False)
        self.wizard_data["seed"] = self.entry_seed.get().strip()
        port_val = self.entry_port.get().strip()
        self.wizard_data["playit_port"] = port_val if port_val else "25565"

    def show_step(self):
        if self.current_step == 1: self.show_step_1()
        elif self.current_step == 2: self.show_step_2()
        elif self.current_step == 3: self.show_step_3()
        elif self.current_step == 4: self.show_step_4()
        elif self.current_step == 5: self.show_step_5()
        elif self.current_step == 6: self.show_step_6()
