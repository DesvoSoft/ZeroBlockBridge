import customtkinter as ctk
import os
import sys
import threading
import webbrowser
import time

# --- Tcl/Tk Fix for Windows Virtual Environments ---
if sys.platform == "win32" and hasattr(sys, 'base_prefix'):
    tcl_dir = os.path.join(sys.base_prefix, "tcl")
    if os.path.exists(tcl_dir):
        for d in os.listdir(tcl_dir):
            if d.startswith("tcl"): os.environ["TCL_LIBRARY"] = os.path.join(tcl_dir, d)
            if d.startswith("tk"): os.environ["TK_LIBRARY"] = os.path.join(tcl_dir, d)

# Add parent directory to path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.ui_components import ConsoleWidget, ServerListItem, DownloadProgressDialog, TunnelSetupDialog
from app.logic import load_config, check_java, save_config, download_server, accept_eula, install_fabric, ServerRunner
import app.logic as logic
from app.constants import SERVERS_DIR, ASSETS_DIR
from app.playit_manager import PlayitManager
from app.server_wizard import ServerWizard
from app.server_properties_editor import ServerPropertiesEditor
from app.scheduler_service import SchedulerService
from app.server_events import ServerEvent
from app.app_config import AppConfig

ctk.set_appearance_mode("Dark")
ctk.set_default_color_theme("blue")

