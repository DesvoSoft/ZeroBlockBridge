"""
Modrinth Mod Browser — Neo-Modern UI for ZeroBlockBridge.

Integrated as a tab within the main console area. Provides search,
version filtering, one-click install, update checking, installed mod
management, and .mrpack modpack import for Modrinth-hosted content.
"""

import customtkinter as ctk
import hashlib
import io
import logging
import os
import shutil
import tempfile
import threading
import tkinter.filedialog
from concurrent.futures import ThreadPoolExecutor
from typing import Callable, Optional

from PIL import Image

from app.core.app_config import AppConfig
from app.core.constants import SERVERS_DIR
from app.services.modrinth import ModrinthClient, ModrinthException
from app.services.mrpack_installer import install_mrpack, MrpackCompatibilityError
from app.services import mod_install_tracker
from app.core.logic import get_server_meta
from app.ui.ui_components import ToolTip, ZBBDialog
from app.ui.icons import icon

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Design tokens — Modrinth-specific (non-duplicates of AppConfig)
# ---------------------------------------------------------------------------
_MODRINTH_GREEN = "#1bd96a"
_MODRINTH_GREEN_HOVER = "#15b858"
_BADGE_BG_LIGHT, _BADGE_BG_DARK = AppConfig.COLOR_BADGE_BG
_BADGE_TEXT_LIGHT, _BADGE_TEXT_DARK = AppConfig.COLOR_BADGE_TEXT
_ICON_COLORS = ["#65a30d", "#d97706", "#16a34a", "#92400e", "#0d9488", "#ca8a04"]
_ICON_CACHE: dict[str, ctk.CTkImage] = {}
_ICONS_IN_FLIGHT: set[str] = set()
_ICONS_LOCK = threading.Lock()
_ICON_EXECUTOR = ThreadPoolExecutor(max_workers=4, thread_name_prefix="modrinth-icon")

_PAGE_SIZE = 20
_RENDER_BATCH_SIZE = 8


def _filter_updates_for_selection(updates: list, selected_filenames: set) -> list:
    """Return the subset of check_updates() results matching selected filenames."""
    return [u for u in updates if u.get("filename") in selected_filenames]


