import customtkinter as ctk
import logging
import os
import sys
import threading
import concurrent.futures
import webbrowser
import time
import subprocess
import tkinter.messagebox

logger = logging.getLogger(__name__)

# --- Tcl/Tk Fix for Windows Virtual Environments ---
if sys.platform == "win32" and hasattr(sys, 'base_prefix'):
    tcl_dir = os.path.join(sys.base_prefix, "tcl")
    if os.path.exists(tcl_dir):
        for d in os.listdir(tcl_dir):
            if d.startswith("tcl"): os.environ["TCL_LIBRARY"] = os.path.join(tcl_dir, d)
            if d.startswith("tk"): os.environ["TK_LIBRARY"] = os.path.join(tcl_dir, d)

# Add parent directory to path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.ui.ui_components import ConsoleWidget, ServerListItem, DownloadProgressDialog, ToolTip, ZBBDialog
from app.ui.icons import icon

import app.core.logic as logic
from app.core.constants import SERVERS_DIR, ASSETS_DIR
from app.ui.server_wizard import ServerWizard
from app.ui.server_properties_editor import ServerPropertiesEditor
from app.core.server_events import ServerEvent, EventBus
from app.core.app_config import AppConfig
from app.ui.modrinth_browser import ModrinthBrowser
from app.services.sanitizer import is_safe_command
from app.ui.toast import Toast
from app.core.core import ZBBManager
from app.ui.players_dashboard import PlayersDashboard

ctk.set_appearance_mode("Dark")
_theme_path = ASSETS_DIR / "zbb_theme.json"
ctk.set_default_color_theme(str(_theme_path) if _theme_path.exists() else "green")