class MCTunnelApp(ctk.CTk):
    def __init__(self):
        super().__init__()
        self._init_window_config()
        self._init_state_variables()
        self._init_managers()
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
        self.server_runner = None
        self.current_server = None
        self.restart_warnings_sent = set()
        self.claim_url = None

    def _init_managers(self):
        self.playit_manager = PlayitManager(
            console_callback=self.update_tunnel_console,
            status_callback=self.update_playit_status,
            claim_callback=self.on_playit_claim,
            on_ready_callback=self.play_notification_sound
        )

    def _build_layout(self):
        self._build_sidebar()
        self._build_main_area()

    def _build_sidebar(self):
        self.sidebar_frame = ctk.CTkFrame(self, width=300, corner_radius=0, fg_color=(AppConfig.COLOR_BG_SIDEBAR_LIGHT, AppConfig.COLOR_BG_SIDEBAR_DARK))
        self.sidebar_frame.grid(row=0, column=0, sticky="nsew")
        self.sidebar_frame.grid_rowconfigure(3, weight=1)
        self.sidebar_frame.grid_columnconfigure(0, weight=1)

        self.logo_label = ctk.CTkLabel(self.sidebar_frame, text="Zero Block\nBridge", font=AppConfig.FONT_TITLE)
        self.logo_label.grid(row=0, column=0, padx=20, pady=(20, 10))

        self.btn_create_server = ctk.CTkButton(self.sidebar_frame, text="Create Server", command=self.create_server_dialog, corner_radius=8, height=36)
        self.btn_create_server.grid(row=1, column=0, padx=20, pady=10, sticky="ew")

        self.lbl_servers = ctk.CTkLabel(self.sidebar_frame, text="Your Servers:", anchor="w", font=AppConfig.FONT_BODY)
        self.lbl_servers.grid(row=2, column=0, padx=20, pady=(10, 0))

        self.server_list_frame = ctk.CTkScrollableFrame(self.sidebar_frame, label_text="", corner_radius=10, border_width=1, border_color=(AppConfig.COLOR_BORDER_LIGHT, AppConfig.COLOR_BORDER_DARK))
        self.server_list_frame.grid(row=3, column=0, padx=20, pady=10, sticky="nsew")

    def _build_main_area(self):
        self.main_frame = ctk.CTkFrame(self, corner_radius=0)
        self.main_frame.grid(row=0, column=1, sticky="nsew")
        self.main_frame.grid_rowconfigure(2, weight=1)
        self.main_frame.grid_columnconfigure(0, weight=1)
        self._build_status_bar()
        self._build_dashboard()
        self._build_console_tabs()

    def _build_status_bar(self):
        self.status_frame = ctk.CTkFrame(self.main_frame, height=45, corner_radius=15, fg_color=(AppConfig.COLOR_BG_LIGHT, AppConfig.COLOR_BG_DARK))
        self.status_frame.grid(row=0, column=0, sticky="ew", padx=15, pady=10)
        
        self.lbl_status = ctk.CTkLabel(self.status_frame, text="⚪ Offline", font=("Roboto Medium", 15))
        self.lbl_status.pack(side="left", padx=20, pady=8)

        self.status_right_frame = ctk.CTkFrame(self.status_frame, fg_color="transparent")
        self.status_right_frame.pack(side="right", padx=20, pady=8)
        
        self.lbl_server_info = ctk.CTkLabel(self.status_right_frame, text="No server selected", text_color=AppConfig.COLOR_TEXT_GRAY, font=AppConfig.FONT_BODY_SMALL)
        self.lbl_server_info.pack(side="left", padx=(0, 15))
        
        self.lbl_player_count = ctk.CTkLabel(self.status_right_frame, text="Players: 0", text_color=AppConfig.COLOR_TEXT_GRAY, font=AppConfig.FONT_BODY_SMALL)
        self.lbl_player_count.pack(side="left", padx=(0, 15))
        
        self.lbl_java_ver = ctk.CTkLabel(self.status_right_frame, text="Checking...", text_color=AppConfig.COLOR_TEXT_GRAY, font=AppConfig.FONT_BODY_SMALL)
        self.lbl_java_ver.pack(side="left")

    def _build_dashboard(self):
        self.dashboard_frame = ctk.CTkFrame(self.main_frame, height=100, corner_radius=15, fg_color=(AppConfig.COLOR_BG_LIGHT, AppConfig.COLOR_BG_DARK))
        self.dashboard_frame.grid(row=1, column=0, sticky="ew", padx=15, pady=(0, 10))
        
        self.lbl_dash_title = ctk.CTkLabel(self.dashboard_frame, text="Select a server", font=AppConfig.FONT_HEADING)
        self.lbl_dash_title.pack(pady=(10, 6))

        self.controls_frame = ctk.CTkFrame(self.dashboard_frame, fg_color="transparent")
        self.controls_frame.pack(pady=6)
        self._build_server_controls()

        self.tunnel_frame = ctk.CTkFrame(self.dashboard_frame, fg_color="transparent")
        self.tunnel_frame.pack(pady=10, fill="x")
        self._build_tunnel_controls()

        self.management_frame = ctk.CTkFrame(self.dashboard_frame, fg_color="transparent")
        self.management_frame.pack(pady=(6, 10), fill="x")
        self._build_management_controls()

    def _build_server_controls(self):
        self.btn_start_all = ctk.CTkButton(self.controls_frame, text="▶ Start All", state="disabled", command=self.start_all_action, fg_color="#00AA00", hover_color="#008800",  width=110, corner_radius=8, height=36, font=("Roboto Medium", 12))
        self.btn_start_all.pack(side="left", padx=5)
        self.btn_start = ctk.CTkButton(self.controls_frame, text="▶", state="disabled", command=self.start_server_action, fg_color=AppConfig.COLOR_BTN_SUCCESS, hover_color=AppConfig.COLOR_BTN_SUCCESS_HOVER, width=45, corner_radius=8, height=36)
        self.btn_start.pack(side="left", padx=2)
        self.btn_stop = ctk.CTkButton(self.controls_frame, text="■", state="disabled", command=self.stop_server_action, fg_color=AppConfig.COLOR_BTN_DANGER, hover_color=AppConfig.COLOR_BTN_DANGER_HOVER, width=45, corner_radius=8, height=36)
        self.btn_stop.pack(side="left", padx=2)
        self.btn_edit_properties = ctk.CTkButton(self.controls_frame, text="⚙", command=self.edit_server_properties, state="disabled", width=45, corner_radius=8, height=36, fg_color=AppConfig.COLOR_BTN_SECONDARY, hover_color=AppConfig.COLOR_BTN_SECONDARY_HOVER)
        self.btn_edit_properties.pack(side="left", padx=2)
        self.btn_open_server_folder = ctk.CTkButton(self.controls_frame, text="📂", command=self.open_mods_folder_action, state="disabled", width=45, corner_radius=8, height=36, fg_color=AppConfig.COLOR_BTN_INFO, hover_color=AppConfig.COLOR_BTN_INFO_HOVER)
        self.btn_open_server_folder.pack(side="left", padx=2)

    def _build_tunnel_controls(self):
        self.lbl_tunnel_status = ctk.CTkLabel(self.tunnel_frame, text="Tunnel: Offline", text_color=AppConfig.COLOR_TEXT_GRAY, font=AppConfig.FONT_BODY)
        self.lbl_tunnel_status.pack(side="left", padx=20)
        self.lbl_public_ip = ctk.CTkLabel(self.tunnel_frame, text="Public IP: N/A", font=("Roboto Medium", 12))
        self.lbl_public_ip.pack(side="left", padx=20)

        self.tunnel_toolbar = ctk.CTkFrame(self.tunnel_frame, fg_color="transparent")
        self.tunnel_toolbar.pack(side="right", padx=10)

        self.btn_tunnel_start = ctk.CTkButton(self.tunnel_toolbar, text="▶", command=self.start_tunnel, width=45, corner_radius=8, height=36, fg_color=AppConfig.COLOR_BTN_SUCCESS, hover_color=AppConfig.COLOR_BTN_SUCCESS_HOVER)
        self.btn_tunnel_start.pack(side="left", padx=2)
        self.btn_tunnel_stop = ctk.CTkButton(self.tunnel_toolbar, text="■", command=self.stop_tunnel, state="disabled", fg_color=AppConfig.COLOR_BTN_DANGER, hover_color=AppConfig.COLOR_BTN_DANGER_HOVER, width=45, corner_radius=8, height=36)
        self.btn_tunnel_stop.pack(side="left", padx=2)
        self.btn_claim = ctk.CTkButton(self.tunnel_toolbar, text="🔗", command=self.open_claim_url, fg_color=AppConfig.COLOR_BTN_WARNING, hover_color=AppConfig.COLOR_BTN_WARNING_HOVER, width=45, corner_radius=8, height=36)
        self.btn_reset = ctk.CTkButton(self.tunnel_toolbar, text="↻", command=self.reset_tunnel, fg_color="gray", hover_color="gray30", width=45, corner_radius=8, height=36)
        self.btn_reset.pack(side="left", padx=2)

    def _build_management_controls(self):
        scheduler_container = ctk.CTkFrame(self.management_frame, fg_color="transparent")
        scheduler_container.pack(side="left", padx=20)
        
        self.lbl_scheduler = ctk.CTkLabel(scheduler_container, text="Auto-Restart:", font=("Roboto Medium", 12))
        self.lbl_scheduler.grid(row=0, column=0, padx=5, sticky="w", columnspan=3)
        
        self.var_scheduler_enabled = ctk.BooleanVar()
        self.chk_scheduler = ctk.CTkCheckBox(scheduler_container, text="", variable=self.var_scheduler_enabled, command=self.toggle_scheduler_inputs, corner_radius=6)
        self.chk_scheduler.grid(row=1, column=0, padx=5)
            if sys.platform == "win32": os.startfile(str(server_path))
            elif sys.platform == "darwin": subprocess.run(["open", str(server_path)])
            else: subprocess.run(["xdg-open", str(server_path)])
            self.server_console.log(f"[System] Opened server folder for '{self.current_server}'")
        except Exception as e:
            self.server_console.log(f"[Error] Failed to open server folder: {e}")

    def update_console(self, text):
        self.after(0, lambda: self.server_console.log(text))

    def update_tunnel_console(self, text):
        self.after(0, lambda: self.tunnel_console.log(text))

    def start_server_action(self):
        if not self.current_server: return
        if self.server_runner and self.server_runner.running:
            self.server_console.log("[Error] A server is already running.")
            return
        
        config = load_config()
        ram = config.get("ram_allocation", "2G")
        self.server_runner = ServerRunner(self.current_server, ram, self.update_console)
        
        self.server_runner.events.on(ServerEvent.READY, self.on_server_ready)
        self.server_runner.events.on(ServerEvent.STOPPED, self.on_server_stopped)
        self.server_runner.events.on(ServerEvent.PLAYER_COUNT, self.on_player_count_update)
        
        self.server_runner.start()
        
        self.lbl_status.configure(text="⏳ Starting...", text_color=AppConfig.COLOR_STATUS_STARTING)
        self.btn_start.configure(state="disabled")
        self.btn_start_all.configure(state="disabled")
        self.btn_stop.configure(state="normal")
        return self.server_runner

    def on_server_ready(self, data=None):
        self.after(0, lambda: self.lbl_status.configure(text="🟢 Running", text_color=AppConfig.COLOR_STATUS_ONLINE))
        self.after(0, self.play_notification_sound)

    def on_player_count_update(self, count):
        self.after(0, lambda: self.lbl_player_count.configure(text=f"Players: {count}"))

    def on_server_stopped(self, data=None):
        self.after(0, lambda: self.lbl_status.configure(text="⚪ Offline", text_color=AppConfig.COLOR_STATUS_OFFLINE))
        self.after(0, lambda: self.btn_start.configure(state="normal"))
        self.after(0, lambda: self.btn_start_all.configure(state="normal"))
        self.after(0, lambda: self.btn_stop.configure(state="disabled"))

    def stop_server_action(self):
        if self.server_runner:
            self.server_runner.stop()
            self.on_server_stopped()

    def create_server_dialog(self):
        ServerWizard(self, on_complete_callback=self.on_wizard_complete)

    def on_wizard_complete(self, config):
        if os.path.exists(os.path.join(SERVERS_DIR, config["name"])):
            self.server_console.log(f"[Error] Server '{config['name']}' already exists.")
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
                    logic.apply_server_settings(name, config["ram"], config["seed"], config["game_mode"], 
                                              config["difficulty"], config["view_distance"], config["simulation_distance"])
                    if config.get("icon_path"): logic.save_server_icon(name, config["icon_path"])
                    
                    self.server_console.log(f"[System] Server '{name}' created successfully.")
                    self.after(0, lambda: self._on_download_complete(dialog))
                else:
                    self.server_console.log(f"[Error] Failed to create server '{name}'. Check terminal for details.")
                    self.after(0, dialog.close)
            except Exception as e:
                self.server_console.log(f"[Error] Installation failed: {e}")
                import traceback
                print(traceback.format_exc())
                self.after(0, dialog.close)
        threading.Thread(target=run_install, daemon=True).start()

    def _on_download_complete(self, dialog):
        dialog.close()
        self.load_servers()

    def start_tunnel(self):
        self.btn_tunnel_start.configure(state="disabled")
        self.btn_tunnel_stop.configure(state="normal")
        threading.Thread(target=self.playit_manager.start, daemon=True).start()

    def stop_tunnel(self):
        self.playit_manager.stop()
        self.btn_tunnel_start.configure(state="normal")
        self.btn_tunnel_stop.configure(state="disabled")

    def reset_tunnel(self):
        if ctk.CTkInputDialog(text="Type 'yes' to confirm reset:", title="Confirm Reset").get_input() != "yes": return
        self.playit_manager.reset()
        config = load_config()
        if "playit_dns" in config:
            del config["playit_dns"]
            save_config(config)
        self.btn_tunnel_start.configure(state="normal")
        self.btn_tunnel_stop.configure(state="disabled")

    def update_playit_status(self, status, ip):
        def _update():
            color = "green" if status == "Online" else "gray"
            icon = "●"
            if status == "Error": color, icon = "red", "✖"
            elif status == "Starting...": color, icon = "orange", "⏳"
            
            self.lbl_tunnel_status.configure(text=f"Tunnel: {icon} {status}", text_color=color)
            
            display_ip = ip
            config = load_config()
            if status == "Online" and config.get("playit_dns"): display_ip = config["playit_dns"]

            if display_ip:
                self.lbl_public_ip.configure(text=f"Public IP: {display_ip}")
                self.btn_claim.pack_forget()
            else:
                self.lbl_public_ip.configure(text="Public IP: N/A")
                
            if status == "Offline":
                self.btn_tunnel_start.configure(state="normal")
                self.btn_tunnel_stop.configure(state="disabled")
                self.btn_claim.pack_forget()
        self.after(0, _update)

    def on_playit_claim(self, url):
        self.claim_url = url
        def _show_ui():
            self.btn_claim.pack(side="right", padx=10)
            self.tunnel_console.log(f"[System] Playit setup required: {url}")
            
            def _ask_dns():
                dialog = TunnelSetupDialog(self, claim_url=url, title="Tunnel DNS Name")
                dns_name = dialog.get_input()
                if dns_name:
                    dns_name = dns_name.strip().rstrip('.')
                    config = load_config()
                    config["playit_dns"] = dns_name
                    save_config(config)
                    self.server_console.log(f"[System] Saved Playit DNS: {dns_name}")
                    if self.playit_manager.current_address:
                        self.lbl_public_ip.configure(text=f"Public IP: {dns_name}")
                else:
                    self.server_console.log("[System] DNS entry skipped.")
            
            self.after(1000, _ask_dns)
            
        self.after(0, _show_ui)

    def open_claim_url(self):
        if hasattr(self, 'claim_url') and self.claim_url:
            self.tunnel_console.log(f"[UI] Manually opening claim URL...")
            webbrowser.open(self.claim_url)
        else: self.tunnel_console.log(f"[Error] No claim URL available yet.")

    def on_close(self):
        if self.server_runner: self.server_runner.stop()
        if self.playit_manager: self.playit_manager.stop()
        self.destroy()
        sys.exit(0)

if __name__ == "__main__":
    app = MCTunnelApp()
    app.protocol("WM_DELETE_WINDOW", app.on_close)
    app.mainloop()