class ModrinthBrowser(ctk.CTkFrame):
    """
    Self-contained Modrinth browsing panel.

    Designed to be packed inside a CTkTabview tab. Handles its own
    threading for API calls — never blocks the UI thread.
    """

    OPTIMIZERS_FABRIC = [
        {"slug": "fabric-api", "name": "Fabric API", "description": "Required by Spark and most Fabric mods."},
        {"slug": "lithium", "name": "Lithium", "description": "General-purpose game code optimizer."},
        {"slug": "ferrite-core", "name": "FerriteCore", "description": "Memory usage optimization."},
        {"slug": "krypton", "name": "Krypton", "description": "Optimizes networking stack."},
        {"slug": "spark", "name": "Spark", "description": "Performance profiler for diagnosing lag."},
    ]

    OPTIMIZERS_FORGE = [
        {"slug": "modernfix", "name": "ModernFix", "description": "General performance/memory optimizer."},
        {"slug": "ferrite-core", "name": "FerriteCore", "description": "Memory usage optimization."},
        {"slug": "clumps", "name": "Clumps", "description": "Reduces lag from scattered XP orbs."},
        {"slug": "spark", "name": "Spark", "description": "Performance profiler for diagnosing lag."},
    ]

    _SORT_OPTIONS = {
        "Relevance": "relevance",
        "Downloads": "downloads",
        "Follows": "follows",
        "Newest": "newest",
        "Updated": "updated",
    }

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
        self.client = ModrinthClient()

        # Search state
        self._search_query = ""
        self._search_project_type = "mod"
        self._search_mc_version: Optional[str] = None
        self._search_loader: Optional[str] = None
        self._search_sort = "relevance"
        self._current_page = 0    # 0-based
        self._total_pages = 0
        self._search_total = 0
        self._current_hits: list = []
        self._spinner_job = None
        self._spinner_frame_idx = 0

        # View state: "search" or "installed"
        self._view = "search"

        # Bulk-selection state (F8)
        self._selected_files: set = set()      # installed view — absolute file paths
        self._selected_hits: dict = {}          # search view — slug/project_id -> hit dict
        self._installed_slugs_cache: set = set()  # search view — slugs already installed on target server

        # Render generation — invalidates stale chunked-render callbacks
        self._render_gen = 0

        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(1, weight=1)

        self._build_search_bar()
        self._build_results_area()
        self._build_pagination_bar()

        # Defer popular mods load until the tab is first shown
        self._popular_loaded = False
        self.bind("<Visibility>", self._on_first_shown)

    # ------------------------------------------------------------------
    # Server context helper (M.1)
    # ------------------------------------------------------------------
    def _resolve_server_context(self) -> Optional[tuple[str, str, str]]:
        """Return (server_name, mc_version, loader) or None."""
        if not self.get_server_info:
            return None
        try:
            info = self.get_server_info()
            if info:
                return info
        except Exception as exc:
            logger.debug("get_server_info failed: %s", exc)
        return None

    def _resolve_install_context(self) -> Optional[tuple[str, str, str]]:
        """Server context for install actions — blocks engines that can't load content."""
        ctx = self._resolve_server_context()
        if not ctx:
            self._set_status("⚠ Select a server first.")
            return None
        _, _, loader = ctx
        if loader is None:
            msg = ("Vanilla servers can't load mods or plugins.\n\n"
                   "Create a Fabric or Forge server for mods, "
                   "or Paper/Purpur for plugins.")
            self._set_status("✗ Vanilla servers can't load mods or plugins.")
            ZBBDialog.info(self.winfo_toplevel(), "Vanilla Server", msg)
            return None
        return ctx

    def refresh_server_context(self):
        """Update the context banner + type filter for the selected server."""
        ctx = self._resolve_server_context()
        if not ctx:
            self.lbl_context.configure(
                text="No server selected — select a server to install content.",
                text_color=AppConfig.COLOR_TEXT_NOTE,
            )
            self._apply_type_options(None)
            self._type_tooltip.text = "Select a server to enable all content types."
            self._opt_tooltip.text = (
                "Fabric: Fabric API, Lithium, FerriteCore, Krypton, Spark\n"
                "Forge: ModernFix, FerriteCore, Clumps, Spark"
            )
            return
        server_name, mc_version, loader = ctx
        engine = (loader or "vanilla").title()
        if loader is None:
            self.lbl_context.configure(
                text=f"⚠ {server_name} · Vanilla {mc_version} — vanilla can't load mods or plugins",
                text_color=AppConfig.COLOR_STATUS_STARTING,
            )
            self._type_tooltip.text = (
                "Vanilla servers can't load mods/plugins — "
                "use Fabric/Forge for mods or Paper/Purpur for plugins."
            )
            self._opt_tooltip.text = "Vanilla servers can't load the Optimizer Bundle."
        else:
            self.lbl_context.configure(
                text=f"Installing to: {server_name} · {engine} {mc_version}",
                text_color=AppConfig.COLOR_TEXT_GRAY,
            )
            self._type_tooltip.text = f"Content types filtered for {engine}."
            if loader == "fabric":
                self._opt_tooltip.text = "Fabric: Fabric API, Lithium, FerriteCore, Krypton, Spark"
            elif loader == "forge":
                self._opt_tooltip.text = "Forge: ModernFix, FerriteCore, Clumps, Spark"
            else:
                self._opt_tooltip.text = f"Optimizer Bundle isn't available for {engine}."
        self._apply_type_options(loader)

    def _apply_type_options(self, loader: Optional[str]):
        """Restrict the project-type filter to what the engine can actually load."""
        if loader in ("fabric", "forge"):
            values, default = ["mod", "modpack"], "mod"
        elif loader in ("paper", "purpur", "spigot"):
            values, default = ["plugin"], "plugin"
        else:
            values, default = ["mod", "plugin", "modpack", "resourcepack", "shader"], "mod"
        self.combo_type.configure(values=values)
        if self.combo_type.get() not in values:
            self.combo_type.set(default)

    # ------------------------------------------------------------------
    # Layout: Search Bar
    # ------------------------------------------------------------------
    def _build_search_bar(self):
        bar = ctk.CTkFrame(self, corner_radius=AppConfig.RADIUS_CARD,
                           fg_color=(AppConfig.COLOR_BG_LIGHT, AppConfig.COLOR_BG_DARK))
        bar.grid(row=0, column=0, sticky="ew", padx=0, pady=(0, 8))
        bar.grid_columnconfigure(1, weight=1)  # search entry soaks up leftover width

        lbl_icon = ctk.CTkLabel(bar, text="", image=icon("search", 15))
        lbl_icon.grid(row=0, column=0, padx=(12, 4), pady=6)

        self.entry_search = ctk.CTkEntry(
            bar,
            placeholder_text="Search mods, plugins, shaders…",
            corner_radius=10,
            height=28,
            width=220,
            font=AppConfig.FONT_BODY_SMALL,
            border_width=0,
            fg_color=(AppConfig.COLOR_BG_CARD_LIGHT, AppConfig.COLOR_BG_CARD_DARK),
        )
        self.entry_search.grid(row=0, column=1, sticky="ew", padx=4, pady=6)
        self.entry_search.bind("<Return>", self._on_search)

        _combo_style = dict(
            corner_radius=AppConfig.RADIUS_BTN, border_width=1,
            border_color=(AppConfig.COLOR_BORDER_LIGHT, AppConfig.COLOR_BORDER_DARK),
            fg_color=(AppConfig.COLOR_BG_CARD_LIGHT, AppConfig.COLOR_BG_CARD_DARK),
            text_color=(AppConfig.COLOR_BTN_GHOST, AppConfig.COLOR_TEXT_PRIMARY),
            button_color=_MODRINTH_GREEN, button_hover_color=_MODRINTH_GREEN_HOVER,
            dropdown_fg_color=(AppConfig.COLOR_BG_CARD_LIGHT, AppConfig.COLOR_BG_CARD_DARK),
            dropdown_text_color=(AppConfig.COLOR_BTN_GHOST, AppConfig.COLOR_TEXT_PRIMARY),
            dropdown_hover_color=_MODRINTH_GREEN,
            font=AppConfig.FONT_BODY_SMALL,
            state="readonly",
        )

        # Filter: Project type
        self.combo_type = ctk.CTkComboBox(
            bar,
            values=["mod", "plugin", "modpack", "resourcepack", "shader"],
            width=120, height=28,
            command=self._on_filter_changed,
            **_combo_style,
        )
        self.combo_type.set("mod")
        self.combo_type.grid(row=0, column=2, padx=4, pady=6)
        self.combo_type._entry.bind("<Button-1>", lambda e: self.combo_type._open_dropdown_menu())
        self.combo_type._entry.configure(cursor="arrow")
        self._type_tooltip = ToolTip(self.combo_type._entry, "Select a server to enable all content types.")

        # Sort dropdown (M.7)
        self.combo_sort = ctk.CTkComboBox(
            bar,
            values=list(self._SORT_OPTIONS.keys()),
            width=115, height=28,
            command=self._on_filter_changed,
            **_combo_style,
        )
        self.combo_sort.set("Relevance")
        self.combo_sort.grid(row=0, column=3, padx=4, pady=6)
        self.combo_sort._entry.bind("<Button-1>", lambda e: self.combo_sort._open_dropdown_menu())
        self.combo_sort._entry.configure(cursor="arrow")

        # Search button
        self.btn_search = ctk.CTkButton(
            bar, text="Search", width=80, height=28,
            corner_radius=10,
            fg_color=_MODRINTH_GREEN, hover_color=_MODRINTH_GREEN_HOVER,
            text_color="#0f172a", font=(AppConfig.FONT_FAMILY_DISPLAY, 12, "bold"),
            command=self._on_search,
        )
        self.btn_search.grid(row=0, column=4, padx=(4, 8), pady=6)

        # Installed toggle button (M.6) — most frequently used, same row as search
        self.btn_installed = ctk.CTkButton(
            bar, text="Installed", width=90, height=28,
            corner_radius=10,
            fg_color=AppConfig.COLOR_BTN_GHOST, hover_color=AppConfig.COLOR_BTN_GHOST_HOVER,
            text_color=("#0f172a", AppConfig.COLOR_TEXT_PRIMARY), font=(AppConfig.FONT_FAMILY_DISPLAY, 11, "bold"),
            command=self._toggle_installed_view,
        )
        self.btn_installed.grid(row=0, column=5, padx=(4, 16), pady=6)

        # Thin separator between search row and context/actions row
        separator = ctk.CTkFrame(
            bar, height=1, fg_color=(AppConfig.COLOR_BORDER_LIGHT, AppConfig.COLOR_BORDER_DARK),
        )
        separator.grid(row=1, column=0, columnspan=6, sticky="ew", padx=12, pady=(0, 0))

        # Row 2: server context + secondary action
        actions_row = ctk.CTkFrame(bar, fg_color="transparent")
        actions_row.grid(row=2, column=0, columnspan=6, sticky="ew", padx=12, pady=(1, 3))

        # Server context banner — which server/engine installs will target
        self.lbl_context = ctk.CTkLabel(
            actions_row, text="No server selected — select a server to install content.",
            font=AppConfig.FONT_BODY_SMALL, text_color=AppConfig.COLOR_TEXT_NOTE,
            anchor="w",
        )
        self.lbl_context.pack(side="left", fill="x", expand=True)

        # Optimizer bundle button
        self.btn_opt = ctk.CTkButton(
            actions_row, text="Optimizers", image=icon("bolt", 12, "#ffffff"), width=90, height=26,
            corner_radius=AppConfig.RADIUS_BTN,
            fg_color=AppConfig.COLOR_BTN_ACCENT_BLUE, hover_color=AppConfig.COLOR_BTN_ACCENT_BLUE_HOVER,
            text_color="white", font=(AppConfig.FONT_FAMILY_DISPLAY, 12, "bold"),
            command=self._on_install_optimizers,
        )
        self.btn_opt.pack(side="right", padx=(0, 4))
        self._opt_tooltip = ToolTip(
            self.btn_opt,
            "Fabric: Fabric API, Lithium, FerriteCore, Krypton, Spark\n"
            "Forge: ModernFix, FerriteCore, Clumps, Spark",
        )

    # ------------------------------------------------------------------
    # Layout: Results Area (scrollable)
    # ------------------------------------------------------------------
    def _build_results_area(self):
        results_container = ctk.CTkFrame(self, fg_color="transparent")
        results_container.grid(row=1, column=0, sticky="nsew", padx=0, pady=0)
        results_container.grid_columnconfigure(0, weight=1)
        results_container.grid_rowconfigure(1, weight=1)

        # Pinned action bar for the "Installed" view — sibling of the scrollable
        # frame so bulk-action buttons stay visible while the list scrolls.
        self.installed_action_bar = ctk.CTkFrame(results_container, fg_color="transparent")
        self.installed_action_bar.grid(row=0, column=0, sticky="ew", padx=8, pady=(0, 4))
        self.installed_action_bar.grid_remove()

        self.results_frame = ctk.CTkScrollableFrame(
            results_container, corner_radius=AppConfig.RADIUS_CARD,
            fg_color=(AppConfig.COLOR_BG_CARD_LIGHT, AppConfig.COLOR_BG_SIDEBAR_DARK),
            border_width=1,
            border_color=(AppConfig.COLOR_BORDER_LIGHT, AppConfig.COLOR_BORDER_DARK),
        )
        self.results_frame.grid(row=1, column=0, sticky="nsew", padx=0, pady=0)
        self.results_frame.grid_columnconfigure(0, weight=1)

        self._show_placeholder("Search for mods on Modrinth to get started.\nResults will appear here.")

    _SPINNER_FRAMES = ["⠋", "⠙", "⠹", "⠸", "⠼", "⠴", "⠦", "⠧", "⠇", "⠏"]

    def _show_placeholder(self, text: str, spinner: bool = False):
        self._stop_spinner()
        for w in self.results_frame.winfo_children():
            w.destroy()
        lbl = ctk.CTkLabel(
            self.results_frame, text=text,
            text_color=AppConfig.COLOR_TEXT_NOTE,
            font=AppConfig.FONT_BODY,
            justify="center",
        )
        lbl.grid(row=0, column=0, pady=60, padx=20)
        if spinner:
            self._animate_spinner(lbl, text)

    def _animate_spinner(self, lbl, base_text: str):
        if not lbl.winfo_exists():
            return
        frame = self._SPINNER_FRAMES[self._spinner_frame_idx % len(self._SPINNER_FRAMES)]
        self._spinner_frame_idx += 1
        lbl.configure(text=f"{frame} {base_text}")
        self._spinner_job = self.after(80, lambda: self._animate_spinner(lbl, base_text))

    def _show_retry_ui(self):
        self._stop_spinner()
        for w in self.results_frame.winfo_children():
            w.destroy()
        ctk.CTkLabel(
            self.results_frame, text="Could not load mods — check your internet connection.",
            text_color=AppConfig.COLOR_STATUS_ERROR,
            font=AppConfig.FONT_BODY, justify="center",
        ).grid(row=0, column=0, pady=(60, 8), padx=20)
        btn = ctk.CTkButton(
            self.results_frame, text="Retry",
            fg_color=AppConfig.COLOR_BTN_PRIMARY,
            hover_color=AppConfig.COLOR_BTN_PRIMARY_HOVER,
            corner_radius=AppConfig.RADIUS_BTN, height=32,
            text_color="white",
            font=(AppConfig.FONT_FAMILY_DISPLAY, 12, "bold"),
            command=self._load_popular_mods,
        )
        btn.grid(row=1, column=0)

    def _stop_spinner(self):
        if self._spinner_job is not None:
            self.after_cancel(self._spinner_job)
            self._spinner_job = None
        self._spinner_frame_idx = 0

    # ------------------------------------------------------------------
    # Layout: Pagination bar (classic Prev/Next)
    # ------------------------------------------------------------------
    def _build_pagination_bar(self):
        # Single persistent footer: status/count always visible, pagination
        # controls show/hide inline as an inner group (no separate status row).
        self.pagination_bar = ctk.CTkFrame(self, height=30, corner_radius=AppConfig.RADIUS_CARD,
                                            fg_color=(AppConfig.COLOR_BG_LIGHT, AppConfig.COLOR_BG_DARK))
        self.pagination_bar.grid(row=2, column=0, sticky="ew", padx=0, pady=(4, 0))

        self._pagination_controls = ctk.CTkFrame(self.pagination_bar, fg_color="transparent")
        self._pagination_controls.pack(side="left", padx=(12, 0), pady=2)

        self.btn_prev = ctk.CTkButton(
            self._pagination_controls, text="Prev", image=icon("chevron_left", 12), width=84, height=28,
            corner_radius=8,
            fg_color=AppConfig.COLOR_BTN_PRIMARY, hover_color=AppConfig.COLOR_BTN_PRIMARY_HOVER,
            text_color="white",
            font=(AppConfig.FONT_FAMILY_DISPLAY, 12, "bold"),
            command=self._on_prev_page,
            state="disabled",
        )
        self.btn_prev.pack(side="left", padx=(0, 6))

        self.lbl_page = ctk.CTkLabel(
            self._pagination_controls, text="",
            font=(AppConfig.FONT_FAMILY_DISPLAY, 13, "bold"),
            text_color=(AppConfig.COLOR_TEXT_PRIMARY, AppConfig.COLOR_TEXT_GRAY),
        )
        self.lbl_page.pack(side="left", padx=8)

        self.btn_next = ctk.CTkButton(
            self._pagination_controls, text="Next", image=icon("chevron_right", 12), compound="right", width=84, height=28,
            corner_radius=8,
            fg_color=AppConfig.COLOR_BTN_PRIMARY, hover_color=AppConfig.COLOR_BTN_PRIMARY_HOVER,
            text_color="white",
            font=(AppConfig.FONT_FAMILY_DISPLAY, 12, "bold"),
            command=self._on_next_page,
            state="disabled",
        )
        self.btn_next.pack(side="left", padx=(6, 0))


        self.btn_install_selected = ctk.CTkButton(
            self.pagination_bar, text="Install Selected (0)", width=150, height=26,
            corner_radius=8,
            fg_color=_MODRINTH_GREEN, hover_color=_MODRINTH_GREEN_HOVER,
            text_color="#0f172a", font=(AppConfig.FONT_FAMILY_DISPLAY, 12, "bold"), state="disabled",
            command=self._on_install_selected,
        )
        self.btn_install_selected.pack(side="right", padx=(4, 8), pady=4)

        self._pagination_controls.pack_forget()  # hidden until first search

    # ------------------------------------------------------------------
    # Search logic
    # ------------------------------------------------------------------
    def _do_search(self):
        """Fetch _current_page of results and render."""
        self.btn_search.configure(state="disabled")
        self.btn_prev.configure(state="disabled")
        self.btn_next.configure(state="disabled")
        self._show_placeholder("Loading mods", spinner=True)
        offset = self._current_page * _PAGE_SIZE
        sort = self._search_sort

        def _search():
            try:
                results = self.client.search(
                    self._search_query,
                    mc_version=self._search_mc_version,
                    loader=self._search_loader,
                    project_type=self._search_project_type,
                    limit=_PAGE_SIZE,
                    offset=offset,
                    index=sort,
                )
                hits = results.get("hits", [])
                total = results.get("total_hits", len(hits))
                self.after(0, lambda: self._on_search_done(hits, total))
            except ModrinthException as exc:
                logger.error("Modrinth search failed: %s", exc)
                msg = f"Search failed:\n{exc}"
                self.after(0, lambda m=msg: self._show_placeholder(m))
            finally:
                self.after(0, lambda: self.btn_search.configure(state="normal"))

        threading.Thread(target=_search, daemon=True).start()

    _ICON_PREFETCH_TIMEOUT = 2.0  # seconds — don't block the page on slow/broken icons

    def _on_search_done(self, hits: list, total: int):
        self._current_hits = hits
        self._search_total = total
        self._total_pages = max(1, (total + _PAGE_SIZE - 1) // _PAGE_SIZE)
        self._selected_hits.clear()
        self._update_install_selected_bar()

        self._render_gen += 1
        gen = self._render_gen
        if not hits:
            self._render_results()
            self._update_pagination()
            return
        self._prefetch_page_icons(hits, gen)

    def _prefetch_page_icons(self, hits: list, gen: int):
        urls = {h.get("icon_url") for h in hits if h.get("icon_url") and h["icon_url"] not in _ICON_CACHE}

        def _wait_and_render():
            if urls:
                futures = [_ICON_EXECUTOR.submit(self._prefetch_icon, u) for u in urls]
                for fut in futures:
                    try:
                        fut.result(timeout=self._ICON_PREFETCH_TIMEOUT)
                    except Exception:
                        # Slow/broken icon must not block the page render;
                        # the card falls back to its initial-letter badge.
                        pass
            if gen == self._render_gen and self.winfo_exists():
                self.after(0, self._render_results)

        threading.Thread(target=_wait_and_render, daemon=True).start()

    def _prefetch_icon(self, icon_url: str):
        if icon_url in _ICON_CACHE:
            return
        with _ICONS_LOCK:
            if icon_url in _ICONS_IN_FLIGHT:
                return
            _ICONS_IN_FLIGHT.add(icon_url)
        try:
            resp = self.client.session.get(icon_url, timeout=self._ICON_PREFETCH_TIMEOUT)
            resp.raise_for_status()
            img = Image.open(io.BytesIO(resp.content)).resize((48, 48), Image.LANCZOS)
            _ICON_CACHE[icon_url] = ctk.CTkImage(img, size=(48, 48))
        except Exception as exc:
            logger.debug("Icon prefetch error: %s", exc)
        finally:
            with _ICONS_LOCK:
                _ICONS_IN_FLIGHT.discard(icon_url)

    def _on_search(self, event=None):
        self._run_search()

    def _on_filter_changed(self, _choice=None):
        """Sort/type dropdown changed — re-run search immediately, even with an empty query (browse mode)."""
        self._run_search()

    def _run_search(self):
        query = self.entry_search.get().strip()
        project_type = self.combo_type.get()
        sort_label = self.combo_sort.get()
        sort = self._SORT_OPTIONS.get(sort_label, "relevance")

        mc_version = None
        loader = None
        ctx = self._resolve_server_context()
        if ctx:
            _, mc_version, loader = ctx

        self._search_query = query
        self._search_project_type = project_type
        self._search_mc_version = mc_version
        self._search_loader = loader
        self._search_sort = sort
        self._current_page = 0

        if self._view == "installed":
            self._toggle_installed_view()  # switch back to search view

        self._do_search()

    def _on_prev_page(self):
        if self._current_page > 0:
            self._current_page -= 1
            self._do_search()

    def _on_next_page(self):
        if self._current_page < self._total_pages - 1:
            self._current_page += 1
            self._do_search()

    def _update_pagination(self):
        if self._search_total == 0:
            self._pagination_controls.pack_forget()
            return

        self._pagination_controls.pack(side="left", padx=(12, 0), pady=2)
        page_num = self._current_page + 1
        self.lbl_page.configure(text=f"Page {page_num} of {self._total_pages}")
        _ghost = (AppConfig.COLOR_BG_SIDEBAR_LIGHT, AppConfig.COLOR_BTN_GHOST)
        prev_ok = self._current_page > 0
        next_ok = self._current_page < self._total_pages - 1
        self.btn_prev.configure(state="normal" if prev_ok else "disabled",
                                fg_color=AppConfig.COLOR_BTN_PRIMARY if prev_ok else _ghost)
        self.btn_next.configure(state="normal" if next_ok else "disabled",
                                fg_color=AppConfig.COLOR_BTN_PRIMARY if next_ok else _ghost)

    def _on_first_shown(self, event=None):
        self.refresh_server_context()
        if not self._popular_loaded:
            self._popular_loaded = True
            self.after(50, self._load_popular_mods)

    def _load_popular_mods(self):
        mc_version = None
        loader = None
        ctx = self._resolve_server_context()
        if ctx:
            _, mc_version, loader = ctx

        self._show_placeholder("Loading mods", spinner=True)
        self._search_query = ""
        self._search_project_type = "mod"
        self._search_mc_version = mc_version
        self._search_loader = loader
        self._search_sort = "downloads"
        self._current_page = 0

        def _do_load():
            try:
                results = self.client.search(
                    "", mc_version=mc_version, loader=loader,
                    project_type="mod", limit=_PAGE_SIZE, index="downloads",
                )
                hits = results.get("hits", [])
                total = results.get("total_hits", len(hits))
                self.after(0, lambda: self._on_search_done(hits, total))
            except Exception as exc:
                logger.error("Failed to load popular mods: %s", exc)
                self.after(0, self._show_retry_ui)

        threading.Thread(target=_do_load, daemon=True).start()

    def _set_status(self, text: str, busy: bool = False):
        pass

    def _on_toggle_hit_selection(self, key: str, hit: dict, var, card=None):
        selected = var.get()
        if selected:
            self._selected_hits[key] = hit
        else:
            self._selected_hits.pop(key, None)
        if card is not None:
            card.configure(
                border_width=2 if selected else 0,
                border_color=_MODRINTH_GREEN,
            )
        self._update_install_selected_bar()

    def _update_install_selected_bar(self):
        n = len(self._selected_hits)
        if hasattr(self, "btn_install_selected"):
            self.btn_install_selected.configure(
                text=f"Install Selected ({n})", state="normal" if n else "disabled",
                fg_color=_MODRINTH_GREEN if n else (AppConfig.COLOR_BG_SIDEBAR_LIGHT, AppConfig.COLOR_BTN_GHOST),
                text_color="#0f172a" if n else ("#0f172a", AppConfig.COLOR_TEXT_PRIMARY))

    def _on_install_selected(self):
        hits = list(self._selected_hits.values())
        if not hits:
            return
        ctx = self._resolve_install_context()
        if not ctx:
            return

        if len(hits) > 1 and not ZBBDialog.confirm(
            self.winfo_toplevel(), "Confirm Install",
            f"Install {len(hits)} mods/modpacks?", confirm_text="Install"
        ):
            return

        self._selected_hits.clear()
        self._update_install_selected_bar()
        self._set_status(f"Queuing {len(hits)} install(s)…")

        batch = {"done": 0, "failed": 0, "total": len(hits)}
        for hit in hits:
            if hit.get("project_type") == "modpack":
                self._on_install_modpack(hit, batch=batch)
            else:
                self._on_install(hit, batch=batch)

    def _note_batch_result(self, batch: dict, ok: bool):
        if batch is None:
            return
        batch["done"] += 1
        if not ok:
            batch["failed"] += 1
        total, done = batch["total"], batch["done"]
        if done >= total:
            failed = batch["failed"]
            if failed:
                self._set_status(f"✓ Installed {total - failed}/{total} ({failed} failed)")
            else:
                self._set_status(f"✓ Installed {total}/{total}")
        else:
            self._set_status(f"Installing… {done}/{total}", busy=True)

    # ------------------------------------------------------------------
    # Render results
    # ------------------------------------------------------------------
    def _render_results(self):
        if self._view != "search":
            # Async search response landed while the Installed view is open —
            # keep the hits (restored on toggle back) but don't clobber the UI.
            return
        self._stop_spinner()
        for w in self.results_frame.winfo_children():
            w.destroy()
        self.results_frame._parent_canvas.yview_moveto(0)

        self._render_gen += 1
        gen = self._render_gen

        if not self._current_hits:
            self._show_placeholder("No results found.\nTry a different search term.")
            return

        ctx = self._resolve_server_context()
        self._installed_slugs_cache = (
            mod_install_tracker.get_installed_slugs(ctx[0]) if ctx else set()
        )
        self._render_cards_batch(list(enumerate(self._current_hits)), gen)

    def _render_cards_batch(self, remaining: list, gen: int):
        if gen != self._render_gen or not self.winfo_exists():
            return
        chunk, rest = remaining[:_RENDER_BATCH_SIZE], remaining[_RENDER_BATCH_SIZE:]
        for idx, hit in chunk:
            card = self._create_mod_card(hit)
            card.grid(row=idx, column=0, sticky="ew", padx=6, pady=3)
        if rest:
            self.after(1, lambda: self._render_cards_batch(rest, gen))
        else:
            self._update_pagination()

    def _create_mod_card(self, hit: dict) -> ctk.CTkFrame:
        title = hit.get("title", "Unknown")
        initial = title[0].upper() if title else "?"
        icon_url = hit.get("icon_url", "")
        color = _ICON_COLORS[int(hashlib.md5(title.encode()).hexdigest(), 16) % len(_ICON_COLORS)]

        hit_key = hit.get("slug") or hit.get("project_id", "")
        is_selected = hit_key in self._selected_hits

        card = ctk.CTkFrame(
            self.results_frame,
            corner_radius=AppConfig.RADIUS_CARD,
            fg_color=(AppConfig.COLOR_BG_CARD_LIGHT, AppConfig.COLOR_BG_CARD_DARK),
            border_width=2 if is_selected else 0,
            border_color=_MODRINTH_GREEN,
        )
        card.grid_columnconfigure(2, weight=1)
        card.grid_rowconfigure(0, weight=1)
        card.grid_rowconfigure(1, weight=1)

        client_only = hit.get("server_side") == "unsupported" and hit.get("project_type") != "modpack"
        select_var = ctk.BooleanVar(value=is_selected)
        chk = ctk.CTkCheckBox(
            card, text="", width=28, height=28,
            checkbox_width=24, checkbox_height=24,
            corner_radius=6, border_width=2,
            fg_color=_MODRINTH_GREEN, hover_color=_MODRINTH_GREEN_HOVER,
            border_color=(AppConfig.COLOR_BORDER_LIGHT, AppConfig.COLOR_BORDER_DARK),
            variable=select_var,
            state="disabled" if client_only else "normal",
            command=lambda h=hit, k=hit_key, v=select_var, c=card: self._on_toggle_hit_selection(k, h, v, c),
        )
        chk.grid(row=0, column=0, rowspan=2, padx=(12, 4), pady=12, sticky="ns")

        icon_frame = ctk.CTkFrame(card, width=48, height=48, corner_radius=AppConfig.RADIUS_CARD, fg_color=color)
        icon_frame.grid(row=0, column=1, rowspan=2, padx=(0, 8), pady=12)
        icon_frame.grid_propagate(False)
        lbl_initial = ctk.CTkLabel(icon_frame, text=initial, font=(AppConfig.FONT_FAMILY_DISPLAY, 20, "bold"),
                                   text_color="white")
        lbl_initial.place(relx=0.5, rely=0.5, anchor="center")

        if icon_url:
            if icon_url in _ICON_CACHE:
                self._apply_icon(icon_frame, lbl_initial, _ICON_CACHE[icon_url])
            else:
                self._queue_icon_fetch(icon_url, icon_frame, lbl_initial)

        # Info section
        info_frame = ctk.CTkFrame(card, fg_color="transparent")
        info_frame.grid(row=0, column=2, sticky="ew", padx=(0, 8), pady=(10, 0))
        info_frame.grid_columnconfigure(0, weight=1)

        author = hit.get("author", "Unknown")
        lbl_title = ctk.CTkLabel(
            info_frame, text=f"{title}  ·  by {author}",
            font=(AppConfig.FONT_FAMILY_DISPLAY, 14, "bold"), anchor="w",
        )
        lbl_title.grid(row=0, column=0, sticky="ew")

        desc = hit.get("description", "")
        if len(desc) > 160:
            desc = desc[:160].rsplit(" ", 1)[0] + "…"
        lbl_desc = ctk.CTkLabel(info_frame, text=desc,
                                text_color=(AppConfig.COLOR_TEXT_GRAY, "#cbd5e1"),
                                font=AppConfig.FONT_BODY_SMALL,
                                anchor="w", wraplength=500, justify="left")
        lbl_desc.grid(row=1, column=0, sticky="ew", pady=(2, 0))
        # Wrap follows the actual column width instead of a fixed 500px
        info_frame.bind(
            "<Configure>",
            lambda e, lbl=lbl_desc: lbl.configure(wraplength=max(280, e.width - 16)),
        )

        # Badges row
        badge_frame = ctk.CTkFrame(card, fg_color="transparent")
        badge_frame.grid(row=1, column=2, sticky="ew", padx=(0, 8), pady=(2, 10))

        downloads = hit.get("downloads", 0)
        dl_text = self._format_downloads(downloads)
        lbl_dl = ctk.CTkLabel(badge_frame, text=dl_text,
                              image=icon("download", 11, AppConfig.COLOR_TEXT_GRAY),
                              compound="left", padx=3,
                              text_color=AppConfig.COLOR_TEXT_GRAY,
                              font=AppConfig.FONT_BODY_SMALL)
        lbl_dl.pack(side="left", padx=(0, 10))

        categories = hit.get("categories", [])[:3]
        for cat in categories:
            badge = ctk.CTkLabel(
                badge_frame, text=cat,
                font=(AppConfig.FONT_FAMILY, 10),
                text_color=(_BADGE_TEXT_LIGHT, _BADGE_TEXT_DARK),
                fg_color=(_BADGE_BG_LIGHT, _BADGE_BG_DARK),
                corner_radius=AppConfig.RADIUS_BADGE, padx=8, pady=2,
            )
            badge.pack(side="left", padx=(0, 4))

        server_side = hit.get("server_side", "unknown")
        if client_only:
            side_badge = ctk.CTkLabel(
                badge_frame, text="Client-only",
                font=(AppConfig.FONT_FAMILY, 10), text_color="white",
                fg_color=AppConfig.COLOR_STATUS_ERROR,
                corner_radius=AppConfig.RADIUS_BADGE, padx=8, pady=2,
            )
            side_badge.pack(side="left", padx=(0, 4))
        elif server_side == "required":
            side_badge = ctk.CTkLabel(
                badge_frame, text="Server",
                font=(AppConfig.FONT_FAMILY, 10), text_color="white",
                fg_color=AppConfig.COLOR_BTN_SUCCESS,
                corner_radius=AppConfig.RADIUS_BADGE, padx=8, pady=2,
            )
            side_badge.pack(side="left", padx=(0, 4))
        elif server_side == "optional":
            side_badge = ctk.CTkLabel(
                badge_frame, text="Client + Server",
                font=(AppConfig.FONT_FAMILY, 10), text_color="white",
                fg_color="#0891b2",
                corner_radius=AppConfig.RADIUS_BADGE, padx=8, pady=2,
            )
            side_badge.pack(side="left", padx=(0, 4))

        if hit_key in self._installed_slugs_cache:
            installed_badge = ctk.CTkLabel(
                badge_frame, text="✓ Installed",
                font=(AppConfig.FONT_FAMILY_DISPLAY, 10, "bold"), text_color="#0f172a",
                fg_color=_MODRINTH_GREEN,
                corner_radius=AppConfig.RADIUS_BADGE, padx=8, pady=2,
            )
            installed_badge.pack(side="left", padx=(0, 4))

        is_modpack = hit.get("project_type") == "modpack"
        install_cmd = self._on_install_modpack if is_modpack else self._on_install
        unsupported = server_side == "unsupported" and not is_modpack
        already_installed = hit_key in self._installed_slugs_cache and not is_modpack
        if already_installed:
            btn_install = ctk.CTkButton(
                card, text="Uninstall", width=90, height=32,
                corner_radius=AppConfig.RADIUS_BTN,
                fg_color=AppConfig.COLOR_BTN_DANGER, hover_color=AppConfig.COLOR_BTN_DANGER_HOVER,
                text_color="white", font=(AppConfig.FONT_FAMILY_DISPLAY, 12, "bold"),
                command=lambda k=hit_key, t=hit.get("title", hit_key): self._confirm_uninstall_mod(k, t),
            )
        else:
            btn_install = ctk.CTkButton(
                card, text="Client-only" if unsupported else "Install", width=90, height=32,
                corner_radius=AppConfig.RADIUS_BTN,
                fg_color=AppConfig.COLOR_BTN_GHOST if unsupported else _MODRINTH_GREEN,
                hover_color=AppConfig.COLOR_BTN_GHOST_HOVER if unsupported else _MODRINTH_GREEN_HOVER,
                text_color=("#0f172a", AppConfig.COLOR_TEXT_PRIMARY) if unsupported else "#0f172a",
                font=(AppConfig.FONT_FAMILY_DISPLAY, 12, "bold"),
                state="disabled" if unsupported else "normal",
                command=None if unsupported else lambda h=hit, fn=install_cmd: fn(h),
            )
        btn_install.grid(row=0, column=3, rowspan=2, padx=(4, 12), pady=12, sticky="e")

        return card

    # ------------------------------------------------------------------
    # Installed view toggle (M.6)
    # ------------------------------------------------------------------
    def _toggle_installed_view(self):
        if self._view == "search":
            self._view = "installed"
            self.btn_installed.configure(
                fg_color=_MODRINTH_GREEN, hover_color=_MODRINTH_GREEN_HOVER,
                text="Explore", text_color="#0f172a",
            )
            self.pagination_bar.grid_remove()
            self._render_installed()
        else:
            self._view = "search"
            self.btn_installed.configure(
                fg_color=AppConfig.COLOR_BTN_GHOST, hover_color=AppConfig.COLOR_BTN_GHOST_HOVER,
                text="Installed", text_color=("#0f172a", AppConfig.COLOR_TEXT_PRIMARY),
            )
            self.installed_action_bar.grid_remove()
            self.pagination_bar.grid()
            if self._current_hits:
                self._render_results()
                self._update_pagination()
            else:
                self._show_placeholder("Search for mods on Modrinth to get started.\nResults will appear here.")

    def _render_installed(self):
        for w in self.results_frame.winfo_children():
            w.destroy()
        for w in self.installed_action_bar.winfo_children():
            w.destroy()
        self.installed_action_bar.grid_remove()
        self._selected_files.clear()

        ctx = self._resolve_server_context()
        if not ctx:
            self._show_placeholder("Select a server to view installed mods.")
            return
        server_name = ctx[0]

        mods_dir = os.path.join(SERVERS_DIR, server_name, "mods")
        plugins_dir = os.path.join(SERVERS_DIR, server_name, "plugins")
        files = []
        for d in [mods_dir, plugins_dir]:
            if os.path.isdir(d):
                for fname in sorted(os.listdir(d)):
                    if fname.endswith(".jar"):
                        files.append(os.path.join(d, fname))

        action_bar = self.installed_action_bar
        action_bar.grid()

        header = ctk.CTkLabel(
            action_bar,
            text=f"Installed mods/plugins — {server_name}  ({len(files)} files)",
            font=(AppConfig.FONT_FAMILY_DISPLAY, 13, "bold"),
            text_color=("#0f172a", AppConfig.COLOR_TEXT_PRIMARY),
            anchor="w",
        )
        header.pack(side="left")

        if files:
            self._btn_delete_selected = ctk.CTkButton(
                action_bar, text="Delete Selected (0)", width=140, height=28,
                corner_radius=8,
                fg_color=(AppConfig.COLOR_BG_SIDEBAR_LIGHT, AppConfig.COLOR_BTN_GHOST),
                hover_color=AppConfig.COLOR_BTN_DANGER_HOVER,
                text_color=("#0f172a", AppConfig.COLOR_TEXT_PRIMARY),
                font=(AppConfig.FONT_FAMILY_DISPLAY, 11, "bold"), state="disabled",
                command=self._on_delete_selected,
            )
            self._btn_delete_selected.pack(side="right", padx=(6, 0))

            self._btn_update_selected = ctk.CTkButton(
                action_bar, text="Update Selected (0)", width=140, height=28,
                corner_radius=8,
                fg_color=(AppConfig.COLOR_BG_SIDEBAR_LIGHT, AppConfig.COLOR_BTN_GHOST),
                hover_color=_MODRINTH_GREEN_HOVER,
                font=(AppConfig.FONT_FAMILY_DISPLAY, 11, "bold"), state="disabled",
                command=self._on_update_selected,
            )
            self._btn_update_selected.pack(side="right", padx=(6, 0))

            ctk.CTkButton(
                action_bar, text="Check Updates", width=120, height=28,
                corner_radius=8,
                fg_color=AppConfig.COLOR_BTN_WARNING, hover_color=AppConfig.COLOR_BTN_WARNING_HOVER,
                text_color="white", font=(AppConfig.FONT_FAMILY_DISPLAY, 11, "bold"),
                command=self._on_check_updates,
            ).pack(side="right", padx=(6, 0))

            ctk.CTkButton(
                action_bar, text="Select All", width=90, height=28,
                corner_radius=8,
                fg_color=AppConfig.COLOR_BTN_GHOST, hover_color=AppConfig.COLOR_BTN_GHOST_HOVER,
                font=(AppConfig.FONT_FAMILY_DISPLAY, 11, "bold"),
                command=lambda: self._select_all_installed(files),
            ).pack(side="right", padx=(6, 0))

        if not files:
            ctk.CTkLabel(
                self.results_frame, text="", image=icon("package", 36, (AppConfig.COLOR_TEXT_MUTED, AppConfig.COLOR_TEXT_MUTED)),
            ).grid(row=1, column=0, pady=(24, 4))
            ctk.CTkLabel(
                self.results_frame,
                text="No mods or plugins installed.",
                font=AppConfig.FONT_BODY, text_color=AppConfig.COLOR_TEXT_NOTE,
            ).grid(row=2, column=0, pady=(0, 10))
            ctk.CTkButton(
                self.results_frame, text="Browse Popular Mods",
                command=self._toggle_installed_view,
                fg_color=AppConfig.COLOR_BTN_PRIMARY,
                hover_color=AppConfig.COLOR_BTN_PRIMARY_HOVER,
                corner_radius=AppConfig.RADIUS_BTN, height=32,
            ).grid(row=3, column=0, pady=(0, 24))
            return

        self._installed_checkboxes = {}
        for i, fpath in enumerate(files):
            fname = os.path.basename(fpath)
            row_frame = ctk.CTkFrame(self.results_frame, corner_radius=8,
                                     fg_color=(AppConfig.COLOR_BG_CARD_LIGHT, AppConfig.COLOR_BG_CARD_DARK))
            row_frame.grid(row=i + 1, column=0, sticky="ew", padx=6, pady=2)
            row_frame.grid_columnconfigure(1, weight=1)

            var = ctk.BooleanVar(value=fpath in self._selected_files)
            chk = ctk.CTkCheckBox(
                row_frame, text="", width=24, height=24,
                checkbox_width=20, checkbox_height=20,
                corner_radius=6, border_width=2,
                fg_color=_MODRINTH_GREEN, hover_color=_MODRINTH_GREEN_HOVER,
                border_color=(AppConfig.COLOR_BORDER_LIGHT, AppConfig.COLOR_BORDER_DARK),
                variable=var,
                command=lambda fp=fpath, v=var: self._on_toggle_installed_selection(fp, v),
            )
            chk.grid(row=0, column=0, padx=(10, 4), pady=6)
            self._installed_checkboxes[fpath] = var

            ctk.CTkLabel(row_frame, text=fname, font=(AppConfig.FONT_FAMILY, 12), anchor="w").grid(
                row=0, column=1, sticky="w", padx=4, pady=6)

            btn_del = ctk.CTkButton(
                row_frame, text="Delete", width=64, height=28,
                corner_radius=8,
                fg_color=AppConfig.COLOR_BTN_DANGER, hover_color=AppConfig.COLOR_BTN_DANGER_HOVER,
                font=(AppConfig.FONT_FAMILY_DISPLAY, 11, "bold"),
                command=lambda fp=fpath: self._confirm_delete_mod(fp),
            )
            btn_del.grid(row=0, column=2, padx=(0, 6), pady=4)

    def _on_toggle_installed_selection(self, filepath: str, var):
        if var.get():
            self._selected_files.add(filepath)
        else:
            self._selected_files.discard(filepath)
        self._update_installed_action_bar()

    def _select_all_installed(self, files: list):
        all_selected = len(self._selected_files) == len(files)
        for fpath in files:
            if all_selected:
                self._selected_files.discard(fpath)
            else:
                self._selected_files.add(fpath)
            var = self._installed_checkboxes.get(fpath)
            if var is not None:
                var.set(fpath in self._selected_files)
        self._update_installed_action_bar()

    def _update_installed_action_bar(self):
        n = len(self._selected_files)
        _ghost = (AppConfig.COLOR_BG_SIDEBAR_LIGHT, AppConfig.COLOR_BTN_GHOST)
        if hasattr(self, "_btn_delete_selected"):
            self._btn_delete_selected.configure(
                text=f"Delete Selected ({n})", state="normal" if n else "disabled",
                fg_color=AppConfig.COLOR_BTN_DANGER if n else _ghost,
                text_color="white" if n else ("#0f172a", AppConfig.COLOR_TEXT_PRIMARY))
        if hasattr(self, "_btn_update_selected"):
            self._btn_update_selected.configure(
                text=f"Update Selected ({n})", state="normal" if n else "disabled",
                fg_color=_MODRINTH_GREEN if n else _ghost,
                text_color="#0f172a" if n else ("#0f172a", AppConfig.COLOR_TEXT_PRIMARY))

    def _confirm_uninstall_mod(self, slug: str, title: str):
        ctx = self._resolve_server_context()
        if not ctx:
            return
        server_name = ctx[0]
        fname = mod_install_tracker.get_installed_filename(server_name, slug)
        if not fname:
            return
        filepath = None
        for subdir in ("mods", "plugins"):
            candidate = os.path.join(SERVERS_DIR, server_name, subdir, fname)
            if os.path.isfile(candidate):
                filepath = candidate
                break
        if not ZBBDialog.confirm(self.winfo_toplevel(), "Uninstall Mod",
                                  f"Uninstall '{title}'?", confirm_text="Uninstall", danger=True):
            return
        try:
            if filepath:
                os.remove(filepath)
            mod_install_tracker.remove_install(server_name, slug)
            self._set_status(f"✓ Uninstalled {title}")
            self._installed_slugs_cache.discard(slug)
            self._render_results()
        except OSError as exc:
            self._set_status(f"✗ Failed to uninstall {title}: {exc}")

    def _confirm_delete_mod(self, filepath: str):
        fname = os.path.basename(filepath)
        if not ZBBDialog.confirm(self.winfo_toplevel(), "Delete Mod",
                                 f"Delete '{fname}'?", confirm_text="Delete", danger=True):
            return
        try:
            os.remove(filepath)
            self._set_status(f"✓ Deleted {fname}")
            self._render_installed()  # refresh inline
        except OSError as exc:
            self._set_status(f"✗ Failed to delete {fname}: {exc}")

    def _on_delete_selected(self):
        selected = list(self._selected_files)
        if not selected:
            return
        if not ZBBDialog.confirm(
            self.winfo_toplevel(), "Delete Selected Mods",
            f"Delete {len(selected)} selected file(s)?", confirm_text="Delete", danger=True
        ):
            return

        deleted, failed = 0, 0
        for fpath in selected:
            try:
                os.remove(fpath)
                deleted += 1
            except OSError as exc:
                logger.warning("Failed to delete %s: %s", fpath, exc)
                failed += 1

        self._set_status(f"✓ Deleted {deleted} file(s)" + (f", {failed} failed" if failed else ""))
        self._render_installed()

    def _on_update_selected(self):
        ctx = self._resolve_server_context()
        if not ctx:
            return
        server_name, mc_version, loader = ctx
        selected_filenames = {os.path.basename(fp) for fp in self._selected_files}
        if not selected_filenames:
            return

        self._set_status("Checking for updates…", busy=True)

        def _worker():
            try:
                updates = self.client.check_updates(server_name, mc_version, loader)
            except Exception as exc:
                self.after(0, lambda e=exc: self._set_status(f"✗ Update check failed: {e}"))
                return

            matched = _filter_updates_for_selection(updates, selected_filenames)
            if not matched:
                self.after(0, lambda: self._set_status("No updates available for the selected mods."))
                return

            updated, failed = 0, 0
            for update in matched:
                self.after(0, lambda u=update: self._set_status(f"Updating {u['filename']}…"))
                try:
                    if self.client.apply_update(update, server_name, loader):
                        updated += 1
                    else:
                        failed += 1
                except Exception as exc:
                    logger.warning("Update failed for %s: %s", update.get("filename"), exc)
                    failed += 1

            self.after(0, lambda: self._set_status(
                f"✓ Updated {updated} mod(s)" + (f", {failed} failed" if failed else "")))
            self.after(0, self._render_installed)

        threading.Thread(target=_worker, daemon=True).start()

    # ------------------------------------------------------------------
    # Install action
    # ------------------------------------------------------------------
    def _on_install(self, hit: dict, batch: dict = None):
        ctx = self._resolve_install_context()
        if not ctx:
            self._note_batch_result(batch, ok=False)
            return
        server_name, mc_version, loader = ctx

        slug = hit.get("slug", hit.get("project_id", ""))
        title = hit.get("title", slug)
        self._set_status(f"Loading versions for {title}…", busy=True)

        def _fetch_versions():
            try:
                versions = self.client.get_versions(slug, mc_version=mc_version, loader=loader)
                if not versions:
                    self.after(0, lambda: self._set_status(f"✗ No compatible versions of {title} found."))
                    self.after(0, lambda: self._note_batch_result(batch, ok=False))
                    return
                if len(versions) == 1:
                    self._do_install_version(versions[0], server_name, loader, title, slug, batch=batch)
                else:
                    self.after(0, lambda: self._show_version_picker(
                        versions, title,
                        on_confirm=lambda v: self._do_install_version(v, server_name, loader, title, slug, batch=batch),
                    ))
            except Exception as exc:
                logger.debug("Project fetch error: %s", exc)
                self.after(0, lambda e=exc: self._set_status(f"✗ Failed to load versions: {e}"))
                self.after(0, lambda: self._note_batch_result(batch, ok=False))

        threading.Thread(target=_fetch_versions, daemon=True).start()

    def _do_install_version(self, version, server_name, loader, title, slug, batch: dict = None):
        self._set_status(f"Installing {title}…", busy=True)

        def _install():
            try:
                path = self.client.download_version(
                    version, server_name, loader,
                    progress_callback=lambda p: self.after(
                        0, lambda: self._set_status(f"Downloading {title}… {int(p * 100)}%")
                    ),
                )
                if path:
                    fname = os.path.basename(path)
                    mod_install_tracker.record_install(server_name, slug, fname)
                    self.after(0, lambda: self._set_status(f"✓ Installed {fname}"))
                    logger.info("Installed %s to %s", title, path)
                    self.after(0, lambda: self._note_batch_result(batch, ok=True))
                else:
                    self.after(0, lambda: self._set_status(f"✗ Install failed for {title}."))
                    self.after(0, lambda: self._note_batch_result(batch, ok=False))
            except Exception as exc:
                self.after(0, lambda e=exc: self._set_status(f"✗ Install failed: {e}"))
                self.after(0, lambda: self._note_batch_result(batch, ok=False))

        threading.Thread(target=_install, daemon=True).start()

    def _on_install_modpack(self, hit: dict, batch: dict = None):
        ctx = self._resolve_install_context()
        if not ctx:
            self._note_batch_result(batch, ok=False)
            return
        server_name, mc_version, loader = ctx

        slug = hit.get("slug", hit.get("project_id", ""))
        title = hit.get("title", slug)
        self._set_status(f"Loading versions for {title}…", busy=True)

        def _fetch_versions():
            try:
                versions = self.client.get_versions(slug, mc_version=mc_version, loader=loader)
                if not versions:
                    self.after(0, lambda: self._set_status(f"✗ No compatible versions of {title} found."))
                    self.after(0, lambda: self._note_batch_result(batch, ok=False))
                    return
                if len(versions) == 1:
                    self._do_install_modpack_version(versions[0], server_name, title, batch=batch)
                else:
                    self.after(0, lambda: self._show_version_picker(
                        versions, title,
                        on_confirm=lambda v: self._do_install_modpack_version(v, server_name, title, batch=batch),
                    ))
            except Exception as exc:
                logger.debug("Modpack version fetch error: %s", exc)
                self.after(0, lambda e=exc: self._set_status(f"✗ Failed to load versions: {e}"))
                self.after(0, lambda: self._note_batch_result(batch, ok=False))

        threading.Thread(target=_fetch_versions, daemon=True).start()

    def _do_install_modpack_version(self, version, server_name, title, batch: dict = None):
        self._set_status(f"Installing modpack {title}…", busy=True)

        def _install():
            tmp_dir = tempfile.mkdtemp(prefix="zbb_modpack_")
            try:
                downloaded = self.client.download_version_to(
                    version, tmp_dir,
                    progress_callback=lambda p: self.after(
                        0, lambda: self._set_status(f"Downloading {title}… {int(p * 100)}%")
                    ),
                )
                if not downloaded:
                    self.after(0, lambda: self._set_status(f"✗ Download failed for {title}."))
                    self.after(0, lambda: self._note_batch_result(batch, ok=False))
                    return

                meta = get_server_meta(server_name)
                summary = install_mrpack(
                    downloaded, server_name,
                    progress_callback=lambda msg: self.after(0, lambda m=msg: self._set_status(m)),
                    server_type=meta.get("type"),
                    mc_version=meta.get("version"),
                )
                self.after(0, lambda: self._set_status(
                    f"✓ Modpack {title}: {self._format_mrpack_summary(summary)}"))
                logger.info("Installed modpack %s to server %s", title, server_name)
                self.after(0, lambda: self._note_batch_result(batch, ok=True))
            except MrpackCompatibilityError as exc:
                self.after(0, lambda e=exc: self._set_status(f"✗ Incompatible: {e}"))
                self.after(0, lambda e=exc: ZBBDialog.info(
                    self.winfo_toplevel(), "Incompatible Modpack", str(e), kind="warning"))
                self.after(0, lambda: self._note_batch_result(batch, ok=False))
            except Exception as exc:
                self.after(0, lambda e=exc: self._set_status(f"✗ Modpack install failed: {e}"))
                self.after(0, lambda: self._note_batch_result(batch, ok=False))
            finally:
                shutil.rmtree(tmp_dir, ignore_errors=True)

        threading.Thread(target=_install, daemon=True).start()

    def _show_version_picker(self, versions, title, on_confirm):
        dialog = ctk.CTkToplevel(self)
        dialog.title(f"Choose Version — {title}")
        dialog.geometry("460x320")
        dialog.transient(self.winfo_toplevel())
        dialog.grab_set()

        frame = ctk.CTkScrollableFrame(dialog, corner_radius=AppConfig.RADIUS_CARD)
        frame.pack(fill="both", expand=True, padx=12, pady=(12, 0))

        ctk.CTkLabel(
            frame, text="Select a version to install:",
            font=(AppConfig.FONT_FAMILY_DISPLAY, 14, "bold"), anchor="w",
        ).grid(row=0, column=0, sticky="w", pady=(0, 10))

        var = ctk.StringVar(value=versions[0].get("id", ""))

        for i, v in enumerate(versions):
            vnum = v.get("version_number", "?")
            mc_v = ", ".join(v.get("game_versions", []))
            rb = ctk.CTkRadioButton(
                frame, text=f"{vnum}  (MC: {mc_v})",
                variable=var, value=v.get("id", ""),
                font=(AppConfig.FONT_FAMILY, 12),
            )
            rb.grid(row=i + 1, column=0, sticky="w", padx=8, pady=2)

        def _on_confirm():
            selected_id = var.get()
            for v in versions:
                if v.get("id") == selected_id:
                    dialog.destroy()
                    on_confirm(v)
                    break

        btn_frame = ctk.CTkFrame(dialog, fg_color="transparent")
        btn_frame.pack(fill="x", padx=12, pady=10)

        ctk.CTkButton(btn_frame, text="Cancel", width=90, height=32,
                       corner_radius=AppConfig.RADIUS_BTN, fg_color=AppConfig.COLOR_BTN_GHOST,
                       hover_color=AppConfig.COLOR_BTN_GHOST_HOVER,
                       command=dialog.destroy).pack(side="right", padx=4)
        ctk.CTkButton(btn_frame, text="Install", width=90, height=32,
                       corner_radius=AppConfig.RADIUS_BTN, fg_color=_MODRINTH_GREEN, hover_color=_MODRINTH_GREEN_HOVER,
                       text_color="#0f172a", command=_on_confirm).pack(side="right", padx=4)

    # ------------------------------------------------------------------
    # Optimizer bundle
    # ------------------------------------------------------------------
    def _on_install_optimizers(self):
        ctx = self._resolve_install_context()
        if not ctx:
            return
        server_name, mc_version, loader = ctx

        if loader not in ("fabric", "forge"):
            ZBBDialog.info(
                self.winfo_toplevel(), "Fabric or Forge Required",
                "The Optimizer Bundle only supports Fabric or Forge servers.",
            )
            return

        bundle = self.OPTIMIZERS_FABRIC if loader == "fabric" else self.OPTIMIZERS_FORGE

        self._set_status("Installing Optimizer Bundle...", busy=True)

        def _run_opt():
            failed = []
            for mod in bundle:
                self.after(0, lambda m=mod: self._set_status(f"Installing {m['name']}..."))
                try:
                    versions = self.client.get_versions(mod["slug"], mc_version=mc_version, loader=loader)
                    if not versions:
                        failed.append(f"{mod['name']} (no build for MC {mc_version} yet)")
                        continue
                    path = self.client.download_mod(mod["slug"], server_name, mc_version, loader)
                    if not path:
                        failed.append(mod["name"])
                    else:
                        mod_install_tracker.record_install(server_name, mod["slug"], os.path.basename(path))
                except Exception as exc:
                    logger.error("Failed to install %s: %s", mod["name"], exc)
                    failed.append(mod["name"])

            if failed:
                msg = f"Installed {len(bundle) - len(failed)}/{len(bundle)}. Failed: {', '.join(failed)}"
                self.after(0, lambda: self._set_status(f"⚠ {msg}"))
                self.after(0, lambda: ZBBDialog.info(
                    self.winfo_toplevel(), "Optimizer Bundle", msg, kind="warning"
                ))
            else:
                self.after(0, lambda: self._set_status("✓ Optimizer Bundle installed."))

        threading.Thread(target=_run_opt, daemon=True).start()

    # ------------------------------------------------------------------
    # Update checker
    # ------------------------------------------------------------------
    def _on_check_updates(self):
        ctx = self._resolve_server_context()
        if not ctx:
            self._set_status("⚠ Select a server first.")
            return
        server_name, mc_version, loader = ctx

        self._set_status("Checking for updates…", busy=True)

        def _check():
            try:
                updates = self.client.check_updates(server_name, mc_version, loader)
                self.after(0, lambda: self._show_updates_dialog(updates))
            except Exception as exc:
                self.after(0, lambda e=exc: self._set_status(f"✗ Update check failed: {e}"))
            finally:
                self.after(0, lambda: self._set_status("Ready"))

        threading.Thread(target=_check, daemon=True).start()

    def _show_updates_dialog(self, updates):
        if not updates:
            self._set_status("✓ All mods are up to date.")
            return

        dialog = ctk.CTkToplevel(self)
        dialog.title("Mod Updates Available")
        dialog.geometry("520x400")
        dialog.transient(self.winfo_toplevel())
        dialog.grab_set()

        frame = ctk.CTkScrollableFrame(dialog, corner_radius=AppConfig.RADIUS_CARD)
        frame.pack(fill="both", expand=True, padx=12, pady=12)

        ctk.CTkLabel(
            frame, text=f"{len(updates)} update(s) available",
            font=(AppConfig.FONT_FAMILY_DISPLAY, 16, "bold"), anchor="w",
        ).grid(row=0, column=0, sticky="w", pady=(0, 10))

        for i, u in enumerate(updates):
            card = ctk.CTkFrame(frame, corner_radius=8)
            card.grid(row=i + 1, column=0, sticky="ew", pady=3)
            card.grid_columnconfigure(0, weight=1)

            ctk.CTkLabel(card, text=u["filename"], font=(AppConfig.FONT_FAMILY_DISPLAY, 13, "bold"), anchor="w").grid(
                row=0, column=0, sticky="w", padx=10, pady=(8, 0))
            ctk.CTkLabel(card, text=f"→ {u.get('latest_version', 'newer version')} available",
                         font=AppConfig.FONT_BODY_SMALL, anchor="w").grid(
                row=1, column=0, sticky="w", padx=10, pady=(0, 8))

        ctk.CTkButton(dialog, text="Close", width=100, height=32,
                       corner_radius=AppConfig.RADIUS_BTN, fg_color=AppConfig.COLOR_BTN_GHOST,
                       hover_color=AppConfig.COLOR_BTN_GHOST_HOVER,
                       command=dialog.destroy).pack(pady=8)

    # ------------------------------------------------------------------
    # Icon loading
    # ------------------------------------------------------------------
    def _queue_icon_fetch(self, icon_url: str, icon_frame, lbl_initial):
        with _ICONS_LOCK:
            if icon_url in _ICONS_IN_FLIGHT:
                return
            _ICONS_IN_FLIGHT.add(icon_url)
        _ICON_EXECUTOR.submit(self._load_icon, icon_url, icon_frame, lbl_initial)

    def _load_icon(self, icon_url: str, icon_frame, lbl_initial):
        try:
            resp = self.client.session.get(icon_url, timeout=8)
            resp.raise_for_status()
            img = Image.open(io.BytesIO(resp.content)).resize((48, 48), Image.LANCZOS)
            ctk_img = ctk.CTkImage(img, size=(48, 48))
            _ICON_CACHE[icon_url] = ctk_img
            self.after(0, lambda: self._apply_icon(icon_frame, lbl_initial, ctk_img))
        except Exception as exc:
            logger.debug("Image fetch error: %s", exc)
        finally:
            with _ICONS_LOCK:
                _ICONS_IN_FLIGHT.discard(icon_url)

    def _apply_icon(self, icon_frame, lbl_initial, ctk_img):
        if not icon_frame.winfo_exists() or not lbl_initial.winfo_exists():
            return
        lbl_initial.configure(image=ctk_img, text="")

    # ------------------------------------------------------------------
    # Utilities
    # ------------------------------------------------------------------
    @staticmethod
    def _format_mrpack_summary(summary: dict) -> str:
        parts = [f"{summary['installed']} mods installed"]
        if summary.get("skipped_client"):
            parts.append(f"{summary['skipped_client']} client-only skipped")
        if summary.get("failed"):
            parts.append(f"{summary['failed']} failed")
        return ", ".join(parts)

    @staticmethod
    def _format_downloads(count: int) -> str:
        if count >= 1_000_000:
            return f"{count / 1_000_000:.1f}M"
        elif count >= 1_000:
            return f"{count / 1_000:.1f}K"
        return str(count)
