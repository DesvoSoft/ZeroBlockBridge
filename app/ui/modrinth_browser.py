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
import tkinter.messagebox
from typing import Callable, Optional

import requests
from PIL import Image

from app.core.app_config import AppConfig
from app.core.constants import SERVERS_DIR
from app.services.modrinth import ModrinthClient, ModrinthException
from app.services.mrpack_installer import install_mrpack, MrpackCompatibilityError
from app.core.logic import get_server_meta

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Design tokens — Modrinth-specific (non-duplicates of AppConfig)
# ---------------------------------------------------------------------------
_MODRINTH_GREEN = "#1bd96a"
_MODRINTH_GREEN_HOVER = "#15b858"
_BADGE_BG_LIGHT, _BADGE_BG_DARK = AppConfig.COLOR_BADGE_BG
_BADGE_TEXT_LIGHT, _BADGE_TEXT_DARK = AppConfig.COLOR_BADGE_TEXT
_DOWNLOADS_COLOR = "#94a3b8"   # slate-400

_ICON_COLORS = ["#3b82f6", "#ef4444", "#22c55e", "#f97316", "#8b5cf6", "#ec4899"]
_ICON_CACHE: dict[str, ctk.CTkImage] = {}

_PAGE_SIZE = 20


def _filter_updates_for_selection(updates: list, selected_filenames: set) -> list:
    """Return the subset of check_updates() results matching selected filenames."""
    return [u for u in updates if u.get("filename") in selected_filenames]


