import customtkinter as ctk
from app.app_config import AppConfig
from app.constants import SERVERS_DIR
import webbrowser
import os
from PIL import Image

class ToolTip:
    def __init__(self, widget, text):
        self.widget = widget
        self.text = text
        self.tooltip = None
        self.schedule_id = None
        self.widget.bind("<Enter>", self.on_enter)
        self.widget.bind("<Leave>", self.hide)
        self.widget.bind("<ButtonPress>", self.hide)

    def on_enter(self, event=None):
        self.unschedule()
        self.schedule_id = self.widget.after(500, self.show)

    def unschedule(self):
        if self.schedule_id:
            self.widget.after_cancel(self.schedule_id)
            self.schedule_id = None

    def show(self, event=None):
        self.unschedule()
        if self.tooltip or not self.widget.winfo_exists():
            return
            
        # Final check: is the mouse still over the widget?
        try:
            x, y = self.widget.winfo_pointerxy()
            widget_x1 = self.widget.winfo_rootx()
            widget_y1 = self.widget.winfo_rooty()
            widget_x2 = widget_x1 + self.widget.winfo_width()
            widget_y2 = widget_y1 + self.widget.winfo_height()
            
            if not (widget_x1 <= x <= widget_x2 and widget_y1 <= y <= widget_y2):
                return
        except:
            return

        # Position relative to mouse
        tip_x = x + 15
        tip_y = y + 15
        
        self.tooltip = ctk.CTkToplevel(self.widget)
        self.tooltip.wm_overrideredirect(True)
        self.tooltip.wm_geometry(f"+{tip_x}+{tip_y}")
        self.tooltip.attributes("-topmost", True)
        self.tooltip.configure(fg_color=("#ebebeb", "#2b2b2b"))
        
        # Ensure it doesn't steal focus
        self.tooltip.bind("<Enter>", lambda e: self.hide())
        
        label = ctk.CTkLabel(self.tooltip, text=self.text, fg_color=("#ebebeb", "#2b2b2b"), 
                             text_color=("black", "white"), corner_radius=6, padx=10, pady=5,
                             font=ctk.CTkFont(size=12))
        label.pack()
        
        # Force update to ensure visibility
        self.tooltip.update_idletasks()
        self.tooltip.lift()

    def hide(self, event=None):
        self.unschedule()
        if self.tooltip:
            try:
                self.tooltip.destroy()
            except:
                pass
            self.tooltip = None

class ConsoleWidget(ctk.CTkTextbox):
    def __init__(self, master, **kwargs):
        super().__init__(master, **kwargs)
        self.configure(
            state="disabled", 
            font=AppConfig.FONT_MONO,
            fg_color=(AppConfig.COLOR_CONSOLE_LIGHT, AppConfig.COLOR_CONSOLE_DARK),
            border_width=2,
            border_color=(AppConfig.COLOR_BORDER_LIGHT, "gray20"),
            wrap="word"
        )
        
    def log(self, message):
        self.configure(state="normal")
        self.insert("end", "> " + message + "\n")
        self.see("end")
        self.configure(state="disabled")

class ServerListItem(ctk.CTkFrame):
    def __init__(self, master, server_name, on_click, **kwargs):
        super().__init__(master, **kwargs)
        self.server_name = server_name
        self.on_click = on_click
        self.full_name = server_name
        
        self.configure(
            corner_radius=6,
            fg_color=(AppConfig.COLOR_BG_LIGHT, AppConfig.COLOR_BG_DARK),
            border_width=1,
            border_color=("gray85", AppConfig.COLOR_BORDER_DARK)
        )
        
        self.grid_columnconfigure(0, weight=0)
        self.grid_columnconfigure(1, weight=1)
        
        icon_path = os.path.join(SERVERS_DIR, server_name, "server-icon.png")
        self.icon_image = None
        
        if os.path.exists(icon_path):
            try:
                with Image.open(icon_path) as img_data:
                    img_in_memory = img_data.copy()
                self.icon_image = ctk.CTkImage(img_in_memory, size=(40, 40))
            except Exception as e:
                print(f"Error loading icon: {e}")
        
        self.lbl_icon = ctk.CTkLabel(self, text="", image=self.icon_image)
        self.lbl_icon.grid(row=0, column=0, padx=(10, 5), pady=5) 
        
        display_name = server_name
        if len(display_name) > 22:
            display_name = display_name[:20] + "..."

        self.lbl_name = ctk.CTkLabel(
            self, 
            text=display_name, 
            font=AppConfig.FONT_HEADING_SMALL,
            anchor="w"
        )
        self.lbl_name.grid(row=0, column=1, padx=(5, 10), pady=5, sticky="ew")

        self.bind_events(self)
        self.bind_events(self.lbl_name)
        self.bind_events(self.lbl_icon)
        self.set_cursor("hand2")

        # Add ToolTip if truncated
        if len(self.full_name) > 22:
            self.tooltip_ref = ToolTip(self, self.full_name)

    def bind_events(self, widget):
        widget.bind("<Button-1>", lambda e: self._on_select())
        widget.bind("<Enter>", self._on_enter)
        widget.bind("<Leave>", self._on_leave)

    def set_cursor(self, cursor_type):
        self.configure(cursor=cursor_type)
        self.lbl_name.configure(cursor=cursor_type)
        self.lbl_icon.configure(cursor=cursor_type)

    def _on_enter(self, event=None):
        self.configure(fg_color=(AppConfig.COLOR_BG_SIDEBAR_LIGHT, AppConfig.COLOR_BG_SIDEBAR_DARK))
        self.configure(border_color=("gray60", "gray50"))

    def _on_leave(self, event=None):
        self.configure(fg_color=(AppConfig.COLOR_BG_LIGHT, AppConfig.COLOR_BG_DARK))
        self.configure(border_color=("gray85", AppConfig.COLOR_BORDER_DARK))
        
    def _on_select(self):
        if self.on_click:
            self.on_click(self.server_name)

