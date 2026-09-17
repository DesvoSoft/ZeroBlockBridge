import customtkinter as ctk
import hashlib
import logging
import re
import threading
import time
import tkinter as tk
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


# Reveal once no widget has been (re)configured for this long — CTk draws on
# <Configure>, so a quiet period means the content is painted.
_REVEAL_QUIET_MS = 50
_REVEAL_POLL_MS = 25
_REVEAL_MAX_WAIT_MS = 600
_FADE_STEP = 0.25
_FADE_INTERVAL_MS = 15


def hide_until_drawn(window, max_wait_ms: int = _REVEAL_MAX_WAIT_MS) -> None:
    """Keep a window fully transparent until its content is drawn, then fade in.

    Windows shows a new window with a white background before Tk paints it,
    and CTk widgets then draw themselves one by one — a visible white flash
    followed by content popping in. Call right after the window is created
    (before it is built); build synchronously; the reveal runs from idle.
    """
    try:
        window.attributes("-alpha", 0.0)
    except tk.TclError as e:
        logger.debug("Window alpha unsupported: %s", e)
        return
    state = {"last": time.monotonic()}
    started = state["last"]

    def note_configure(_event=None):
        state["last"] = time.monotonic()

    def fade_in(alpha=0.0):
        if not window.winfo_exists():
            return
        alpha = min(alpha + _FADE_STEP, 1.0)
        try:
            window.attributes("-alpha", alpha)
        except tk.TclError as e:
            logger.debug("Window fade-in error: %s", e)
            return
        if alpha < 1.0:
            window.after(_FADE_INTERVAL_MS, fade_in, alpha)
        else:
            window.unbind("<Configure>", bind_id)

    def wait_until_drawn():
        if not window.winfo_exists():
            return
        now = time.monotonic()
        quiet = (now - state["last"]) * 1000 >= _REVEAL_QUIET_MS
        timed_out = (now - started) * 1000 >= max_wait_ms
        if window.winfo_ismapped() and (quiet or timed_out):
            fade_in()
        else:
            window.after(_REVEAL_POLL_MS, wait_until_drawn)

    # A toplevel binding sees <Configure> from every descendant.
    bind_id = window.bind("<Configure>", note_configure, add="+")
    # Idle runs after the caller has built the whole window.
    window.after_idle(wait_until_drawn)