class ModrinthBrowser(ctk.CTkFrame):
    """
    Self-contained Modrinth browsing panel.

    Designed to be packed inside a CTkTabview tab. Handles its own
    threading for API calls — never blocks the UI thread.
    """

    OPTIMIZERS = [
        {"slug": "lithium", "name": "Lithium", "description": "General-purpose game code optimizer."},
        {"slug": "ferrite-core", "name": "FerriteCore", "description": "Memory usage optimization."},
        {"slug": "krypton", "name": "Krypton", "description": "Optimizes networking stack."},
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

        # View state: "search" or "installed"
        self._view = "search"

        # Bulk-selection state (F8)
        self._selected_files: set = set()      # installed view — absolute file paths
        self._selected_hits: dict = {}          # search view — slug/project_id -> hit dict

        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(1, weight=1)

        self._build_search_bar()
        self._build_results_area()
        self._build_pagination_bar()
        self._build_status_bar()

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
            tkinter.messagebox.showinfo("Vanilla Server", msg, parent=self.winfo_toplevel())
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
            return
        server_name, mc_version, loader = ctx
        engine = (loader or "vanilla").title()
        if loader is None:
            self.lbl_context.configure(
                text=f"⚠ {server_name} · Vanilla {mc_version} — vanilla can't load mods or plugins",
                text_color=AppConfig.COLOR_STATUS_STARTING,
            )
        else:
            self.lbl_context.configure(
                text=f"Installing to: {server_name} · {engine} {mc_version}",
                text_color=AppConfig.COLOR_TEXT_GRAY,
            )
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
        bar = ctk.CTkFrame(self, corner_radius=12,
                           fg_color=(AppConfig.COLOR_BG_LIGHT, AppConfig.COLOR_BG_DARK))
        bar.grid(row=0, column=0, sticky="ew", padx=0, pady=(0, 8))
        bar.grid_columnconfigure(1, weight=1)

        lbl_icon = ctk.CTkLabel(bar, text="🔍", font=("Roboto", 16))
        lbl_icon.grid(row=0, column=0, padx=(12, 4), pady=8)

        self.entry_search = ctk.CTkEntry(
            bar,
            placeholder_text="Search Modrinth for mods, plugins, shaders…",
            corner_radius=12,
            height=36,
            font=AppConfig.FONT_BODY,
            border_width=0,
            fg_color=(AppConfig.COLOR_BG_CARD_LIGHT, AppConfig.COLOR_BG_CARD_DARK),
        )
        self.entry_search.grid(row=0, column=1, sticky="ew", padx=4, pady=8)
        self.entry_search.bind("<Return>", self._on_search)

        # Filter: Project type
        self.combo_type = ctk.CTkComboBox(
            bar,
            values=["mod", "plugin", "modpack", "resourcepack", "shader"],
            width=110, height=36, corner_radius=12,
        )
        self.combo_type.set("mod")
        self.combo_type.grid(row=0, column=2, padx=4, pady=8)
        self.combo_type._entry.bind("<Button-1>", lambda e: self.combo_type._open_dropdown_menu())
        self.combo_type._entry.configure(cursor="arrow")

        # Sort dropdown (M.7)
        self.combo_sort = ctk.CTkComboBox(
            bar,
            values=list(self._SORT_OPTIONS.keys()),
            width=105, height=36, corner_radius=12,
        )
        self.combo_sort.set("Relevance")
        self.combo_sort.grid(row=0, column=3, padx=4, pady=8)
        self.combo_sort._entry.bind("<Button-1>", lambda e: self.combo_sort._open_dropdown_menu())
        self.combo_sort._entry.configure(cursor="arrow")

        # Search button
        self.btn_search = ctk.CTkButton(
            bar, text="Search", width=80, height=36,
            corner_radius=12,
            fg_color=_MODRINTH_GREEN, hover_color=_MODRINTH_GREEN_HOVER,
            text_color="white", font=("Roboto Medium", 12),
            command=self._on_search,
        )
        self.btn_search.grid(row=0, column=4, padx=4, pady=8)

        # Optimizer bundle button
        self.btn_opt = ctk.CTkButton(
            bar, text="⚡ Optimizers", width=100, height=36,
            corner_radius=12,
            fg_color=AppConfig.COLOR_BTN_PRIMARY, hover_color=AppConfig.COLOR_BTN_PRIMARY_HOVER,
            text_color="white", font=("Roboto Medium", 12),
            command=self._on_install_optimizers,
        )
        self.btn_opt.grid(row=0, column=5, padx=(4, 0), pady=8)

        # Check updates button
        self.btn_updates = ctk.CTkButton(
            bar, text="Check Updates", width=110, height=36,
            corner_radius=12,
            fg_color=AppConfig.COLOR_BTN_WARNING, hover_color=AppConfig.COLOR_BTN_WARNING_HOVER,
            text_color="white", font=("Roboto Medium", 11),
            command=self._on_check_updates,
        )
        self.btn_updates.grid(row=0, column=6, padx=(4, 4), pady=8)

        # Installed toggle button (M.6)
        self.btn_installed = ctk.CTkButton(
            bar, text="Installed", width=90, height=36,
            corner_radius=12,
            fg_color=AppConfig.COLOR_BTN_GHOST, hover_color=AppConfig.COLOR_BTN_GHOST_HOVER,
            text_color=AppConfig.COLOR_TEXT_PRIMARY, font=("Roboto Medium", 11),
            command=self._toggle_installed_view,
        )
        self.btn_installed.grid(row=0, column=7, padx=(4, 4), pady=8)

        # Import modpack button (CA-M04)
        self.btn_mrpack = ctk.CTkButton(
            bar, text="📦 Import .mrpack", width=130, height=36,
            corner_radius=12,
            fg_color="#7c3aed", hover_color="#6d28d9",
            text_color="white", font=("Roboto Medium", 11),
            command=self._on_import_mrpack,
        )
        self.btn_mrpack.grid(row=0, column=8, padx=(4, 12), pady=8)

        # Server context banner — which server/engine installs will target
        self.lbl_context = ctk.CTkLabel(
            bar, text="No server selected — select a server to install content.",
            font=AppConfig.FONT_BODY_SMALL, text_color=AppConfig.COLOR_TEXT_NOTE,
            anchor="w",
        )
        self.lbl_context.grid(row=1, column=0, columnspan=9, sticky="ew", padx=14, pady=(0, 6))

    # ------------------------------------------------------------------
    # Layout: Results Area (scrollable)
    # ------------------------------------------------------------------
    def _build_results_area(self):
        self.results_frame = ctk.CTkScrollableFrame(
            self, corner_radius=12,
            fg_color=(AppConfig.COLOR_BG_CARD_LIGHT, AppConfig.COLOR_BG_SIDEBAR_DARK),
            border_width=1,
            border_color=(AppConfig.COLOR_BORDER_LIGHT, AppConfig.COLOR_BORDER_DARK),
            label_text="",
        )
        self.results_frame.grid(row=1, column=0, sticky="nsew", padx=0, pady=0)
        self.results_frame.grid_columnconfigure(0, weight=1)

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
    # Layout: Pagination bar (classic Prev/Next)
    # ------------------------------------------------------------------
    def _build_pagination_bar(self):
        self.pagination_bar = ctk.CTkFrame(self, height=36, corner_radius=12,
                                            fg_color=(AppConfig.COLOR_BG_LIGHT, AppConfig.COLOR_BG_DARK))
        self.pagination_bar.grid(row=2, column=0, sticky="ew", padx=0, pady=(4, 0))

        self.btn_prev = ctk.CTkButton(
            self.pagination_bar, text="< Prev", width=80, height=28,
            corner_radius=8,
            fg_color=(AppConfig.COLOR_BORDER_LIGHT, AppConfig.COLOR_BTN_GHOST),
            hover_color=(AppConfig.COLOR_BORDER_DARK, AppConfig.COLOR_BTN_GHOST_HOVER),
            text_color=(AppConfig.COLOR_TEXT_NOTE, AppConfig.COLOR_TEXT_PRIMARY),
            font=("Roboto Medium", 12),
            command=self._on_prev_page,
            state="disabled",
        )
        self.btn_prev.pack(side="left", padx=(12, 4), pady=4)

        self.lbl_page = ctk.CTkLabel(
            self.pagination_bar, text="",
            font=AppConfig.FONT_BODY_SMALL,
            text_color=AppConfig.COLOR_TEXT_NOTE,
        )
        self.lbl_page.pack(side="left", padx=8)

        self.btn_next = ctk.CTkButton(
            self.pagination_bar, text="Next >", width=80, height=28,
            corner_radius=8,
            fg_color=(AppConfig.COLOR_BORDER_LIGHT, AppConfig.COLOR_BTN_GHOST),
            hover_color=(AppConfig.COLOR_BORDER_DARK, AppConfig.COLOR_BTN_GHOST_HOVER),
            text_color=(AppConfig.COLOR_TEXT_NOTE, AppConfig.COLOR_TEXT_PRIMARY),
            font=("Roboto Medium", 12),
            command=self._on_next_page,
            state="disabled",
        )
        self.btn_next.pack(side="left", padx=(4, 0), pady=4)

        self.btn_install_selected = ctk.CTkButton(
            self.pagination_bar, text="Install Selected (0)", width=150, height=28,
            corner_radius=8,
            fg_color=_MODRINTH_GREEN, hover_color=_MODRINTH_GREEN_HOVER,
            font=("Roboto Medium", 12), state="disabled",
            command=self._on_install_selected,
        )
        self.btn_install_selected.pack(side="right", padx=(4, 12), pady=4)

        self.pagination_bar.grid_remove()  # hidden until first search

    # ------------------------------------------------------------------
    # Layout: Status Bar
    # ------------------------------------------------------------------
    def _build_status_bar(self):
        self.status_bar = ctk.CTkFrame(self, height=28, corner_radius=12,
                                        fg_color=("gray95", "gray15"))
        self.status_bar.grid(row=3, column=0, sticky="ew", padx=0, pady=(4, 0))

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
    # Search logic
    # ------------------------------------------------------------------
    def _do_search(self):
        """Fetch _current_page of results and render."""
        self.btn_search.configure(state="disabled")
        self._set_status("Searching…", busy=True)
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
                self.after(0, lambda: self._set_status("Ready"))

        threading.Thread(target=_search, daemon=True).start()

    def _on_search_done(self, hits: list, total: int):
        self._current_hits = hits
        self._search_total = total
        self._total_pages = max(1, (total + _PAGE_SIZE - 1) // _PAGE_SIZE)
        self._selected_hits.clear()
        self._update_install_selected_bar()
        self._render_results()
        self._update_pagination()

    def _on_search(self, event=None):
        query = self.entry_search.get().strip()
        if not query:
            return
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
            self.pagination_bar.grid_remove()
            return

        self.pagination_bar.grid()
        page_num = self._current_page + 1
        self.lbl_page.configure(text=f"Page {page_num} of {self._total_pages}")
        self.btn_prev.configure(state="normal" if self._current_page > 0 else "disabled")
        self.btn_next.configure(state="normal" if self._current_page < self._total_pages - 1 else "disabled")
        self.lbl_count.configure(
            text=f"{len(self._current_hits)} of {self._search_total} results"
        )

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

        self._set_status("Loading popular mods...", busy=True)
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
            finally:
                self.after(0, lambda: self._set_status("Ready"))

        threading.Thread(target=_do_load, daemon=True).start()

    def _set_status(self, text: str, busy: bool = False):
        self.lbl_status.configure(text=text)

    def _on_toggle_hit_selection(self, key: str, hit: dict, var):
        if var.get():
            self._selected_hits[key] = hit
        else:
            self._selected_hits.pop(key, None)
        self._update_install_selected_bar()

    def _update_install_selected_bar(self):
        n = len(self._selected_hits)
        if hasattr(self, "btn_install_selected"):
            self.btn_install_selected.configure(
                text=f"Install Selected ({n})", state="normal" if n else "disabled")

    def _on_install_selected(self):
        hits = list(self._selected_hits.values())
        if not hits:
            return
        ctx = self._resolve_install_context()
        if not ctx:
            return

        if len(hits) > 1 and not tkinter.messagebox.askyesno(
            "Confirm Install", f"Install {len(hits)} mods/modpacks?"
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
        if batch["done"] >= batch["total"]:
            total, failed = batch["total"], batch["failed"]
            if failed:
                self._set_status(f"✓ Installed {total - failed}/{total} ({failed} failed)")
            else:
                self._set_status(f"✓ Installed {total}/{total}")

    # ------------------------------------------------------------------
    # Render results
    # ------------------------------------------------------------------
    def _render_results(self):
        for w in self.results_frame.winfo_children():
            w.destroy()

        if not self._current_hits:
            self._show_placeholder("No results found.\nTry a different search term.")
            self.lbl_count.configure(text="0 results")
            return

        for idx, hit in enumerate(self._current_hits):
            card = self._create_mod_card(hit)
            card.grid(row=idx, column=0, sticky="ew", padx=6, pady=3)

    def _create_mod_card(self, hit: dict) -> ctk.CTkFrame:
        title = hit.get("title", "Unknown")
        initial = title[0].upper() if title else "?"
        icon_url = hit.get("icon_url", "")
        color = _ICON_COLORS[int(hashlib.md5(title.encode()).hexdigest(), 16) % len(_ICON_COLORS)]

        card = ctk.CTkFrame(
            self.results_frame,
            corner_radius=12,
            fg_color=(AppConfig.COLOR_BG_CARD_LIGHT, AppConfig.COLOR_BG_CARD_DARK),
        )
        card.grid_columnconfigure(1, weight=1)

        hit_key = hit.get("slug") or hit.get("project_id", "")
        client_only = hit.get("server_side") == "unsupported" and hit.get("project_type") != "modpack"
        select_var = ctk.BooleanVar(value=hit_key in self._selected_hits)
        chk = ctk.CTkCheckBox(
            card, text="", width=20, variable=select_var,
            state="disabled" if client_only else "normal",
            command=lambda h=hit, k=hit_key, v=select_var: self._on_toggle_hit_selection(k, h, v),
        )
        chk.grid(row=0, column=0, rowspan=2, padx=(10, 0), pady=12, sticky="n")

        icon_frame = ctk.CTkFrame(card, width=48, height=48, corner_radius=12, fg_color=color)
        icon_frame.grid(row=0, column=0, rowspan=2, padx=(38, 8), pady=12, sticky="n")
        icon_frame.grid_propagate(False)
        lbl_initial = ctk.CTkLabel(icon_frame, text=initial, font=("Roboto Medium", 20),
                                   text_color="white")
        lbl_initial.place(relx=0.5, rely=0.5, anchor="center")

        if icon_url and icon_url not in _ICON_CACHE:
            threading.Thread(target=self._load_icon, args=(icon_url, icon_frame, lbl_initial),
                             daemon=True).start()
        elif icon_url in _ICON_CACHE:
            self._apply_icon(icon_frame, lbl_initial, _ICON_CACHE[icon_url])

        # Info section
        info_frame = ctk.CTkFrame(card, fg_color="transparent")
        info_frame.grid(row=0, column=1, sticky="ew", padx=(0, 8), pady=(10, 0))
        info_frame.grid_columnconfigure(0, weight=1)

        title_row = ctk.CTkFrame(info_frame, fg_color="transparent")
        title_row.grid(row=0, column=0, sticky="ew")

        lbl_title = ctk.CTkLabel(title_row, text=title, font=("Roboto Medium", 14), anchor="w")
        lbl_title.pack(side="left")

        author = hit.get("author", "Unknown")
        lbl_author = ctk.CTkLabel(title_row, text=f"by {author}",
                                  text_color=_DOWNLOADS_COLOR,
                                  font=AppConfig.FONT_BODY_SMALL, anchor="w")
        lbl_author.pack(side="left", padx=(8, 0))

        desc = hit.get("description", "")[:120]
        lbl_desc = ctk.CTkLabel(info_frame, text=desc,
                                text_color=(AppConfig.COLOR_TEXT_GRAY, "#cbd5e1"),
                                font=AppConfig.FONT_BODY_SMALL,
                                anchor="w", wraplength=500, justify="left")
        lbl_desc.grid(row=1, column=0, sticky="ew", pady=(2, 0))

        # Badges row
        badge_frame = ctk.CTkFrame(card, fg_color="transparent")
        badge_frame.grid(row=1, column=1, sticky="ew", padx=(0, 8), pady=(2, 10))

        downloads = hit.get("downloads", 0)
        dl_text = self._format_downloads(downloads)
        lbl_dl = ctk.CTkLabel(badge_frame, text=f"⬇ {dl_text}",
                              text_color=_DOWNLOADS_COLOR,
                              font=AppConfig.FONT_BODY_SMALL)
        lbl_dl.pack(side="left", padx=(0, 10))

        categories = hit.get("categories", [])[:3]
        for cat in categories:
            badge = ctk.CTkLabel(
                badge_frame, text=cat,
                font=("Roboto", 10),
                text_color=(_BADGE_TEXT_LIGHT, _BADGE_TEXT_DARK),
                fg_color=(_BADGE_BG_LIGHT, _BADGE_BG_DARK),
                corner_radius=12, padx=8, pady=2,
            )
            badge.pack(side="left", padx=(0, 4))

        server_side = hit.get("server_side", "unknown")
        if client_only:
            side_badge = ctk.CTkLabel(
                badge_frame, text="Client-only",
                font=("Roboto", 10), text_color="white",
                fg_color=AppConfig.COLOR_STATUS_ERROR,
                corner_radius=12, padx=8, pady=2,
            )
            side_badge.pack(side="left", padx=(0, 4))
        elif server_side == "required":
            side_badge = ctk.CTkLabel(
                badge_frame, text="Server",
                font=("Roboto", 10), text_color="white",
                fg_color=AppConfig.COLOR_BTN_SUCCESS,
                corner_radius=12, padx=8, pady=2,
            )
            side_badge.pack(side="left", padx=(0, 4))

        is_modpack = hit.get("project_type") == "modpack"
        install_cmd = self._on_install_modpack if is_modpack else self._on_install
        unsupported = server_side == "unsupported" and not is_modpack
        btn_install = ctk.CTkButton(
            card, text="Client-only" if unsupported else "Install", width=90, height=32,
            corner_radius=12,
            fg_color=AppConfig.COLOR_BTN_GHOST if unsupported else _MODRINTH_GREEN,
            hover_color=AppConfig.COLOR_BTN_GHOST_HOVER if unsupported else _MODRINTH_GREEN_HOVER,
            text_color="white", font=("Roboto Medium", 12),
            state="disabled" if unsupported else "normal",
            command=None if unsupported else lambda h=hit, fn=install_cmd: fn(h),
        )
        btn_install.grid(row=0, column=2, rowspan=2, padx=(4, 12), pady=12, sticky="e")

        # Hover effect (M.8 — bind only on card itself, not children)
        bg_normal = (AppConfig.COLOR_BG_CARD_LIGHT, AppConfig.COLOR_BG_CARD_DARK)
        bg_hover = (AppConfig.COLOR_BORDER_LIGHT, AppConfig.COLOR_BTN_GHOST_HOVER)
        card.bind("<Enter>", lambda e: card.configure(fg_color=bg_hover))
        card.bind("<Leave>", lambda e: card.configure(fg_color=bg_normal))

        return card

    # ------------------------------------------------------------------
    # Installed view toggle (M.6)
    # ------------------------------------------------------------------
    def _toggle_installed_view(self):
        if self._view == "search":
            self._view = "installed"
            self.btn_installed.configure(
                fg_color=_MODRINTH_GREEN, hover_color=_MODRINTH_GREEN_HOVER,
                text="Search",
            )
            self.pagination_bar.grid_remove()
            self._render_installed()
        else:
            self._view = "search"
            self.btn_installed.configure(
                fg_color=AppConfig.COLOR_BTN_GHOST, hover_color=AppConfig.COLOR_BTN_GHOST_HOVER,
                text="Installed",
            )
            if self._current_hits:
                self._render_results()
                self._update_pagination()
            else:
                self._show_placeholder("Search for mods on Modrinth to get started.\nResults will appear here.")

    def _render_installed(self):
        for w in self.results_frame.winfo_children():
            w.destroy()
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

        action_bar = ctk.CTkFrame(self.results_frame, fg_color="transparent")
        action_bar.grid(row=0, column=0, sticky="ew", padx=8, pady=(8, 4))

        header = ctk.CTkLabel(
            action_bar,
            text=f"Installed mods/plugins — {server_name}  ({len(files)} files)",
            font=("Roboto Medium", 13),
            text_color=AppConfig.COLOR_TEXT_PRIMARY,
            anchor="w",
        )
        header.pack(side="left")

        if files:
            self._btn_delete_selected = ctk.CTkButton(
                action_bar, text="Delete Selected (0)", width=140, height=28,
                corner_radius=8,
                fg_color=AppConfig.COLOR_BTN_DANGER, hover_color=AppConfig.COLOR_BTN_DANGER_HOVER,
                font=("Roboto Medium", 11), state="disabled",
                command=self._on_delete_selected,
            )
            self._btn_delete_selected.pack(side="right", padx=(6, 0))

            self._btn_update_selected = ctk.CTkButton(
                action_bar, text="Update Selected (0)", width=140, height=28,
                corner_radius=8,
                fg_color=_MODRINTH_GREEN, hover_color=_MODRINTH_GREEN_HOVER,
                font=("Roboto Medium", 11), state="disabled",
                command=self._on_update_selected,
            )
            self._btn_update_selected.pack(side="right", padx=(6, 0))

            ctk.CTkButton(
                action_bar, text="Select All", width=90, height=28,
                corner_radius=8,
                fg_color=AppConfig.COLOR_BTN_GHOST, hover_color=AppConfig.COLOR_BTN_GHOST_HOVER,
                font=("Roboto Medium", 11),
                command=lambda: self._select_all_installed(files),
            ).pack(side="right", padx=(6, 0))

        if not files:
            ctk.CTkLabel(
                self.results_frame, text="📦", font=("Roboto", 28),
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
                corner_radius=12, height=32,
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
                row_frame, text="", width=20, variable=var,
                command=lambda fp=fpath, v=var: self._on_toggle_installed_selection(fp, v),
            )
            chk.grid(row=0, column=0, padx=(10, 4), pady=6)
            self._installed_checkboxes[fpath] = var

            ctk.CTkLabel(row_frame, text=fname, font=("Roboto", 12), anchor="w").grid(
                row=0, column=1, sticky="w", padx=4, pady=6)

            btn_del = ctk.CTkButton(
                row_frame, text="Delete", width=64, height=28,
                corner_radius=8,
                fg_color=AppConfig.COLOR_BTN_DANGER, hover_color=AppConfig.COLOR_BTN_DANGER_HOVER,
                font=("Roboto Medium", 11),
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
        if hasattr(self, "_btn_delete_selected"):
            self._btn_delete_selected.configure(
                text=f"Delete Selected ({n})", state="normal" if n else "disabled")
        if hasattr(self, "_btn_update_selected"):
            self._btn_update_selected.configure(
                text=f"Update Selected ({n})", state="normal" if n else "disabled")

    def _confirm_delete_mod(self, filepath: str):
        fname = os.path.basename(filepath)
        if not tkinter.messagebox.askyesno("Delete Mod", f"Delete '{fname}'?"):
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
        if not tkinter.messagebox.askyesno(
            "Delete Selected Mods", f"Delete {len(selected)} selected file(s)?"
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
                    self._do_install_version(versions[0], server_name, loader, title, batch=batch)
                else:
                    self.after(0, lambda: self._show_version_picker(
                        versions, title,
                        on_confirm=lambda v: self._do_install_version(v, server_name, loader, title, batch=batch),
                    ))
            except Exception as exc:
                logger.debug("Project fetch error: %s", exc)
                self.after(0, lambda e=exc: self._set_status(f"✗ Failed to load versions: {e}"))
                self.after(0, lambda: self._note_batch_result(batch, ok=False))

        threading.Thread(target=_fetch_versions, daemon=True).start()

    def _do_install_version(self, version, server_name, loader, title, batch: dict = None):
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
                self.after(0, lambda e=exc: tkinter.messagebox.showwarning(
                    "Incompatible Modpack", str(e), parent=self.winfo_toplevel()))
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

        frame = ctk.CTkScrollableFrame(dialog, corner_radius=12)
        frame.pack(fill="both", expand=True, padx=12, pady=(12, 0))

        ctk.CTkLabel(
            frame, text="Select a version to install:",
            font=("Roboto Medium", 14), anchor="w",
        ).grid(row=0, column=0, sticky="w", pady=(0, 10))

        var = ctk.StringVar(value=versions[0].get("id", ""))

        for i, v in enumerate(versions):
            vnum = v.get("version_number", "?")
            mc_v = ", ".join(v.get("game_versions", []))
            rb = ctk.CTkRadioButton(
                frame, text=f"{vnum}  (MC: {mc_v})",
                variable=var, value=v.get("id", ""),
                font=("Roboto", 12),
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
                       corner_radius=12, fg_color=AppConfig.COLOR_BTN_GHOST,
                       hover_color=AppConfig.COLOR_BTN_GHOST_HOVER,
                       command=dialog.destroy).pack(side="right", padx=4)
        ctk.CTkButton(btn_frame, text="Install", width=90, height=32,
                       corner_radius=12, fg_color=_MODRINTH_GREEN, hover_color=_MODRINTH_GREEN_HOVER,
                       text_color="white", command=_on_confirm).pack(side="right", padx=4)

    # ------------------------------------------------------------------
    # Optimizer bundle
    # ------------------------------------------------------------------
    def _on_install_optimizers(self):
        ctx = self._resolve_install_context()
        if not ctx:
            return
        server_name, mc_version, loader = ctx

        if loader != "fabric":
            tkinter.messagebox.showinfo(
                "Fabric Required",
                "The Optimizer Bundle (Lithium, FerriteCore, Krypton, Spark) "
                "only supports Fabric servers.",
                parent=self.winfo_toplevel(),
            )
            return

        self._set_status("Installing Optimizer Bundle...", busy=True)

        def _run_opt():
            failed = []
            for mod in self.OPTIMIZERS:
                self.after(0, lambda m=mod: self._set_status(f"Installing {m['name']}..."))
                try:
                    path = self.client.download_mod(mod["slug"], server_name, mc_version, loader)
                    if not path:
                        failed.append(mod["name"])
                except Exception as exc:
                    logger.error("Failed to install %s: %s", mod["name"], exc)
                    failed.append(mod["name"])

            if failed:
                msg = f"Installed {len(self.OPTIMIZERS) - len(failed)}/{len(self.OPTIMIZERS)}. Failed: {', '.join(failed)}"
                self.after(0, lambda: self._set_status(f"⚠ {msg}"))
                self.after(0, lambda: tkinter.messagebox.showwarning(
                    "Optimizer Bundle", msg, parent=self.winfo_toplevel()
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

        frame = ctk.CTkScrollableFrame(dialog, corner_radius=12)
        frame.pack(fill="both", expand=True, padx=12, pady=12)

        ctk.CTkLabel(
            frame, text=f"{len(updates)} update(s) available",
            font=("Roboto Medium", 16), anchor="w",
        ).grid(row=0, column=0, sticky="w", pady=(0, 10))

        for i, u in enumerate(updates):
            card = ctk.CTkFrame(frame, corner_radius=8)
            card.grid(row=i + 1, column=0, sticky="ew", pady=3)
            card.grid_columnconfigure(0, weight=1)

            ctk.CTkLabel(card, text=u["filename"], font=("Roboto Medium", 13), anchor="w").grid(
                row=0, column=0, sticky="w", padx=10, pady=(8, 0))
            ctk.CTkLabel(card, text=f"→ {u.get('latest_version', 'newer version')} available",
                         font=AppConfig.FONT_BODY_SMALL, anchor="w").grid(
                row=1, column=0, sticky="w", padx=10, pady=(0, 8))

        ctk.CTkButton(dialog, text="Close", width=100, height=32,
                       corner_radius=12, fg_color=AppConfig.COLOR_BTN_GHOST,
                       hover_color=AppConfig.COLOR_BTN_GHOST_HOVER,
                       command=dialog.destroy).pack(pady=8)

    # ------------------------------------------------------------------
    # .mrpack modpack import (CA-M04)
    # ------------------------------------------------------------------
    def _on_import_mrpack(self):
        ctx = self._resolve_install_context()
        if not ctx:
            return
        server_name, mc_version, loader = ctx

        mrpack_path = tkinter.filedialog.askopenfilename(
            title="Select Modpack File",
            filetypes=[("Modrinth Modpack", "*.mrpack"), ("All files", "*.*")],
        )
        if not mrpack_path:
            return

        self._set_status("Importing modpack…", busy=True)
        self.btn_mrpack.configure(state="disabled")

        def _import():
            try:
                meta = get_server_meta(server_name)
                summary = install_mrpack(
                    mrpack_path=mrpack_path,
                    server_name=server_name,
                    progress_callback=lambda msg: self.after(0, lambda m=msg: self._set_status(m)),
                    server_type=meta.get("type"),
                    mc_version=meta.get("version"),
                )
                self.after(0, lambda: self._set_status(
                    f"✓ Modpack installed — {self._format_mrpack_summary(summary)}"))
            except MrpackCompatibilityError as exc:
                self.after(0, lambda e=exc: self._set_status(f"✗ Incompatible: {e}"))
                self.after(0, lambda e=exc: tkinter.messagebox.showwarning(
                    "Incompatible Modpack", str(e), parent=self.winfo_toplevel()))
            except Exception as exc:
                logger.error("mrpack import failed: %s", exc)
                self.after(0, lambda e=exc: self._set_status(f"✗ Import failed: {e}"))
            finally:
                self.after(0, lambda: self.btn_mrpack.configure(state="normal"))

        threading.Thread(target=_import, daemon=True).start()

    # ------------------------------------------------------------------
    # Icon loading
    # ------------------------------------------------------------------
    def _load_icon(self, icon_url: str, icon_frame, lbl_initial):
        try:
            resp = requests.get(icon_url, timeout=8)
            resp.raise_for_status()
            img = Image.open(io.BytesIO(resp.content)).resize((48, 48), Image.LANCZOS)
            ctk_img = ctk.CTkImage(img, size=(48, 48))
            _ICON_CACHE[icon_url] = ctk_img
            self.after(0, lambda: self._apply_icon(icon_frame, lbl_initial, ctk_img))
        except Exception as exc:
            logger.debug("Image fetch error: %s", exc)

    def _apply_icon(self, icon_frame, lbl_initial, ctk_img):
        if not icon_frame.winfo_exists():
            return
        lbl_initial.destroy()
        lbl_icon = ctk.CTkLabel(icon_frame, image=ctk_img, text="")
        lbl_icon.place(relx=0.5, rely=0.5, anchor="center")

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
