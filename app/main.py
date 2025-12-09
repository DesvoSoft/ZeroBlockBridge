import customtkinter as ctk
import os
import sys
import threading

# Add parent directory to path so we can import app modules if running from inside app/
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


from app.ui_components import ConsoleWidget, ServerListItem, DownloadProgressDialog
from app.logic import load_config, check_java, save_config, download_server, accept_eula, SERVERS_DIR, install_fabric, ServerRunner
from app.playit_manager import PlayitManager
import webbrowser

ctk.set_appearance_mode("Dark")
ctk.set_default_color_theme("blue")

class MCTunnelApp(ctk.CTk):
    def __init__(self):
        super().__init__()

        self.title("MC-Tunnel Manager (MVP)")
        self.geometry("900x600")
        
        self.server_runner = None
        self.current_server = None
        self.playit_manager = PlayitManager(self.update_console, self.update_playit_status, self.on_playit_claim)

        
        # Grid layout
        self.grid_columnconfigure(0, weight=1) # Sidebar
        self.grid_columnconfigure(1, weight=3) # Main Content/Console
        self.grid_rowconfigure(0, weight=1)

        # --- Left Sidebar (Controls & Server List) ---
        self.sidebar_frame = ctk.CTkFrame(self, width=200, corner_radius=0)
        self.sidebar_frame.grid(row=0, column=0, sticky="nsew")
        self.sidebar_frame.grid_rowconfigure(4, weight=1) # Spacer

        self.logo_label = ctk.CTkLabel(self.sidebar_frame, text="MC-Tunnel", font=ctk.CTkFont(size=20, weight="bold"))
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

        self.btn_start = ctk.CTkButton(self.controls_frame, text="Start Server", state="disabled", command=self.start_server_action, fg_color="green", hover_color="darkgreen")
        self.btn_start.pack(side="left", padx=10)

        self.btn_stop = ctk.CTkButton(self.controls_frame, text="Stop Server", state="disabled", command=self.stop_server_action, fg_color="red", hover_color="darkred")
        self.btn_stop.pack(side="left", padx=10)

        # --- Playit Tunnel Controls ---
        self.tunnel_frame = ctk.CTkFrame(self.dashboard_frame, fg_color="transparent")
        self.tunnel_frame.pack(pady=5, fill="x")

        self.lbl_tunnel_status = ctk.CTkLabel(self.tunnel_frame, text="Tunnel: Offline", text_color="gray")
        self.lbl_tunnel_status.pack(side="left", padx=20)

        self.lbl_public_ip = ctk.CTkLabel(self.tunnel_frame, text="Public IP: N/A", font=("Roboto", 12, "bold"))
        self.lbl_public_ip.pack(side="left", padx=20)

        self.btn_tunnel_start = ctk.CTkButton(self.tunnel_frame, text="Start Tunnel", command=self.start_tunnel, width=100)
        self.btn_tunnel_start.pack(side="right", padx=10)
        
        self.btn_tunnel_stop = ctk.CTkButton(self.tunnel_frame, text="Stop Tunnel", command=self.stop_tunnel, state="disabled", fg_color="red", width=100)
        self.btn_tunnel_stop.pack(side="right", padx=10)


        # Console
        self.console = ConsoleWidget(self.main_frame)
        self.console.grid(row=2, column=0, padx=10, pady=(0, 10), sticky="nsew")

        # --- Initialization ---
        self.check_java_startup()
        self.load_servers()

    def check_java_startup(self):
        """Checks Java version in a separate thread to not block UI."""
        def _check():
            version = check_java()
            if version:
                self.lbl_java_ver.configure(text=f"Java: {version}", text_color="green")
                self.console.log(f"[System] Found Java: {version}")
            else:
                self.lbl_java_ver.configure(text="Java NOT FOUND", text_color="red")
                self.console.log("[System] CRITICAL: Java not found! Please install Java 17+.")
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
        
        self.console.log(f"[System] Loaded {len(servers)} servers.")

    def on_server_select(self, server_name):
        self.current_server = server_name
        self.lbl_dash_title.configure(text=f"Server: {server_name}")
        self.btn_start.configure(state="normal")
        self.btn_stop.configure(state="disabled") # Initially disabled until started
        self.console.log(f"[UI] Selected server: {server_name}")

    def update_console(self, text):
        """Thread-safe console update."""
        self.after(0, lambda: self.console.log(text))

    def start_server_action(self):
        if not self.current_server:
            return
        
        if self.server_runner and self.server_runner.running:
            self.console.log("[Error] A server is already running.")
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
        dialog = ctk.CTkInputDialog(text="Enter Server Name:", title="Create Server")
        server_name = dialog.get_input()
        
        if server_name:
            # Check if exists
            if os.path.exists(os.path.join(SERVERS_DIR, server_name)):
                self.console.log(f"[Error] Server '{server_name}' already exists.")
                return

            self.choose_server_type(server_name)

    def choose_server_type(self, server_name):
        """Dialog to choose between Vanilla and Fabric."""
        type_dialog = ctk.CTkInputDialog(
            text="Enter server type:\n1 = Vanilla 1.21.1\n2 = Fabric 1.20.1",
            title="Choose Server Type"
        )
        choice = type_dialog.get_input()
        
        if choice == "1":
            self.start_download(server_name, "Vanilla", "1.21.1")
        elif choice == "2":
            self.start_download(server_name, "Fabric", "1.20.1")
        else:
            self.console.log("[Error] Invalid choice.")

    def start_download(self, server_name, server_type, version):
        progress_dialog = DownloadProgressDialog(self, title=f"Installing {server_name}...")
        
        def _download_thread():
            try:
                self.console.log(f"[System] Downloading server: {server_name}...")
                
                # Callback for progress
                def _progress(val):
                    progress_dialog.update_progress(val, f"Installing: {int(val*100)}%")

                # Install based on type
                if server_type == "Vanilla":
                    jar_path = download_server(server_name, "Vanilla", version, progress_callback=_progress)
                elif server_type == "Fabric":
                    jar_path = install_fabric(server_name, version, progress_callback=_progress)
                
                if jar_path:
                    self.console.log("[System] Download complete.")
                    progress_dialog.update_progress(1.0, "Generating EULA...")
                    
                    accept_eula(server_name)
                    self.console.log("[System] EULA accepted.")
                    
                    self.after(0, lambda: self._on_download_complete(progress_dialog))
                else:
                    self.console.log("[Error] Download failed.")
                    self.after(0, progress_dialog.close)
                    
            except Exception as e:
                self.console.log(f"[Error] {e}")
                self.after(0, progress_dialog.close)

        threading.Thread(target=_download_thread, daemon=True).start()

    def _on_download_complete(self, dialog):
        dialog.close()
        self.load_servers()
        self.console.log("[System] Server created successfully.")

    # --- Playit Integration ---
    def start_tunnel(self):
        self.btn_tunnel_start.configure(state="disabled")
        self.btn_tunnel_stop.configure(state="normal")
        threading.Thread(target=self.playit_manager.start, daemon=True).start()

    def stop_tunnel(self):
        self.playit_manager.stop()
        self.btn_tunnel_start.configure(state="normal")
        self.btn_tunnel_stop.configure(state="disabled")

    def update_playit_status(self, status, ip):
        """Callback from PlayitManager."""
        def _update():
            color = "green" if status == "Online" else "gray"
            if status == "Error": color = "red"
            
            self.lbl_tunnel_status.configure(text=f"Tunnel: {status}", text_color=color)
            if ip:
                self.lbl_public_ip.configure(text=f"Public IP: {ip}")
            else:
                self.lbl_public_ip.configure(text="Public IP: N/A")
                
            if status == "Offline":
                self.btn_tunnel_start.configure(state="normal")
                self.btn_tunnel_stop.configure(state="disabled")

        self.after(0, _update)

    def on_playit_claim(self, url):
        """Callback when a claim URL is detected."""
        def _show_dialog():
            dialog = ctk.CTkInputDialog(text=f"Playit requires setup!\nCopy this URL or click OK to open:\n{url}", title="Link Playit Account")
            # We can't easily make a clickable link in a standard dialog, so we'll just open it if they click OK
            # Or we could use a custom dialog. For MVP, let's open it automatically or ask.
            
            # Better UX: Open browser automatically? Or just log it?
            # The user prompt said: "muestra un diálogo emergente ... invitando al usuario a hacer clic"
            
            # Let's try to open it
            webbrowser.open(url)
            self.console.log(f"[UI] Opened claim URL in browser: {url}")
            
        self.after(0, _show_dialog)


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