class MCTunnelApp(ctk.CTk):
    def __init__(self):
        from app.services.settings_manager import SettingsManager
        from app.core.constants import CONFIG_DIR
        settings_manager = SettingsManager()
        settings_manager.set_config_dir(str(CONFIG_DIR))
        theme = settings_manager.get("theme", "Dark")
        ctk.set_appearance_mode(theme)
        
        super().__init__()
        self._init_window_config()
        self._init_state_variables()
        self._build_layout()
        self._init_background_services()

    def _init_window_config(self):
        self.title(AppConfig.WINDOW_TITLE)
        self.geometry(f"{AppConfig.DEFAULT_WIDTH}x{AppConfig.DEFAULT_HEIGHT}")
        self.minsize(AppConfig.MIN_WIDTH, AppConfig.MIN_HEIGHT)
        self.grid_columnconfigure(0, weight=0, minsize=300)
        self.grid_columnconfigure(1, weight=1)
        self.grid_rowconfigure(0, weight=1)

    def _init_state_variables(self):
        self.claim_url = None
        self.server_items = {}

        self.events = EventBus()
        self.zbb_manager = ZBBManager(self.events)
        self.executor = concurrent.futures.ThreadPoolExecutor(max_workers=10, thread_name_prefix='UI_Worker')
        
        self.events.subscribe(ServerEvent.CONSOLE_LINE, self.update_console)
        self.events.subscribe(ServerEvent.NOTIFICATION, self._handle_notification)
        self.events.subscribe(ServerEvent.TUNNEL_CONSOLE_LINE, self.update_tunnel_console)
        self.events.subscribe(ServerEvent.TUNNEL_STATUS, self.on_tunnel_status)
        self.events.subscribe(ServerEvent.READY, self.on_server_ready)
        self.events.subscribe(ServerEvent.STARTING, self.on_server_starting)
        self.events.subscribe(ServerEvent.STOPPED, self.on_server_stopped)
        self.events.subscribe(ServerEvent.PLAYER_COUNT, self.on_player_count_update)
        # Toast notification for lag spikes
        self.events.subscribe(ServerEvent.LAG_SPIKE, lambda d: self.after(0, lambda: (
            self.update_console("[Watchdog] Lag threshold exceeded. Consider reducing world size or adding more RAM."),
            Toast.show(self, "Lag spike threshold exceeded", toast_type="warning"),
        )))

    def _build_layout(self):
        self._build_sidebar()
        self._build_main_area()

    def _build_sidebar(self):
        self.sidebar_frame = ctk.CTkFrame(self, width=300, corner_radius=0, fg_color=(AppConfig.COLOR_BG_SIDEBAR_LIGHT, AppConfig.COLOR_BG_SIDEBAR_DARK))
        self.sidebar_frame.grid(row=0, column=0, sticky="nsew")
        self.sidebar_frame.grid_rowconfigure(4, weight=1) # List frame should expand, NOT the label
        self.sidebar_frame.grid_columnconfigure(0, weight=1)

        # Logo
        try:
            from PIL import Image
            logo_path = ASSETS_DIR / "logo.png"
            if logo_path.exists():
                pil_image = Image.open(logo_path)
                self.logo_image = ctk.CTkImage(light_image=pil_image, dark_image=pil_image, size=(150, 100)) # Logo size (width, height)
                self.logo_label = ctk.CTkLabel(self.sidebar_frame, text="", image=self.logo_image)
            else:
                self.logo_label = ctk.CTkLabel(self.sidebar_frame, text="Zero Block\nBridge", font=AppConfig.FONT_TITLE)
        except Exception as e:
            logger.error("Error loading logo: %s", e)
            self.logo_label = ctk.CTkLabel(self.sidebar_frame, text="Zero Block\nBridge", font=AppConfig.FONT_TITLE)
            
        self.logo_label.grid(row=0, column=0, padx=20, pady=(15, 5))

        # --- Actions Group ---
        self.actions_frame = ctk.CTkFrame(self.sidebar_frame, fg_color="transparent")
        self.actions_frame.grid(row=1, column=0, padx=20, pady=(10, 0), sticky="ew")
        self.actions_frame.grid_columnconfigure(0, weight=1)

        self.btn_create_server = ctk.CTkButton(
            self.actions_frame, text="Create New Server",
            image=icon("plus", 14, "#ffffff"),
            command=self.create_server_dialog, corner_radius=AppConfig.RADIUS_BTN, height=36,
            fg_color=AppConfig.COLOR_BTN_PRIMARY, hover_color=AppConfig.COLOR_BTN_PRIMARY_HOVER,
            font=(AppConfig.FONT_FAMILY_DISPLAY, 13, "bold")
        )
        self.btn_create_server.pack(fill="x", pady=(0, 5))

        self.btn_add_server = ctk.CTkButton(
            self.actions_frame, text="Add Server",
            image=icon("folder", 14),
            command=self.show_add_server_menu, corner_radius=AppConfig.RADIUS_BTN, height=32,
            fg_color="transparent", border_width=1,
            border_color=(AppConfig.COLOR_BORDER_LIGHT, AppConfig.COLOR_BORDER_DARK),
            text_color=("#0f172a", AppConfig.COLOR_TEXT_PRIMARY),
            hover_color=(AppConfig.COLOR_BG_CARD_LIGHT, AppConfig.COLOR_BTN_GHOST),
            font=(AppConfig.FONT_FAMILY, 12)
        )
        self.btn_add_server.pack(fill="x", pady=(0, 10))

        # --- Separator ---
        self.sep = ctk.CTkFrame(self.sidebar_frame, height=2,
                                fg_color=(AppConfig.COLOR_BORDER_LIGHT, AppConfig.COLOR_BORDER_DARK))
        self.sep.grid(row=2, column=0, padx=25, pady=5, sticky="ew")

        # --- List Group ---
        self.lbl_servers = ctk.CTkLabel(
            self.sidebar_frame, text="YOUR SERVERS",
            anchor="w", font=(AppConfig.FONT_FAMILY_DISPLAY, 11, "bold"), text_color=AppConfig.COLOR_TEXT_GRAY
        )
        self.lbl_servers.grid(row=3, column=0, padx=25, pady=(5, 2), sticky="w")

        self.server_list_frame = ctk.CTkScrollableFrame(
            self.sidebar_frame, label_text="", corner_radius=AppConfig.RADIUS_CARD,
            border_width=0,
            fg_color=(AppConfig.COLOR_BG_CARD_LIGHT, AppConfig.COLOR_BG_CARD_DARK)
        )
        self.server_list_frame.grid(row=4, column=0, padx=20, pady=(5, 15), sticky="nsew")

    def _build_main_area(self):
        self.main_frame = ctk.CTkFrame(self, corner_radius=0, fg_color=(AppConfig.COLOR_BG_LIGHT, AppConfig.COLOR_BG_DARK))
        self.main_frame.grid(row=0, column=1, sticky="nsew")
        self.main_frame.grid_rowconfigure(0, weight=0) # Status bar
        self.main_frame.grid_rowconfigure(1, weight=0) # Compact Dashboard (Controls & Tunnel)
        self.main_frame.grid_rowconfigure(2, weight=1) # Console tabs & Mods (Prominent)
        self.main_frame.grid_columnconfigure(0, weight=1)
        self._build_status_bar()
        self._build_dashboard()
        self._build_console_tabs()

    def _build_status_bar(self):
        self.status_frame = ctk.CTkFrame(self.main_frame, height=45, corner_radius=AppConfig.RADIUS_CARD, fg_color=(AppConfig.COLOR_BG_CARD_LIGHT, AppConfig.COLOR_BG_CARD_DARK))
        self.status_frame.grid(row=0, column=0, sticky="ew", padx=15, pady=(10, 2))

        self.lbl_status = ctk.CTkLabel(self.status_frame, text="● Offline",
                                       font=(AppConfig.FONT_FAMILY_DISPLAY, 15, "bold"),
                                       text_color=AppConfig.COLOR_STATUS_OFFLINE)
        self.lbl_status.pack(side="left", padx=20, pady=8)

        self.btn_start = ctk.CTkButton(self.status_frame, text="", image=icon("play", 14, "#ffffff"), state="disabled", command=self.start_server_action, fg_color=AppConfig.COLOR_BTN_SUCCESS, hover_color=AppConfig.COLOR_BTN_SUCCESS_HOVER, width=45, corner_radius=AppConfig.RADIUS_BTN, height=36)
        self.btn_start.pack(side="left", padx=2)
        ToolTip(self.btn_start, "Start server")
        self.btn_stop = ctk.CTkButton(self.status_frame, text="", image=icon("stop", 14, "#ffffff"), state="disabled", command=self.stop_server_action, fg_color=AppConfig.COLOR_BTN_DANGER, hover_color=AppConfig.COLOR_BTN_DANGER_HOVER, width=45, corner_radius=AppConfig.RADIUS_BTN, height=36)
        self.btn_stop.pack(side="left", padx=2)
        ToolTip(self.btn_stop, "Stop server")

        _ghost_hover = (AppConfig.COLOR_BG_SIDEBAR_LIGHT, AppConfig.COLOR_BTN_GHOST_HOVER)
        self.btn_config = ctk.CTkButton(
            self.status_frame, text="", image=icon("gear", 17), width=36, height=36,
            corner_radius=AppConfig.RADIUS_BTN, fg_color="transparent", hover_color=_ghost_hover,
            command=self.edit_server_properties,
            state="disabled"
        )
        self.btn_config.pack(side="left", padx=5)
        ToolTip(self.btn_config, "Server settings")

        self.btn_open_folder = ctk.CTkButton(
            self.status_frame, text="", image=icon("folder", 16), width=36, height=36,
            corner_radius=AppConfig.RADIUS_BTN, fg_color="transparent", hover_color=_ghost_hover,
            command=self.open_server_folder,
            state="disabled"
        )
        self.btn_open_folder.pack(side="left", padx=5)
        ToolTip(self.btn_open_folder, "Open server folder")

        self.lbl_dash_title = ctk.CTkLabel(self.status_frame, text="Select a server", font=AppConfig.FONT_HEADING)
        self.lbl_dash_title.pack(side="left", padx=(5, 10), pady=8)

        self.status_right_frame = ctk.CTkFrame(self.status_frame, fg_color="transparent")
        self.status_right_frame.pack(side="right", fill="x", expand=True, padx=5, pady=8)

        badge_java = ctk.CTkFrame(
            self.status_right_frame, fg_color="transparent"
        )
        badge_java.pack(side="right", padx=(5, 10))
        self.lbl_java_ver = ctk.CTkLabel(
            badge_java, text="Checking...", text_color=AppConfig.COLOR_TEXT_GRAY,
            font=AppConfig.FONT_BODY_SMALL
        )
        self.lbl_java_ver.pack(padx=8, pady=2)

        badge_server_info = ctk.CTkFrame(
            self.status_right_frame, fg_color="transparent"
        )
        badge_server_info.pack(side="right", padx=(5, 10))
        self.lbl_server_info = ctk.CTkLabel(
            badge_server_info, text="No server selected", text_color=AppConfig.COLOR_TEXT_GRAY,
            font=AppConfig.FONT_BODY_SMALL
        )
        self.lbl_server_info.pack(padx=8, pady=2)

        badge_players = ctk.CTkFrame(
            self.status_right_frame, fg_color=AppConfig.COLOR_BADGE_BG, corner_radius=AppConfig.RADIUS_BADGE
        )
        badge_players.pack(side="right", padx=(5, 5))
        self.btn_players = ctk.CTkButton(
            badge_players,
            text="0",
            image=icon("user", 13, AppConfig.COLOR_BADGE_TEXT),
            command=self.open_players_dashboard,
            fg_color="transparent",
            text_color=AppConfig.COLOR_BADGE_TEXT,
            hover_color=(AppConfig.COLOR_BG_SIDEBAR_LIGHT, AppConfig.COLOR_BTN_GHOST_HOVER),
            font=AppConfig.FONT_BODY_SMALL,
            height=24,
            width=60
        )
        self.btn_players.pack(padx=2, pady=2)
        ToolTip(self.btn_players, "Players online")



    def _build_dashboard(self):
        self.dashboard_frame = ctk.CTkFrame(self.main_frame, corner_radius=AppConfig.RADIUS_CARD, fg_color=(AppConfig.COLOR_BG_CARD_LIGHT, AppConfig.COLOR_BG_CARD_DARK))
        self.dashboard_frame.grid(row=1, column=0, sticky="ew", padx=15, pady=(2, 10))
 
        # --- Tunnel ---
        self.tunnel_frame = ctk.CTkFrame(self.dashboard_frame, fg_color="transparent")
        self.tunnel_frame.pack(fill="x", padx=15, pady=(4, 4))
        self._build_tunnel_controls()

    def _build_tunnel_controls(self):
        self.lbl_tunnel_status = ctk.CTkLabel(self.tunnel_frame, text="Tunnel: Offline", text_color=AppConfig.COLOR_TEXT_GRAY, font=AppConfig.FONT_BODY)
        self.lbl_tunnel_status.pack(side="left", padx=(20, 5))

        self.ip_frame = ctk.CTkFrame(self.tunnel_frame, fg_color="transparent")
        self.ip_frame.pack(side="left", fill="x", expand=True)

        self.lbl_dns_display = ctk.CTkLabel(self.ip_frame, text="", font=(AppConfig.FONT_FAMILY_DISPLAY, 13, "bold"), text_color=AppConfig.COLOR_LINK)
        self.lbl_dns_display.pack(side="left", padx=(5, 0))

        self.btn_copy_ip = ctk.CTkButton(
            self.ip_frame, text="", image=icon("copy", 14, AppConfig.COLOR_LINK),
            command=self._copy_ip_to_clipboard,
            fg_color="transparent",
            hover_color=(AppConfig.COLOR_BG_SIDEBAR_LIGHT, AppConfig.COLOR_BTN_GHOST_HOVER),
            border_width=1, border_color=AppConfig.COLOR_LINK,
            width=36, corner_radius=AppConfig.RADIUS_BTN, height=28,
        )
        ToolTip(self.btn_copy_ip, "Copy address")

        self.tunnel_toolbar = ctk.CTkFrame(self.tunnel_frame, fg_color="transparent")
        self.tunnel_toolbar.pack(side="right", padx=10)

        self.btn_tunnel_start = ctk.CTkButton(self.tunnel_toolbar, text="", image=icon("play", 14, "#ffffff"), command=self.start_tunnel, width=45, corner_radius=AppConfig.RADIUS_BTN, height=36, fg_color=AppConfig.COLOR_BTN_SUCCESS, hover_color=AppConfig.COLOR_BTN_SUCCESS_HOVER)
        ToolTip(self.btn_tunnel_start, "Start tunnel")
        self.btn_tunnel_stop = ctk.CTkButton(self.tunnel_toolbar, text="", image=icon("stop", 14, "#ffffff"), command=self.stop_tunnel, state="disabled", fg_color=AppConfig.COLOR_BTN_DANGER, hover_color=AppConfig.COLOR_BTN_DANGER_HOVER, width=45, corner_radius=AppConfig.RADIUS_BTN, height=36)
        ToolTip(self.btn_tunnel_stop, "Stop tunnel")

        # --- Playit Account Linking (collapsible when unlinked) ---
        self._setup_expanded = False
        self.btn_toggle_setup = ctk.CTkButton(
            self.tunnel_toolbar, text="Link", image=icon("bolt", 14, AppConfig.COLOR_ACCENT_AMBER),
            command=self._toggle_setup_section,
            fg_color=(AppConfig.COLOR_BG_SIDEBAR_LIGHT, AppConfig.COLOR_BTN_GHOST),
            hover_color=(AppConfig.COLOR_BORDER_LIGHT, AppConfig.COLOR_BTN_GHOST_HOVER),
            border_width=1, border_color=AppConfig.COLOR_ACCENT_AMBER,
            width=80, corner_radius=AppConfig.RADIUS_BTN, height=36,
            font=(AppConfig.FONT_FAMILY_DISPLAY, 12, "bold"), text_color=AppConfig.COLOR_ACCENT_AMBER,
        )
        self.setup_frame = ctk.CTkFrame(self.tunnel_toolbar, fg_color="transparent")
        self.entry_setup_code = ctk.CTkEntry(self.setup_frame, placeholder_text="Paste Setup Code", width=200, height=36, corner_radius=AppConfig.RADIUS_INPUT)
        self.btn_link_code = ctk.CTkButton(self.setup_frame, text="Link", command=self._link_with_setup_code, width=60, height=36, corner_radius=AppConfig.RADIUS_BTN, fg_color=AppConfig.COLOR_BTN_PRIMARY, hover_color=AppConfig.COLOR_BTN_PRIMARY_HOVER)
        self.btn_claim = ctk.CTkButton(self.setup_frame, text="Get Code", command=self.open_claim_url, fg_color=AppConfig.COLOR_BTN_WARNING, hover_color=AppConfig.COLOR_BTN_WARNING_HOVER, width=70, corner_radius=AppConfig.RADIUS_BTN, height=36, font=(AppConfig.FONT_FAMILY_DISPLAY, 11, "bold"))

        self.btn_reset = ctk.CTkButton(self.tunnel_toolbar, text="", image=icon("reset", 15, AppConfig.COLOR_ACCENT_AMBER),
                                   command=self.reset_tunnel,
                                   fg_color=(AppConfig.COLOR_BG_SIDEBAR_LIGHT, AppConfig.COLOR_BTN_GHOST),
                                   hover_color=("#fde9c8", "#3a2e12"),
                                   border_width=1, border_color=AppConfig.COLOR_ACCENT_AMBER,
                                   width=45, corner_radius=AppConfig.RADIUS_BTN, height=36)
        self.btn_reset.pack(side="left", padx=2)
        ToolTip(self.btn_reset, "Reset tunnels")

        # Initial UI State Check
        self.after(500, lambda: self.on_tunnel_status({"status": "Offline"}))

    def _toggle_setup_section(self):
        self._setup_expanded = not self._setup_expanded
        if self._setup_expanded:
            import webbrowser
            webbrowser.open(AppConfig.PLAYIT_WIZARD_URL)
            self.tunnel_console.log(f"[UI] Opening Playit Setup Wizard...")
        self.on_tunnel_status({"status": "Offline", "skip_debounce": True})

    def _build_console_tabs(self):
        self.console_tabs = ctk.CTkTabview(self.main_frame)
        self.console_tabs.grid(row=2, column=0, padx=15, pady=(0, 15), sticky="nsew")
        
        self.console_tabs.add("Console")
        self.console_tabs.add("Tunnel Log")

        self._build_console_search_bar(self.console_tabs.tab("Console"), "server_console")
        self.server_console = ConsoleWidget(self.console_tabs.tab("Console"), max_lines=500)
        self.server_console.pack(fill="both", expand=True)

        self.console_input_frame = ctk.CTkFrame(self.console_tabs.tab("Console"), height=40, corner_radius=AppConfig.RADIUS_CARD, fg_color=(AppConfig.COLOR_CONSOLE_LIGHT, AppConfig.COLOR_CONSOLE_DARK))
        self.console_input_frame.pack(fill="x", pady=(5, 0))

        self.entry_console = ctk.CTkEntry(self.console_input_frame, placeholder_text="Select a server to send commands...", corner_radius=AppConfig.RADIUS_INPUT, height=36, state="disabled")
        self.entry_console.pack(side="left", fill="x", expand=True, padx=(10, 5), pady=5)
        self.entry_console.bind("<Return>", self.send_server_command)

        self.btn_send = ctk.CTkButton(self.console_input_frame, text="Send", width=80, command=self.send_server_command, corner_radius=AppConfig.RADIUS_BTN, height=36, fg_color=AppConfig.COLOR_BTN_PRIMARY, hover_color=AppConfig.COLOR_BTN_PRIMARY_HOVER, state="disabled")
        self.btn_send.pack(side="right", padx=10, pady=5)

        self._build_console_search_bar(self.console_tabs.tab("Tunnel Log"), "tunnel_console")
        self.tunnel_console = ConsoleWidget(self.console_tabs.tab("Tunnel Log"), max_lines=500)
        self.tunnel_console.pack(fill="both", expand=True)

        # --- Mods Tab (Modrinth Browser) ---
        self.console_tabs.add("Mods")
        self.modrinth_browser = ModrinthBrowser(
            self.console_tabs.tab("Mods"),
            get_server_info=self._get_current_server_info,
        )
        self.modrinth_browser.pack(fill="both", expand=True)
        self._update_mods_tab_state()

    def _init_background_services(self):
        self.check_java_startup()
        self.load_servers()
        self.zbb_manager.bootstrap()
        # Pre-warm now handled by ZBBManager.bootstrap() → core.py

    def _build_console_search_bar(self, parent, console_attr):
        bar = ctk.CTkFrame(parent, fg_color="transparent")
        bar.pack(fill="x", pady=(0, 5))

        entry = ctk.CTkEntry(bar, placeholder_text="Search console...", corner_radius=AppConfig.RADIUS_INPUT, height=30)
        entry.pack(side="left", fill="x", expand=True, padx=(0, 5))

        def do_search(event=None):
            console = getattr(self, console_attr)
            console.highlight(entry.get())

        def do_next(event=None):
            console = getattr(self, console_attr)
            pattern = entry.get()
            if pattern != getattr(console, "_last_pattern", None) or not getattr(console, "_search_matches", None):
                console.highlight(pattern)
            else:
                console.jump_to_next_match()

        entry.bind("<Return>", do_search)

        btn_next = ctk.CTkButton(bar, text="Next", width=60, height=30, corner_radius=AppConfig.RADIUS_BTN,
                                  command=do_next)
        btn_next.pack(side="right")

    def send_server_command(self, event=None):
        if not self.zbb_manager.is_running():
            self.server_console.log("[UI] Server is not running.")
            return
        cmd = self.entry_console.get()
        if not cmd: return
        safe, reason = is_safe_command(cmd)
        if not safe:
            self.server_console.log(f"[Security] Command blocked: {reason}")
            logger.warning("Blocked command from user: %r (reason: %s)", cmd, reason)
            self.entry_console.delete(0, "end")
            return
        self.zbb_manager.send_command(cmd)
        self.entry_console.delete(0, "end")

    def check_java_startup(self):
        def _check():
            from app.services.java_detector import JavaDetector
            detector = JavaDetector()
            installations = detector.detect_all()
            if installations:
                best = installations[0]
                source_badge = "Portable" if best.source == "PORTABLE" else "System"
                label = f"Java {best.major} ({source_badge})"
                self.after(0, lambda: self.lbl_java_ver.configure(text=label, text_color=AppConfig.COLOR_BTN_SUCCESS))
                self.after(0, lambda: self.server_console.log(f"[System] Found Java: {best.version_string}"))
            else:
                self.after(0, lambda: self.lbl_java_ver.configure(text="No Java", text_color=AppConfig.COLOR_STATUS_ERROR))
                self.after(0, lambda: self.server_console.log("[System] No Java detected on this system. ZeroBlockBridge will auto-install the required JDK when the server starts."))
        self.executor.submit(_check)

    def load_servers(self):
        def _scan():
            try:
                if not os.path.exists(SERVERS_DIR):
                    os.makedirs(SERVERS_DIR, exist_ok=True)
                servers = [d for d in os.listdir(SERVERS_DIR) if os.path.isdir(os.path.join(SERVERS_DIR, d))]
            except OSError as e:
                logger.warning("Failed to scan servers: %s", e)
                servers = []
            self.after(0, lambda s=servers: self._render_server_list(s))
        self.executor.submit(_scan)

    def _render_server_list(self, servers):
        for widget in self.server_list_frame.winfo_children():
            widget.destroy()
        self.server_items = {}
        if not servers:
            ctk.CTkLabel(
                self.server_list_frame, text="",
                image=icon("package", 40, (AppConfig.COLOR_TEXT_MUTED, AppConfig.COLOR_TEXT_MUTED))
            ).pack(pady=(24, 4))
            ctk.CTkLabel(
                self.server_list_frame, text="No servers yet.",
                text_color=AppConfig.COLOR_TEXT_MUTED, font=(AppConfig.FONT_FAMILY, 13)
            ).pack(pady=(0, 6))
            ctk.CTkButton(
                self.server_list_frame, text="Create your first server",
                command=self.create_server_dialog,
                fg_color=AppConfig.COLOR_BTN_PRIMARY,
                hover_color=AppConfig.COLOR_BTN_PRIMARY_HOVER,
                corner_radius=AppConfig.RADIUS_BTN, height=32
            ).pack(padx=16)
        else:
            for s in servers:
                item = ServerListItem(self.server_list_frame, server_name=s, on_click=self.on_server_select,
                                      on_delete=self.on_server_delete, on_export=self.on_server_export)
                item.pack(fill="x", padx=5, pady=5)
                self.server_items[s] = item
        self.server_console.log(f"[System] Loaded {len(servers)} servers.")

    def _update_mods_tab_state(self):
        """Mods tab is only usable with a server selected."""
        enabled = bool(self.zbb_manager.current_server)
        try:
            btn = self.console_tabs._segmented_button._buttons_dict["Mods"]
            btn.configure(state="normal" if enabled else "disabled")
        except (AttributeError, KeyError) as e:
            logger.debug("Mods tab state update failed: %s", e)
        if not enabled and self.console_tabs.get() == "Mods":
            self.console_tabs.set("Console")

    def on_server_delete(self, server_name):
        if self.zbb_manager.is_running() and self.zbb_manager.current_server == server_name:
            Toast.show(self, "Stop the server before deleting it", toast_type="warning")
            return
        confirmed = ZBBDialog.confirm(
            self, "Delete Server",
            f"Delete '{server_name}' permanently?\n\n"
            "The world, configs and everything inside the server folder "
            "will be removed. This cannot be undone.\n\n"
            "(Imported servers: only the link is removed, the original "
            "folder is kept.)",
            confirm_text="Delete", danger=True,
        )
        if not confirmed:
            return
        try:
            logic.delete_server(server_name)
        except OSError as e:
            Toast.show(self, f"Delete failed: {e}", toast_type="error")
            return
        if self.zbb_manager.current_server == server_name:
            self.zbb_manager.current_server = None
            self.lbl_dash_title.configure(text="Select a server")
            self.lbl_server_info.configure(text="No server selected", text_color=AppConfig.COLOR_BADGE_TEXT)
            self.btn_start.configure(state="disabled")
            self.btn_stop.configure(state="disabled")
            self._update_mods_tab_state()
        Toast.show(self, f"Server '{server_name}' deleted", toast_type="info")
        self.load_servers()

    def on_server_export(self, server_name):
        from tkinter import filedialog
        from app.services.migration import export_server, MigrationError

        dest_path = filedialog.asksaveasfilename(
            defaultextension=".zbbpack",
            initialfile=f"{server_name}.zbbpack",
            filetypes=[("ZeroBlockBridge Pack", "*.zbbpack")],
        )
        if not dest_path:
            return
        try:
            export_server(server_name, dest_path)
        except (MigrationError, OSError) as e:
            Toast.show(self, f"Export failed: {e}", toast_type="error")
            return
        Toast.show(self, f"Server '{server_name}' exported", toast_type="info")

    def show_add_server_menu(self):
        import tkinter as tk
        menu = tk.Menu(
            self, tearoff=0,
            bg=AppConfig.COLOR_BG_CARD_DARK,
            fg=AppConfig.COLOR_TEXT_PRIMARY,
            activebackground=AppConfig.COLOR_BTN_GHOST_HOVER,
            activeforeground=AppConfig.COLOR_TEXT_PRIMARY,
            borderwidth=0,
        )
        menu.add_command(label="From Folder (existing server)", command=self.load_existing_server_action)
        menu.add_command(label="From .zbbpack (import)", command=self.on_import_zbbpack)
        btn = self.btn_add_server
        x = btn.winfo_rootx()
        y = btn.winfo_rooty() + btn.winfo_height()
        try:
            menu.tk_popup(x, y)
        finally:
            menu.grab_release()

    def on_import_zbbpack(self):
        from tkinter import filedialog
        from app.services.migration import import_server, MigrationError

        src_path = filedialog.askopenfilename(
            filetypes=[("ZeroBlockBridge Pack", "*.zbbpack")],
        )
        if not src_path:
            return
        new_name = os.path.splitext(os.path.basename(src_path))[0]
        try:
            import_server(src_path, new_name)
        except (MigrationError, OSError) as e:
            Toast.show(self, f"Import failed: {e}", toast_type="error")
            return
        Toast.show(self, f"Server '{new_name}' imported. Reinstall the server jar via Properties before starting.", toast_type="info")
        self.load_servers()

    def on_server_select(self, server_name):
        # UI Locking: Block switching if current server is active
        if self.zbb_manager.is_running() and self.zbb_manager.current_server != server_name:
            Toast.show(self, "Stop the current server before switching", toast_type="warning")
            return

        self.zbb_manager.select_server(server_name)
        self.lbl_dash_title.configure(text=f"{server_name}")

        for name, it in self.server_items.items():
            it.set_selected(name == server_name)

        meta = logic.get_server_meta(server_name)
        server_type = meta.get("type", "Vanilla") if meta else "Vanilla"
        mc_version = meta.get("version", "?") if meta else "?"
        self.lbl_server_info.configure(text=f"{server_type} {mc_version}", text_color=("#0f172a", AppConfig.COLOR_TEXT_PRIMARY))

        is_running = self.zbb_manager.is_running() and self.zbb_manager.current_server == server_name

        self.btn_start.configure(state="disabled" if is_running else "normal")
        self.btn_stop.configure(state="normal" if is_running else "disabled")

        if hasattr(self, "modrinth_browser"):
            self.modrinth_browser.refresh_server_context()
        self._update_mods_tab_state()

        item = self.server_items.get(server_name)
        if item:
            item.set_status("online" if is_running else "offline")

        self.btn_config.configure(state="normal")
        self.btn_open_folder.configure(state="normal")
        self.entry_console.configure(state="normal", placeholder_text="Type command here...")
        self.btn_send.configure(state="normal")
        self.server_console.log(f"[UI] Selected server: {server_name}")

    def _open_in_file_manager(self, path) -> None:
        try:
            if sys.platform == "win32":
                subprocess.run(["explorer", str(path)], check=False)
            elif sys.platform == "darwin":
                subprocess.run(["open", str(path)], check=False)
            else:
                subprocess.run(["xdg-open", str(path)], check=False)
        except Exception as e:
            self.server_console.log(f"[Error] Failed to open folder: {e}")

    def open_server_folder(self):
        if not self.zbb_manager.current_server:
            self._open_in_file_manager(SERVERS_DIR)
            return
        server_path = os.path.join(SERVERS_DIR, self.zbb_manager.current_server)
        if os.path.exists(server_path):
            self._open_in_file_manager(server_path)

    def _get_current_server_info(self):
        if not self.zbb_manager.current_server:
            return None
        meta = logic.get_server_meta(self.zbb_manager.current_server)
        mc_version = meta.get("version", "1.20.1")
        loader = None
        stype = meta.get("type", "Vanilla").lower()
        if stype in ("fabric", "forge", "paper", "purpur", "spigot"):
            loader = stype
        
        logger.info("Server Info for Mod Search: %s | MC: %s | Loader: %s", self.zbb_manager.current_server, mc_version, loader or 'any')
        return (self.zbb_manager.current_server, mc_version, loader)

    def save_advanced_settings(self, *args):
        if not self.zbb_manager.current_server: return
        label = self.var_java_path.get()
        path = getattr(self, "_java_label_to_path", {}).get(label, "auto")
        logic.update_server_meta(self.zbb_manager.current_server, {
            "advanced_mode": self.var_advanced_mode.get(),
            "java_path": path,
            "use_aikars": self.var_use_aikars.get(),
        })

    def edit_server_properties(self):
        if not self.zbb_manager.current_server: return
        if self.zbb_manager.is_running():
            self.server_console.log("[Error] Stop the server before editing properties.")
            return
        ServerPropertiesEditor(self, self.zbb_manager.current_server, logic, self.zbb_manager)

    def update_console(self, text):
        if isinstance(text, str):
            self.after(0, lambda: self.server_console.log(text))

    def _handle_notification(self, data):
        if data and isinstance(data, dict):
            msg = data.get("msg", "")
            toast_type = Toast.resolve_type(data)
            duration = 6000 if toast_type == "error" else 4000
            self.after(0, lambda: Toast.show(self, msg, toast_type=toast_type, duration=duration))

    def update_tunnel_console(self, text):
        self.after(0, lambda: self.tunnel_console.log(text))

    def start_server_action(self):
        def _start():
            self.zbb_manager.start_server()
        self.executor.submit(_start)

    def _set_current_server_pill(self, status: str):
        item = self.server_items.get(self.zbb_manager.current_server)
        if item:
            item.set_status(status)

    def on_server_starting(self, data=None):
        self.after(0, lambda: self.lbl_status.configure(text="● Starting...", text_color=AppConfig.COLOR_STATUS_STARTING))
        self.after(0, lambda: self.btn_start.configure(state="disabled"))
        self.after(0, lambda: self.btn_stop.configure(state="normal"))
        self.after(0, lambda: self._set_current_server_pill("starting"))
        if data and isinstance(data, dict):
            jdk_src = data.get("jdk_source", "unknown")
            java_ver = data.get("required_java", "?")
            label = f"Java {java_ver} ({jdk_src})"
            color = AppConfig.COLOR_STATUS_ONLINE if jdk_src == "system" else AppConfig.COLOR_STATUS_STARTING
            self.after(0, lambda: self.lbl_java_ver.configure(text=label, text_color=color))

    def on_server_ready(self, data=None):
        self.after(0, lambda: self.lbl_status.configure(text="● Running", text_color=AppConfig.COLOR_STATUS_ONLINE))
        self.after(0, lambda: self._set_current_server_pill("online"))

    def on_player_count_update(self, count):
        self.after(0, lambda: self.btn_players.configure(text=f"{count}"))

    def open_players_dashboard(self):
        if hasattr(self, "players_dashboard_window") and self.players_dashboard_window is not None and self.players_dashboard_window.winfo_exists():
            self.players_dashboard_window.focus()
        else:
            self.players_dashboard_window = PlayersDashboard(self, self.events, self.zbb_manager)

    def on_server_stopped(self, data=None):
        self.after(0, lambda: self.lbl_status.configure(text="● Offline", text_color=AppConfig.COLOR_STATUS_OFFLINE))
        self.after(0, lambda: self.btn_start.configure(state="normal"))
        self.after(0, lambda: self.btn_stop.configure(state="disabled"))
        self.after(0, lambda: self._set_current_server_pill("offline"))

    def stop_server_action(self):
        # Off the Tk thread: stop() blocks up to ~15s (graceful wait + kill).
        def _stop():
            self.zbb_manager.stop_server()
            self.on_server_stopped()
        self.executor.submit(_stop)

    def create_server_dialog(self):
        ServerWizard(self, on_complete_callback=self.on_wizard_complete)

    def on_wizard_complete(self, config):
        if os.path.exists(os.path.join(SERVERS_DIR, config["name"])):
            self.server_console.log(f"[Error] Server '{config['name']}' already exists.")
            return
            
        custom_loc = config.get("location", str(SERVERS_DIR))
        if custom_loc and os.path.normpath(custom_loc) != os.path.normpath(str(SERVERS_DIR)):
            from app.core.logic import create_junction
            target_path = os.path.join(custom_loc, config["name"])
            link_path = os.path.join(SERVERS_DIR, config["name"])
            try:
                os.makedirs(target_path, exist_ok=True)
                create_junction(target_path, link_path)
                self.server_console.log(f"[System] Created link for custom location: {target_path}")
            except Exception as e:
                self.server_console.log(f"[Error] Failed to map custom location: {e}")
                return

        self.executor.submit(self.start_download_process, config)

    def start_download_process(self, config):
        self.after(0, lambda: self.show_progress_dialog(config))

    def show_progress_dialog(self, config):
        dialog = DownloadProgressDialog(self, title=f"Installing {config['name']}...")
        
        def run_install():
            try:
                name = config["name"]
                version = config["version"]
                engine = config["type"]
                dialog.update_progress(0.0, f"Downloading {engine} {version} server jar...")
                if engine == "Vanilla":
                    self.server_console.log(f"[System] Downloading Vanilla {version}...")
                    success = logic.download_server(name, engine, version, dialog.update_progress)
                elif engine == "Paper":
                    self.server_console.log(f"[System] Downloading Paper {version}...")
                    success = logic.download_server(name, engine, version, dialog.update_progress)
                elif engine == "Purpur":
                    self.server_console.log(f"[System] Downloading Purpur {version}...")
                    success = logic.download_server(name, engine, version, dialog.update_progress)
                elif engine == "Fabric":
                    self.server_console.log(f"[System] Installing Fabric {version}...")
                    from app.services.java_installer import JdkManagerInstance
                    from app.services.java_detector import get_required_java
                    _java_bin = JdkManagerInstance.ensure_java(get_required_java(version)) or "java"
                    success = logic.install_fabric(name, version, dialog.update_progress, java_bin=_java_bin)
                elif engine == "Forge":
                    self.server_console.log(f"[System] Installing Forge {version}...")
                    from app.services.java_installer import JdkManagerInstance
                    from app.services.java_detector import get_required_java
                    _java_bin = JdkManagerInstance.ensure_java(get_required_java(version)) or "java"
                    success = logic.install_forge(name, version, dialog.update_progress, java_bin=_java_bin)
                else:
                    self.server_console.log(f"[Error] Unknown server type: {engine}")
                    success = False
                
                if success:
                    self.server_console.log(f"[System] Installation success. Applying settings...")
                    dialog.update_progress(0.25, "Verifying file integrity...")
                    if config.get("icon_path"):
                        dialog.update_progress(0.30, "Applying server icon...")
                        logic.save_server_icon(name, config["icon_path"])

                    # --- PROV-02: Pre-Boot Scaffolding ---
                    dialog.update_progress(0.35, "Configuring server environment...")
                    self.server_console.log("[System] Scaffolding server environment...")
                    from app.services.scaffolder import pre_boot_scaffold
                    server_dir = os.path.join(SERVERS_DIR, name)
                    port_str = config.get("playit_port")
                    port = int(port_str) if port_str and str(port_str).isdigit() else self.zbb_manager.get_server_port(name)
                    pre_boot_scaffold(server_dir, port=port, eula_accepted=True, config=config)
                    self.server_console.log("[System] Environment ready (eula.txt, server.properties, directories).")
                    if "auto_install_jdk" in config:
                        logic.update_server_meta(name, {"auto_install_jdk": config["auto_install_jdk"]})

                    # --- PROV-03: Bytecode Analysis ---
                    dialog.update_progress(0.50, "Analyzing Java requirements from server jar...")
                    self.server_console.log("[System] Analyzing Java requirements from server jar...")
                    from app.services.bytecode_analyzer import analyze_jar_bytecode
                    jar_path = os.path.join(server_dir, "server.jar")
                    # Sync guarantee: wait until server.jar exists and size > 0 (handles Forge normalization race)
                    self.server_console.log("[System] Waiting for server.jar normalization...")
                    dialog.update_progress(0.55, "Waiting for server.jar normalization...")
                    import time
                    required_java = None
                    for _ in range(20):
                        if os.path.exists(jar_path) and os.path.getsize(jar_path) > 0:
                            break
                        time.sleep(0.5)
                    else:
                        self.server_console.log("[Warning] server.jar not found after 10s. Aborting bytecode analysis.")
                    
                    if os.path.exists(jar_path) and os.path.getsize(jar_path) > 0:
                        try:
                            required_java = analyze_jar_bytecode(jar_path)
                        except Exception as e:
                            self.server_console.log(f"[Warning] Bytecode analysis crashed: {e}")

                    from app.services.java_installer import JdkManagerInstance
                    from app.services.java_detector import get_required_java
                    version_map_java = get_required_java(version)
                    # Floor bytecode result against version-map to avoid Forge shim (Java 8) overriding correct version
                    if required_java and required_java >= version_map_java:
                        final_java = required_java
                    else:
                        final_java = version_map_java
                    self.server_console.log(f"[System] Java {final_java} required (source: {'bytecode' if required_java and required_java >= version_map_java else 'version-map'}).")
                    logic.update_server_meta(name, {"required_java": final_java})
                    if not JdkManagerInstance.get_java_path(final_java):
                        dialog.update_progress(0.65, f"Downloading Java {final_java}...")
                        self.server_console.log(f"[System] Downloading Java {final_java}...")
                        try:
                            JdkManagerInstance.ensure_java(final_java)
                            self.server_console.log(f"[System] Java {final_java} ready.")
                        except Exception as jde:
                            self.server_console.log(f"[Warning] Java {final_java} download failed: {jde}")

                    dialog.update_progress(0.70, "Setting up Playit tunnel...")
                    self.server_console.log(f"[System] Server '{name}' created successfully.")
                    self.zbb_manager.create_tunnel_for_server(name)
                    dialog.update_progress(1.0, "Server ready!")
                    self.after(0, lambda: self._on_download_complete(dialog, name))
                else:
                    self.server_console.log(f"[Error] Failed to create server '{name}'. Check terminal for details.")
                    self.after(0, dialog.close)
            except Exception as e:
                self.server_console.log(f"[Error] Installation failed: {e}")
                import traceback
                logger.error("Installation failed:\n%s", traceback.format_exc())
                self.after(0, dialog.close)
        self.executor.submit(run_install)

    def _on_download_complete(self, dialog, name):
        self.load_servers()
        self.server_console.log(f"[System] Setup complete for '{name}'.")
        self.on_server_select(name)
        dialog.close()
        start_now = ZBBDialog.confirm(
            self, "Server Ready",
            f"'{name}' has been created successfully.\n\nDo you want to start it now?",
            confirm_text="Start now", cancel_text="Later",
        )
        if start_now:
            self.start_server_action()

    def start_tunnel(self):
        self.btn_tunnel_start.configure(state="disabled")
        self.btn_tunnel_stop.configure(state="normal")
        self.zbb_manager.start_tunnel()

    def stop_tunnel(self):
        self.zbb_manager.stop_tunnel()
        self.btn_tunnel_start.configure(state="normal")
        self.btn_tunnel_stop.configure(state="disabled")

    def reset_tunnel(self):
        msg = (
            "This will delete all tunnels but keep your agent linked.\n\n"
            "After reset, click ▶ to create a new tunnel.\n\n"
            "Are you sure?"
        )
        if not ZBBDialog.confirm(self, "Reset Tunnels", msg, confirm_text="Reset"): return
        
        Toast.show(self, "Clearing tunnels...", toast_type="info")
        self.tunnel_console.log("[System] Clearing tunnels...")
        
        def _reset_task():
            self.zbb_manager.reset_tunnel(mode="soft")
            self.after(0, lambda: self.on_tunnel_status({"status": "Offline", "skip_debounce": True}))
            self.after(0, lambda: self.btn_tunnel_start.configure(state="normal"))
            self.after(0, lambda: self.btn_tunnel_stop.configure(state="disabled"))
            self.after(0, lambda: self.tunnel_console.log("[System] Tunnels cleared. Use ▶ to create a new tunnel."))
            # Toast is handled by PlayitManager.notification_callback via EventBus

        self.executor.submit(_reset_task)

    def on_tunnel_status(self, data):
        if not data: return
        if not data.get("skip_debounce"):
            from app.core.statemanager import schedule_update as _schedule_tunnel_update
            if not _schedule_tunnel_update(data):
                return
        status = data.get("status", "Offline")
        ip = data.get("ip", None)
        dns = data.get("dns", None)

        def _update():
            # 1. Update Status Label and Colors
            color = AppConfig.COLOR_STATUS_OFFLINE
            if status == "Online": color = AppConfig.COLOR_STATUS_ONLINE
            elif status == "Error": color = AppConfig.COLOR_STATUS_ERROR
            elif status == "Starting...": color = AppConfig.COLOR_STATUS_STARTING

            self.lbl_tunnel_status.configure(text=f"Tunnel: ● {status}", text_color=color)
            
            # --- CRITICAL DNS DISPLAY LOGIC (DO NOT TOUCH!) ---
            # DO NOT MODIFY: this section is the final link in the DNS recovery chain.
            # See playit_manager.py: _dns_polling_loop, _parse_line, _stdout_dns.
            # The address assigned by Playit appears here via TUNNEL_STATUS event.
            display_dns = dns or ip
            
            # Hide labels first to be clean
            self.lbl_dns_display.pack_forget()
            self.btn_copy_ip.pack_forget()
            
            if status == "Online" and display_dns:
                self._last_full_ip = display_dns
                host = display_dns.split(":")[0] if ":" in display_dns else display_dns
                self.lbl_dns_display.configure(text=host, text_color=AppConfig.COLOR_LINK)
                self.lbl_dns_display.pack(side="left", padx=5)
                self.btn_copy_ip.configure(state="normal")
                self.btn_copy_ip.pack(side="left", padx=(5, 0))
            elif status == "Starting...":
                self.lbl_dns_display.configure(text="Waiting for domain...", text_color=AppConfig.COLOR_STATUS_STARTING)
                self.lbl_dns_display.pack(side="left", padx=5)
            elif status == "Error":
                self.lbl_dns_display.configure(text="Error", text_color=AppConfig.COLOR_STATUS_ERROR)
                self.lbl_dns_display.pack(side="left", padx=5)
            else: # Offline
                self.lbl_dns_display.configure(text="")
                self._last_full_ip = None

            # 2. Update Buttons Visibility and State
            is_linked = self.zbb_manager.playit_manager.is_linked

            if not is_linked:
                self.btn_tunnel_start.pack_forget()
                self.btn_tunnel_stop.pack_forget()
                self.setup_frame.pack_forget()
                self.btn_reset.pack_forget()
                self.btn_toggle_setup.pack(side="left", padx=(8, 2))
                if self._setup_expanded:
                    self.btn_toggle_setup.pack_forget()
                    self.setup_frame.pack(side="left", fill="x")
                    self.entry_setup_code.pack(side="left", padx=2)
                    self.btn_link_code.pack(side="left", padx=2)
                    self.btn_claim.pack(side="left", padx=2)
                else:
                    self.setup_frame.pack_forget()
                    self.entry_setup_code.pack_forget()
                    self.btn_link_code.pack_forget()
                    self.btn_claim.pack_forget()
            else:
                self.btn_toggle_setup.pack_forget()
                self.setup_frame.pack_forget()
                self.entry_setup_code.pack_forget()
                self.btn_link_code.pack_forget()
                self.btn_claim.pack_forget()

                self.btn_tunnel_start.pack(side="left", padx=2)
                self.btn_tunnel_stop.pack(side="left", padx=2)
                self.btn_reset.pack(side="left", padx=2)

                if status == "Online":
                    self.btn_tunnel_start.configure(state="disabled")
                    self.btn_tunnel_stop.configure(state="normal")
                elif status == "Starting...":
                    self.btn_tunnel_start.configure(state="disabled")
                    self.btn_tunnel_stop.configure(state="disabled")
                else:
                    self.btn_tunnel_start.configure(state="normal")
                    self.btn_tunnel_stop.configure(state="disabled")

        self.after(0, _update)

    def _copy_ip_to_clipboard(self):
        full_ip = getattr(self, "_last_full_ip", None)
        if full_ip and full_ip not in ["Connecting...", ""]:
            host = full_ip.split(":")[0] if full_ip and ":" in full_ip else full_ip
            self.clipboard_clear()
            self.clipboard_append(host)
            Toast.show(self, "Address copied to clipboard!", toast_type="success", duration=3000)

    def open_claim_url(self):
        """Opens the official Playit wizard and shows setup instructions."""
        url = AppConfig.PLAYIT_WIZARD_URL
        self.tunnel_console.log(f"[UI] Opening Playit Setup Wizard...")
        webbrowser.open(url)
        Toast.show(self, "1. Get your Setup Code from Playit\n2. Paste it here to link.", toast_type="info", duration=5000)

    def _link_with_setup_code(self):
        code = self.entry_setup_code.get().strip()
        if not code:
            Toast.show(self, "Please enter a valid Setup Code.", toast_type="error")
            return
            
        self.btn_link_code.configure(state="disabled")
        self.tunnel_console.log(f"[System] Linking account...")
        Toast.show(self, "Verifying code with Playit...", toast_type="info")
        
        def _link_task():
            success = self.zbb_manager.link_playit_manually(code)
            self.after(0, lambda: self.btn_link_code.configure(state="normal"))
            if success:
                self.after(0, lambda: self.entry_setup_code.delete(0, 'end'))
                self.after(0, lambda: setattr(self, '_setup_expanded', False))
            else:
                self.after(0, lambda: Toast.show(self, "Link failed. Verify your code.", toast_type="error"))
        
        self.executor.submit(_link_task)

    def load_existing_server_action(self):
        folder = ctk.filedialog.askdirectory(title="Select Existing Server Folder")
        if not folder: return
        
        # Quick validation: check for any .jar
        try:
            files = os.listdir(folder)
            jars = [f for f in files if f.endswith(".jar")]
            if not jars:
                Toast.show(self, "No .jar file found in the selected folder.", toast_type="error")
                return
                
            if self.zbb_manager.load_server_manually(folder):
                self.load_servers() # Refresh list
                Toast.show(self, "Server loaded successfully!", toast_type="success")
        except Exception as e:
            Toast.show(self, f"Failed to load server: {e}", toast_type="error")

    def on_close(self):
        self.withdraw()

        # Cancel in-flight UI tasks immediately (downloads, link checks, etc.)
        self.executor.shutdown(wait=False, cancel_futures=True)

        self._shutdown_event = threading.Event()

        def _do_shutdown():
            try:
                self.zbb_manager.shutdown()
                self._kill_orphan_processes()
            finally:
                if hasattr(self, '_instance_lock'):
                    self._instance_lock.release()
                self._shutdown_event.set()

        threading.Thread(target=_do_shutdown, daemon=True, name="AppShutdown").start()
        self._poll_shutdown(deadline=time.monotonic() + 8.0)

    def _kill_orphan_processes(self):
        """Force-kill any subprocesses still alive after graceful shutdown."""
        runner = getattr(self.zbb_manager, 'server_runner', None)
        if runner:
            proc = getattr(runner, 'process', None)
            if proc and proc.poll() is None:
                try:
                    proc.kill()
                    proc.wait(timeout=2)
                except Exception:
                    pass
        pm = getattr(self.zbb_manager, 'playit_manager', None)
        if pm:
            proc = getattr(pm, 'process', None)
            if proc and proc.poll() is None:
                try:
                    proc.kill()
                    proc.wait(timeout=2)
                except Exception:
                    pass

    def _poll_shutdown(self, deadline: float):
        if self._shutdown_event.is_set() or time.monotonic() >= deadline:
            self.destroy()
            return
        self.after(100, lambda: self._poll_shutdown(deadline))

