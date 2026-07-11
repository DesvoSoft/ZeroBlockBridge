import customtkinter as ctk
import logging
import threading
from app.core.app_config import AppConfig
from app.core.constants import SERVERS_DIR
from app.ui.icons import icon
from app.ui.win_effects import apply_rounded_corners
import os
from PIL import Image

logger = logging.getLogger(__name__)


def resolve_color(color):
    """Resolve (light, dark) tuple to active appearance mode string.
    
    Passes plain strings through unchanged. Tokens like
    ``AppConfig.COLOR_TEXT_PRIMARY = ("#0f172a", "#f1f5f9")``
    are resolved to the single hex string matching the current
    ``ctk.get_appearance_mode()``, for use with Tk-native widgets
    (``tag_config``, ``tk.Menu``, PIL drawing) that don't accept tuples.
    """
    if isinstance(color, tuple):
        return color[0] if ctk.get_appearance_mode() == "Light" else color[1]
    return color


def center_on_parent(toplevel, parent, width, height):
    parent.update_idletasks()
    x = parent.winfo_rootx() + (parent.winfo_width() - width) // 2
    y = parent.winfo_rooty() + (parent.winfo_height() - height) // 2
    toplevel.geometry(f"{width}x{height}+{max(x, 0)}+{max(y, 0)}")


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
        except Exception as e:
            logger.debug("ToolTip pointer check failed: %s", e)
            return

        # Position relative to mouse
        tip_x = x + 15
        tip_y = y + 15
        
        self.tooltip = ctk.CTkToplevel(self.widget)
        self.tooltip.wm_overrideredirect(True)
        self.tooltip.wm_geometry(f"+{tip_x}+{tip_y}")
        self.tooltip.attributes("-topmost", True)
        self.tooltip.configure(fg_color=AppConfig.COLOR_BTN_GHOST_HOVER)

        # Ensure it doesn't steal focus
        self.tooltip.bind("<Enter>", lambda e: self.hide())

        label = ctk.CTkLabel(self.tooltip, text=self.text,
                             fg_color=AppConfig.COLOR_BTN_GHOST_HOVER,
                             text_color=AppConfig.COLOR_TEXT_PRIMARY,
                             corner_radius=AppConfig.RADIUS_BADGE, padx=10, pady=5,
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
            except Exception as e:
                logger.debug("ToolTip destroy ignored: %s", e)
            self.tooltip = None

class ConsoleWidget(ctk.CTkTextbox):
    def __init__(self, master, max_lines=1000, **kwargs):
        super().__init__(master, **kwargs)
        self.configure(
            state="disabled",
            font=AppConfig.FONT_MONO,
            fg_color=(AppConfig.COLOR_CONSOLE_LIGHT, AppConfig.COLOR_CONSOLE_DARK),
            border_width=0,
            corner_radius=AppConfig.RADIUS_CARD,
            wrap="word"
        )
        self.max_lines = max_lines
        self._buffer = []
        self._is_paused = False

        self._apply_tag_colors()

        # Bind visibility events for lazy rendering (ARCH-04)
        top = self.winfo_toplevel()
        top.bind("<Unmap>", self._on_unmap, add="+")
        top.bind("<Map>", self._on_map, add="+")

    def _apply_tag_colors(self):
        self.tag_config("line_error", foreground=resolve_color(AppConfig.COLOR_STATUS_OFFLINE))
        self.tag_config("line_warn", foreground=resolve_color(AppConfig.COLOR_ACCENT_AMBER))
        self.tag_config("line_join", foreground=resolve_color(AppConfig.COLOR_STATUS_ONLINE))
        self.tag_config("line_leave", foreground=resolve_color(AppConfig.COLOR_TEXT_MUTED))
        self.tag_config("line_server", foreground=resolve_color(AppConfig.COLOR_ACCENT_BROWN))

    def _set_appearance_mode(self, mode_string):
        # CTk calls this on every widget when the theme flips; tag colors are
        # plain Tk strings that don't auto-switch, so re-resolve them here.
        super()._set_appearance_mode(mode_string)
        self._apply_tag_colors()

    @staticmethod
    def _line_tag(message):
        if "ERROR" in message:
            return "line_error"
        if "WARN" in message:
            return "line_warn"
        if "joined the game" in message:
            return "line_join"
        if "left the game" in message:
            return "line_leave"
        if "[Server]" in message:
            return "line_server"
        return None

    def _on_unmap(self, event):
        if event.widget == self.winfo_toplevel():
            self._is_paused = True

    def _on_map(self, event):
        if event.widget == self.winfo_toplevel():
            self._is_paused = False
            self._flush_buffer()

    def _flush_buffer(self):
        if not self._buffer: return
        self.configure(state="normal")
        
        # Batch insert up to the last 100 lines to avoid UI freeze if huge backlog
        lines_to_render = self._buffer[-100:]
        for line in lines_to_render:
            tag = self._line_tag(line)
            self.insert("end", "> " + line + "\n", tag if tag else ())
        self._buffer.clear()
        
        self._enforce_limit()
        self.see("end")
        self.configure(state="disabled")

    def _enforce_limit(self):
        lines = int(self.index("end-1c").split(".")[0])
        if lines > self.max_lines:
            # Delete from line 1.0 to (lines - max_lines + 1).0
            delete_to = float(lines - self.max_lines + 1)
            self.delete("1.0", str(delete_to))

    def log(self, message):
        # Callable from worker threads: marshal to the Tk main loop first
        if threading.current_thread() is not threading.main_thread():
            try:
                self.after(0, lambda: self.log(message))
            except Exception as e:
                logger.debug("Console log dropped (widget gone): %s", e)
            return

        if self._is_paused:
            self._buffer.append(message)
            # Cap the memory buffer as well
            if len(self._buffer) > self.max_lines:
                self._buffer = self._buffer[-self.max_lines:]
            return

        self.configure(state="normal")
        tag = self._line_tag(message)
        self.insert("end", "> " + message + "\n", tag if tag else ())
        self._enforce_limit()
        self.see("end")
        self.configure(state="disabled")

    def highlight(self, pattern):
        self.tag_remove("search_hit", "1.0", "end")
        self.tag_remove("search_hit_current", "1.0", "end")
        self._search_matches = []
        self._match_index = -1
        self._match_len = len(pattern)
        self._last_pattern = pattern
        if not pattern:
            return
        self.tag_config("search_hit", background=resolve_color(AppConfig.COLOR_ACCENT_AMBER), foreground=resolve_color(AppConfig.COLOR_TEXT_PRIMARY))
        self.tag_config("search_hit_current", background=resolve_color(AppConfig.COLOR_STATUS_ONLINE), foreground=resolve_color(AppConfig.COLOR_TEXT_PRIMARY))
        start = "1.0"
        while True:
            pos = self.search(pattern, start, stopindex="end", nocase=True)
            if not pos:
                break
            end = f"{pos}+{len(pattern)}c"
            self.tag_add("search_hit", pos, end)
            self._search_matches.append(pos)
            start = end
        if self._search_matches:
            self.jump_to_next_match()

    def jump_to_next_match(self):
        matches = getattr(self, "_search_matches", [])
        if not matches:
            return
        prev_index = getattr(self, "_match_index", -1)
        if prev_index >= 0:
            prev_pos = matches[prev_index]
            self.tag_remove("search_hit_current", prev_pos, f"{prev_pos}+{self._match_len}c")
            self.tag_add("search_hit", prev_pos, f"{prev_pos}+{self._match_len}c")

        self._match_index = (prev_index + 1) % len(matches)
        cur_pos = matches[self._match_index]
        self.tag_remove("search_hit", cur_pos, f"{cur_pos}+{self._match_len}c")
        self.tag_add("search_hit_current", cur_pos, f"{cur_pos}+{self._match_len}c")
        self.see(cur_pos)


class ServerListItem(ctk.CTkFrame):
    def __init__(self, master, server_name, on_click, on_delete=None, on_export=None, **kwargs):
        super().__init__(master, **kwargs)
        self.server_name = server_name
        self.on_click = on_click
        self.on_delete = on_delete
        self.on_export = on_export
        self.full_name = server_name
        self._selected = False
        # Border color matches fg (invisible) until selected/hovered —
        # per-side borders don't exist in CTk, this fakes an accent ring.
        self._fg_idle = (AppConfig.COLOR_BG_CARD_LIGHT, AppConfig.COLOR_BG_CARD_DARK)
        self._fg_hover = AppConfig.COLOR_BTN_GHOST_HOVER

        self.configure(
            corner_radius=AppConfig.RADIUS_CARD,
            fg_color=self._fg_idle,
            border_width=1,
            border_color=self._fg_idle
        )

        self.grid_columnconfigure(0, weight=0)
        self.grid_columnconfigure(1, weight=1)
        self.grid_columnconfigure(2, weight=0)
        self.grid_columnconfigure(3, weight=0)

        icon_path = os.path.join(SERVERS_DIR, server_name, "server-icon.png")
        self.icon_image = None
        
        if os.path.exists(icon_path):
            try:
                with Image.open(icon_path) as img_data:
                    img_in_memory = img_data.copy()
                    if img_in_memory.mode != "RGBA":
                        img_in_memory = img_in_memory.convert("RGBA")
                self.icon_image = ctk.CTkImage(img_in_memory, size=(40, 40))
            except Exception as e:
                logger.error("Error loading icon: %s", e)
        
        self.lbl_icon = ctk.CTkLabel(self, text="", image=self.icon_image, width=40, height=40)
        self.lbl_icon.grid(row=0, column=0, padx=(10, 5), pady=5) 
        
        # Truncate by rendered pixel width, not char count (proportional font)
        display_name = server_name
        try:
            import tkinter.font as tkfont
            f = tkfont.Font(family=AppConfig.FONT_FAMILY_DISPLAY, size=14, weight="bold")
            max_px = 165
            if f.measure(display_name) > max_px:
                while display_name and f.measure(display_name + "…") > max_px:
                    display_name = display_name[:-1]
                display_name += "…"
        except Exception as e:
            logger.debug("Font measure failed, char fallback: %s", e)
            if len(display_name) > 22:
                display_name = display_name[:20] + "…"

        self.lbl_name = ctk.CTkLabel(
            self, 
            text=display_name, 
            font=AppConfig.FONT_HEADING_SMALL,
            anchor="w"
        )
        self.lbl_name.grid(row=0, column=1, padx=(5, 10), pady=5, sticky="ew")

        self.status_dot = ctk.CTkLabel(
            self, text="", width=12, height=12,
            image=icon("dot", 12, AppConfig.COLOR_STATUS_OFFLINE),
        )
        self.status_dot.grid(row=0, column=2, padx=(0, 8), pady=5)

        self.bind_events(self)
        self.bind_events(self.lbl_name)
        self.bind_events(self.lbl_icon)
        self.set_cursor("hand2")

        # Add ToolTip if truncated
        if display_name != self.full_name:
            self.tooltip_ref = ToolTip(self, self.full_name)

    def set_selected(self, selected: bool):
        self._selected = selected
        self._apply_style(hovering=False)

    def _apply_style(self, hovering: bool):
        if self._selected:
            self.configure(fg_color=self._fg_hover if hovering else self._fg_idle,
                           border_color=AppConfig.COLOR_ACCENT_GREEN)
        elif hovering:
            self.configure(fg_color=self._fg_hover,
                           border_color=AppConfig.COLOR_ACCENT_GREEN)
        else:
            self.configure(fg_color=self._fg_idle, border_color=self._fg_idle)

    def set_status(self, status: str):
        color = {
            "online": AppConfig.COLOR_STATUS_ONLINE,
            "starting": AppConfig.COLOR_STATUS_STARTING,
            "offline": AppConfig.COLOR_STATUS_OFFLINE,
        }.get(status, AppConfig.COLOR_STATUS_OFFLINE)
        self.status_dot.configure(image=icon("dot", 12, color))

    def bind_events(self, widget):
        widget.bind("<Button-1>", lambda e: self._on_select())
        widget.bind("<Button-3>", self._on_right_click)
        widget.bind("<Enter>", self._on_enter)
        widget.bind("<Leave>", self._on_leave)

    def _on_right_click(self, event):
        if not self.on_delete and not self.on_export:
            return
        import tkinter as tk
        menu = tk.Menu(
            self, tearoff=0,
            bg=resolve_color((AppConfig.COLOR_BG_CARD_LIGHT, AppConfig.COLOR_BG_CARD_DARK)),
            fg=resolve_color(AppConfig.COLOR_TEXT_PRIMARY),
            activebackground=resolve_color(AppConfig.COLOR_ACCENT_GREEN),
            activeforeground=resolve_color(AppConfig.COLOR_TEXT_PRIMARY),
            activeborderwidth=0,
            borderwidth=1,
            relief="flat",
            font=(AppConfig.FONT_FAMILY, 11),
        )
        if self.on_export:
            menu.add_command(
                label="  Export as .zbbpack",
                command=lambda: self.on_export(self.server_name),
            )
        if self.on_delete:
            if self.on_export:
                menu.add_separator()
            menu.add_command(
                label=f"  Delete '{self.full_name}'",
                foreground=resolve_color(AppConfig.COLOR_BTN_DANGER),
                activeforeground=resolve_color(AppConfig.COLOR_TEXT_PRIMARY),
                activebackground=resolve_color(AppConfig.COLOR_BTN_DANGER),
                command=lambda: self.on_delete(self.server_name),
            )
        try:
            menu.tk_popup(event.x_root, event.y_root)
        finally:
            menu.grab_release()

    def set_cursor(self, cursor_type):
        self.configure(cursor=cursor_type)
        self.lbl_name.configure(cursor=cursor_type)
        self.lbl_icon.configure(cursor=cursor_type)

    def _on_enter(self, event=None):
        self._apply_style(hovering=True)

    def _on_leave(self, event=None):
        self._apply_style(hovering=False)
        
    def _on_select(self):
        if self.on_click:
            self.on_click(self.server_name)

class DownloadProgressDialog(ctk.CTkToplevel):
    def __init__(self, master, title="Downloading..."):
        super().__init__(master)
        self.title(title)
        self.geometry("350x180")
        center_on_parent(self, master, 350, 180)
        self.resizable(False, False)
        self.cancelled = False
        
        self.label = ctk.CTkLabel(self, text="Starting download...", font=AppConfig.FONT_BODY)
        self.label.pack(pady=(20, 10))

        self.progress_bar = ctk.CTkProgressBar(self, width=280, height=10, corner_radius=AppConfig.RADIUS_BADGE)
        self.progress_bar.pack(pady=10)
        self.progress_bar.set(0)

        self.btn_cancel = ctk.CTkButton(
            self,
            text="Cancel",
            width=100,
            corner_radius=AppConfig.RADIUS_BTN,
            fg_color="transparent",
            border_width=1,
            border_color=(AppConfig.COLOR_BORDER_LIGHT, AppConfig.COLOR_BORDER_DARK),
            text_color=AppConfig.COLOR_TEXT_PRIMARY,
            hover_color=AppConfig.COLOR_BTN_GHOST,
            command=self._on_cancel
        )
        self.btn_cancel.pack(pady=(10, 20))

        apply_rounded_corners(self)
        self.transient(master)
        self.wait_visibility()
        self.grab_set()
        self.protocol("WM_DELETE_WINDOW", self.close)
        
    def _on_cancel(self):
        self.cancelled = True
        self.close()
        
    def update_progress(self, val, status_text=None):
        # Callable from worker threads: marshal to the Tk main loop first
        if threading.current_thread() is not threading.main_thread():
            try:
                self.after(0, lambda: self.update_progress(val, status_text))
            except Exception as e:
                logger.debug("Progress update dropped (dialog gone): %s", e)
            return
        if self.cancelled or not self.winfo_exists():
            return
        try:
            self.progress_bar.set(val)
            if status_text:
                self.label.configure(text=status_text)
            self.update_idletasks()
        except Exception as e:
            logger.debug("Progress update ignored: %s", e)

    def close(self):
        try:
            self.grab_release()
            self.destroy()
        except Exception as e:
            logger.debug("Dialog close ignored: %s", e)


class EulaDialog(ctk.CTkToplevel):
    """First-run modal: Minecraft EULA consent.

    ZBB auto-writes eula=true on servers it creates, so the user must
    consent once. Caller checks .accepted after wait_window().
    """

    EULA_URL = "https://aka.ms/MinecraftEULA"

    def __init__(self, master):
        super().__init__(master)
        self.accepted = False
        self.title("Minecraft EULA")
        self.resizable(False, False)
        self.configure(fg_color=(AppConfig.COLOR_BG_CARD_LIGHT, AppConfig.COLOR_BG_CARD_DARK))
        self.protocol("WM_DELETE_WINDOW", self._decline)

        frame = ctk.CTkFrame(self, fg_color="transparent")
        frame.pack(padx=30, pady=25, fill="both", expand=True)

        ctk.CTkLabel(
            frame, text="Minecraft End User License Agreement",
            font=AppConfig.FONT_HEADING,
        ).pack(anchor="w", pady=(0, 12))

        ctk.CTkLabel(
            frame,
            text=(
                "Zero Block Bridge downloads and runs Minecraft server software.\n\n"
                "Running a Minecraft server requires accepting Mojang's End User\n"
                "License Agreement (EULA). If you accept, ZBB will automatically\n"
                "set eula=true for the servers you create.\n\n"
                "If you decline, the application will close."
            ),
            font=AppConfig.FONT_BODY, justify="left",
        ).pack(anchor="w", pady=(0, 10))

        link = ctk.CTkLabel(
            frame, text="Read the Minecraft EULA (aka.ms/MinecraftEULA)",
            font=AppConfig.FONT_BODY, text_color=AppConfig.COLOR_LINK, cursor="hand2",
        )
        link.pack(anchor="w", pady=(0, 18))
        link.bind("<Button-1>", self._open_eula)

        buttons = ctk.CTkFrame(frame, fg_color="transparent")
        buttons.pack(fill="x")
        ctk.CTkButton(
            buttons, text="Decline", corner_radius=AppConfig.RADIUS_BTN, width=120,
            fg_color="transparent", border_width=1,
            border_color=(AppConfig.COLOR_BORDER_LIGHT, AppConfig.COLOR_BORDER_DARK),
            text_color=AppConfig.COLOR_TEXT_PRIMARY,
            hover_color=AppConfig.COLOR_BTN_GHOST_HOVER,
            command=self._decline,
        ).pack(side="left")
        ctk.CTkButton(
            buttons, text="I Accept the EULA", corner_radius=AppConfig.RADIUS_BTN, width=180,
            fg_color=AppConfig.COLOR_BTN_PRIMARY, hover_color=AppConfig.COLOR_BTN_PRIMARY_HOVER,
            command=self._accept,
        ).pack(side="right")

        apply_rounded_corners(self)
        self.update_idletasks()
        self._center_over(master)
        self.grab_set()
        self.focus_force()

    def _center_over(self, master):
        try:
            w, h = self.winfo_reqwidth(), self.winfo_reqheight()
            x = master.winfo_rootx() + (master.winfo_width() - w) // 2
            y = master.winfo_rooty() + (master.winfo_height() - h) // 2
            self.geometry(f"+{max(x, 0)}+{max(y, 0)}")
        except Exception as e:
            logger.debug("EULA dialog centering failed: %s", e)

    def _open_eula(self, event=None):
        import webbrowser
        webbrowser.open(self.EULA_URL)

    def _accept(self):
        self.accepted = True
        self.grab_release()
        self.destroy()

    def _decline(self):
        self.accepted = False
        self.grab_release()
        self.destroy()


class ZBBDialog(ctk.CTkToplevel):
    """Themed modal dialog replacing tkinter.messagebox (which renders as
    a native gray Windows dialog and clashes with the dark UI).

    Use the classmethods:
        ZBBDialog.confirm(parent, title, message, danger=False) -> bool
        ZBBDialog.info(parent, title, message, kind="info"|"warning"|"error")
    """

    _KIND_STYLE = {
        "info":    ("dot", AppConfig.COLOR_BTN_PRIMARY),
        "warning": ("dot", AppConfig.COLOR_ACCENT_AMBER),
        "error":   ("close", AppConfig.COLOR_BTN_DANGER),
        "question": ("dot", AppConfig.COLOR_BTN_PRIMARY),
    }

    def __init__(self, parent, title, message, *, confirm_text="OK",
                 cancel_text=None, danger=False, kind="question"):
        super().__init__(parent)
        self.result = False
        self.title(title)
        self.resizable(False, False)
        self.configure(fg_color=(AppConfig.COLOR_BG_CARD_LIGHT, AppConfig.COLOR_BG_CARD_DARK))
        self.protocol("WM_DELETE_WINDOW", self._cancel)

        frame = ctk.CTkFrame(self, fg_color="transparent")
        frame.pack(padx=25, pady=20, fill="both", expand=True)

        header = ctk.CTkFrame(frame, fg_color="transparent")
        header.pack(fill="x", pady=(0, 8))
        icon_name, accent = self._KIND_STYLE.get(kind, self._KIND_STYLE["question"])
        if danger:
            accent = AppConfig.COLOR_BTN_DANGER
        ctk.CTkLabel(header, text="", image=icon(icon_name, 18, accent), width=18).pack(side="left", padx=(0, 8))
        ctk.CTkLabel(header, text=title, font=AppConfig.FONT_HEADING_SMALL).pack(side="left")

        ctk.CTkLabel(
            frame, text=message, font=AppConfig.FONT_BODY,
            justify="left", wraplength=380, anchor="w",
        ).pack(anchor="w", fill="x", pady=(0, 16))

        buttons = ctk.CTkFrame(frame, fg_color="transparent")
        buttons.pack(fill="x")
        if cancel_text:
            ctk.CTkButton(
                buttons, text=cancel_text, width=110, height=32,
                corner_radius=AppConfig.RADIUS_BTN,
                fg_color="transparent", border_width=1,
                border_color=(AppConfig.COLOR_BORDER_LIGHT, AppConfig.COLOR_BORDER_DARK),
                text_color=AppConfig.COLOR_TEXT_PRIMARY,
                hover_color=AppConfig.COLOR_BTN_GHOST_HOVER,
                command=self._cancel,
            ).pack(side="left")
        confirm_fg = AppConfig.COLOR_BTN_DANGER if danger else AppConfig.COLOR_BTN_PRIMARY
        confirm_hover = AppConfig.COLOR_BTN_DANGER_HOVER if danger else AppConfig.COLOR_BTN_PRIMARY_HOVER
        btn_ok = ctk.CTkButton(
            buttons, text=confirm_text, width=130, height=32,
            corner_radius=AppConfig.RADIUS_BTN,
            fg_color=confirm_fg, hover_color=confirm_hover,
            command=self._confirm,
        )
        btn_ok.pack(side="right")

        self.bind("<Return>", lambda e: self._confirm())
        self.bind("<Escape>", lambda e: self._cancel())

        apply_rounded_corners(self)
        self.update_idletasks()
        w, h = self.winfo_reqwidth(), self.winfo_reqheight()
        center_on_parent(self, parent, w, h)
        self.transient(parent)
        try:
            self.wait_visibility()
            self.grab_set()
        except Exception as e:
            logger.debug("ZBBDialog grab failed: %s", e)
        btn_ok.focus_set()

    def _confirm(self):
        self.result = True
        self._close()

    def _cancel(self):
        self.result = False
        self._close()

    def _close(self):
        try:
            self.grab_release()
        except Exception as e:
            logger.debug("ZBBDialog grab release failed: %s", e)
        self.destroy()

    @classmethod
    def confirm(cls, parent, title, message, *, confirm_text="Yes",
                cancel_text="Cancel", danger=False) -> bool:
        dlg = cls(parent, title, message, confirm_text=confirm_text,
                  cancel_text=cancel_text, danger=danger, kind="question")
        parent.wait_window(dlg)
        return dlg.result

    @classmethod
    def info(cls, parent, title, message, kind="info") -> None:
        dlg = cls(parent, title, message, confirm_text="OK", kind=kind,
                  danger=(kind == "error"))
        parent.wait_window(dlg)
