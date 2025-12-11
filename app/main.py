import customtkinter as ctk
import os
import sys
import threading

# Add parent directory to path so we can import app modules if running from inside app/
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


from app.ui_components import ConsoleWidget, ServerListItem, DownloadProgressDialog
from app.logic import load_config, check_java, save_config, download_server, accept_eula, install_fabric, ServerRunner
import app.logic as logic
from app.constants import SERVERS_DIR # Import SERVERS_DIR from constants
from app.playit_manager import PlayitManager
from app.server_wizard import ServerWizard
from app.server_properties_editor import ServerPropertiesEditor
from app.scheduler_service import SchedulerService
import webbrowser
import winsound  # For sound notifications

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
        """Configure window properties."""
        self.title("Zero Block Bridge")
        self.geometry("1000x650")  # Increased default size
        self.minsize(800, 550)  # Minimum window size for usability
        
        # Grid layout - Responsive weights
        self.grid_columnconfigure(0, weight=0, minsize=200)  # Sidebar - fixed min width
        self.grid_columnconfigure(1, weight=1)  # Main Content - takes remaining space
        self.grid_rowconfigure(0, weight=1)

    def _init_state_variables(self):
        """Initialize all state variables."""
        self.server_runner = None
        self.current_server = None
        self.restart_warnings_sent = set()
        self.claim_url = None

    def _init_managers(self):
        """Initialize PlayitManager and other services."""
        self.playit_manager = PlayitManager(self.update_tunnel_console, self.update_playit_status, self.on_playit_claim)

    def _build_layout(self):
        """Construct entire UI layout."""
        self._build_sidebar()
        self._build_main_area()
    
    def _build_sidebar(self):
        """Build left sidebar with server list."""
        self.sidebar_frame = ctk.CTkFrame(
            self, 
            width=200, 
            corner_radius=0,
            fg_color=("gray92", "gray14")  # Slight distinction from background
        )
        self.sidebar_frame.grid(row=0, column=0, sticky="nsew")
        self.sidebar_frame.grid_rowconfigure(3, weight=1)  # Server list gets weight
        self.sidebar_frame.grid_columnconfigure(0, weight=1)  # Allow horizontal stretch

        self.logo_label = ctk.CTkLabel(
            self.sidebar_frame, 
            text="Zero Block\nBridge", 
            font=("Roboto Medium", 20)  # Typography hierarchy
        )
        self.logo_label.grid(row=0, column=0, padx=20, pady=(20, 10))

        self.btn_create_server = ctk.CTkButton(
            self.sidebar_frame, 
            text="Create Server", 
            command=self.create_server_dialog,
            corner_radius=8,
            height=36
        )
        self.btn_create_server.grid(row=1, column=0, padx=20, pady=10, sticky="ew")

        self.lbl_servers = ctk.CTkLabel(
            self.sidebar_frame, 
            text="Your Servers:", 
            anchor="w",
            font=("Roboto Medium", 13)
        )
        self.lbl_servers.grid(row=2, column=0, padx=20, pady=(10, 0))

        # Scrollable list for servers with card styling
        self.server_list_frame = ctk.CTkScrollableFrame(
            self.sidebar_frame, 
            label_text="",
            corner_radius=10,
            border_width=1,
            border_color=("gray80", "gray25")
        )
        self.server_list_frame.grid(row=3, column=0, padx=20, pady=10, sticky="nsew")

    def _build_main_area(self):
        """Build main content area."""
        self.main_frame = ctk.CTkFrame(self, corner_radius=0)
        self.main_frame.grid(row=0, column=1, sticky="nsew")
        self.main_frame.grid_rowconfigure(2, weight=1) # Console gets weight
        self.main_frame.grid_columnconfigure(0, weight=1)

        self._build_status_bar()
        self._build_dashboard()
        self._build_console_tabs()

    def _build_status_bar(self):
        """Build the top status bar."""
        self.status_frame = ctk.CTkFrame(
            self.main_frame, 
            height=45,
            corner_radius=15,
            fg_color=("white", "gray17")
        )
        self.status_frame.grid(row=0, column=0, sticky="ew", padx=15, pady=10)
        
        self.lbl_status = ctk.CTkLabel(
            self.status_frame, 
            text="⚪ Offline", 
            font=("Roboto Medium", 15)
        )
        self.lbl_status.pack(side="left", padx=20, pady=8)

        # Right side info container
        self.status_right_frame = ctk.CTkFrame(self.status_frame, fg_color="transparent")
        self.status_right_frame.pack(side="right", padx=20, pady=8)
        
        self.lbl_server_info = ctk.CTkLabel(
            self.status_right_frame, 
            text="No server selected", 
            text_color="gray",
            font=("Roboto", 11)
        )
        self.lbl_server_info.pack(side="left", padx=(0, 15))
        
        self.lbl_java_ver = ctk.CTkLabel(
            self.status_right_frame, 
            text="Checking...", 
            text_color="gray",
            font=("Roboto", 11)
        )
        self.lbl_java_ver.pack(side="left")

    def _build_dashboard(self):
        """Build the main dashboard with all controls."""
        self.dashboard_frame = ctk.CTkFrame(
            self.main_frame, 
            height=100,
            corner_radius=15,
            fg_color=("white", "gray17")
        )
        self.dashboard_frame.grid(row=1, column=0, sticky="ew", padx=15, pady=(0, 10))
        
        self.lbl_dash_title = ctk.CTkLabel(
            self.dashboard_frame, 
            text="Select a server", 
            font=("Roboto Medium", 18)
        )
        self.lbl_dash_title.pack(pady=(10, 6))

        self.controls_frame = ctk.CTkFrame(self.dashboard_frame, fg_color="transparent")
        self.controls_frame.pack(pady=6)

        # Server Controls Toolbar
        self.btn_start_all = ctk.CTkButton(self.controls_frame, text="▶ Start All", state="disabled", command=self.start_all_action, fg_color="#00AA00", hover_color="#008800",  width=110, corner_radius=8, height=36, font=("Roboto Medium", 12))
        self.btn_start_all.pack(side="left", padx=5)
        
        self.btn_start = ctk.CTkButton(self.controls_frame, text="▶", state="disabled", command=self.start_server_action, fg_color="#22c55e", hover_color="#16a34a", width=45, corner_radius=8, height=36)
        self.btn_start.pack(side="left", padx=2)

        self.btn_stop = ctk.CTkButton(self.controls_frame, text="■", state="disabled", command=self.stop_server_action, fg_color="#ef4444", hover_color="#dc2626", width=45, corner_radius=8, height=36)
        self.btn_stop.pack(side="left", padx=2)

        self.btn_edit_properties = ctk.CTkButton(self.controls_frame, text="⚙", command=self.edit_server_properties, state="disabled", width=45, corner_radius=8, height=36, fg_color="#6366f1", hover_color="#4f46e5")
        self.btn_edit_properties.pack(side="left", padx=2)

        # Playit Tunnel Controls
        self.tunnel_frame = ctk.CTkFrame(self.dashboard_frame, fg_color="transparent")
        self.tunnel_frame.pack(pady=10, fill="x")

        self.lbl_tunnel_status = ctk.CTkLabel(self.tunnel_frame, text="Tunnel: Offline", text_color="gray", font=("Roboto", 13))
        self.lbl_tunnel_status.pack(side="left", padx=20)

        self.lbl_public_ip = ctk.CTkLabel(self.tunnel_frame, text="Public IP: N/A", font=("Roboto Medium", 12))
        self.lbl_public_ip.pack(side="left", padx=20)

        self.tunnel_toolbar = ctk.CTkFrame(self.tunnel_frame, fg_color="transparent")
        self.tunnel_toolbar.pack(side="right", padx=10)

        self.btn_tunnel_start = ctk.CTkButton(self.tunnel_toolbar, text="▶", command=self.start_tunnel, width=45, corner_radius=8, height=36, fg_color="#22c55e", hover_color="#16a34a")
        self.btn_tunnel_start.pack(side="left", padx=2)
        
        self.btn_tunnel_stop = ctk.CTkButton(self.tunnel_toolbar, text="■", command=self.stop_tunnel, state="disabled", fg_color="#ef4444", hover_color="#dc2626", width=45, corner_radius=8, height=36)
        self.btn_tunnel_stop.pack(side="left", padx=2)

        self.btn_claim = ctk.CTkButton(self.tunnel_toolbar, text="🔗", command=self.open_claim_url, fg_color="#f97316", hover_color="#ea580c", width=45, corner_radius=8, height=36)
        # Don't pack it yet, only show when needed

        self.btn_reset = ctk.CTkButton(self.tunnel_toolbar, text="↻", command=self.reset_tunnel, fg_color="#6b7280", hover_color="#4b5563", width=45, corner_radius=8, height=36)
        self.btn_reset.pack(side="left", padx=2)

        # Management Controls (Backups & Scheduler)
        self.management_frame = ctk.CTkFrame(self.dashboard_frame, fg_color="transparent")
        self.management_frame.pack(pady=(6, 10), fill="x")
        
        # Scheduler Section
        scheduler_container = ctk.CTkFrame(self.management_frame, fg_color="transparent")
        scheduler_container.pack(side="left", padx=20)
        
        self.lbl_scheduler = ctk.CTkLabel(scheduler_container, text="Auto-Restart:", font=("Roboto Medium", 12))
        self.lbl_scheduler.grid(row=0, column=0, padx=5, sticky="w", columnspan=3)
        
        self.var_scheduler_enabled = ctk.BooleanVar()
        self.chk_scheduler = ctk.CTkCheckBox(scheduler_container, text="", variable=self.var_scheduler_enabled, command=self.toggle_scheduler_inputs, corner_radius=6)
        self.chk_scheduler.grid(row=1, column=0, padx=5)
        
        self.combo_schedule_mode = ctk.CTkComboBox(scheduler_container, values=["Interval", "Daily Time"], width=100, command=self.toggle_schedule_mode, corner_radius=8, state="readonly")
        self.combo_schedule_mode.grid(row=1, column=1, padx=5)
        self.combo_schedule_mode.set("Interval")
        
        self.entry_scheduler_interval = ctk.CTkEntry(scheduler_container, width=50, placeholder_text="6", corner_radius=8)
        self.entry_scheduler_interval.grid(row=1, column=2, padx=2)
        
        self.lbl_interval_unit = ctk.CTkLabel(scheduler_container, text="h")
        self.lbl_interval_unit.grid(row=1, column=3, padx=2)
        
        self.entry_restart_time = ctk.CTkEntry(scheduler_container, width=60, placeholder_text="03:00", corner_radius=8)
        self.entry_restart_time.bind("<KeyRelease>", self._format_time_input)
        
        self.btn_apply_schedule = ctk.CTkButton(scheduler_container, text="Apply", width=70, command=self.save_scheduler_dashboard, fg_color="#3b82f6", hover_color="#2563eb", corner_radius=8, height=32)
        self.btn_apply_schedule.grid(row=1, column=4, padx=5)

        # Backup Section
        self.backup_frame = ctk.CTkFrame(self.management_frame, fg_color="transparent")
        self.backup_frame.pack(side="right", padx=20, fill="x", expand=True)
        self.backup_frame.grid_columnconfigure(1, weight=1) # Make column 1 expandable

        self.lbl_backup_title = ctk.CTkLabel(self.backup_frame, text="Quick Backup:", font=("Roboto Medium", 12))
        self.lbl_backup_title.grid(row=0, column=0, columnspan=2, sticky="w", padx=5)

        self.lbl_last_backup = ctk.CTkLabel(
            self.backup_frame, 
            text="Last: None", 
            text_color="gray",
            font=("Roboto", 12)
        )
        self.lbl_last_backup.grid(row=1, column=0, sticky="w", padx=5, pady=(0, 5))
        
        self.btn_quick_backup = ctk.CTkButton(
            self.backup_frame, 
            text="✚ Backup Now", 
            command=self.quick_backup_action, 
            width=120, 
            fg_color="#3b82f6",
            hover_color="#2563eb",
            corner_radius=8,
            height=32
        )
        self.btn_quick_backup.grid(row=1, column=1, sticky="e", padx=5, pady=(0, 5))

    def _build_console_tabs(self):
        """Build the console and log tabs."""
        self.console_tabs = ctk.CTkTabview(self.main_frame)
        self.console_tabs.grid(row=2, column=0, padx=15, pady=(0, 15), sticky="nsew")
        
        self.console_tabs.add("Console")
        self.console_tabs.add("Tunnel Log")
        
        # Server Console
        self.server_console = ConsoleWidget(self.console_tabs.tab("Console"))
        self.server_console.pack(fill="both", expand=True)
        
        self.console_input_frame = ctk.CTkFrame(self.console_tabs.tab("Console"), height=40, corner_radius=10, fg_color=("gray95", "gray15"))
        self.console_input_frame.pack(fill="x", pady=(5, 0))
        
        self.entry_console = ctk.CTkEntry(self.console_input_frame, placeholder_text="Type command here...", corner_radius=8, height=36)
        self.entry_console.pack(side="left", fill="x", expand=True, padx=(10, 5), pady=5)
        self.entry_console.bind("<Return>", self.send_server_command)
        
        self.btn_send = ctk.CTkButton(self.console_input_frame, text="Send", width=80, command=self.send_server_command, corner_radius=8, height=36, fg_color="#3b82f6", hover_color="#2563eb")
        self.btn_send.pack(side="right", padx=10, pady=5)
        
        # Tunnel Console
        self.tunnel_console = ConsoleWidget(self.console_tabs.tab("Tunnel Log"))
        self.tunnel_console.pack(fill="both", expand=True)

    def _init_background_services(self):
        """Initialize and start background services."""
        self.check_java_startup()
        self.load_servers()
        self.start_scheduler()

    def start_scheduler(self):
        """Starts the background scheduler thread."""
        def _scheduler_loop():
            import time
            while True:
                time.sleep(30)  # Check every 30 seconds
                
                if not (self.server_runner and self.server_runner.running and self.current_server):
                    continue

                service = SchedulerService(self.current_server)
                status = service.get_status()

                if not status:
                    continue
                
                # Check for warnings
                key, message = service.get_warning_message(status["remaining_seconds"], self.restart_warnings_sent)
                if key:
                    self.send_restart_warning(message)
                    self.restart_warnings_sent.add(key)
                
                # Check if restart is due
                if status["is_due"]:
                    self.server_console.log("[System] Scheduled restart due. Initiating final countdown...")
                    self.restart_server_sequence()
                    service.scheduler.update_last_run()  # Update last run time
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

    def _format_time_input(self, event=None):
        """Auto-format time input to HH:MM format."""
        current = self.entry_restart_time.get()
        
        # Remove any non-digit characters except colon
        cleaned = ''.join(c for c in current if c.isdigit() or c == ':')
        
        # Remove existing colons for processing
        digits_only = cleaned.replace(':', '')
        
        # Limit to 4 digits max
        if len(digits_only) > 4:
            digits_only = digits_only[:4]
        
        # Auto-insert colon after 2 digits
        if len(digits_only) >= 2:
            formatted = digits_only[:2] + ':' + digits_only[2:4]
        else:
            formatted = digits_only
        
        # Only update if changed to avoid cursor jumping
        if formatted != current:
            self.entry_restart_time.delete(0, "end")
            self.entry_restart_time.insert(0, formatted)


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
                # Clean version parsing - extract just the number
                # Java versions come in formats like "java version 17.0.2" or "openjdk version 17.0.2"
                if 'version' in version.lower():
                    # Extract version after "version" keyword
                    version_part = version.lower().split('version')[1].strip()
                    # Take first part (major version)
                    major_version = version_part.split('.')[0].strip('"').strip()
                else:
                    major_version = version.split('.')[0] if '.' in version else version
                
                self.lbl_java_ver.configure(text=f"Java {major_version}", text_color="green")
                self.server_console.log(f"[System] Found Java: {version}")
            else:
                self.lbl_java_ver.configure(text="No Java", text_color="red")
                self.server_console.log("[System] CRITICAL: Java not found! Please install Java 17+.")
                # In a real app, show a popup here as per MDD
        
        threading.Thread(target=_check, daemon=True).start()

    def play_notification_sound(self):
        """Plays a pleasant notification sound on Windows."""
        try:
            # Play a nice triple-beep notification
            threading.Thread(target=self._play_beeps, daemon=True).start()
        except:
            pass  # Silently fail if sound doesn't work
    
    def _play_beeps(self):
        """Plays three ascending beeps for notification."""
        try:
            import time
            # Three pleasant ascending beeps
            winsound.Beep(800, 150)   # First beep: 800Hz, 150ms
            time.sleep(0.1)
            winsound.Beep(1000, 150)  # Second beep: 1000Hz, 150ms
            time.sleep(0.1)
            winsound.Beep(1200, 200)  # Third beep: 1200Hz, 200ms
        except:
            pass

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
        
        # Detect server type (Fabric or Vanilla)
        server_path = os.path.join(SERVERS_DIR, server_name)
        server_type = "Vanilla"
        if os.path.exists(os.path.join(server_path, "fabric-server-launch.jar")):
            server_type = "Fabric"
        
        self.lbl_server_info.configure(text=f"🎮 {server_type}", text_color="white")
        self.btn_start.configure(state="normal")
        self.btn_start_all.configure(state="normal")
        self.btn_stop.configure(state="disabled") # Initially disabled until started
        self.server_console.log(f"[UI] Selected server: {server_name}")
        
        # Update UI state
        if self.server_runner and self.server_runner.running and self.server_runner.server_name == server_name:
            self.btn_start.configure(state="disabled")
            self.btn_start_all.configure(state="disabled")
            self.btn_stop.configure(state="normal")
            self.lbl_status.configure(text="🟢 Running", text_color="#22c55e")
            # Keep server type in info
            server_path = os.path.join(SERVERS_DIR, server_name)
            server_type = "Vanilla"
            if os.path.exists(os.path.join(server_path, "fabric-server-launch.jar")):
                server_type = "Fabric"
            self.lbl_server_info.configure(text=f"🎮 {server_type}", text_color="white")
            self.btn_edit_properties.configure(state="disabled")
        else:
            self.btn_start.configure(state="normal")
            self.btn_start_all.configure(state="normal")
            self.btn_stop.configure(state="disabled")
            self.lbl_status.configure(text="⚪ Offline", text_color="white")
            
            # Only enable edit button if server properties exist
            props_path = os.path.join(SERVERS_DIR, server_name, "server.properties")
            if os.path.exists(props_path):
                self.btn_edit_properties.configure(state="normal")
            else:
                self.btn_edit_properties.configure(state="disabled")

            # Keep server type in info
            server_path = os.path.join(SERVERS_DIR, server_name)
            server_type = "Vanilla"
            if os.path.exists(os.path.join(server_path, "fabric-server-launch.jar")):
                server_type = "Fabric"
            self.lbl_server_info.configure(text=f"🎮 {server_type}", text_color="white")
        
        self.update_management_ui()

    def start_all_action(self):
        """Start both server and tunnel with one click."""
        if not self.current_server:
            return
        
        # Start server first
        self.start_server_action()
        
        # Wait a moment then start tunnel
        import time
        threading.Thread(target=lambda: (time.sleep(2), self.after(0, self.start_tunnel)), daemon=True).start()
        
        self.server_console.log("[System] Starting server and tunnel...")

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
        self.btn_apply_schedule.configure(state=state)

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
        
        # Check if server is ready (Done message)
        if "Done (" in text and "For help, type" in text:
            # Server is ready! Update status and play notification sound
            self.lbl_status.configure(text="🟢 Running", text_color="#22c55e")
            self.after(0, self.play_notification_sound)

    def update_tunnel_console(self, text):
        """Thread-safe tunnel console update."""
        self.after(0, lambda: self.tunnel_console.log(text))

    def start_server_action(self):
        self.server_console.log("[Debug] start_server_action called.")
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
        
        # Update UI to "Starting" state
        self.lbl_status.configure(text="⏳ Starting...", text_color="orange")
        self.btn_start.configure(state="disabled")
        self.btn_start_all.configure(state="disabled")
        self.btn_stop.configure(state="normal")

    def stop_server_action(self):
        if self.server_runner:
            self.server_runner.stop()
            self.btn_start.configure(state="normal")
            self.btn_start_all.configure(state="normal")
            self.btn_stop.configure(state="disabled")
            self.lbl_status.configure(text="⚪ Offline", text_color="white")
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
        view_distance = config["view_distance"]
        simulation_distance = config["simulation_distance"]
        
        # Check if server exists
        if os.path.exists(os.path.join(SERVERS_DIR, name)):
            self.server_console.log(f"[Error] Server '{name}' already exists.")
            return

        # Start download thread
        args = (name, srv_type, version, ram, seed, game_mode, difficulty, view_distance, simulation_distance)
        threading.Thread(target=self.start_download_process, args=args, daemon=True).start()

    def start_download_process(self, name, srv_type, version, ram, seed, game_mode, difficulty, view_distance, simulation_distance):
        # Schedule UI update on main thread
        args = (name, srv_type, version, ram, seed, game_mode, difficulty, view_distance, simulation_distance)
        self.after(0, lambda: self.show_progress_dialog(*args))

    def show_progress_dialog(self, name, srv_type, version, ram, seed, game_mode, difficulty, view_distance, simulation_distance):
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
                    logic.apply_server_settings(name, ram, seed, game_mode, difficulty, view_distance, simulation_distance)
                    
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