class DownloadProgressDialog(ctk.CTkToplevel):
    def __init__(self, master, title="Downloading..."):
        super().__init__(master)
        self.title(title)
        self.geometry("350x180")
        self.resizable(False, False)
        self.cancelled = False
        
        self.label = ctk.CTkLabel(self, text="Starting download...", font=AppConfig.FONT_BODY)
        self.label.pack(pady=(20, 10))
        
        self.progress_bar = ctk.CTkProgressBar(self, width=280, height=12, corner_radius=6)
        self.progress_bar.pack(pady=10)
        self.progress_bar.set(0)
        
        self.btn_cancel = ctk.CTkButton(
            self,
            text="Cancel",
            width=100,
            corner_radius=8,
            fg_color="transparent",
            border_width=1,
            border_color=("gray70", "gray30"),
            hover_color=("gray90", "gray20"),
            command=self._on_cancel
        )
        self.btn_cancel.pack(pady=(10, 20))
        
        self.transient(master)
        self.wait_visibility()
        self.grab_set()
        
    def _on_cancel(self):
        self.cancelled = True
        self.close()
        
    def update_progress(self, val, status_text=None):
        if self.cancelled or not self.winfo_exists():
            return
        try:
            self.progress_bar.set(val)
            if status_text:
                self.label.configure(text=status_text)
            self.update_idletasks()
        except Exception:
            pass
        
    def close(self):
        try:
            self.grab_release()
            self.destroy()
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

        def create_label(text, font=AppConfig.FONT_BODY, color=None):
            return ctk.CTkLabel(self, text=text, font=font, wraplength=380, justify="left", text_color=color)

        create_label("Required: visit the Playit setup page to create your tunnel.").pack(pady=(20, 10), padx=20, anchor="w")

        btn_frame = ctk.CTkFrame(self, fg_color="transparent")
        btn_frame.pack(fill="x", padx=20, pady=(0, 15))
        
        self.btn_open_url = ctk.CTkButton(
            btn_frame, text="🔗 Open Website", command=self._open_url,
            fg_color=AppConfig.COLOR_BTN_WARNING, hover_color=AppConfig.COLOR_BTN_WARNING_HOVER, width=180
        )
        self.btn_open_url.pack(side="left", padx=(0, 10))
        
        self.btn_copy_url = ctk.CTkButton(
            btn_frame, text="Copy URL", command=self._copy_url,
            fg_color=AppConfig.COLOR_BTN_INFO, hover_color=AppConfig.COLOR_BTN_INFO_HOVER, width=100
        )
        self.btn_copy_url.pack(side="left")

        create_label(
            "Note: Connection may take a few tries. Wait for Step 4.", 
            font=AppConfig.FONT_NOTE, color=AppConfig.COLOR_TEXT_NOTE
        ).pack(pady=(0, 15), padx=20, anchor="w")

        create_label("(Optional) Paste assigned domain below:").pack(pady=(0, 5), padx=20, anchor="w")

        self.entry = ctk.CTkEntry(self, width=380)
        self.entry.pack(pady=(0, 15), padx=20)

        self.btn_confirm = ctk.CTkButton(
            self, text="Confirm", command=self._on_confirm,
            fg_color=AppConfig.COLOR_BTN_SUCCESS, hover_color=AppConfig.COLOR_BTN_SUCCESS_HOVER
        )
        self.btn_confirm.pack(pady=(0, 20))

        self.transient(master)
        self.wait_visibility()
        self.grab_set()

    def _open_url(self):
        if self.claim_url: webbrowser.open(self.claim_url)

    def _copy_url(self):
        if self.claim_url:
            self.clipboard_clear()
            self.clipboard_append(self.claim_url)
            self.update()
            
            orig_text = self.btn_copy_url.cget("text")
            self.btn_copy_url.configure(text="✅")
            self.after(1500, lambda: self.btn_copy_url.configure(text=orig_text))

    def _on_confirm(self):
        self.result = self.entry.get()
        self.close()

    def close(self):
        self.grab_release()
        self.destroy()

    def get_input(self):
        self.master.wait_window(self)
        return self.result