class ZBBToplevel(ctk.CTkToplevel):
    """CTkToplevel that only becomes visible once its content is drawn (no
    white flash, no widgets popping in) — see hide_until_drawn."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        hide_until_drawn(self)


class ScrollableFrame(ctk.CTkScrollableFrame):
    """CTkScrollableFrame whose scrollbar only shows while the content
    overflows (CTk always shows it, even for a two-row list)."""

    _CHECK_DELAY_MS = 50

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._scrollbar_shown = True
        self._scrollbar_job = None
        # add="+": CTk already binds both for its own scrollregion/fit logic.
        self.bind("<Configure>", self._schedule_scrollbar_check, add="+")
        self._parent_canvas.bind("<Configure>", self._schedule_scrollbar_check, add="+")

    def _schedule_scrollbar_check(self, _event=None):
        if self._scrollbar_job is not None:
            self.after_cancel(self._scrollbar_job)
        self._scrollbar_job = self.after(self._CHECK_DELAY_MS, self._update_scrollbar)

    def _update_scrollbar(self):
        self._scrollbar_job = None
        if not self.winfo_exists():
            return
        needed = self.winfo_reqheight() > self._parent_canvas.winfo_height() + 1
        if needed == self._scrollbar_shown:
            return
        self._scrollbar_shown = needed
        if needed:
            self._scrollbar.grid()
        else:
            self._scrollbar.grid_remove()
            self._parent_canvas.yview_moveto(0)

def center_on_parent(toplevel, parent, width, height):
    parent.update_idletasks()
    x = parent.winfo_rootx() + (parent.winfo_width() - width) // 2
    y = parent.winfo_rooty() + (parent.winfo_height() - height) // 2
    toplevel.geometry(f"{width}x{height}+{max(x, 0)}+{max(y, 0)}")


class PopupMenu:
    """Themed popup menu (tk.Menu is a native Win32 menu that can't follow the
    app's look). Same calls as tk.Menu where the app uses them — add_command,
    add_separator, add_cascade, tk_popup, grab_release — plus icons and a
    danger style. Cascades open in place with a Back row instead of a second
    floating window.
    """

    _open_window = None
    _MIN_WIDTH = 190
    _ROW_HEIGHT = 30

    def __init__(self, parent):
        self.widget = parent.widget if isinstance(parent, PopupMenu) else parent
        self.items: list[dict] = []

    def add_command(self, label="", command=None, icon_name=None, danger=False, **_tk_options):
        self.items.append({"kind": "command", "label": label.strip(), "command": command,
                           "icon": icon_name, "danger": danger})

    def add_separator(self):
        self.items.append({"kind": "separator"})

    def add_cascade(self, label="", menu=None, icon_name=None, **_tk_options):
        self.items.append({"kind": "cascade", "label": label.strip(), "menu": menu, "icon": icon_name})

    def tk_popup(self, x, y):
        PopupMenu.close_open()
        PopupMenu._open_window = _PopupWindow(self, int(x), int(y))

    def grab_release(self):
        """tk.Menu compatibility: tk_popup doesn't block here, nothing to release."""

    @classmethod
    def close_open(cls):
        window = cls._open_window
        cls._open_window = None
        if window is not None and window.winfo_exists():
            window.destroy()


class _PopupWindow(ctk.CTkToplevel):
    def __init__(self, menu: PopupMenu, x: int, y: int):
        root = menu.widget.winfo_toplevel()
        super().__init__(root)
        self.withdraw()
        self.overrideredirect(True)
        self.attributes("-topmost", True)
        self.attributes("-alpha", 0.0)
        self.configure(fg_color=(AppConfig.COLOR_BG_CARD_LIGHT, AppConfig.COLOR_BG_CARD_DARK))
        self._anchor = (x, y)
        self._stack: list[PopupMenu] = []

        self.body = ctk.CTkFrame(
            self, corner_radius=AppConfig.RADIUS_CARD, border_width=1,
            fg_color=(AppConfig.COLOR_BG_CARD_LIGHT, AppConfig.COLOR_BG_CARD_DARK),
            border_color=(AppConfig.COLOR_BORDER_LIGHT, AppConfig.COLOR_BORDER_DARK),
        )
        self.body.pack(fill="both", expand=True)
        self._show(menu)

        self.bind("<Escape>", lambda e: PopupMenu.close_open())
        self.bind("<FocusOut>", self._on_focus_out, add="+")
        _install_popup_click_away(root)
        self.after(10, self._reveal)

    # ---------------------------------------------------------------- layout
    def _show(self, menu: PopupMenu, push: bool = True):
        if push:
            self._stack.append(menu)
        for child in self.body.winfo_children():
            child.destroy()
        rows = ctk.CTkFrame(self.body, fg_color="transparent")
        rows.pack(fill="both", expand=True, padx=5, pady=5)

        with_icons = any(item.get("icon") for item in menu.items) or len(self._stack) > 1
        if len(self._stack) > 1:
            self._row(rows, "Back", self._back, "chevron_left", muted=True)
            self._separator(rows)
        for item in menu.items:
            if item["kind"] == "separator":
                self._separator(rows)
            elif item["kind"] == "cascade":
                self._row(rows, item["label"], lambda m=item["menu"]: self._show(m),
                          item.get("icon") or ("blank" if with_icons else None), chevron=True)
            else:
                self._row(rows, item["label"], lambda c=item["command"]: self._run(c),
                          item.get("icon") or ("blank" if with_icons else None), danger=item["danger"])
        self._place()

    def _row(self, parent, text, command, icon_name=None, danger=False, chevron=False, muted=False):
        if danger:
            text_color, hover = AppConfig.COLOR_BADGE_DANGER_TEXT, AppConfig.COLOR_BADGE_DANGER_BG
        else:
            text_color = AppConfig.COLOR_TEXT_GRAY if muted else AppConfig.COLOR_TEXT_PRIMARY
            hover = AppConfig.COLOR_BTN_GHOST_HOVER
        image = None
        if icon_name == "blank":
            image = _blank_icon(14)
        elif icon_name:
            image = icon(icon_name, 14, text_color)
        button = ctk.CTkButton(
            parent, text=text, image=image, compound="left", anchor="w", height=self._height(),
            corner_radius=AppConfig.RADIUS_BADGE, fg_color="transparent", hover_color=hover,
            text_color=text_color, font=AppConfig.FONT_BODY_SMALL, command=command,
        )
        button.pack(fill="x")
        if chevron:
            arrow = ctk.CTkLabel(button, text="", image=icon("chevron_right", 12, AppConfig.COLOR_TEXT_GRAY),
                                 width=12, height=12, fg_color="transparent")
            arrow.place(relx=1.0, rely=0.5, x=-10, anchor="e")
            arrow.bind("<Button-1>", lambda e: command())
            arrow.bind("<Enter>", lambda e: button._on_enter())

    def _height(self):
        return PopupMenu._ROW_HEIGHT

    def _separator(self, parent):
        ctk.CTkFrame(parent, height=1, fg_color=(AppConfig.COLOR_BORDER_LIGHT, AppConfig.COLOR_BORDER_DARK)).pack(
            fill="x", padx=6, pady=4)

    def _place(self):
        self.update_idletasks()
        width = max(PopupMenu._MIN_WIDTH, self.body.winfo_reqwidth())
        height = self.body.winfo_reqheight()
        x, y = self._anchor
        screen_w, screen_h = self.winfo_screenwidth(), self.winfo_screenheight()
        if x + width > screen_w:
            x = max(0, screen_w - width - 4)
        if y + height > screen_h:
            y = max(0, y - height)
        self.geometry(f"{width}x{height}+{x}+{y}")

    def _reveal(self):
        if not self.winfo_exists():
            return
        self.deiconify()
        from app.ui.win_effects import round_window_corners
        round_window_corners(self, small=True)
        self.lift()
        self.focus_force()
        self.after(15, lambda: self.winfo_exists() and self.attributes("-alpha", 1.0))

    # ---------------------------------------------------------------- behavior
    def _back(self):
        self._stack.pop()
        self._show(self._stack[-1], push=False)

    def _run(self, command):
        PopupMenu.close_open()
        if command is not None:
            # After the popup is gone: the command may open a dialog or grab.
            self.master.after(10, command)

    def _on_focus_out(self, _event=None):
        # Focus left the whole app (another program was clicked): close. Focus
        # moving inside the app is handled by the click-away binding.
        self.after(60, lambda: self.winfo_exists() and self.focus_get() is None and PopupMenu.close_open())

    def contains(self, x_root: int, y_root: int) -> bool:
        return (self.winfo_rootx() <= x_root < self.winfo_rootx() + self.winfo_width()
                and self.winfo_rooty() <= y_root < self.winfo_rooty() + self.winfo_height())


_BLANK_ICONS: dict = {}


def _blank_icon(size: int):
    """Transparent spacer so labels line up when only some items have icons."""
    if size not in _BLANK_ICONS:
        blank = Image.new("RGBA", (size, size), (0, 0, 0, 0))
        _BLANK_ICONS[size] = ctk.CTkImage(blank, size=(size, size))
    return _BLANK_ICONS[size]


def _install_popup_click_away(root):
    """One app-wide handler (installed once): a click anywhere outside the open
    popup closes it. Never unbound, so it can't remove CTk's own bindings."""
    if getattr(root, "_zbb_popup_click_away", False):
        return
    root._zbb_popup_click_away = True

    def on_click(event):
        window = PopupMenu._open_window
        if window is not None and window.winfo_exists() and not window.contains(event.x_root, event.y_root):
            PopupMenu.close_open()

    root.bind_all("<Button-1>", on_click, add="+")
    root.bind_all("<Button-3>", on_click, add="+")
    root.bind("<Configure>", lambda e: e.widget is root and PopupMenu.close_open(), add="+")


def themed_menu(parent):
    """App-styled popup menu (see PopupMenu)."""
    return PopupMenu(parent)


def add_danger_command(menu, label, command, icon_name=None):
    menu.add_command(label=label, command=command, icon_name=icon_name, danger=True)


def dialog_header(parent, title, subtitle=None):
    """Title (+ optional subtitle, e.g. the server it applies to) at the top of
    a dialog body. Titlebars draw no caption, so every dialog names itself
    here. Returns (frame, title_label, subtitle_label_or_None); the caller
    places the frame."""
    frame = ctk.CTkFrame(parent, fg_color="transparent")
    lbl_title = ctk.CTkLabel(frame, text=title, font=AppConfig.FONT_HEADING, anchor="w")
    lbl_title.pack(anchor="w")
    lbl_subtitle = None
    if subtitle is not None:
        lbl_subtitle = ctk.CTkLabel(frame, text=subtitle, font=AppConfig.FONT_BODY_SMALL,
                                    text_color=AppConfig.COLOR_TEXT_GRAY, anchor="w")
        lbl_subtitle.pack(anchor="w")
    return frame, lbl_title, lbl_subtitle


def dialog_buttons(parent, primary_text, on_primary, secondary_text=None, on_secondary=None,
                   danger=False, primary_colors=None, height=32, primary_width=130, secondary_width=110):
    """Footer buttons shared by every dialog, one convention everywhere:
    right-aligned, primary action rightmost (lime; red when destructive, or a
    caller's (fg, hover, text) brand triple), outlined secondary right beside it.

    Returns (row_frame, primary_button, secondary_button_or_None); the caller
    places row_frame.
    """
    row = ctk.CTkFrame(parent, fg_color="transparent")
    if primary_colors:
        fg, hover, text = primary_colors
    elif danger:
        fg, hover, text = AppConfig.COLOR_BTN_DANGER, AppConfig.COLOR_BTN_DANGER_HOVER, AppConfig.COLOR_TEXT_ON_ACCENT
    else:
        fg, hover, text = AppConfig.COLOR_BTN_PRIMARY, AppConfig.COLOR_BTN_PRIMARY_HOVER, AppConfig.COLOR_TEXT_ON_ACCENT
    primary = ctk.CTkButton(
        row, text=primary_text, width=primary_width, height=height, corner_radius=AppConfig.RADIUS_BTN,
        fg_color=fg, hover_color=hover, text_color=text, command=on_primary,
    )
    primary.pack(side="right")
    secondary = None
    if secondary_text:
        secondary = ctk.CTkButton(
            row, text=secondary_text, width=secondary_width, height=height, corner_radius=AppConfig.RADIUS_BTN,
            fg_color="transparent", border_width=AppConfig.BORDER_BTN,
            border_color=(AppConfig.COLOR_BORDER_LIGHT, AppConfig.COLOR_BORDER_DARK),
            text_color=AppConfig.COLOR_TEXT_PRIMARY, hover_color=AppConfig.COLOR_BTN_GHOST_HOVER,
            command=on_secondary,
        )
        secondary.pack(side="right", padx=(0, 8))
    return row, primary, secondary


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
        if self.tooltip or not self.text or not self.widget.winfo_exists():
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
                             font=AppConfig.FONT_CAPTION)
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

