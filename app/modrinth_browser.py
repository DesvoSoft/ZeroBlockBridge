"""
Modrinth Mod Browser — Neo-Modern UI for ZeroBlockBridge.

Integrated as a tab within the main console area. Provides search,
version filtering, one-click install, and update checking for
Modrinth-hosted mods and plugins.
"""

import customtkinter as ctk
import logging
import os
import threading
from typing import Callable, Optional

from app.app_config import AppConfig
from app.constants import SERVERS_DIR
from app.services.mod_provider import ModProvider
from app.services.modrinth import ModrinthException

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Design tokens (extending AppConfig's Neo-Modern palette)
# ---------------------------------------------------------------------------
_MODRINTH_GREEN = "#1bd96a"
_MODRINTH_GREEN_HOVER = "#15b858"
_CARD_BG_LIGHT = "#f1f5f9"   # slate-100
_CARD_BG_DARK = "#1e293b"    # slate-800
_CARD_HOVER_LIGHT = "#e2e8f0"
_CARD_HOVER_DARK = "#334155"
_BADGE_BG_LIGHT = "#dbeafe"  # blue-100
_BADGE_BG_DARK = "#1e3a5f"
_BADGE_TEXT_LIGHT = "#1e40af" # blue-800
_BADGE_TEXT_DARK = "#93c5fd"  # blue-300
_SEPARATOR_LIGHT = "#e2e8f0"
_SEPARATOR_DARK = "#334155"
_DOWNLOADS_COLOR = "#94a3b8"  # slate-400


class ModrinthBrowser(ctk.CTkFrame):
    """
    Self-contained Modrinth browsing panel.

    Designed to be packed inside a CTkTabview tab. Handles its own
    threading for API calls — never blocks the UI thread.
    """

    def __init__(self, master, get_server_info: Callable = None, **kwargs):
        """
        Args:
            master: Parent widget (the tab frame).
            get_server_info: Callable returning (server_name, mc_version, loader)
                             for the currently selected server. If None, search
                             still works but install is disabled.
        """
        super().__init__(master, fg_color="transparent", **kwargs)
        self.get_server_info = get_server_info
        self.provider = ModProvider()
        self._current_hits = []
        self._search_thread = None

        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(1, weight=1)

        self._build_search_bar()
        self._build_results_area()
        self._build_status_bar()
        
        # Load popular mods on startup
        self.after(500, self._load_popular_mods)

    # ------------------------------------------------------------------
    # Layout: Search Bar
    # ------------------------------------------------------------------
    def _build_search_bar(self):
        bar = ctk.CTkFrame(self, corner_radius=12,
                           fg_color=(AppConfig.COLOR_BG_LIGHT, AppConfig.COLOR_BG_DARK))
        bar.grid(row=0, column=0, sticky="ew", padx=0, pady=(0, 8))
        bar.grid_columnconfigure(1, weight=1)

        # Modrinth icon label
        lbl_icon = ctk.CTkLabel(bar, text="🔍", font=("Roboto", 16))
        lbl_icon.grid(row=0, column=0, padx=(12, 4), pady=8)

        # Search entry
        self.entry_search = ctk.CTkEntry(
            bar,
            placeholder_text="Search Modrinth for mods, plugins, shaders…",
            corner_radius=8,
            height=36,
            font=AppConfig.FONT_BODY,
            border_width=0,
            fg_color=("gray95", "gray15"),
        )
        self.entry_search.grid(row=0, column=1, sticky="ew", padx=4, pady=8)
        self.entry_search.bind("<Return>", self._on_search)

        # Filter: Project type
        self.combo_type = ctk.CTkComboBox(
            bar,
            values=["mod", "plugin", "modpack", "resourcepack", "shader"],
            width=110, height=36, corner_radius=8,
            state="readonly", font=AppConfig.FONT_BODY_SMALL,
        )
        self.combo_type.set("mod")
        self.combo_type.grid(row=0, column=2, padx=4, pady=8)
        # Fix clickable anywhere
        self.combo_type._entry.bind("<Button-1>", lambda e: self.combo_type._open_dropdown_menu())
        self.combo_type._entry.configure(cursor="arrow")

        # Search button
        self.btn_search = ctk.CTkButton(
            bar, text="Search", width=90, height=36,
            corner_radius=8,
            fg_color=_MODRINTH_GREEN, hover_color=_MODRINTH_GREEN_HOVER,
            text_color="white", font=("Roboto Medium", 12),
            command=self._on_search,
        )
        self.btn_search.grid(row=0, column=3, padx=4, pady=8)

        # Optimizer button
        self.btn_opt = ctk.CTkButton(
            bar, text="⚡ Optimizers", width=100, height=36,
            corner_radius=8,
            fg_color="#3b82f6", hover_color="#2563eb",
            text_color="white", font=("Roboto Medium", 12),
            command=self._on_install_optimizers,
        )
        self.btn_opt.grid(row=0, column=4, padx=(4, 12), pady=8)

    # ------------------------------------------------------------------
    # Layout: Results Area (scrollable)
    # ------------------------------------------------------------------
    def _build_results_area(self):
        self.results_frame = ctk.CTkScrollableFrame(
            self, corner_radius=12,
            fg_color=("white", "gray14"),
            border_width=1,
            border_color=(AppConfig.COLOR_BORDER_LIGHT, AppConfig.COLOR_BORDER_DARK),
            label_text="",
        )
        self.results_frame.grid(row=1, column=0, sticky="nsew", padx=0, pady=0)
        self.results_frame.grid_columnconfigure(0, weight=1)

        # Placeholder
        self._show_placeholder("Search for mods on Modrinth to get started.\nResults will appear here.")

    def _show_placeholder(self, text: str):
        for w in self.results_frame.winfo_children():
            w.destroy()
        lbl = ctk.CTkLabel(
            self.results_frame, text=text,
            text_color=AppConfig.COLOR_TEXT_NOTE,
            font=AppConfig.FONT_BODY,
            justify="center",
        )
        lbl.grid(row=0, column=0, pady=60, padx=20)

    # ------------------------------------------------------------------
    # Layout: Status Bar
    # ------------------------------------------------------------------
    def _build_status_bar(self):
        self.status_bar = ctk.CTkFrame(self, height=28, corner_radius=8,
                                        fg_color=("gray95", "gray15"))
        self.status_bar.grid(row=2, column=0, sticky="ew", padx=0, pady=(6, 0))

        self.lbl_status = ctk.CTkLabel(
            self.status_bar, text="Ready",
            text_color=AppConfig.COLOR_TEXT_NOTE,
            font=AppConfig.FONT_BODY_SMALL,
        )
        self.lbl_status.pack(side="left", padx=12, pady=3)

        self.lbl_count = ctk.CTkLabel(
            self.status_bar, text="",
            text_color=AppConfig.COLOR_TEXT_NOTE,
            font=AppConfig.FONT_BODY_SMALL,
        )
        self.lbl_count.pack(side="right", padx=12, pady=3)

    # ------------------------------------------------------------------
    # Server Initialization Guard
    # ------------------------------------------------------------------
    def _is_server_initialized(self) -> bool:
        """Checks if the currently selected server has been started at least once."""
        if not self.get_server_info: return False
        try:
            info = self.get_server_info()
            if not info: return False
            server_name = info[0]
            jar_path = os.path.join(SERVERS_DIR, server_name, "server.jar")
            return os.path.exists(jar_path)
        except Exception:
            return False

    def _show_uninitialized_warning(self):
        self._show_placeholder("🔒 Server Not Initialized\n\nPlease start the server at least once\nto install the engine before exploring mods.")
        self._set_status("⚠ First boot required")

    # ------------------------------------------------------------------
    # Search logic
    # ------------------------------------------------------------------
    def _on_search(self, event=None):
        if not self._is_server_initialized():
            self._show_uninitialized_warning()
            return
            
        query = self.entry_search.get().strip()
        if not query:
            return

        project_type = self.combo_type.get()

        # Get server context for filtering
        mc_version = None
        loader = None
        if self.get_server_info:
            try:
                info = self.get_server_info()
                if info:
                    _, mc_version, loader = info
            except Exception:
                pass

        self._set_status("Searching…", busy=True)
        self.btn_search.configure(state="disabled")

        def _do_search(q, mv, ld):
            try:
                hits = self.provider.search_mods(
                    q,
                    mc_version=mv,
                    loader=ld,
                    limit=25,
                )
                
                # Fallback: if loader is vanilla and no results, try without loader or with fabric
                if not hits and ld == "vanilla":
                    hits = self.provider.search_mods(q, mc_version=mv, loader=None, limit=25)
                
                self._current_hits = hits
                total = len(hits)
                self.after(0, lambda: self._render_results(self._current_hits, total))
            except ModrinthException as exc:
                logger.error("Modrinth search failed: %s", exc)
                self.after(0, lambda: self._show_placeholder(f"Search failed:\n{exc}"))
            finally:
                self.after(0, lambda: self.btn_search.configure(state="normal"))
                self.after(0, lambda: self._set_status("Ready"))

        self._search_thread = threading.Thread(target=_do_search, args=(query, mc_version, loader), daemon=True)
        self._search_thread.start()

    def _load_popular_mods(self):
        """Fetch and show popular mods."""
        if not self._is_server_initialized():
            self._show_uninitialized_warning()
            return
            
        mc_version = None
        loader = None
        if self.get_server_info:
            try:
                info = self.get_server_info()
                if info: _, mc_version, loader = info
            except: pass

        self._set_status("Loading popular mods...", busy=True)
        
        def _do_load():
            try:
                # If vanilla, search popular without loader filter to show useful things
                search_loader = loader if loader != "vanilla" else None
                hits = self.provider.get_popular_mods(mc_version=mc_version, loader=search_loader)
                self.after(0, lambda: self._render_results(hits, len(hits)))
            except Exception as e:
                logger.error(f"Failed to load popular mods: {e}")
            finally:
                self.after(0, lambda: self._set_status("Ready"))
                
        threading.Thread(target=_do_load, daemon=True).start()

    def _set_status(self, text: str, busy: bool = False):
        self.lbl_status.configure(text=text)

    # ------------------------------------------------------------------
    # Render results
    # ------------------------------------------------------------------
    def _render_results(self, hits: list, total: int):
        for w in self.results_frame.winfo_children():
            w.destroy()

        if not hits:
            self._show_placeholder("No results found.\nTry a different search term.")
            self.lbl_count.configure(text="0 results")
            return

        self.lbl_count.configure(text=f"{len(hits)} of {total} results")

        for idx, hit in enumerate(hits):
            card = self._create_mod_card(hit, idx)
            card.grid(row=idx, column=0, sticky="ew", padx=6, pady=3)

    def _create_mod_card(self, hit: dict, index: int) -> ctk.CTkFrame:
        """Build a single mod result card — Neo-Modern style."""
        card = ctk.CTkFrame(
            self.results_frame,
            corner_radius=10,
            fg_color=(_CARD_BG_LIGHT, _CARD_BG_DARK),
            border_width=1,
            border_color=(_SEPARATOR_LIGHT, _SEPARATOR_DARK),
        )
        card.grid_columnconfigure(1, weight=1)

        # --- Icon placeholder (colored circle with initial) ---
        title = hit.get("title", "?")
        initial = title[0].upper() if title else "?"
        # Deterministic color from project slug
        colors = ["#3b82f6", "#8b5cf6", "#ec4899", "#f97316", "#14b8a6",
                  "#6366f1", "#06b6d4", "#84cc16", "#f43f5e", "#a855f7"]
        color = colors[hash(hit.get("slug", "")) % len(colors)]

        icon_frame = ctk.CTkFrame(card, width=48, height=48, corner_radius=10, fg_color=color)
        icon_frame.grid(row=0, column=0, rowspan=2, padx=(12, 8), pady=12, sticky="n")
        icon_frame.grid_propagate(False)
        lbl_initial = ctk.CTkLabel(icon_frame, text=initial, font=("Roboto Medium", 20),
                                   text_color="white")
        lbl_initial.place(relx=0.5, rely=0.5, anchor="center")

        # --- Info section ---
        info_frame = ctk.CTkFrame(card, fg_color="transparent")
        info_frame.grid(row=0, column=1, sticky="ew", padx=(0, 8), pady=(10, 0))
        info_frame.grid_columnconfigure(0, weight=1)

        # Title row
        title_row = ctk.CTkFrame(info_frame, fg_color="transparent")
        title_row.grid(row=0, column=0, sticky="ew")

        lbl_title = ctk.CTkLabel(title_row, text=title, font=("Roboto Medium", 14),
                                 anchor="w")
        lbl_title.pack(side="left")

        # Author
        author = hit.get("author", "Unknown")
        lbl_author = ctk.CTkLabel(title_row, text=f"by {author}",
                                  text_color=_DOWNLOADS_COLOR,
                                  font=AppConfig.FONT_BODY_SMALL, anchor="w")
        lbl_author.pack(side="left", padx=(8, 0))

        # Description
        desc = hit.get("description", "")[:120]
        lbl_desc = ctk.CTkLabel(info_frame, text=desc,
                                text_color=(AppConfig.COLOR_TEXT_GRAY, "#cbd5e1"),
                                font=AppConfig.FONT_BODY_SMALL,
                                anchor="w", wraplength=500, justify="left")
        lbl_desc.grid(row=1, column=0, sticky="ew", pady=(2, 0))

        # --- Badges row ---
        badge_frame = ctk.CTkFrame(card, fg_color="transparent")
        badge_frame.grid(row=1, column=1, sticky="ew", padx=(0, 8), pady=(2, 10))

        downloads = hit.get("downloads", 0)
        dl_text = self._format_downloads(downloads)
        lbl_dl = ctk.CTkLabel(badge_frame, text=f"⬇ {dl_text}",
                              text_color=_DOWNLOADS_COLOR,
                              font=AppConfig.FONT_BODY_SMALL)
        lbl_dl.pack(side="left", padx=(0, 10))

        # Category badges
        categories = hit.get("categories", [])[:3]
        for cat in categories:
            badge = ctk.CTkLabel(
                badge_frame, text=cat,
                font=("Roboto", 10),
                text_color=(_BADGE_TEXT_LIGHT, _BADGE_TEXT_DARK),
                fg_color=(_BADGE_BG_LIGHT, _BADGE_BG_DARK),
                corner_radius=6, padx=8, pady=2,
            )
            badge.pack(side="left", padx=(0, 4))

        # --- Install button ---
        btn_install = ctk.CTkButton(
            card, text="Install", width=80, height=32,
            corner_radius=8,
            fg_color=_MODRINTH_GREEN, hover_color=_MODRINTH_GREEN_HOVER,
            text_color="white", font=("Roboto Medium", 12),
            command=lambda h=hit: self._on_install(h),
        )
        btn_install.grid(row=0, column=2, rowspan=2, padx=(4, 12), pady=12, sticky="e")

        # Hover effect
        def _on_enter(e):
            card.configure(fg_color=(_CARD_HOVER_LIGHT, _CARD_HOVER_DARK))
        def _on_leave(e):
            card.configure(fg_color=(_CARD_BG_LIGHT, _CARD_BG_DARK))
        card.bind("<Enter>", _on_enter)
        card.bind("<Leave>", _on_leave)

        return card

    # ------------------------------------------------------------------
    # Install action
    # ------------------------------------------------------------------
    def _on_install(self, hit: dict):
        if not self._is_server_initialized():
            self._show_uninitialized_warning()
            return

        try:
            info = self.get_server_info()
            if not info:
                self._set_status("⚠ Select a server first.")
                return
            server_name, mc_version, loader = info
        except Exception:
            self._set_status("⚠ Could not determine server context.")
            return

        slug = hit.get("slug", hit.get("project_id", ""))
        title = hit.get("title", slug)

        self._set_status(f"Installing {title}…", busy=True)

        def _do_install():
            try:
                path = self.provider.download_mod(
                    slug, server_name, mc_version, loader,
                    progress_callback=lambda p: self.after(
                        0, lambda: self._set_status(f"Downloading {title}… {int(p * 100)}%")
                    ),
                )
                if path:
                    fname = os.path.basename(path)
                    self.after(0, lambda: self._set_status(f"✓ Installed {fname}"))
                    logger.info("Installed mod %s to %s", title, path)
                else:
                    self.after(0, lambda: self._set_status(f"✗ No compatible version of {title} found."))
            except Exception as exc:
                logger.error("Install failed for %s: %s", title, exc)
                self.after(0, lambda: self._set_status(f"✗ Install failed: {exc}"))

        threading.Thread(target=_do_install, daemon=True).start()

    def _on_install_optimizers(self):
        if not self._is_server_initialized():
            self._show_uninitialized_warning()
            return
            
        info = self.get_server_info()
        if not info:
            self._set_status("⚠ Select a server first.")
            return
        server_name, mc_version, loader = info
        
        self._set_status("Installing Optimizer Bundle...", busy=True)
        self.provider.install_optimizer_bundle(
            server_name, mc_version, loader,
            status_callback=lambda s: self.after(0, lambda: self._set_status(s))
        )

    # ------------------------------------------------------------------
    # Utilities
    # ------------------------------------------------------------------
    @staticmethod
    def _format_downloads(count: int) -> str:
        if count >= 1_000_000:
            return f"{count / 1_000_000:.1f}M"
        elif count >= 1_000:
            return f"{count / 1_000:.1f}K"
        return str(count)
