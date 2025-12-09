import customtkinter as ctk
import os
import sys
import threading

# Add parent directory to path so we can import app modules if running from inside app/
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


from app.ui_components import ConsoleWidget, ServerListItem, DownloadProgressDialog
from app.logic import load_config, check_java, save_config, download_server, accept_eula, SERVERS_DIR, install_fabric, ServerRunner
import app.logic as logic
from app.playit_manager import PlayitManager
from app.server_wizard import ServerWizard
from app.server_properties_editor import ServerPropertiesEditor
import webbrowser

ctk.set_appearance_mode("Dark")
ctk.set_default_color_theme("blue")

class MCTunnelApp(ctk.CTk):
    def __init__(self):
        super().__init__()

        self.title("Zero Block Bridge")
        self.geometry("900x600")
        
        self.server_runner = None
        self.current_server = None
        self.server_runner = None
        self.current_server = None
        self.playit_manager = PlayitManager(self.update_tunnel_console, self.update_playit_status, self.on_playit_claim)

        
        # Grid layout
        self.grid_columnconfigure(0, weight=1) # Sidebar
        self.grid_columnconfigure(1, weight=3) # Main Content/Console
        self.grid_rowconfigure(0, weight=1)

        # --- Left Sidebar (Controls & Server List) ---
        self.sidebar_frame = ctk.CTkFrame(self, width=200, corner_radius=0)
        self.sidebar_frame.grid(row=0, column=0, sticky="nsew")
        self.sidebar_frame.grid_rowconfigure(4, weight=1) # Spacer

        self.logo_label = ctk.CTkLabel(self.sidebar_frame, text="Zero Block\nBridge", font=ctk.CTkFont(size=20, weight="bold"))
        self.logo_label.grid(row=0, column=0, padx=20, pady=(20, 10))

        self.btn_create_server = ctk.CTkButton(self.sidebar_frame, text="Create Server", command=self.create_server_dialog)
        self.btn_create_server.grid(row=1, column=0, padx=20, pady=10)

        self.lbl_servers = ctk.CTkLabel(self.sidebar_frame, text="Your Servers:", anchor="w")
        self.lbl_servers.grid(row=2, column=0, padx=20, pady=(10, 0))

        # Scrollable list for servers
        self.server_list_frame = ctk.CTkScrollableFrame(self.sidebar_frame, label_text="Server List")
        self.server_list_frame.grid(row=3, column=0, padx=20, pady=10, sticky="nsew")
        
        # --- Right Side (Console & Status) ---
        self.main_frame = ctk.CTkFrame(self, corner_radius=0)
        self.main_frame.grid(row=0, column=1, sticky="nsew")
        self.main_frame.grid_rowconfigure(2, weight=1) # Console gets weight
        self.main_frame.grid_columnconfigure(0, weight=1)

        # Header / Status Bar
        self.status_frame = ctk.CTkFrame(self.main_frame, height=50)
        self.status_frame.grid(row=0, column=0, sticky="ew", padx=10, pady=10)
        
        self.lbl_status = ctk.CTkLabel(self.status_frame, text="Status: Idle", font=("Roboto", 16))
        self.lbl_status.pack(side="left", padx=20)

        self.lbl_java_ver = ctk.CTkLabel(self.status_frame, text="Checking Java...", text_color="gray")
        self.lbl_java_ver.pack(side="right", padx=20)

        # Dashboard / Controls (Initially hidden/empty)
        self.dashboard_frame = ctk.CTkFrame(self.main_frame, height=100)
        self.dashboard_frame.grid(row=1, column=0, sticky="ew", padx=10, pady=(0, 10))
        
        self.lbl_dash_title = ctk.CTkLabel(self.dashboard_frame, text="Select a server", font=("Roboto", 18, "bold"))
        self.lbl_dash_title.pack(pady=10)

        self.controls_frame = ctk.CTkFrame(self.dashboard_frame, fg_color="transparent")
        self.controls_frame.pack(pady=5)

        # Server Controls Toolbar
        self.btn_start = ctk.CTkButton(self.controls_frame, text="▶ Start", state="disabled", command=self.start_server_action, fg_color="green", hover_color="darkgreen", width=100)
        self.btn_start.pack(side="left", padx=5)

        self.btn_stop = ctk.CTkButton(self.controls_frame, text="■ Stop", state="disabled", command=self.stop_server_action, fg_color="red", hover_color="darkred", width=100)
        self.btn_stop.pack(side="left", padx=5)

        self.btn_edit_properties = ctk.CTkButton(self.controls_frame, text="⚙ Properties", command=self.edit_server_properties, state="disabled", width=100)
        self.btn_edit_properties.pack(side="left", padx=5)

        # --- Playit Tunnel Controls ---
        self.tunnel_frame = ctk.CTkFrame(self.dashboard_frame, fg_color="transparent")
        self.tunnel_frame.pack(pady=10, fill="x")

        self.lbl_tunnel_status = ctk.CTkLabel(self.tunnel_frame, text="Tunnel: Offline", text_color="gray")
        self.lbl_tunnel_status.pack(side="left", padx=20)

        self.lbl_public_ip = ctk.CTkLabel(self.tunnel_frame, text="Public IP: N/A", font=("Roboto", 12, "bold"))
        self.lbl_public_ip.pack(side="left", padx=20)

        # Tunnel Toolbar
        self.tunnel_toolbar = ctk.CTkFrame(self.tunnel_frame, fg_color="transparent")
        self.tunnel_toolbar.pack(side="right", padx=10)

        self.btn_tunnel_start = ctk.CTkButton(self.tunnel_toolbar, text="▶ Start Tunnel", command=self.start_tunnel, width=120)
        self.btn_tunnel_start.pack(side="left", padx=5)
        
        self.btn_tunnel_stop = ctk.CTkButton(self.tunnel_toolbar, text="■ Stop Tunnel", command=self.stop_tunnel, state="disabled", fg_color="red", width=120)
        self.btn_tunnel_stop.pack(side="left", padx=5)

        self.btn_claim = ctk.CTkButton(self.tunnel_toolbar, text="🔗 Link", command=self.open_claim_url, fg_color="orange", width=80)
        # Don't pack it yet, only show when needed

        self.btn_reset = ctk.CTkButton(self.tunnel_toolbar, text="↻ Reset", command=self.reset_tunnel, fg_color="gray", hover_color="darkgray", width=80)
        self.btn_reset.pack(side="left", padx=5)

        # --- Management Controls (Backups & Scheduler) ---
        self.management_frame = ctk.CTkFrame(self.dashboard_frame, fg_color="transparent")
        self.management_frame.pack(pady=5, fill="x")
        
        # Scheduler Section
        self.scheduler_frame = ctk.CTkFrame(self.management_frame, fg_color="transparent")
        self.scheduler_frame.pack(side="left", padx=20)
        
        self.lbl_scheduler = ctk.CTkLabel(self.scheduler_frame, text="Auto-Restart:", font=("Roboto", 12, "bold"))
        self.lbl_scheduler.pack(side="left", padx=5)
        
        self.var_scheduler_enabled = ctk.BooleanVar()
        self.chk_scheduler = ctk.CTkCheckBox(self.scheduler_frame, text="Enable", variable=self.var_scheduler_enabled, command=self.save_scheduler_dashboard)
        self.chk_scheduler.pack(side="left", padx=5)
        
        self.entry_scheduler_interval = ctk.CTkEntry(self.scheduler_frame, width=50, placeholder_text="6")
        self.entry_scheduler_interval.pack(side="left", padx=5)
        self.entry_scheduler_interval.bind("<Return>", lambda e: self.save_scheduler_dashboard())
        
        ctk.CTkLabel(self.scheduler_frame, text="h").pack(side="left")

        # Backup Section
        self.backup_frame = ctk.CTkFrame(self.management_frame, fg_color="transparent")
        self.backup_frame.pack(side="right", padx=20)
        
        self.lbl_last_backup = ctk.CTkLabel(self.backup_frame, text="Last Backup: None", text_color="gray")
        self.lbl_last_backup.pack(side="left", padx=10)
        
        self.btn_quick_backup = ctk.CTkButton(self.backup_frame, text="✚ Backup Now", command=self.quick_backup_action, width=100, fg_color="#2B719E")
        self.btn_quick_backup.pack(side="left", padx=5)


        # Console Tabs
        self.console_tabs = ctk.CTkTabview(self.main_frame)
        self.console_tabs.grid(row=2, column=0, padx=10, pady=(0, 10), sticky="nsew")
        
        self.console_tabs.add("Server Log")
        self.console_tabs.add("Tunnel Log")
        
        # Server Console
        self.server_console = ConsoleWidget(self.console_tabs.tab("Server Log"))
        self.server_console.pack(fill="both", expand=True)
        
        # Tunnel Console
        self.tunnel_console = ConsoleWidget(self.console_tabs.tab("Tunnel Log"))
        self.tunnel_console.pack(fill="both", expand=True)

        # --- Initialization ---
        self.check_java_startup()
        self.load_servers()
        self.start_scheduler()

    def start_scheduler(self):
        """Starts the background scheduler thread."""
        def _scheduler_loop():
            import time
            while True:
                time.sleep(60) # Check every minute
                
                if self.server_runner and self.server_runner.running and self.current_server:
                    scheduler = logic.Scheduler(self.current_server)
                    if scheduler.check_due():
                        self.server_console.log("[System] Scheduled restart due. Initiating sequence...")
                        self.restart_server_sequence()
                        scheduler.update_last_run() # Update immediately to prevent double trigger
        
        threading.Thread(target=_scheduler_loop, daemon=True).start()

    def restart_server_sequence(self):
        """Handles the automated restart sequence."""
        def _restart():
            # 1. Warn players
            if self.server_runner and self.server_runner.process:
                try:
                    self.server_console.log("[System] Broadcasting restart warning...")
                    self.server_runner.process.stdin.write("say Server restarting in 10 seconds for scheduled maintenance!\n")
                    self.server_runner.process.stdin.flush()
                except:
                    pass
            
            import time
            time.sleep(10)
            
            # 2. Stop Server
            self.after(0, self.stop_server_action)
            
            # Wait for it to actually stop
            timeout = 30
            while timeout > 0:
                if not self.server_runner: # stop_server_action sets it to None
                    break
                time.sleep(1)
                timeout -= 1
            
            time.sleep(5) # Cooldown
            
            # 3. Start Server
            self.after(0, self.start_server_action)
            
        threading.Thread(target=_restart, daemon=True).start()

    def check_java_startup(self):
        """Checks Java version in a separate thread to not block UI."""
        def _check():
            version = check_java()
            if version:
                self.lbl_java_ver.configure(text=f"Java: {version}", text_color="green")
                self.server_console.log(f"[System] Found Java: {version}")
            else:
                self.lbl_java_ver.configure(text="Java NOT FOUND", text_color="red")
                self.server_console.log("[System] CRITICAL: Java not found! Please install Java 17+.")
                # In a real app, show a popup here as per MDD
        
        threading.Thread(target=_check, daemon=True).start()

    def load_servers(self):
        # Clear existing list
        for widget in self.server_list_frame.winfo_children():
            widget.destroy()

        if not os.path.exists(SERVERS_DIR):
            os.makedirs(SERVERS_DIR)

        servers = [d for d in os.listdir(SERVERS_DIR) if os.path.isdir(os.path.join(SERVERS_DIR, d))]
        
        if not servers:
            lbl = ctk.CTkLabel(self.server_list_frame, text="No servers found.")
            lbl.pack(pady=10)
        else:
            for s in servers:
                item = ServerListItem(self.server_list_frame, server_name=s, on_click=self.on_server_select)
                item.pack(fill="x", padx=5, pady=5)
        
        self.server_console.log(f"[System] Loaded {len(servers)} servers.")

    def on_server_select(self, server_name):
        self.current_server = server_name
        self.lbl_dash_title.configure(text=f"Server: {server_name}")
        self.btn_start.configure(state="normal")
        self.btn_stop.configure(state="disabled") # Initially disabled until started
        self.server_console.log(f"[UI] Selected server: {server_name}")
        
        # Update UI state
        if self.server_runner and self.server_runner.running and self.server_runner.server_name == server_name:
            self.btn_start.configure(state="disabled")
            self.btn_stop.configure(state="normal")
            self.lbl_status.configure(text=f"Status: Running {server_name}", text_color="green")
            self.btn_edit_properties.configure(state="disabled")
        else:
            self.btn_start.configure(state="normal")
            self.btn_stop.configure(state="disabled")
            self.lbl_status.configure(text="Status: Idle", text_color="white")
            self.btn_edit_properties.configure(state="normal")
        
        self.update_management_ui()

    def update_management_ui(self):
        """Updates the management dashboard with current server info."""
        if not self.current_server:
            return
            
        # Scheduler
        scheduler = logic.Scheduler(self.current_server)
        schedule = scheduler.get_schedule()
        
        if schedule:
            self.var_scheduler_enabled.set(True)
            if schedule["type"] == "interval":
                self.entry_scheduler_interval.delete(0, "end")
                self.entry_scheduler_interval.insert(0, str(schedule["interval_hours"]))
        else:
            self.var_scheduler_enabled.set(False)
            
        # Backups
        backup_manager = logic.BackupManager(self.current_server)
        backups = backup_manager.list_backups()
        if backups:
            latest = backups[0] # Sorted desc
            self.lbl_last_backup.configure(text=f"Last: {latest['date']}")
        else:
            self.lbl_last_backup.configure(text="Last Backup: None")

    def save_scheduler_dashboard(self):
        if not self.current_server:
            return
            
        enabled = self.var_scheduler_enabled.get()
        interval = 6
        try:
            interval = int(self.entry_scheduler_interval.get())
        except:
            pass
            
        scheduler = logic.Scheduler(self.current_server)
        scheduler.set_restart_schedule(enabled, interval)
        self.server_console.log(f"[System] Scheduler updated: {'Enabled' if enabled else 'Disabled'} (Every {interval}h)")

    def quick_backup_action(self):
        if not self.current_server:
            return
            
        self.server_console.log("[System] Creating backup...")
        
        def _run():
            manager = logic.BackupManager(self.current_server)
            path = manager.create_backup()
            if path:
                self.server_console.log(f"[System] Backup created: {os.path.basename(path)}")
                self.after(0, self.update_management_ui)
            else:
                self.server_console.log("[Error] Backup failed.")
                
        threading.Thread(target=_run, daemon=True).start()

    def edit_server_properties(self):
        if not self.current_server:
            return
        if self.server_runner and self.server_runner.running:
            self.server_console.log("[Error] Stop the server before editing properties.")
            return
        
        ServerPropertiesEditor(self, self.current_server, logic)
        # Refresh UI after close in case they changed settings there
        # We can't easily hook into close, but the dashboard updates on select/actions.

    def update_console(self, text):
        """Thread-safe server console update."""
        self.after(0, lambda: self.server_console.log(text))

    def update_tunnel_console(self, text):
        """Thread-safe tunnel console update."""
        self.after(0, lambda: self.tunnel_console.log(text))

    def start_server_action(self):
        if not self.current_server:
            return
        
        if self.server_runner and self.server_runner.running:
            self.server_console.log("[Error] A server is already running.")
            return

        # Get RAM from config or default
        config = load_config()
        ram = config.get("ram_allocation", "2G")

        self.server_runner = ServerRunner(self.current_server, ram, self.update_console)
        self.server_runner.start()
        
        self.btn_start.configure(state="disabled")
        self.btn_stop.configure(state="normal")
        self.lbl_status.configure(text=f"Status: Running {self.current_server}", text_color="green")

    def stop_server_action(self):
        if self.server_runner:
            self.server_runner.stop()
            self.btn_start.configure(state="normal")
            self.btn_stop.configure(state="disabled")
            self.lbl_status.configure(text="Status: Idle", text_color="white")
            self.server_runner = None

    def create_server_dialog(self):
        # Open the new wizard
        ServerWizard(self, on_complete_callback=self.on_wizard_complete)

    def on_wizard_complete(self, config):
        # Callback from wizard
        name = config["name"]
        srv_type = config["type"]
        version = config["version"]
        ram = config["ram"]
        seed = config["seed"]
        game_mode = config["game_mode"]
        difficulty = config["difficulty"]
        
        # Check if server exists
        if os.path.exists(os.path.join(SERVERS_DIR, name)):
            self.server_console.log(f"[Error] Server '{name}' already exists.")
            return

        # Start download thread
        threading.Thread(target=self.start_download_process, args=(name, srv_type, version, ram, seed, game_mode, difficulty), daemon=True).start()

    def start_download_process(self, name, srv_type, version, ram, seed, game_mode, difficulty):
        # Schedule UI update on main thread
        self.after(0, lambda: self.show_progress_dialog(name, srv_type, version, ram, seed, game_mode, difficulty))

    def show_progress_dialog(self, name, srv_type, version, ram, seed, game_mode, difficulty):
        dialog = DownloadProgressDialog(self, title=f"Installing {name}...")
        
        def run_install():
            try:
                if srv_type == "Vanilla":
                    self.server_console.log(f"[System] Downloading Vanilla {version}...")
                    success = logic.download_server(name, srv_type, version, dialog.update_progress)
                else:
                    self.server_console.log(f"[System] Installing Fabric {version}...")
                    success = logic.install_fabric(name, version, dialog.update_progress)
                
                if success:
                    # Apply settings (RAM, Seed, Game Mode, Difficulty)
                    logic.apply_server_settings(name, ram, seed, game_mode, difficulty)
                    
                    self.server_console.log(f"[System] Server '{name}' created successfully.")
                    self.after(0, lambda: self._on_download_complete(dialog))
                else:
                    self.server_console.log(f"[Error] Failed to create server '{name}'.")
                    self.after(0, dialog.close)
            except Exception as e:
                self.server_console.log(f"[Error] Installation failed: {e}")
                self.after(0, dialog.close)
                
        threading.Thread(target=run_install, daemon=True).start()

    def _on_download_complete(self, dialog):
        dialog.close()
        self.load_servers()
        self.server_console.log("[System] Server created successfully.")

    # --- Playit Integration ---
    def start_tunnel(self):
        self.btn_tunnel_start.configure(state="disabled")
        self.btn_tunnel_stop.configure(state="normal")
        threading.Thread(target=self.playit_manager.start, daemon=True).start()

    def stop_tunnel(self):
        self.playit_manager.stop()
        self.btn_tunnel_start.configure(state="normal")
        self.btn_tunnel_stop.configure(state="disabled")

    def reset_tunnel(self):
        """Resets the playit agent."""
        if ctk.CTkInputDialog(text="Type 'yes' to confirm reset:", title="Confirm Reset").get_input() != "yes":
            return
            
        self.playit_manager.reset()
        self.btn_tunnel_start.configure(state="normal")
        self.btn_tunnel_stop.configure(state="disabled")

    def update_playit_status(self, status, ip):
        """Callback from PlayitManager."""
        def _update():
            color = "green" if status == "Online" else "gray"
            icon = "●"
            if status == "Error": 
                color = "red"
                icon = "✖"
            elif status == "Starting...":
                color = "orange"
                icon = "⏳"
            
            self.lbl_tunnel_status.configure(text=f"Tunnel: {icon} {status}", text_color=color)
            if ip:
                self.lbl_public_ip.configure(text=f"Public IP: {ip}")
                # If online, we probably don't need the claim button anymore
                self.btn_claim.pack_forget()
            else:
                self.lbl_public_ip.configure(text="Public IP: N/A")
                
            if status == "Offline":
                self.btn_tunnel_start.configure(state="normal")
                self.btn_tunnel_stop.configure(state="disabled")
                self.btn_claim.pack_forget() # Hide claim button when stopped

        self.after(0, _update)

    def on_playit_claim(self, url):
        """Callback when a claim URL is detected."""
        self.claim_url = url
        
        def _show_ui():
            # Show the button
            self.btn_claim.pack(side="right", padx=10)
            
            # Also show dialog/open browser as before
            dialog = ctk.CTkInputDialog(text=f"Playit requires setup!\nCopy this URL or click OK to open:\n{url}", title="Link Playit Account")
            webbrowser.open(url)
            self.tunnel_console.log(f"[UI] Opened claim URL in browser: {url}")
            
        self.after(0, _show_ui)

    def open_claim_url(self):
        if hasattr(self, 'claim_url') and self.claim_url:
            webbrowser.open(self.claim_url)


    def on_close(self):
        """Handles app closure to ensure subprocesses are killed."""
        if self.server_runner:
            self.server_runner.stop()
        if self.playit_manager:
            self.playit_manager.stop()
        self.destroy()
        sys.exit(0)

if __name__ == "__main__":
    app = MCTunnelApp()
    app.protocol("WM_DELETE_WINDOW", app.on_close)
    app.mainloop()