_AGENT_LINE_RE = re.compile(r"^\[Playit\] (\S+\s+)?(TRACE|DEBUG|INFO)\b")


class ConsoleWidget(ctk.CTkTextbox):
    # Category filter groups — a filter hides every tag not in the selected
    # group by setting Tk's own `elide` option (hides tagged text without
    # deleting it, so switching back to "All" is instant, no re-render).
    _FILTER_GROUPS = {
        "errors": ("line_error",),
        "warnings": ("line_warn",),
        "security": ("line_security",),
        "players": ("line_join", "line_leave"),
        "server": ("line_server",),
    }
    _ALL_TAGS = ("line_error", "line_warn", "line_join", "line_leave", "line_server", "line_security", "line_plain")
    # (menu label, _FILTER_GROUPS key) for the category dropdown above the log
    FILTERS = (("All", None), ("Errors", "errors"), ("Warnings", "warnings"),
               ("Security", "security"), ("Players", "players"), ("Server", "server"))
    FILTER_HINT = "Show only lines in this category (join/leave, errors, etc.)"

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
        self._active_filter = None

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
        self.tag_config("line_security", foreground=resolve_color(AppConfig.COLOR_STATUS_ERROR))

    def _set_appearance_mode(self, mode_string):
        # CTk calls this on every widget when the theme flips; tag colors are
        # plain Tk strings that don't auto-switch, so re-resolve them here.
        super()._set_appearance_mode(mode_string)
        self._apply_tag_colors()

    @staticmethod
    def _line_tag(message):
        # Prefix match only: server output (player chat) can contain the
        # literal text "[Security]" and must not pass as a ZBB alert.
        # Always returns a tag (never None) — "line_plain" for everything
        # else — so the category filter can also hide/show untagged lines.
        if message.startswith("[Security]"):
            return "line_security"
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
        return "line_plain"

    @classmethod
    def _elide_map(cls, category: str | None) -> dict:
        """Pure logic behind set_category_filter: {tag: should_be_hidden}.
        Kept Tk-free (same reasoning as _line_tag being a @staticmethod) so
        it's unit-testable without a live display. Unknown/None/"all" all
        mean "show everything".
        """
        visible_tags = cls._FILTER_GROUPS.get(category) if category else None
        return {tag: (visible_tags is not None and tag not in visible_tags) for tag in cls._ALL_TAGS}

    def set_category_filter(self, category: str | None):
        """Show only lines in `category` (a key of _FILTER_GROUPS), or
        everything when `category` is None/"all"/unrecognized. Hiding uses
        Tk's `elide` tag option — lines stay in the buffer, so switching
        back to "All" is instant and loses nothing."""
        self._active_filter = category
        for tag, hidden in self._elide_map(category).items():
            self.tag_config(tag, elide=hidden)

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