def main():
    # --- CONV-01: Structured Logging Configuration ---
    logging.basicConfig(
        level=logging.INFO,
        format="[%(asctime)s] [%(levelname)s] [%(name)s] %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    # Single-instance lock: prevent multiple app instances
    from app.core.single_instance import SingleInstanceLock
    from app.core.constants import CONFIG_DIR

    instance_lock = SingleInstanceLock(CONFIG_DIR / ".zbb.lock")
    if not instance_lock.try_acquire():
        import tkinter.messagebox
        tkinter.messagebox.showwarning(
            "Zero Block Bridge",
            "Another instance is already running.\n\n"
            "Only one instance of the application is allowed."
        )
        sys.exit(1)

    app = MCTunnelApp()
    app._instance_lock = instance_lock
    app.protocol("WM_DELETE_WINDOW", app.on_close)

    # First-run Minecraft EULA consent (shown once; ZBB auto-writes
    # eula=true on created servers, so explicit consent is required).
    from app.services.settings_manager import SettingsManager
    _settings = SettingsManager()
    if not _settings.get("eula_accepted", False):
        from app.ui.ui_components import EulaDialog
        eula_dialog = EulaDialog(app)
        app.wait_window(eula_dialog)
        if not eula_dialog.accepted:
            logger.info("EULA declined - exiting.")
            instance_lock.release()
            app.destroy()
            sys.exit(0)
        _settings.set("eula_accepted", True)

    import signal
    signal.signal(signal.SIGTERM, lambda sig, frame: app.after(0, app.on_close))
    signal.signal(signal.SIGINT, lambda sig, frame: app.after(0, app.on_close))

    app.mainloop()

if __name__ == "__main__":
    main()
