import customtkinter as ctk
from app.app_config import AppConfig
from app.constants import SERVERS_DIR
import webbrowser
import os
from PIL import Image


class ConsoleWidget(ctk.CTkTextbox):
    def __init__(self, master, **kwargs):
        super().__init__(master, **kwargs)
        self.configure(
            state="disabled", 
            font=AppConfig.FONT_MONO,
            fg_color=(AppConfig.COLOR_CONSOLE_LIGHT, AppConfig.COLOR_CONSOLE_DARK),  # Sunken terminal look
            border_width=2,
            border_color=(AppConfig.COLOR_BORDER_LIGHT, "gray20")
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
            fg_color=(AppConfig.COLOR_BG_LIGHT, AppConfig.COLOR_BG_DARK),
            border_width=1,
            border_color=("gray85", AppConfig.COLOR_BORDER_DARK)
        )
        
        # Configure grid
        self.grid_columnconfigure(0, weight=0)  # Icon
        self.grid_columnconfigure(1, weight=1)  # Name
        
        # Icon
        icon_path = os.path.join(SERVERS_DIR, server_name, "server-icon.png")
        if os.path.exists(icon_path):
            try:
                img = ctk.CTkImage(Image.open(icon_path), size=(48, 48))
                self.lbl_icon = ctk.CTkLabel(self, text="", image=img)
                self.lbl_icon.grid(row=0, column=0, padx=(15, 5), pady=10)
                self.lbl_icon.bind("<Button-1>", lambda e: self._on_select())
            except:
                pass # Fallback to no icon
        
        self.lbl_name = ctk.CTkLabel(
            self, 
            text=server_name, 
            font=AppConfig.FONT_HEADING_SMALL,
            anchor="w"
        )
        self.lbl_name.grid(row=0, column=1, padx=10, pady=15, sticky="ew")
        self.lbl_name.bind("<Button-1>", lambda e: self._on_select())

        # Make entire frame clickable and add hover effects
        self.bind("<Button-1>", lambda e: self._on_select())
        self.bind("<Enter>", self._on_enter)
        self.bind("<Leave>", self._on_leave)
        
        # Set cursor to hand
        self.configure(cursor="hand2")
        self.lbl_name.configure(cursor="hand2")
        if hasattr(self, "lbl_icon"):
            self.lbl_icon.configure(cursor="hand2")

    def _on_enter(self, event=None):
        self.configure(fg_color=(AppConfig.COLOR_BG_SIDEBAR_LIGHT, AppConfig.COLOR_BG_SIDEBAR_DARK))

    def _on_leave(self, event=None):
        self.configure(fg_color=(AppConfig.COLOR_BG_LIGHT, AppConfig.COLOR_BG_DARK))
        
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
            font=AppConfig.FONT_BODY  # Body text typography
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
        self.wait_visibility()
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

class TunnelSetupDialog(ctk.CTkToplevel):
    def __init__(self, master, claim_url, title="Tunnel DNS Name"):
        super().__init__(master)
        self.claim_url = claim_url
        self.title(title)
        self.geometry("420x350")
        self.resizable(False, False)
        self.result = None

        # 1. Required: Visit Playit setup
        self.lbl_step1 = ctk.CTkLabel(
            self,
            text="Required: visit the Playit setup page to create your tunnel.",
            font=AppConfig.FONT_BODY,
            wraplength=380,
            justify="left"
        )
        self.lbl_step1.pack(pady=(20, 10), padx=20, anchor="w")

        # Button to open playit.gg setup website
        self.btn_open_url = ctk.CTkButton(
            self,
            text="🔗 Open playit.gg setup website",
            command=self._open_url,
            fg_color=AppConfig.COLOR_BTN_WARNING,
            hover_color=AppConfig.COLOR_BTN_WARNING_HOVER
        )
        self.btn_open_url.pack(pady=(0, 20), padx=20, anchor="w")
        
        # NEW: Button to copy claim_url to clipboard
        self.btn_copy_url = ctk.CTkButton(
            self, text="Copy URL",
            command=self._copy_url,
            fg_color=AppConfig.COLOR_BTN_INFO,
            hover_color=AppConfig.COLOR_BTN_INFO_HOVER
        )
        self.btn_copy_url.pack(pady=(0, 20), padx=20, anchor="w")

        # 2. Note about Step 3 connection behavior
        self.lbl_step1_note = ctk.CTkLabel(
            self,
            text="Note: During Step 3 on the Playit website, it may take a few tries to connect. This is expected — please wait until Step 4 appears before continuing.",
            font=AppConfig.FONT_NOTE,
            wraplength=380,
            justify="left",
            text_color=AppConfig.COLOR_TEXT_NOTE
        )
        self.lbl_step1_note.pack(pady=(0, 20), padx=20, anchor="w")


        # 3. Optional: Enter Domain
        self.lbl_step2 = ctk.CTkLabel(
            self,
            text="(Optional) Once the setup steps were completed, paste your assigned domain below to display it in the dashboard:",
            font=AppConfig.FONT_BODY,
            wraplength=380,
            justify="left"
        )
        self.lbl_step2.pack(pady=(0, 10), padx=20, anchor="w")

        self.entry = ctk.CTkEntry(self, width=380)
        self.entry.pack(pady=(0, 20), padx=20)

        # Confirm Button
        self.btn_confirm = ctk.CTkButton(
            self,
            text="Confirm",
            command=self._on_confirm,
            fg_color=AppConfig.COLOR_BTN_SUCCESS,
            hover_color=AppConfig.COLOR_BTN_SUCCESS_HOVER
        )
        self.btn_confirm.pack(pady=(0, 20))

        # Make modal
        self.transient(master)
        self.wait_visibility()
        self.grab_set()

    def _open_url(self):
        if self.claim_url:
            webbrowser.open(self.claim_url)

    def _copy_url(self):
        if self.claim_url:
            self.clipboard_clear()
            self.clipboard_append(self.claim_url)
            self.update() # Ensure clipboard is updated
            
            # Visual feedback
            old_text = self.btn_copy_url.cget("text")
            self.btn_copy_url.configure(text="✅ Copied!")
            self.after(2000, lambda: self.btn_copy_url.configure(text=old_text))

    def _on_confirm(self):
        self.result = self.entry.get()
        self.close()

    def close(self):
        self.grab_release()
        self.destroy()

    def get_input(self):
        self.master.wait_window(self)
        return self.result
