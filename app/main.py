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
        scheduler_container = ctk.CTkFrame(self.management_frame, fg_color="transparent")
        scheduler_container.pack(side="left", padx=20)
        
        self.lbl_scheduler = ctk.CTkLabel(scheduler_container, text="Auto-Restart:", font=("Roboto", 12, "bold"))
        self.lbl_scheduler.grid(row=0, column=0, padx=5, sticky="w", columnspan=3)
        
        self.var_scheduler_enabled = ctk.BooleanVar()
        self.chk_scheduler = ctk.CTkCheckBox(scheduler_container, text="", variable=self.var_scheduler_enabled, command=self.toggle_scheduler_inputs)
        self.chk_scheduler.grid(row=1, column=0, padx=5)
        
        self.combo_schedule_mode = ctk.CTkComboBox(scheduler_container, values=["Interval", "Daily Time"], width=100, command=self.toggle_schedule_mode)
        self.combo_schedule_mode.grid(row=1, column=1, padx=5)
        self.combo_schedule_mode.set("Interval")
        
        # Interval inputs (shown by default)
        self.entry_scheduler_interval = ctk.CTkEntry(scheduler_container, width=50, placeholder_text="6")
        self.entry_scheduler_interval.grid(row=1, column=2, padx=2)
        self.entry_scheduler_interval.bind("<Return>", lambda e: self.save_scheduler_dashboard())
        
        self.lbl_interval_unit = ctk.CTkLabel(scheduler_container, text="h")
        self.lbl_interval_unit.grid(row=1, column=3, padx=2)
        
        # Time inputs (hidden by default)
        self.entry_restart_time = ctk.CTkEntry(scheduler_container, width=60, placeholder_text="03:00")
        


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
        
        self.console_input_frame = ctk.CTkFrame(self.console_tabs.tab("Server Log"), height=40)
        self.console_input_frame.pack(fill="x", pady=(5, 0))
        
        self.entry_console = ctk.CTkEntry(self.console_input_frame, placeholder_text="Type command here...")
        self.entry_console.pack(side="left", fill="x", expand=True, padx=(0, 5))
        self.entry_console.bind("<Return>", self.send_server_command)
        
        self.btn_send = ctk.CTkButton(self.console_input_frame, text="Send", width=60, command=self.send_server_command)
        self.btn_send.pack(side="right")
        
        # Tunnel Console
        self.tunnel_console = ConsoleWidget(self.console_tabs.tab("Tunnel Log"))
        self.tunnel_console.pack(fill="both", expand=True)

        # --- Initialization ---
        self.check_java_startup()
        self.load_servers()
        self.restart_warnings_sent = set()  # Track which warnings have been sent
        self.start_scheduler()

    def start_scheduler(self):
        """Starts the background scheduler thread."""
        def _scheduler_loop():
            import time
            import datetime
            
            while True:
                time.sleep(30)  # Check every 30 seconds for better warning accuracy
                
                if self.server_runner and self.server_runner.running and self.current_server:
                    scheduler = logic.Scheduler(self.current_server)
                    schedule = scheduler.get_schedule()
                    
                    if not schedule:
                        continue
                    
                    now = datetime.datetime.now()
                    remaining = None
                    
                    # Calculate time remaining based on schedule type
                    if schedule["type"] == "interval":
                        last_run_str = schedule.get("last_run")
                        if not last_run_str:
                            continue
                            
                        last_run = datetime.datetime.fromisoformat(last_run_str)
                        interval = datetime.timedelta(hours=schedule["interval_hours"])
                        next_restart = last_run + interval
                        remaining = (next_restart - now).total_seconds()
                        
                    elif schedule["type"] == "time":
                        # Time-based schedule
                        restart_time_str = schedule["restart_time"]
                        hour, minute = map(int, restart_time_str.split(":"))
                        target_time = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
                        
                        # If target time passed today, it's for tomorrow
                        if target_time <= now:
                            target_time += datetime.timedelta(days=1)
                        
                        remaining = (target_time - now).total_seconds()
                    
                    if remaining is None or remaining < 0:
                        continue
                    
                    # Send warnings at specific intervals
                    if remaining <= 3660 and remaining > 3600 and '1h' not in self.restart_warnings_sent:
                        self.send_restart_warning("Server will restart in 1 hour!")
                        self.restart_warnings_sent.add('1h')
                    elif remaining <= 1860 and remaining > 1800 and '30m' not in self.restart_warnings_sent:
                        self.send_restart_warning("Server will restart in 30 minutes!")
                        self.restart_warnings_sent.add('30m')
                    elif remaining <= 960 and remaining > 900 and '15m' not in self.restart_warnings_sent:
                        self.send_restart_warning("Server will restart in 15 minutes!")
                        self.restart_warnings_sent.add('15m')
                    elif remaining <= 65 and remaining > 60 and '1m' not in self.restart_warnings_sent:
                        self.send_restart_warning("Server will restart in 1 minute!")
                        self.restart_warnings_sent.add('1m')
                    elif remaining <= 0:
                        self.server_console.log("[System] Scheduled restart due. Initiating final countdown...")
                        self.restart_server_sequence()
                        scheduler.update_last_run()
                        self.restart_warnings_sent.clear()  # Reset for next cycle
        
        threading.Thread(target=_scheduler_loop, daemon=True).start()

    def send_restart_warning(self, message):
        """Sends a restart warning to players."""
        if self.server_runner and self.server_runner.process:
            try:
                self.server_console.log(f"[System] {message}")
                self.server_runner.process.stdin.write(f"say {message}\n")
                self.server_runner.process.stdin.flush()
            except:
                pass

    def restart_server_sequence(self):
        """Handles the automated restart sequence with final countdown."""
        def _restart():
            import time
            
            # Final 5-second countdown
            for i in [5, 4, 3, 2]:
                if self.server_runner and self.server_runner.process:
                    try:
                        self.server_console.log(f"[System] Restarting in {i}...")
                        self.server_runner.process.stdin.write(f"say Restarting in {i}...\n")
                        self.server_runner.process.stdin.flush()
                    except:
                        pass
                time.sleep(1)
            
            # Final message
            if self.server_runner and self.server_runner.process:
                try:
                    self.server_console.log("[System] Restarting NOW!")
                    self.server_runner.process.stdin.write("say Restarting NOW!\n")
                    self.server_runner.process.stdin.flush()
                except:
                    pass
            
            time.sleep(1)
            
            # Stop Server
            self.after(0, self.stop_server_action)
            
            # Wait for it to actually stop
            timeout = 30
            while timeout > 0:
                if not self.server_runner:
                    break
                time.sleep(1)
                timeout -= 1
            
            time.sleep(5)  # Cooldown
            
            # Start Server
            self.after(0, self.start_server_action)
            
            # Wait for server to start
            time.sleep(10)
            
            # Check if restart was successful
            if self.server_runner and self.server_runner.running:
                self.server_console.log("[System] ✓ Scheduled restart completed successfully! Server is back online.")
            else:
                self.server_console.log("[System] ✗ ERROR: Server failed to restart automatically. Please check logs and start manually.")
            
        threading.Thread(target=_restart, daemon=True).start()


    def send_server_command(self, event=None):
        if not self.server_runner or not self.server_runner.running:
            self.server_console.log("[UI] Server is not running.")
            return
            
        cmd = self.entry_console.get()
        if not cmd:
            return
            
        self.server_runner.send_command(cmd)
        self.entry_console.delete(0, "end")

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
                self.combo_schedule_mode.set("Interval")
                self.entry_scheduler_interval.delete(0, "end")
                self.entry_scheduler_interval.insert(0, str(schedule["interval_hours"]))
                self.toggle_schedule_mode("Interval")
            elif schedule["type"] == "time":
                self.combo_schedule_mode.set("Daily Time")
                self.entry_restart_time.delete(0, "end")
                self.entry_restart_time.insert(0, schedule["restart_time"])
                self.toggle_schedule_mode("Daily Time")
        else:
            self.var_scheduler_enabled.set(False)
        self.toggle_scheduler_inputs()
            
        # Backups
        backup_manager = logic.BackupManager(self.current_server)
        backups = backup_manager.list_backups()
        if backups:
            latest = backups[0] # Sorted desc
            self.lbl_last_backup.configure(text=f"Last: {latest['date']}")
        else:
            self.lbl_last_backup.configure(text="Last Backup: None")

    def toggle_scheduler_inputs(self):
        """Enable/disable scheduler inputs based on checkbox."""
        enabled = self.var_scheduler_enabled.get()
        state = "normal" if enabled else "disabled"
        self.combo_schedule_mode.configure(state=state)
        self.entry_scheduler_interval.configure(state=state)
        self.entry_restart_time.configure(state=state)
        if enabled:
            self.save_scheduler_dashboard()

    def toggle_schedule_mode(self, mode=None):
        """Switch between interval and time-based scheduling."""
        if mode is None:
            mode = self.combo_schedule_mode.get()
        
        if mode == "Interval":
            self.entry_scheduler_interval.grid(row=1, column=2, padx=2)
            self.lbl_interval_unit.grid(row=1, column=3, padx=2)
            self.entry_restart_time.grid_forget()
        else:  # Daily Time
            self.entry_scheduler_interval.grid_forget()
            self.lbl_interval_unit.grid_forget()
            self.entry_restart_time.grid(row=1, column=2, padx=2, columnspan=2)

    def save_scheduler_dashboard(self):
        if not self.current_server:
            return
            
        enabled = self.var_scheduler_enabled.get()
        mode = self.combo_schedule_mode.get()
        
        scheduler = logic.Scheduler(self.current_server)
        
        if mode == "Interval":
            interval = 6
            try:
                interval = int(self.entry_scheduler_interval.get())
            except:
                pass
            scheduler.set_restart_schedule(enabled, interval_hours=interval)
            self.server_console.log(f"[System] Scheduler updated: {'Enabled' if enabled else 'Disabled'} (Every {interval}h)")
        else:  # Daily Time
            restart_time = self.entry_restart_time.get() or "03:00"
            scheduler.set_restart_schedule(enabled, restart_time=restart_time)
            self.server_console.log(f"[System] Scheduler updated: {'Enabled' if enabled else 'Disabled'} (Daily at {restart_time})")

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

