"""
Modrinth Mod Browser — Neo-Modern UI for ZeroBlockBridge.

Integrated as a tab within the main console area. Provides search,
version filtering, one-click install, and update checking for
Modrinth-hosted mods and plugins.
"""

import customtkinter as ctk
import io
import logging
import os
import threading
import tkinter.messagebox
from typing import Callable, Optional

import requests
from PIL import Image

from app.core.app_config import AppConfig
from app.core.constants import SERVERS_DIR
from app.services.modrinth import ModrinthClient, ModrinthException

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

_ICON_CACHE: dict[str, ctk.CTkImage] = {}


class ModrinthBrowser(ctk.CTkFrame):
    """
    Self-contained Modrinth browsing panel.

    Designed to be packed inside a CTkTabview tab. Handles its own
    threading for API calls — never blocks the UI thread.
    """

    OPTIMIZERS = [
        {"slug": "sodium", "name": "Sodium", "description": "High performance rendering engine."},
        {"slug": "lithium", "name": "Lithium", "description": "General-purpose game code optimizer."},
        {"slug": "ferrite-core", "name": "FerriteCore", "description": "Memory usage optimization."},
        {"slug": "starlight", "name": "Starlight", "description": "Rewrite of light engine for performance."},
        {"slug": "iris", "name": "Iris Shaders", "description": "Modern shader support for Sodium."}
    ]

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
        self._current_hits = []
        self._search_thread = None
        self._search_query = ""
        self._search_project_type = "mod"
        self._search_mc_version = None
        self._search_loader = None
        self._search_offset = 0
        self._search_total = 0

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
            corner_radius=12,
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
            width=110, height=36, corner_radius=12,
        )
        self.combo_type.set("mod")
        self.combo_type.grid(row=0, column=2, padx=4, pady=8)
        # Fix clickable anywhere
        self.combo_type._entry.bind("<Button-1>", lambda e: self.combo_type._open_dropdown_menu())
        self.combo_type._entry.configure(cursor="arrow")

        # Search button
        self.btn_search = ctk.CTkButton(
            bar, text="Search", width=90, height=36,
            corner_radius=12,
            fg_color=_MODRINTH_GREEN, hover_color=_MODRINTH_GREEN_HOVER,
            text_color="white", font=("Roboto Medium", 12),
            command=self._on_search,
        )
        self.btn_search.grid(row=0, column=3, padx=4, pady=8)

        # Optimizer button
        self.btn_opt = ctk.CTkButton(
            bar, text="⚡ Optimizers", width=100, height=36,
            corner_radius=12,
            fg_color="#3b82f6", hover_color="#2563eb",
            text_color="white", font=("Roboto Medium", 12),
            command=self._on_install_optimizers,
        )
        self.btn_opt.grid(row=0, column=4, padx=(4, 0), pady=8)

        # Check for Updates button
        self.btn_updates = ctk.CTkButton(
            bar, text="Check Updates", width=110, height=36,
            corner_radius=12,
            fg_color="#f59e0b", hover_color="#d97706",
            text_color="white", font=("Roboto Medium", 11),
            command=self._on_check_updates,
        )
        self.btn_updates.grid(row=0, column=5, padx=(4, 4), pady=8)

        # Installed mods button
        self.btn_installed = ctk.CTkButton(
            bar, text="Installed", width=90, height=36,
            corner_radius=12,
            fg_color="#64748b", hover_color="#475569",
            text_color="white", font=("Roboto Medium", 11),
            command=self._on_show_installed,
        )
        self.btn_installed.grid(row=0, column=6, padx=(4, 12), pady=8)

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
        self.status_bar = ctk.CTkFrame(self, height=28, corner_radius=12,
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
    # Search logic
    # ------------------------------------------------------------------
    def _do_search(self, reset=False):
        if reset:
            self._current_hits = []
            self._search_offset = 0
            self.btn_search.configure(state="disabled")
        self._set_status("Searching…", busy=True)

        def _search():
            try:
                results = self.client.search(
                    self._search_query,
                    mc_version=self._search_mc_version,
                    loader=self._search_loader,
                    project_type=self._search_project_type,
                    limit=25,
                    offset=self._search_offset,
                )
                hits = results.get("hits", [])
                self._current_hits.extend(hits)
                self._search_total = results.get("total_hits", len(hits))
                total_shown = len(self._current_hits)
                self._search_offset += len(hits)
                self.after(0, lambda: self._render_results(total_shown))
            except ModrinthException as exc:
                logger.error("Modrinth search failed: %s", exc)
                msg = f"Search failed:\n{exc}"
                self.after(0, lambda m=msg: self._show_placeholder(m))
            finally:
                self.after(0, lambda: self.btn_search.configure(state="normal"))
                self.after(0, lambda: self._set_status("Ready"))

        threading.Thread(target=_search, daemon=True).start()
    
    def _on_load_more(self):
        self._do_search(reset=False)

    def _on_search(self, event=None):
        query = self.entry_search.get().strip()
        if not query:
            return
        project_type = self.combo_type.get()
        mc_version = None
        loader = None
        if self.get_server_info:
            try:
                info = self.get_server_info()
                if info:
                    _, mc_version, loader = info
            except Exception:
                pass
        self._search_query = query
        self._search_project_type = project_type
        self._search_mc_version = mc_version
        self._search_loader = loader
        self._do_search(reset=True)

    def _load_popular_mods(self):
        """Fetch and show popular mods."""
        mc_version = None
        loader = None
        if self.get_server_info:
            try:
                info = self.get_server_info()
                if info: _, mc_version, loader = info
            except Exception as e:
                logger.debug("Modrinth get_server_info failed: %s", e)

        self._set_status("Loading popular mods...", busy=True)
        
        def _do_load():
            try:
                results = self.client.search(
                    "", mc_version=mc_version, loader=loader,
                    project_type="mod", limit=20,
                )
                hits = results.get("hits", [])
                self._current_hits = hits
                self._search_total = results.get("total_hits", len(hits))
                total_shown = len(hits)
                self.after(0, lambda: self._render_results(total_shown))
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
    def _render_results(self, total_shown: int):
        for w in self.results_frame.winfo_children():
            w.destroy()

        if not self._current_hits:
            self._show_placeholder("No results found.\nTry a different search term.")
            self.lbl_count.configure(text="0 results")
            return

        self.lbl_count.configure(text=f"{total_shown} of {self._search_total} results")

        for idx, hit in enumerate(self._current_hits):
            card = self._create_mod_card(hit, idx)
            card.grid(row=idx, column=0, sticky="ew", padx=6, pady=3)

        if total_shown < self._search_total:
            btn_more = ctk.CTkButton(
                self.results_frame, text="Load More", width=140, height=36,
                corner_radius=12,
                fg_color=("#e2e8f0", "#334155"),
                hover_color=("#cbd5e1", "#475569"),
                text_color=("black", "white"),
                font=("Roboto Medium", 12),
                command=self._on_load_more,
            )
            btn_more.grid(row=len(self._current_hits), column=0, pady=10)

    def _create_mod_card(self, hit: dict, index: int) -> ctk.CTkFrame:
        title = hit.get("title", "Unknown")
        initial = title[0].upper() if title else "?"
        icon_url = hit.get("icon_url", "")
        import hashlib
        _ICON_COLORS = ["#3b82f6", "#ef4444", "#22c55e", "#f97316", "#8b5cf6", "#ec4899"]
        color = _ICON_COLORS[int(hashlib.md5(title.encode()).hexdigest(), 16) % len(_ICON_COLORS)]

        card = ctk.CTkFrame(
            self.results_frame,
            corner_radius=12,
        )
        card_inner = ctk.CTkScrollableFrame(card, fg_color="transparent")
        
        icon_frame = ctk.CTkFrame(card, width=48, height=48, corner_radius=12, fg_color=color)
        icon_frame.grid(row=0, column=0, rowspan=2, padx=(12, 8), pady=12, sticky="n")
        icon_frame.grid_propagate(False)
        lbl_initial = ctk.CTkLabel(icon_frame, text=initial, font=("Roboto Medium", 20),
                                   text_color="white")
        lbl_initial.place(relx=0.5, rely=0.5, anchor="center")

        # Async load real icon
        if icon_url and icon_url not in _ICON_CACHE:
            threading.Thread(target=self._load_icon, args=(icon_url, icon_frame, lbl_initial), daemon=True).start()
        elif icon_url in _ICON_CACHE:
            self._apply_icon(icon_frame, lbl_initial, _ICON_CACHE[icon_url])

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
                corner_radius=12, padx=8, pady=2,
            )
            badge.pack(side="left", padx=(0, 4))

        # --- Install button ---
        btn_install = ctk.CTkButton(
            card, text="Install", width=80, height=32,
            corner_radius=12,
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
        if not self.get_server_info:
            self._set_status("⚠ No server selected — cannot install.")
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

        self._set_status(f"Loading versions for {title}…", busy=True)

        def _fetch_versions():
            try:
                versions = self.client.get_versions(slug, mc_version=mc_version, loader=loader)
                if not versions:
                    self.after(0, lambda: self._set_status(f"✗ No compatible versions of {title} found."))
                    return
                if len(versions) == 1:
                    self._do_install_version(versions[0], server_name, loader, title)
                else:
                    self.after(0, lambda: self._show_version_picker(versions, server_name, loader, title))
            except Exception as exc:
                self.after(0, lambda: self._set_status(f"✗ Failed to load versions: {exc}"))

        threading.Thread(target=_fetch_versions, daemon=True).start()

    def _do_install_version(self, version, server_name, loader, title):
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
                else:
                    self.after(0, lambda: self._set_status(f"✗ Install failed for {title}."))
            except Exception as exc:
                self.after(0, lambda: self._set_status(f"✗ Install failed: {exc}"))
        threading.Thread(target=_install, daemon=True).start()

    def _show_version_picker(self, versions, server_name, loader, title):
        dialog = ctk.CTkToplevel(self)
        dialog.title(f"Choose Version — {title}")
        dialog.geometry("460x320")
        dialog.transient(self.winfo_toplevel())
        dialog.grab_set()

        frame = ctk.CTkScrollableFrame(dialog, corner_radius=12)
        frame.pack(fill="both", expand=True, padx=12, pady=(12, 0))

        ctk.CTkLabel(
            frame, text=f"Select a version to install:",
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
                    self._do_install_version(v, server_name, loader, title)
                    break

        btn_frame = ctk.CTkFrame(dialog, fg_color="transparent")
        btn_frame.pack(fill="x", padx=12, pady=10)

        ctk.CTkButton(btn_frame, text="Cancel", width=90, height=32,
                       corner_radius=12, command=dialog.destroy).pack(side="right", padx=4)
        ctk.CTkButton(btn_frame, text="Install", width=90, height=32,
                       corner_radius=12, fg_color=_MODRINTH_GREEN, hover_color=_MODRINTH_GREEN_HOVER,
                       text_color="white", command=_on_confirm).pack(side="right", padx=4)

    def _on_install_optimizers(self):
        if not self.get_server_info: return
        info = self.get_server_info()
        if not info:
            self._set_status("⚠ Select a server first.")
            return
        server_name, mc_version, loader = info
        
        self._set_status("Installing Optimizer Bundle...", busy=True)
        def _run_opt():
            for mod in self.OPTIMIZERS:
                self.after(0, lambda m=mod: self._set_status(f"Installing {m['name']}..."))
                try:
                    self.client.download_mod(
                        mod["slug"], server_name, mc_version, loader
                    )
                except Exception as e:
                    logger.error("Failed to install %s: %s", mod["name"], e)
            self.after(0, lambda: self._set_status("Ready"))
        threading.Thread(target=_run_opt, daemon=True).start()

    def _on_check_updates(self):
        if not self.get_server_info:
            self._set_status("⚠ No server selected.")
            return
        info = self.get_server_info()
        if not info:
            self._set_status("⚠ Select a server first.")
            return
        server_name, mc_version, loader = info

        self._set_status("Checking for updates…", busy=True)

        def _check():
            try:
                updates = self.client.check_updates(server_name, mc_version, loader)
                self.after(0, lambda: self._show_updates_dialog(updates))
            except Exception as exc:
                self.after(0, lambda: self._set_status(f"✗ Update check failed: {exc}"))
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

        lbl_title = ctk.CTkLabel(
            frame, text=f"{len(updates)} update(s) available",
            font=("Roboto Medium", 16), anchor="w",
        )
        lbl_title.grid(row=0, column=0, sticky="w", pady=(0, 10))

        for i, u in enumerate(updates):
            card = ctk.CTkFrame(frame, corner_radius=8)
            card.grid(row=i + 1, column=0, sticky="ew", pady=3)
            card.grid_columnconfigure(0, weight=1)

            ctk.CTkLabel(card, text=u["filename"], font=("Roboto Medium", 13), anchor="w").grid(
                row=0, column=0, sticky="w", padx=10, pady=(8, 0))
            ctk.CTkLabel(card, text=f"→ {u.get('latest_version', 'newer version')} available",
                         font=AppConfig.FONT_BODY_SMALL, anchor="w").grid(
                row=1, column=0, sticky="w", padx=10, pady=(0, 8))

        btn_close = ctk.CTkButton(dialog, text="Close", width=100, height=32,
                                   corner_radius=12, command=dialog.destroy)
        btn_close.pack(pady=8)

    def _on_show_installed(self):
        if not self.get_server_info:
            self._set_status("⚠ No server selected.")
            return
        info = self.get_server_info()
        if not info:
            self._set_status("⚠ Select a server first.")
            return
        server_name = info[0]

        dialog = ctk.CTkToplevel(self)
        dialog.title("Installed Mods / Plugins")
        dialog.geometry("500x400")
        dialog.transient(self.winfo_toplevel())
        dialog.grab_set()

        frame = ctk.CTkScrollableFrame(dialog, corner_radius=12)
        frame.pack(fill="both", expand=True, padx=12, pady=(12, 0))
        frame.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(
            frame, text=f"Installed files for '{server_name}':",
            font=("Roboto Medium", 14), anchor="w",
        ).grid(row=0, column=0, sticky="w", pady=(0, 10))

        mods_dir = os.path.join(SERVERS_DIR, server_name, "mods")
        plugins_dir = os.path.join(SERVERS_DIR, server_name, "plugins")
        files = []
        for d in [mods_dir, plugins_dir]:
            if os.path.isdir(d):
                for fname in sorted(os.listdir(d)):
                    if fname.endswith(".jar"):
                        files.append(os.path.join(d, fname))

        if not files:
            ctk.CTkLabel(frame, text="No mods or plugins installed.",
                         font=AppConfig.FONT_BODY, text_color=AppConfig.COLOR_TEXT_NOTE).grid(
                row=1, column=0, pady=20)
        else:
            delete_btns = []
            for i, fpath in enumerate(files):
                fname = os.path.basename(fpath)
                row_frame = ctk.CTkFrame(frame, corner_radius=8)
                row_frame.grid(row=i + 1, column=0, sticky="ew", pady=2)
                row_frame.grid_columnconfigure(0, weight=1)

                ctk.CTkLabel(row_frame, text=fname, font=("Roboto", 12), anchor="w").grid(
                    row=0, column=0, sticky="w", padx=10, pady=6)

                btn_del = ctk.CTkButton(
                    row_frame, text="🗑", width=36, height=28,
                    corner_radius=8,
                    fg_color="#ef4444", hover_color="#dc2626",
                    font=("Roboto", 12),
                    command=lambda fp=fpath: self._confirm_delete_mod(fp, dialog),
                )
                btn_del.grid(row=0, column=1, padx=(0, 6), pady=4)

        ctk.CTkButton(dialog, text="Close", width=100, height=32,
                       corner_radius=12, command=dialog.destroy).pack(pady=10)

    def _confirm_delete_mod(self, filepath, dialog):
        fname = os.path.basename(filepath)
        if not tkinter.messagebox.askyesno("Delete Mod", f"Delete '{fname}'?"):
            return
        try:
            os.remove(filepath)
            self._set_status(f"✓ Deleted {fname}")
            dialog.destroy()
            self._on_show_installed()
        except OSError as e:
            self._set_status(f"✗ Failed to delete {fname}: {e}")

    def _load_icon(self, icon_url, icon_frame, lbl_initial):
        try:
            resp = requests.get(icon_url, timeout=8)
            resp.raise_for_status()
            img = Image.open(io.BytesIO(resp.content)).resize((48, 48), Image.LANCZOS)
            ctk_img = ctk.CTkImage(img, size=(48, 48))
            _ICON_CACHE[icon_url] = ctk_img
            self.after(0, lambda: self._apply_icon(icon_frame, lbl_initial, ctk_img))
        except Exception:
            pass

    def _apply_icon(self, icon_frame, lbl_initial, ctk_img):
        lbl_initial.destroy()
        lbl_icon = ctk.CTkLabel(icon_frame, image=ctk_img, text="")
        lbl_icon.place(relx=0.5, rely=0.5, anchor="center")

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
