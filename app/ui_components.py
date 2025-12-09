import customtkinter as ctk

class ConsoleWidget(ctk.CTkTextbox):
    def __init__(self, master, **kwargs):
        super().__init__(master, **kwargs)
        self.configure(state="disabled", font=("Consolas", 12))
        
    def log(self, message):
        self.configure(state="normal")
        self.insert("end", message + "\n")
        self.see("end")
        self.configure(state="disabled")

class ServerListItem(ctk.CTkFrame):
    def __init__(self, master, server_name, on_click, **kwargs):
        super().__init__(master, **kwargs)
        self.server_name = server_name
        self.on_click = on_click
        
        self.lbl_name = ctk.CTkLabel(self, text=server_name, font=("Roboto", 14, "bold"))
        self.lbl_name.pack(side="left", padx=10, pady=10)
        
        self.btn_select = ctk.CTkButton(self, text="Select", width=60, command=self._on_select)
        self.btn_select.pack(side="right", padx=10, pady=10)
        
    def _on_select(self):
        if self.on_click:
            self.on_click(self.server_name)

class DownloadProgressDialog(ctk.CTkToplevel):
    def __init__(self, master, title="Downloading..."):
        super().__init__(master)
        self.title(title)
        self.geometry("300x150")
        self.resizable(False, False)
        
        self.label = ctk.CTkLabel(self, text="Starting download...")
        self.label.pack(pady=20)
        
        self.progress_bar = ctk.CTkProgressBar(self, width=200)
        self.progress_bar.pack(pady=10)
        self.progress_bar.set(0)
        
        # Make modal
        self.transient(master)
        self.grab_set()
        
    def update_progress(self, val, status_text=None):
        self.progress_bar.set(val)
        if status_text:
            self.label.configure(text=status_text)
        self.update_idletasks()
        
    def close(self):
        self.grab_release()
        self.destroy()