class TunnelLogWidget(ConsoleWidget):
    """Tunnel Log: same widget, tunnel-specific categories. Player/security
    categories never match Playit output; what matters here is ZBB's own
    tunnel lifecycle messages vs the agent's raw log."""

    _FILTER_GROUPS = {
        "errors": ("line_error",),
        "warnings": ("line_warn",),
        "tunnel": ("line_tunnel",),
        "agent": ("line_agent",),
    }
    _ALL_TAGS = ("line_error", "line_warn", "line_tunnel", "line_agent", "line_plain")
    FILTERS = (("All", None), ("Errors", "errors"), ("Warnings", "warnings"),
               ("Tunnel", "tunnel"), ("Agent", "agent"))
    FILTER_HINT = "Tunnel: ZBB's tunnel steps (start, address, reset). Agent: raw playitd output."

    @staticmethod
    def _line_tag(message):
        if "ERROR" in message or "Error" in message or "failed" in message or "Failed" in message:
            return "line_error"
        if "WARN" in message:
            return "line_warn"
        if _AGENT_LINE_RE.match(message):
            return "line_agent"
        if message.startswith(("[Playit]", "[System]", "[UI]")):
            return "line_tunnel"
        return "line_plain"

    def _apply_tag_colors(self):
        self.tag_config("line_error", foreground=resolve_color(AppConfig.COLOR_STATUS_OFFLINE))
        self.tag_config("line_warn", foreground=resolve_color(AppConfig.COLOR_ACCENT_AMBER))
        self.tag_config("line_agent", foreground=resolve_color(AppConfig.COLOR_TEXT_MUTED))


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
        
        if self.icon_image is not None:
            self.lbl_icon = ctk.CTkLabel(self, text="", image=self.icon_image, width=40, height=40)
        else:
            # Initial-letter tile (same scheme as mod cards): without it, rows
            # for icon-less servers showed an empty gap beside the name.
            tile = AppConfig.ICON_PLACEHOLDER_COLORS[
                int(hashlib.md5(server_name.encode()).hexdigest(), 16) % len(AppConfig.ICON_PLACEHOLDER_COLORS)]
            self.lbl_icon = ctk.CTkLabel(
                self, text=(server_name[:1] or "?").upper(), width=40, height=40,
                fg_color=tile, corner_radius=AppConfig.RADIUS_BTN,
                font=AppConfig.FONT_HEADING_SMALL, text_color=AppConfig.COLOR_TEXT_ON_ACCENT,
            )
        self.lbl_icon.grid(row=0, column=0, rowspan=2, padx=(10, 8), pady=8)
        
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
        self.lbl_name.grid(row=0, column=1, padx=(0, 10), pady=(8, 0), sticky="sew")

        # Subtitle: engine + version.
        self.lbl_engine = ctk.CTkLabel(self, text=self._engine_text(server_name), height=16, anchor="w",
                                       font=AppConfig.FONT_BODY_SMALL, text_color=AppConfig.COLOR_TEXT_GRAY)
        self.lbl_engine.grid(row=1, column=1, padx=(0, 10), pady=(0, 8), sticky="nw")

        # State LED: right edge, vertically centered, only while running/starting
        # (one server runs at a time, so the LED alone marks it).
        self.status_led = ctk.CTkLabel(self, text="", width=12, height=12)
        self.status_led.grid(row=0, column=2, rowspan=2, padx=(0, 14))
        self.set_status("offline")

        self.bind_events(self)
        for widget in (self.lbl_name, self.lbl_icon, self.lbl_engine, self.status_led):
            self.bind_events(widget)
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

    _LED_COLORS = {
        "online": (AppConfig.COLOR_STATUS_ONLINE, "Running"),
        "starting": (AppConfig.COLOR_STATUS_STARTING, "Starting"),
    }

    @staticmethod
    def _engine_text(server_name: str) -> str:
        from app.core.logic import get_server_meta
        meta = get_server_meta(server_name) or {}
        engine = str(meta.get("type") or "vanilla").title()
        return f"{engine} {meta.get('version', '')}".strip()

    def set_status(self, status: str):
        led = self._LED_COLORS.get(status)
        if led is None:
            self.status_led.grid_remove()
            return
        color, label = led
        self.status_led.configure(image=icon("dot", 12, color))
        self.status_led.grid()
        if not hasattr(self, "_led_tooltip"):
            self._led_tooltip = ToolTip(self.status_led, label)
        else:
            self._led_tooltip.text = label

    def bind_events(self, widget):
        widget.bind("<Button-1>", lambda e: self._on_select())
        widget.bind("<Button-3>", self._on_right_click)
        widget.bind("<Enter>", self._on_enter)
        widget.bind("<Leave>", self._on_leave)

    def _on_right_click(self, event):
        if not self.on_delete and not self.on_export:
            return
        menu = themed_menu(self)
        if self.on_export:
            menu.add_command(
                label="Export as .zbbpack", icon_name="package",
                command=lambda: self.on_export(self.server_name),
            )
        if self.on_delete:
            if self.on_export:
                menu.add_separator()
            add_danger_command(menu, f"Delete '{self.full_name}'",
                               lambda: self.on_delete(self.server_name), icon_name="trash")
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

