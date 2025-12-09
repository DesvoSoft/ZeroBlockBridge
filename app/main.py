import customtkinter as ctk
import os
import sys
import threading

# Add parent directory to path so we can import app modules if running from inside app/
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.ui_components import ConsoleWidget, ServerListItem, DownloadProgressDialog
from app.logic import load_config, check_java, save_config, download_server, accept_eula, SERVERS_DIR

ctk.set_appearance_mode("Dark")
ctk.set_default_color_theme("blue")

class MCTunnelApp(ctk.CTk):
    def __init__(self):
        super().__init__()

        self.title("MC-Tunnel Manager (MVP)")
        self.geometry("900x600")
        
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
        self.main_frame.grid_rowconfigure(1, weight=1)
        self.main_frame.grid_columnconfigure(0, weight=1)

        # Header / Status Bar
        self.status_frame = ctk.CTkFrame(self.main_frame, height=50)
        self.status_frame.grid(row=0, column=0, sticky="ew", padx=10, pady=10)
        
        self.lbl_status = ctk.CTkLabel(self.status_frame, text="Status: Idle", font=("Roboto", 16))
        self.lbl_status.pack(side="left", padx=20)

        self.lbl_java_ver = ctk.CTkLabel(self.status_frame, text="Checking Java...", text_color="gray")
        self.lbl_java_ver.pack(side="right", padx=20)

        # Console
        self.console = ConsoleWidget(self.main_frame)
        self.console.grid(row=1, column=0, padx=10, pady=(0, 10), sticky="nsew")

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
        self.console.log(f"[UI] Selected server: {server_name}")
        # TODO: Load server details

    def create_server_dialog(self):
        dialog = ctk.CTkInputDialog(text="Enter Server Name:", title="Create Server")
        server_name = dialog.get_input()
        
        if server_name:
            # Check if exists
            if os.path.exists(os.path.join(SERVERS_DIR, server_name)):
                self.console.log(f"[Error] Server '{server_name}' already exists.")
                return

            self.start_download(server_name)

    def start_download(self, server_name):
        progress_dialog = DownloadProgressDialog(self, title=f"Installing {server_name}...")
        
        def _download_thread():
            try:
                self.console.log(f"[System] Downloading server: {server_name}...")
                
                # Callback for progress
                def _progress(val):
                    progress_dialog.update_progress(val, f"Downloading: {int(val*100)}%")

                # Download Vanilla 1.21.1
                jar_path = download_server(server_name, "Vanilla", "1.21.1", progress_callback=_progress)
                
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

if __name__ == "__main__":
    app = MCTunnelApp()
    app.mainloop()
