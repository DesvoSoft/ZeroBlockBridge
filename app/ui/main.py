import customtkinter as ctk
import logging
import os
import sys
import threading
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

from app.ui.ui_components import ConsoleWidget, ServerListItem, DownloadProgressDialog
from app.core.logic import check_java, download_server, accept_eula, install_fabric, Scheduler
import app.core.logic as logic
from app.core.constants import SERVERS_DIR, ASSETS_DIR
from app.ui.server_wizard import ServerWizard
from app.ui.server_properties_editor import ServerPropertiesEditor
from app.core.server_events import ServerEvent, EventBus
from app.core.app_config import AppConfig
from app.ui.modrinth_browser import ModrinthBrowser
from app.services.sanitizer import is_safe_command
from app.services.toast import Toast
from app.core.core import ZBBManager

ctk.set_appearance_mode("Dark")
ctk.set_default_color_theme("blue")

class MCTunnelApp(ctk.CTk):
    def __init__(self):
        from app.services.settings_manager import SettingsManager
        self.settings = SettingsManager()
        theme = self.settings.get("theme", "Dark")
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
        self._show_setup_input = False
        
        self.events = EventBus()
        self.zbb_manager = ZBBManager(self.events)
        
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
            self.actions_frame, text="+ Create New Server", 
            command=self.create_server_dialog, corner_radius=12, height=36,
            font=("Roboto Medium", 13)
        )
        self.btn_create_server.pack(fill="x", pady=(0, 5))

        self.btn_load_server = ctk.CTkButton(
            self.actions_frame, text="📁 Load Existing Folder", 
            command=self.load_existing_server_action, corner_radius=12, height=32, 
            fg_color="transparent", border_width=1, border_color=AppConfig.COLOR_BORDER_DARK,
            font=("Roboto", 12)
        )
        self.btn_load_server.pack(fill="x", pady=(0, 10))

        # --- Separator ---
        self.sep = ctk.CTkFrame(self.sidebar_frame, height=2, fg_color=AppConfig.COLOR_BORDER_DARK)
        self.sep.grid(row=2, column=0, padx=25, pady=5, sticky="ew")

        # --- List Group ---
        self.lbl_servers = ctk.CTkLabel(
            self.sidebar_frame, text="YOUR SERVERS", 
            anchor="w", font=("Roboto Medium", 11), text_color=AppConfig.COLOR_TEXT_GRAY
        )
        self.lbl_servers.grid(row=3, column=0, padx=25, pady=(5, 2), sticky="w")

        self.server_list_frame = ctk.CTkScrollableFrame(
            self.sidebar_frame, label_text="", corner_radius=12, 
            border_width=1, border_color=(AppConfig.COLOR_BORDER_LIGHT, AppConfig.COLOR_BORDER_DARK),
            fg_color=("gray95", "gray12")
        )
        self.server_list_frame.grid(row=4, column=0, padx=20, pady=(5, 15), sticky="nsew")

    def _build_main_area(self):
        self.main_frame = ctk.CTkFrame(self, corner_radius=0)
        self.main_frame.grid(row=0, column=1, sticky="nsew")
        self.main_frame.grid_rowconfigure(0, weight=0) # Status bar
        self.main_frame.grid_rowconfigure(1, weight=0) # Compact Dashboard (Controls & Tunnel)
        self.main_frame.grid_rowconfigure(2, weight=1) # Console tabs & Mods (Prominent)
        self.main_frame.grid_columnconfigure(0, weight=1)
        self._build_status_bar()
        self._build_dashboard()
        self._build_console_tabs()

    def _build_status_bar(self):
        self.status_frame = ctk.CTkFrame(self.main_frame, height=45, corner_radius=12, fg_color=(AppConfig.COLOR_BG_LIGHT, AppConfig.COLOR_BG_DARK))
        self.status_frame.grid(row=0, column=0, sticky="ew", padx=15, pady=(10, 2))
        
        self.lbl_status = ctk.CTkLabel(self.status_frame, text="⚪ Offline", font=("Roboto Medium", 15))
        self.lbl_status.pack(side="left", padx=20, pady=8)

        # Moved from dashboard to save space
        self.lbl_dash_title = ctk.CTkLabel(self.status_frame, text="Select a server", font=AppConfig.FONT_HEADING)
        self.lbl_dash_title.pack(side="left", padx=(0, 10), pady=8)

        self.btn_config = ctk.CTkButton(
            self.status_frame, text="⚙", width=36, height=36, 
            corner_radius=12, fg_color="transparent", hover_color="#334155",
            font=("Roboto", 18), command=self.edit_server_properties,
            state="disabled"
        )
        self.btn_config.pack(side="left", padx=5)

        self.status_right_frame = ctk.CTkFrame(self.status_frame, fg_color="transparent")
        self.status_right_frame.pack(side="right", padx=20, pady=8)
        
        self.lbl_server_info = ctk.CTkLabel(self.status_right_frame, text="No server selected", text_color=AppConfig.COLOR_TEXT_GRAY, font=AppConfig.FONT_BODY_SMALL)
        self.lbl_server_info.pack(side="left", padx=(0, 15))
        
        self.lbl_player_count = ctk.CTkLabel(self.status_right_frame, text="Players: 0", text_color=AppConfig.COLOR_TEXT_GRAY, font=AppConfig.FONT_BODY_SMALL)
        self.lbl_player_count.pack(side="left", padx=(0, 15))
        
        self.lbl_java_ver = ctk.CTkLabel(self.status_right_frame, text="Checking...", text_color=AppConfig.COLOR_TEXT_GRAY, font=AppConfig.FONT_BODY_SMALL)
        self.lbl_java_ver.pack(side="left", padx=(0, 15))



    def _build_dashboard(self):
        self.dashboard_frame = ctk.CTkFrame(self.main_frame, corner_radius=12, fg_color=(AppConfig.COLOR_BG_LIGHT, AppConfig.COLOR_BG_DARK))
        self.dashboard_frame.grid(row=1, column=0, sticky="ew", padx=15, pady=(2, 10))
        
        self.controls_frame = ctk.CTkFrame(self.dashboard_frame, fg_color="transparent")
        self.controls_frame.pack(pady=4)
        self._build_server_controls()

        self.tunnel_frame = ctk.CTkFrame(self.dashboard_frame, fg_color="transparent")
        self.tunnel_frame.pack(pady=5, fill="x")
        self._build_tunnel_controls()

    def _build_server_controls(self):
        self.btn_start_all = ctk.CTkButton(self.controls_frame, text="▶ Start All", state="disabled", command=self.start_all_action, fg_color="#00AA00", hover_color="#008800",  width=110, corner_radius=12, height=36, font=("Roboto Medium", 12))
        self.btn_start_all.pack(side="left", padx=5)
        self.btn_start = ctk.CTkButton(self.controls_frame, text="▶", state="disabled", command=self.start_server_action, fg_color=AppConfig.COLOR_BTN_SUCCESS, hover_color=AppConfig.COLOR_BTN_SUCCESS_HOVER, width=45, corner_radius=12, height=36)
        self.btn_start.pack(side="left", padx=2)
        self.btn_stop = ctk.CTkButton(self.controls_frame, text="■", state="disabled", command=self.stop_server_action, fg_color=AppConfig.COLOR_BTN_DANGER, hover_color=AppConfig.COLOR_BTN_DANGER_HOVER, width=45, corner_radius=12, height=36)
        self.btn_stop.pack(side="left", padx=2)

    def _build_tunnel_controls(self):
        self.lbl_tunnel_status = ctk.CTkLabel(self.tunnel_frame, text="Tunnel: Offline", text_color=AppConfig.COLOR_TEXT_GRAY, font=AppConfig.FONT_BODY)
        self.lbl_tunnel_status.pack(side="left", padx=(20, 5))

        self.ip_frame = ctk.CTkFrame(self.tunnel_frame, fg_color="transparent")
        self.ip_frame.pack(side="left", fill="x", expand=True)

        self.lbl_dns_display = ctk.CTkLabel(self.ip_frame, text="", font=("Roboto Medium", 13), text_color="#3b82f6")
        self.lbl_dns_display.pack(side="left", padx=(5, 0))

        self.btn_copy_ip = ctk.CTkButton(
            self.ip_frame, text="📋", command=self._copy_ip_to_clipboard,
            fg_color="#1e293b", hover_color="#334155",
            border_width=1, border_color="#3b82f6",
            width=36, corner_radius=12, height=28,
            font=("Roboto", 13), text_color="#3b82f6",
        )

        self.tunnel_toolbar = ctk.CTkFrame(self.tunnel_frame, fg_color="transparent")
        self.tunnel_toolbar.pack(side="right", padx=10)

        self.btn_tunnel_start = ctk.CTkButton(self.tunnel_toolbar, text="▶", command=self.start_tunnel, width=45, corner_radius=12, height=36, fg_color=AppConfig.COLOR_BTN_SUCCESS, hover_color=AppConfig.COLOR_BTN_SUCCESS_HOVER)
        self.btn_tunnel_stop = ctk.CTkButton(self.tunnel_toolbar, text="■", command=self.stop_tunnel, state="disabled", fg_color=AppConfig.COLOR_BTN_DANGER, hover_color=AppConfig.COLOR_BTN_DANGER_HOVER, width=45, corner_radius=12, height=36)
        
        # Setup Code Input & Link Button
        self.entry_setup_code = ctk.CTkEntry(self.tunnel_toolbar, placeholder_text="Setup Code", width=120, height=36, corner_radius=12)
        self.btn_link_code = ctk.CTkButton(self.tunnel_toolbar, text="🔗 Link", command=self._link_with_setup_code, width=60, height=36, corner_radius=12, fg_color=AppConfig.COLOR_BTN_PRIMARY)
        self.btn_claim = ctk.CTkButton(self.tunnel_toolbar, text="Link Playit.gg", command=self.open_claim_url, fg_color=AppConfig.COLOR_BTN_WARNING, hover_color=AppConfig.COLOR_BTN_WARNING_HOVER, width=130, corner_radius=12, height=36, font=("Roboto Medium", 12))
        
        self.btn_reset = ctk.CTkButton(self.tunnel_toolbar, text="↻", command=self.reset_tunnel, fg_color="gray", hover_color="gray30", width=45, corner_radius=12, height=36)
        self.btn_reset.pack(side="left", padx=2)
        
        # Initial UI State Check
        self.after(500, lambda: self.on_tunnel_status({"status": "Offline"}))

    def _build_console_tabs(self):
        self.console_tabs = ctk.CTkTabview(self.main_frame)
        self.console_tabs.grid(row=2, column=0, padx=15, pady=(0, 15), sticky="nsew")
        
        self.console_tabs.add("Console")
        self.console_tabs.add("Tunnel Log")
        
        self.server_console = ConsoleWidget(self.console_tabs.tab("Console"), max_lines=500)
        self.server_console.pack(fill="both", expand=True)
        
        self.console_input_frame = ctk.CTkFrame(self.console_tabs.tab("Console"), height=40, corner_radius=12, fg_color=(AppConfig.COLOR_CONSOLE_LIGHT, AppConfig.COLOR_CONSOLE_DARK))
        self.console_input_frame.pack(fill="x", pady=(5, 0))
        
        self.entry_console = ctk.CTkEntry(self.console_input_frame, placeholder_text="Type command here...", corner_radius=12, height=36)
        self.entry_console.pack(side="left", fill="x", expand=True, padx=(10, 5), pady=5)
        self.entry_console.bind("<Return>", self.send_server_command)
        
        self.btn_send = ctk.CTkButton(self.console_input_frame, text="Send", width=80, command=self.send_server_command, corner_radius=12, height=36, fg_color=AppConfig.COLOR_BTN_PRIMARY, hover_color=AppConfig.COLOR_BTN_PRIMARY_HOVER)
        self.btn_send.pack(side="right", padx=10, pady=5)
        
        self.tunnel_console = ConsoleWidget(self.console_tabs.tab("Tunnel Log"), max_lines=500)
        self.tunnel_console.pack(fill="both", expand=True)

        # --- Mods Tab (Modrinth Browser) ---
        self.console_tabs.add("Mods")
        self.modrinth_browser = ModrinthBrowser(
            self.console_tabs.tab("Mods"),
            get_server_info=self._get_current_server_info,
        )
        self.modrinth_browser.pack(fill="both", expand=True)

    def _init_background_services(self):
        self.check_java_startup()
        self.load_servers()
        self.zbb_manager.bootstrap()
        # Pre-warm now handled by ZBBManager.bootstrap() → core.py

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
            version = check_java()
            if version:
                if 'version' in version.lower():
                    version_part = version.lower().split('version')[1].strip()
                    major_version = version_part.split('.')[0].strip('"').strip()
                else:
                    major_version = version.split('.')[0] if '.' in version else version
                
                self.after(0, lambda: self.lbl_java_ver.configure(text=f"Java {major_version}", text_color="green"))
                self.after(0, lambda: self.server_console.log(f"[System] Found Java: {version}"))
            else:
                self.after(0, lambda: self.lbl_java_ver.configure(text="No Java", text_color="red"))
                self.after(0, lambda: self.server_console.log("[System] CRITICAL: Java not found! Please install Java 17+."))
        threading.Thread(target=_check, daemon=True).start()

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
        threading.Thread(target=_scan, daemon=True).start()

    def _render_server_list(self, servers):
        for widget in self.server_list_frame.winfo_children():
            widget.destroy()
        if not servers:
            lbl = ctk.CTkLabel(self.server_list_frame, text="No servers found.")
            lbl.pack(pady=10)
        else:
            for s in servers:
                item = ServerListItem(self.server_list_frame, server_name=s, on_click=self.on_server_select)
                item.pack(fill="x", padx=5, pady=5)
        self.server_console.log(f"[System] Loaded {len(servers)} servers.")

    def on_server_select(self, server_name):
        # UI Locking: Block switching if current server is active
        if self.zbb_manager.is_running() and self.zbb_manager.current_server != server_name:
            Toast.show(self, "Stop the current server before switching", toast_type="warning")
            return

        self.zbb_manager.select_server(server_name)
        self.zbb_manager.select_server(server_name)
        self.lbl_dash_title.configure(text=f"{server_name}")
        server_path = os.path.join(SERVERS_DIR, server_name)
        
        server_type = "Vanilla"
        if os.path.exists(os.path.join(server_path, "fabric-server-launch.jar")): 
            server_type = "Fabric"
        elif os.path.exists(os.path.join(server_path, "run.bat")) or os.path.exists(os.path.join(server_path, "run.sh")):
            server_type = "Forge"
        
        self.lbl_server_info.configure(text=f"🎮 {server_type}", text_color="white")
        
        is_running = self.zbb_manager.is_running() and self.zbb_manager.current_server == server_name
        
        self.btn_start.configure(state="disabled" if is_running else "normal")
        self.btn_start_all.configure(state="disabled" if is_running else "normal")
        self.btn_stop.configure(state="normal" if is_running else "disabled")
        
        self.btn_config.configure(state="normal")
        self.server_console.log(f"[UI] Selected server: {server_name}")
    def open_server_folder(self):
        def _open_folder(p):
            import subprocess
            if sys.platform == "win32":
                os.startfile(p)
            elif sys.platform == "darwin":
                subprocess.run(["open", str(p)])
            else:
                subprocess.run(["xdg-open", str(p)])

        if not self.zbb_manager.current_server:
            path = SERVERS_DIR
            _open_folder(path)
            return
            
        server_path = os.path.join(SERVERS_DIR, self.zbb_manager.current_server)
        if os.path.exists(server_path):
            _open_folder(server_path)

    def _get_current_server_info(self):
        """Return (server_name, mc_version, loader) for the current server."""
        if not self.zbb_manager.current_server:
            return None
        server_path = os.path.join(SERVERS_DIR, self.zbb_manager.current_server)
        meta_path = os.path.join(server_path, "metadata.json")
        mc_version = "1.20.1"
        loader = None
        
        if os.path.exists(meta_path):
            try:
                import json
                with open(meta_path, "r") as f:
                    meta = json.load(f)
                mc_version = meta.get("version", "1.20.1")
                stype = meta.get("type", "Vanilla").lower()
                if stype in ("fabric", "forge", "paper", "purpur", "spigot"):
                    loader = stype
            except Exception:
                pass
        
        logger.info(f"Server Info for Mod Search: {self.zbb_manager.current_server} | MC: {mc_version} | Loader: {loader or 'any'}")
        return (self.zbb_manager.current_server, mc_version, loader)

    def start_all_action(self):
        if not self.zbb_manager.current_server: return
        if self.start_server_action():
            self.update_console("[System] Starting server and tunnel...")
            self.start_tunnel()

    def save_advanced_settings(self, *args):
        if not self.zbb_manager.current_server: return
        import json
        from app.core.constants import SERVERS_DIR
        meta_path = os.path.join(SERVERS_DIR, self.zbb_manager.current_server, "metadata.json")
        try:
            with open(meta_path, "r") as f:
                meta = json.load(f)
            meta["advanced_mode"] = self.var_advanced_mode.get()
            
            # Map label back to path
            label = self.var_java_path.get()
            path = getattr(self, "_java_label_to_path", {}).get(label, "auto")
            meta["java_path"] = path
            
            meta["use_aikars"] = self.var_use_aikars.get()
            with open(meta_path, "w") as f:
                json.dump(meta, f, indent=4)
        except Exception as e:
            self.server_console.log(f"[Error] Failed to save advanced settings: {e}")

    def edit_server_properties(self):
        if not self.zbb_manager.current_server: return
        if self.zbb_manager.is_running():
            self.server_console.log("[Error] Stop the server before editing properties.")
            return
        ServerPropertiesEditor(self, self.zbb_manager.current_server, logic)

    def open_mods_folder_action(self):
        if not self.zbb_manager.current_server: return
        server_path = SERVERS_DIR / self.zbb_manager.current_server
        if not server_path.exists(): return
        try:
            if sys.platform == "win32": os.startfile(str(server_path))
            elif sys.platform == "darwin": subprocess.run(["open", str(server_path)])
            else: subprocess.run(["xdg-open", str(server_path)])
            self.server_console.log(f"[System] Opened server folder for '{self.zbb_manager.current_server}'")
        except Exception as e:
            self.server_console.log(f"[Error] Failed to open server folder: {e}")

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
        threading.Thread(target=_start, daemon=True).start()

    def on_server_starting(self, data=None):
        self.after(0, lambda: self.lbl_status.configure(text="⏳ Starting...", text_color=AppConfig.COLOR_STATUS_STARTING))
        self.after(0, lambda: self.btn_start.configure(state="disabled"))
        self.after(0, lambda: self.btn_start_all.configure(state="disabled"))
        self.after(0, lambda: self.btn_stop.configure(state="normal"))
        if data and isinstance(data, dict):
            jdk_src = data.get("jdk_source", "unknown")
            java_ver = data.get("required_java", "?")
            label = f"Java {java_ver} ({jdk_src})"
            color = "green" if jdk_src == "system" else "orange"
            self.after(0, lambda: self.lbl_java_ver.configure(text=label, text_color=color))

    def on_server_ready(self, data=None):
        self.after(0, lambda: self.lbl_status.configure(text="🟢 Running", text_color=AppConfig.COLOR_STATUS_ONLINE))

    def on_player_count_update(self, count):
        self.after(0, lambda: self.lbl_player_count.configure(text=f"Players: {count}"))

    def on_server_stopped(self, data=None):
        self.after(0, lambda: self.lbl_status.configure(text="⚪ Offline", text_color=AppConfig.COLOR_STATUS_OFFLINE))
        self.after(0, lambda: self.btn_start.configure(state="normal"))
        self.after(0, lambda: self.btn_start_all.configure(state="normal"))
        self.after(0, lambda: self.btn_stop.configure(state="disabled"))

    def stop_server_action(self):
        self.zbb_manager.stop_server()
        self.on_server_stopped()

    def create_server_dialog(self):
        ServerWizard(self, on_complete_callback=self.on_wizard_complete)

    def on_wizard_complete(self, config):
        if os.path.exists(os.path.join(SERVERS_DIR, config["name"])):
            self.server_console.log(f"[Error] Server '{config['name']}' already exists.")
            return
            
        custom_loc = config.get("location", str(SERVERS_DIR))
        if custom_loc and os.path.normpath(custom_loc) != os.path.normpath(str(SERVERS_DIR)):
            target_path = os.path.join(custom_loc, config["name"])
            link_path = os.path.join(SERVERS_DIR, config["name"])
            try:
                os.makedirs(target_path, exist_ok=True)
                if sys.platform == "win32":
                    import _winapi
                    _winapi.CreateJunction(target_path, link_path)
                else:
                    os.symlink(target_path, link_path)
                self.server_console.log(f"[System] Created link for custom location: {target_path}")
            except Exception as e:
                self.server_console.log(f"[Error] Failed to map custom location: {e}")
                return

        threading.Thread(target=self.start_download_process, args=(config,), daemon=True).start()

    def start_download_process(self, config):
        self.after(0, lambda: self.show_progress_dialog(config))

    def show_progress_dialog(self, config):
        dialog = DownloadProgressDialog(self, title=f"Installing {config['name']}...")
        
        def run_install():
            try:
                name = config["name"]
                version = config["version"]
                if config["type"] == "Vanilla":
                    self.server_console.log(f"[System] Downloading Vanilla {version}...")
                    success = logic.download_server(name, config["type"], version, dialog.update_progress)
                elif config["type"] == "Paper":
                    self.server_console.log(f"[System] Downloading Paper {version}...")
                    success = logic.download_server(name, config["type"], version, dialog.update_progress)
                elif config["type"] == "Purpur":
                    self.server_console.log(f"[System] Downloading Purpur {version}...")
                    success = logic.download_server(name, config["type"], version, dialog.update_progress)
                elif config["type"] == "Fabric":
                    self.server_console.log(f"[System] Installing Fabric {version}...")
                    success = logic.install_fabric(name, version, dialog.update_progress)
                elif config["type"] == "Forge":
                    self.server_console.log(f"[System] Installing Forge {version}...")
                    success = logic.install_forge(name, version, dialog.update_progress)
                else:
                    self.server_console.log(f"[Error] Unknown server type: {config['type']}")
                    success = False
                
                if success:
                    self.server_console.log(f"[System] Installation success. Applying settings...")
                    if config.get("icon_path"): logic.save_server_icon(name, config["icon_path"])

                    # --- PROV-02: Pre-Boot Scaffolding ---
                    self.server_console.log("[System] Scaffolding server environment...")
                    from app.services.scaffolder import pre_boot_scaffold
                    server_dir = os.path.join(SERVERS_DIR, name)
                    port = self.zbb_manager.get_server_port(name)
                    pre_boot_scaffold(server_dir, port=port, eula_accepted=True, config=config)
                    self.server_console.log("[System] Environment ready (eula.txt, server.properties, directories).")
                    meta_path = os.path.join(server_dir, "metadata.json")
                    if os.path.exists(meta_path):
                        try:
                            import json
                            with open(meta_path, "r") as f:
                                meta = json.load(f)
                            if "auto_install_jdk" in config:
                                meta["auto_install_jdk"] = config["auto_install_jdk"]
                            with open(meta_path, "w") as f:
                                json.dump(meta, f, indent=4)
                        except Exception:
                            pass

                    # --- PROV-03: Bytecode Analysis ---
                    self.server_console.log("[System] Analyzing Java requirements from server jar...")
                    from app.services.bytecode_analyzer import analyze_jar_bytecode
                    from app.core.logic import wait_for_jar_ready
                    jar_path = os.path.join(server_dir, "server.jar")
                    # Sync guarantee: wait until server.jar exists and size > 0 (handles Forge normalization race)
                    self.server_console.log("[System] Waiting for server.jar normalization...")
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

                    if required_java:
                        self.server_console.log(f"[System] Bytecode analysis: Java {required_java} required.")
                    else:
                        self.server_console.log("[System] Bytecode analysis inconclusive; will use version map at startup.")

                    self.server_console.log(f"[System] Server '{name}' created successfully.")
                    self.zbb_manager.create_tunnel_for_server(name)
                    self.after(0, lambda: self._on_download_complete(dialog, name))
                else:
                    self.server_console.log(f"[Error] Failed to create server '{name}'. Check terminal for details.")
                    self.after(0, dialog.close)
            except Exception as e:
                self.server_console.log(f"[Error] Installation failed: {e}")
                import traceback
                logger.error("Installation failed:\n%s", traceback.format_exc())
                self.after(0, dialog.close)
        threading.Thread(target=run_install, daemon=True).start()

    def _on_download_complete(self, dialog, name):
        self.load_servers()
        self.server_console.log(f"[System] Setup complete for '{name}'. You can now start it manually.")
        self.on_server_select(name)
        dialog.close()

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
            "This will wipe your local Playit configuration and delete the tunnel.\n\n"
            "Note: Due to Playit API restrictions, the Agent might still appear in your "
            "web dashboard and will need to be deleted manually there if desired.\n\n"
            "Are you sure you want to proceed?"
        )
        if not tkinter.messagebox.askyesno("Reset Playit", msg): return
        
        Toast.show(self, "Performing full account reset...", toast_type="info")
        self.tunnel_console.log("[System] Initiating Playit account reset...")
        
        def _reset_task():
            self.zbb_manager.reset_tunnel()
            self.after(0, lambda: self.on_tunnel_status({"status": "Offline"}))
            self.after(0, lambda: self.btn_tunnel_start.configure(state="normal"))
            self.after(0, lambda: self.btn_tunnel_stop.configure(state="disabled"))
            self.after(0, lambda: Toast.show(self, "Full reset complete. Account unlinked.", toast_type="success"))
            self._show_setup_input = False

        threading.Thread(target=_reset_task, daemon=True).start()

    def on_tunnel_status(self, data):
        if not data: return
        status = data.get("status", "Offline")
        ip = data.get("ip", None)
        dns = data.get("dns", None)
        
        def _update():
            # 1. Update Status Label and Colors
            color = "gray"
            icon = "●"
            if status == "Online": color = "green"
            elif status == "Error": color, icon = "red", "✖"
            elif status in ("Starting...", "Connecting..."): color, icon = "orange", "⏳"
            
            self.lbl_tunnel_status.configure(text=f"Tunnel: {icon} {status}", text_color=color)
            
            # --- CRITICAL DNS DISPLAY LOGIC (DO NOT TOUCH!) ---
            # This logic ensures the public address appears immediately 
            # and hides redundant/stale labels. 
            display_dns = dns or ip
            
            # Hide labels first to be clean
            self.lbl_dns_display.pack_forget()
            self.btn_copy_ip.pack_forget()
            
            if status == "Online" and display_dns:
                self._last_full_ip = display_dns
                host = display_dns.split(":")[0] if ":" in display_dns else display_dns
                self.lbl_dns_display.configure(text=host, text_color="#3b82f6")
                self.lbl_dns_display.pack(side="left", padx=5)
                self.btn_copy_ip.configure(state="normal")
                self.btn_copy_ip.pack(side="left", padx=(5, 0))
            elif status in ("Starting...", "Connecting..."):
                self.lbl_dns_display.configure(text="Connecting...", text_color="#f97316")
                self.lbl_dns_display.pack(side="left", padx=5)
            elif status == "Error":
                self.lbl_dns_display.configure(text="Error", text_color="#ef4444")
                self.lbl_dns_display.pack(side="left", padx=5)
            else: # Offline
                self.lbl_dns_display.configure(text="")
                self._last_full_ip = None

            # 3. Update Buttons Visibility and State
            is_linked = self.zbb_manager.playit_manager.is_linked
            
            if not is_linked:
                self.btn_tunnel_start.pack_forget()
                self.btn_tunnel_stop.pack_forget()
                self.btn_reset.pack_forget()
                
                if not getattr(self, "_show_setup_input", False):
                    self.btn_claim.pack(side="left", padx=2)
                    self.entry_setup_code.pack_forget()
                    self.btn_link_code.pack_forget()
                else:
                    self.btn_claim.pack_forget()
                    self.entry_setup_code.pack(side="left", padx=2)
                    self.btn_link_code.pack(side="left", padx=2)
            else:
                self.btn_claim.pack_forget()
                self.entry_setup_code.pack_forget()
                self.btn_link_code.pack_forget()
                
                self.btn_tunnel_start.pack(side="left", padx=2)
                self.btn_tunnel_stop.pack(side="left", padx=2)
                self.btn_reset.pack(side="left", padx=2)
                
                if status == "Online":
                    self.btn_tunnel_start.configure(state="disabled")
                    self.btn_tunnel_stop.configure(state="normal")
                elif status in ("Starting...", "Connecting..."):
                    self.btn_tunnel_start.configure(state="disabled")
                    self.btn_tunnel_stop.configure(state="disabled")
                else:
                    self.btn_tunnel_start.configure(state="normal")
                    self.btn_tunnel_stop.configure(state="disabled")

        self.after(0, _update)

    def _copy_ip_to_clipboard(self):
        full_ip = getattr(self, "_last_full_ip", None)
        if full_ip and full_ip not in ["Connecting...", ""]:
            self.clipboard_clear()
            self.clipboard_append(full_ip)
            Toast.show(self, "Full address copied to clipboard!", toast_type="success", duration=3000)

    def open_claim_url(self):
        """Opens the official Playit wizard and switches to setup code input."""
        url = AppConfig.PLAYIT_WIZARD_URL
        self.tunnel_console.log(f"[UI] Opening Playit Setup Wizard...")
        webbrowser.open(url)
        self._show_setup_input = True
        self.on_tunnel_status({"status": "Offline"}) # Refresh UI
        Toast.show(self, "1. Get your Setup Code from Playit\n2. Paste it here to link.", toast_type="info", duration=5000)

    def _link_with_setup_code(self):
        code = self.entry_setup_code.get().strip()
        if not code:
            Toast.show(self, "Please enter a valid Setup Code.", toast_type="error")
            return
            
        self.tunnel_console.log(f"[System] Linking account...")
        Toast.show(self, "Verifying code with Playit...", toast_type="info")
        
        def _link_task():
            success = self.zbb_manager.link_playit_manually(code)
            if success:
                self.after(0, lambda: Toast.show(self, "Success! Account linked. Tunnel starting...", toast_type="success"))
                self.after(0, lambda: self.entry_setup_code.delete(0, 'end'))
                self.after(0, lambda: setattr(self, '_show_setup_input', False))
            else:
                self.after(0, lambda: Toast.show(self, "Link failed. Verify your code.", toast_type="error"))
        
        threading.Thread(target=_link_task, daemon=True).start()

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
        self.zbb_manager.shutdown()
        if hasattr(self, '_instance_lock'): self._instance_lock.release()
        self.destroy()
        sys.exit(0)

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

    import signal
    signal.signal(signal.SIGTERM, lambda sig, frame: app.after(0, app.on_close))
    signal.signal(signal.SIGINT, lambda sig, frame: app.after(0, app.on_close))

    app.mainloop()

if __name__ == "__main__":
    main()