class DownloadProgressDialog(ZBBToplevel):
    def __init__(self, master, title="Downloading..."):
        super().__init__(master)
        self.title(title)
        self.geometry("350x210")
        center_on_parent(self, master, 350, 210)
        self.resizable(False, False)
        self.cancelled = False
        
        header, _, _ = dialog_header(self, title)
        header.pack(fill="x", padx=20, pady=(16, 0))
        self.label = ctk.CTkLabel(self, text="Starting download...", font=AppConfig.FONT_BODY)
        self.label.pack(pady=(8, 10))

        self.progress_bar = ctk.CTkProgressBar(self, width=280, height=10, corner_radius=AppConfig.RADIUS_BADGE)
        self.progress_bar.pack(pady=10)
        self.progress_bar.set(0)

        self.btn_cancel = ctk.CTkButton(
            self,
            text="Cancel",
            width=100,
            corner_radius=AppConfig.RADIUS_BTN,
            fg_color="transparent",
            border_width=AppConfig.BORDER_BTN,
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


class EulaDialog(ZBBToplevel):
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

        buttons, _, _ = dialog_buttons(
            frame, "I Accept the EULA", self._accept, "Decline", self._decline,
            primary_width=180, secondary_width=120,
        )
        buttons.pack(fill="x")

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


class ZBBDialog(ZBBToplevel):
    """Themed modal dialog replacing tkinter.messagebox (which renders as
    a native gray Windows dialog and clashes with the dark UI).

    Use the classmethods:
        ZBBDialog.confirm(parent, title, message, danger=False) -> bool
        ZBBDialog.info(parent, title, message, kind="info"|"warning"|"error")
        ZBBDialog.ask_string(parent, title, message, initial="") -> str | None
    """

    _KIND_STYLE = {
        "info":    ("dot", AppConfig.COLOR_BTN_PRIMARY),
        "warning": ("dot", AppConfig.COLOR_ACCENT_AMBER),
        "error":   ("close", AppConfig.COLOR_BTN_DANGER),
        "question": ("dot", AppConfig.COLOR_BTN_PRIMARY),
    }

    def __init__(self, parent, title, message, *, confirm_text="OK",
                 cancel_text=None, danger=False, kind="question",
                 input_value=None, placeholder=""):
        super().__init__(parent)
        self.result = False
        # Text entered on confirm; stays None on cancel or when the dialog
        # has no input field (input_value=None).
        self.value = None
        self._entry = None
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
        ).pack(anchor="w", fill="x", pady=(0, 8 if input_value is not None else 16))

        if input_value is not None:
            self._entry = ctk.CTkEntry(
                frame, width=380, height=32, corner_radius=AppConfig.RADIUS_BTN,
                placeholder_text=placeholder or None,
            )
            if input_value:
                self._entry.insert(0, input_value)
            self._entry.pack(fill="x", pady=(0, 16))

        buttons, btn_ok, _ = dialog_buttons(
            frame, confirm_text, self._confirm, cancel_text or None, self._cancel, danger=danger,
        )
        buttons.pack(fill="x")

        self.bind("<Return>", lambda e: self._confirm())
        self.bind("<Escape>", lambda e: self._cancel())

        apply_rounded_corners(self)
        self.update_idletasks()
        w, h = self.winfo_reqwidth(), self.winfo_reqheight()
        center_on_parent(self, parent, w, h)
        self.transient(parent)
        # A modal parent (wizard, properties editor) holds the grab; take it
        # back on close or that window silently stops being modal.
        self._prev_grab = None
        try:
            self._prev_grab = self.grab_current()
        except (KeyError, tk.TclError) as e:
            logger.debug("ZBBDialog could not read current grab: %s", e)
        try:
            self.wait_visibility()
            self.grab_set()
        except Exception as e:
            logger.debug("ZBBDialog grab failed: %s", e)
        if self._entry is not None:
            self._entry.focus_set()
            self._entry.select_range(0, "end")
        else:
            btn_ok.focus_set()

    def _confirm(self):
        self.result = True
        if self._entry is not None:
            self.value = self._entry.get()
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
        if self._prev_grab is not None:
            try:
                if self._prev_grab.winfo_exists():
                    self._prev_grab.grab_set()
            except tk.TclError as e:
                logger.debug("ZBBDialog could not restore parent grab: %s", e)

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

    @classmethod
    def ask_string(cls, parent, title, message, *, initial="", placeholder="",
                   confirm_text="OK", cancel_text="Cancel"):
        """Themed replacement for CTkInputDialog. Returns the entered text
        (possibly empty) on confirm, None on cancel/close."""
        dlg = cls(parent, title, message, confirm_text=confirm_text,
                  cancel_text=cancel_text, kind="question",
                  input_value=initial, placeholder=placeholder)
        parent.wait_window(dlg)
        return dlg.value
