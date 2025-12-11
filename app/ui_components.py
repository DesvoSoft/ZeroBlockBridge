import customtkinter as ctk

class ConsoleWidget(ctk.CTkTextbox):
    def __init__(self, master, **kwargs):
        super().__init__(master, **kwargs)
        self.configure(
            state="disabled", 
            font=("Consolas", 12),
            fg_color=("gray95", "gray10"),  # Sunken terminal look
            border_width=2,
            border_color=("gray80", "gray20")
        )
        
    def log(self, message):
        self.configure(state="normal")
        self.insert("end", "> " + message + "\n")  # Terminal-style prefix
        self.see("end")
        self.configure(state="disabled")

class ServerListItem(ctk.CTkFrame):
    def __init__(self, master, server_name, on_click, **kwargs):
        super().__init__(master, **kwargs)
        self.server_name = server_name
        self.on_click = on_click
        
        # Card-style design
        self.configure(
            corner_radius=15,
            fg_color=("white", "gray17"),
            border_width=1,
            border_color=("gray85", "gray25")
        )
        
        # Configure a 2-column grid
        self.grid_columnconfigure(0, weight=1)  # Name column expands
        self.grid_columnconfigure(1, weight=0)  # Button column is fixed
        
        self.lbl_name = ctk.CTkLabel(
            self, 
            text=server_name, 
            font=("Roboto Medium", 14),
            anchor="w"  # Anchor text to the left
        )
        self.lbl_name.grid(row=0, column=0, padx=15, pady=15, sticky="ew")
        
        self.btn_select = ctk.CTkButton(
            self, 
            text="→", 
            width=36, 
            font=("Roboto Medium", 18), # Larger font for icon
            corner_radius=8,
            fg_color="royalblue",
            hover_color="#3a5ba0",
            command=self._on_select
        )
        self.btn_select.grid(row=0, column=1, padx=5, pady=15)
        
    def _on_select(self):
        if self.on_click:
            self.on_click(self.server_name)

class DownloadProgressDialog(ctk.CTkToplevel):
    def __init__(self, master, title="Downloading..."):
        super().__init__(master)
        self.title(title)
        self.geometry("350x180")  # Increased size for better spacing
        self.resizable(False, False)
        self.cancelled = False
        
        # Main content with padding
        self.label = ctk.CTkLabel(
            self, 
            text="Starting download...",
            font=("Roboto", 13)  # Body text typography
        )
        self.label.pack(pady=(20, 10))
        
        # Modern, thicker progress bar
        self.progress_bar = ctk.CTkProgressBar(
            self, 
            width=280,
            height=12,  # Thicker for modern look
            corner_radius=6
        )
        self.progress_bar.pack(pady=10)
        self.progress_bar.set(0)
        
        # Secondary ghost-style cancel button
        self.btn_cancel = ctk.CTkButton(
            self,
            text="Cancel",
            width=100,
            corner_radius=8,
            fg_color="transparent",  # Ghost button style
            border_width=1,
            border_color=("gray70", "gray30"),
            hover_color=("gray90", "gray20"),
            command=self._on_cancel
        )
        self.btn_cancel.pack(pady=(10, 20))
        
        # Make modal
        self.transient(master)
        self.grab_set()
        
    def _on_cancel(self):
        self.cancelled = True
        self.close()
        
    def update_progress(self, val, status_text=None):
        try:
            if self.cancelled:
                return
            self.progress_bar.set(val)
            if status_text:
                self.label.configure(text=status_text)
            self.update_idletasks()
        except Exception:
            pass
        
    def close(self):
        try:
            self.grab_release()
            self.withdraw()
            # Delay destroy to prevent race condition with CTk internal callbacks
            # if the window is closed too quickly after creation.
            self.after(500, self.destroy)
        except Exception:
            pass
