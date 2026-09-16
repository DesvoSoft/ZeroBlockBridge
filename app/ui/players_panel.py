"""Players tab: one roster of every player the selected server knows.

Online players, usercache, whitelist, operators, bans and play history are
merged by core.players.PlayerOrchestrator; this panel only filters, renders
and dispatches actions (from worker threads — lookups can hit Mojang).
"""

import datetime
import hashlib
import logging

import customtkinter as ctk
from PIL import Image

from app.core.app_config import AppConfig
from app.core.players import OP_LEVELS
from app.core.server_events import ServerEvent
from app.services.player_heads import fetch_head
from app.ui.formatting import format_duration, format_relative
from app.ui.icons import icon
from app.ui.ui_components import ScrollableFrame, ToolTip, ZBBDialog, add_danger_command, themed_menu

logger = logging.getLogger(__name__)

_FILTERS = ("All", "Online", "Ops", "Whitelisted", "Banned")
_OP_LEVEL_LABELS = {
    1: "Level 1 · Bypass spawn protection",
    2: "Level 2 · Cheats and command blocks",
    3: "Level 3 · Manage players",
    4: "Level 4 · Everything, including /stop",
}


class PlayersPanel(ctk.CTkFrame):
    # The server rewrites its player files right after a command; re-read then.
    _RESYNC_MS = 1500
    _EVENT_DEBOUNCE_MS = 300
    _HEAD_SIZE = 36

    _STATUS_STYLES = {
        "success": (AppConfig.COLOR_STATUS_ONLINE, "check"),
        "error": (AppConfig.COLOR_STATUS_ERROR, "close"),
        "warning": (AppConfig.COLOR_STATUS_STARTING, "warning"),
    }

    def __init__(self, master, zbb_manager, event_bus, run_async, **kwargs):
        super().__init__(master, fg_color="transparent", **kwargs)
        self.zbb = zbb_manager
        self.events = event_bus
        self.run_async = run_async

        self._roster: list[dict] = []
        self._rows: dict[str, list] = {}      # name.lower() -> [row frame, state]
        self._heads: dict[str, ctk.CTkImage] = {}
        self._heads_pending: set[str] = set()
        self._online_mode = True
        self._live = False
        self._default_level = 4
        self._refresh_gen = 0
        self._event_job = None

        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(1, weight=1)
        self._build_toolbar()
        self._build_list()
        self._build_footer()

        for event in (ServerEvent.PLAYER_LIST, ServerEvent.READY, ServerEvent.STOPPED):
            self.events.subscribe(event, self._on_server_event)
        self.refresh()

    def destroy(self):
        for event in (ServerEvent.PLAYER_LIST, ServerEvent.READY, ServerEvent.STOPPED):
            self.events.unsubscribe(event, self._on_server_event)
        super().destroy()

    # ------------------------------------------------------------------ layout
    def _build_toolbar(self):
        bar = ctk.CTkFrame(self, corner_radius=AppConfig.RADIUS_CARD,
                           fg_color=(AppConfig.COLOR_BG_LIGHT, AppConfig.COLOR_BG_DARK))
        bar.grid(row=0, column=0, sticky="ew", pady=(0, 8))
        bar.grid_columnconfigure(1, weight=1)

        ctk.CTkLabel(bar, text="", image=icon("search", 15)).grid(row=0, column=0, padx=(12, 4), pady=(8, 6))
        self.entry_search = ctk.CTkEntry(
            bar, placeholder_text="Search players…", height=28, border_width=0,
            corner_radius=AppConfig.RADIUS_INPUT, font=AppConfig.FONT_BODY_SMALL,
            fg_color=(AppConfig.COLOR_BG_CARD_LIGHT, AppConfig.COLOR_BG_CARD_DARK),
        )
        self.entry_search.grid(row=0, column=1, sticky="ew", padx=4, pady=(8, 6))
        self.entry_search.bind("<KeyRelease>", lambda e: self._render())

        self.filter = ctk.CTkSegmentedButton(
            bar, values=list(_FILTERS), height=28, font=AppConfig.FONT_BODY_SMALL,
            command=lambda _v: self._render(),
        )
        self.filter.set("All")
        self.filter.grid(row=0, column=2, padx=(4, 12), pady=(8, 6))

        ctk.CTkFrame(bar, height=1, fg_color=(AppConfig.COLOR_BORDER_LIGHT, AppConfig.COLOR_BORDER_DARK)).grid(
            row=1, column=0, columnspan=3, sticky="ew", padx=12)

        actions = ctk.CTkFrame(bar, fg_color="transparent")
        actions.grid(row=2, column=0, columnspan=3, sticky="ew", padx=12, pady=(6, 8))

        self.switch_whitelist = ctk.CTkSwitch(
            actions, text="Whitelist only", width=0, font=AppConfig.FONT_BODY_SMALL,
            text_color=AppConfig.COLOR_TEXT_PRIMARY, command=self._toggle_whitelist,
        )
        self.switch_whitelist.pack(side="left")
        ToolTip(self.switch_whitelist, "When on, only whitelisted players can join.")

        self.lbl_summary = ctk.CTkLabel(actions, text="", font=AppConfig.FONT_BODY_SMALL,
                                        text_color=AppConfig.COLOR_TEXT_GRAY)
        self.lbl_summary.pack(side="left", padx=(16, 0))

        self.btn_add = ctk.CTkButton(
            actions, text="Add", image=icon("chevron_down", 12, AppConfig.COLOR_TEXT_ON_ACCENT), compound="right",
            width=80, height=28, corner_radius=AppConfig.RADIUS_BTN, font=AppConfig.FONT_LABEL_SMALL,
            fg_color=AppConfig.COLOR_BTN_PRIMARY, hover_color=AppConfig.COLOR_BTN_PRIMARY_HOVER,
            text_color=AppConfig.COLOR_TEXT_ON_ACCENT, command=self._open_add_menu,
        )
        self.btn_add.pack(side="right")
        self.entry_add = ctk.CTkEntry(actions, placeholder_text="Player name", width=160, height=28,
                                      corner_radius=AppConfig.RADIUS_INPUT, font=AppConfig.FONT_BODY_SMALL)
        self.entry_add.pack(side="right", padx=(0, 8))
        self.entry_add.bind("<Return>", lambda e: self._open_add_menu())

    def _build_list(self):
        self.list_frame = ScrollableFrame(
            self, corner_radius=AppConfig.RADIUS_CARD, border_width=1,
            fg_color=(AppConfig.COLOR_BG_SIDEBAR_LIGHT, AppConfig.COLOR_BG_SIDEBAR_DARK),
            border_color=(AppConfig.COLOR_BORDER_LIGHT, AppConfig.COLOR_BORDER_DARK),
        )
        self.list_frame.grid(row=1, column=0, sticky="nsew")
        self.list_frame.grid_columnconfigure(0, weight=1)

        self._empty = ctk.CTkFrame(self.list_frame, fg_color="transparent")
        ctk.CTkLabel(self._empty, text="", image=icon("user", 36, AppConfig.COLOR_TEXT_MUTED)).pack(pady=(40, 6))
        self._empty_title = ctk.CTkLabel(self._empty, text="", font=AppConfig.FONT_BODY,
                                         text_color=AppConfig.COLOR_TEXT_NOTE)
        self._empty_title.pack()
        self._empty_hint = ctk.CTkLabel(self._empty, text="", font=AppConfig.FONT_BODY_SMALL,
                                        text_color=AppConfig.COLOR_TEXT_GRAY)
        self._empty_hint.pack(pady=(2, 40))

    def _build_footer(self):
        footer = ctk.CTkFrame(self, corner_radius=AppConfig.RADIUS_CARD,
                              fg_color=(AppConfig.COLOR_BG_LIGHT, AppConfig.COLOR_BG_DARK))
        footer.grid(row=2, column=0, sticky="ew", pady=(8, 0))
        self.lbl_status = ctk.CTkLabel(footer, text="", anchor="w", height=28,
                                       font=AppConfig.FONT_BODY_SMALL, text_color=AppConfig.COLOR_TEXT_GRAY)
        self.lbl_status.pack(side="left", fill="x", expand=True, padx=12, pady=6)
        self._set_status("Open a player's actions menu, or type a name and use Add.")

    def _set_status(self, text: str, kind: str = None):
        style = self._STATUS_STYLES.get(kind)
        color = style[0] if style else AppConfig.COLOR_TEXT_GRAY
        self.lbl_status.configure(
            text=f" {text}" if style else text, text_color=color,
            image=icon(style[1], 12, color) if style else None, compound="left" if style else "center",
        )

    # ------------------------------------------------------------------ data
    def _on_server_event(self, _data=None):
        self.after(0, self._schedule_refresh)

    def _schedule_refresh(self):
        if self._event_job is not None:
            self.after_cancel(self._event_job)
        self._event_job = self.after(self._EVENT_DEBOUNCE_MS, self._refresh_from_event)

    def _refresh_from_event(self):
        self._event_job = None
        self.refresh()

    def refresh(self):
        """Reload the roster for the selected server (off the Tk thread)."""
        self._refresh_gen += 1
        gen = self._refresh_gen
        server = self.zbb.current_server
        if not server:
            self._apply_refresh(gen, None, [], True, False, False, 4)
            return
        players = self.zbb.players

        def work():
            try:
                roster = players.roster(server)
                online_mode = players.online_mode(server)
                whitelist = players.whitelist_enabled(server)
                live = players.is_live(server)
                level = players.default_op_level(server)
            except Exception:
                logger.exception("Loading players for %s failed", server)
                return
            self.after(0, lambda: self._apply_refresh(gen, server, roster, online_mode, whitelist, live, level))

        self.run_async(work)

    def _apply_refresh(self, gen, server, roster, online_mode, whitelist, live, level):
        if gen != self._refresh_gen or not self.winfo_exists():
            return
        self._server = server
        self._roster = roster
        self._online_mode = online_mode
        self._live = live
        self._default_level = level
        if whitelist:
            self.switch_whitelist.select()
        else:
            self.switch_whitelist.deselect()
        self.switch_whitelist.configure(state="normal" if server else "disabled")
        online = sum(1 for p in roster if p["online"])
        self.lbl_summary.configure(
            text=f"{online} online · {len(roster)} known" if server else "")
        self._render()
        self._load_heads()

    # ------------------------------------------------------------------ rendering
    def _visible(self) -> list[dict]:
        query = self.entry_search.get().strip().lower()
        mode = self.filter.get()
        keep = {
            "All": lambda p: True,
            "Online": lambda p: p["online"],
            "Ops": lambda p: p["op_level"] is not None,
            "Whitelisted": lambda p: p["whitelisted"],
            "Banned": lambda p: p["banned"],
        }[mode]
        return [p for p in self._roster if keep(p) and query in p["name"].lower()]

    def _row_state(self, player: dict) -> tuple:
        return (tuple(sorted(player.items())), player["uuid"] in self._heads, self._live)

    def _render(self):
        """Rebuild only rows whose player changed; reorder the rest in place."""
        visible = self._visible()
        keys = [p["name"].lower() for p in visible]
        for key in list(self._rows):
            if key not in keys:
                self._rows.pop(key)[0].destroy()

        if not visible:
            if not self._server:
                title, hint = "No server selected", "Select a server to manage its players."
            elif self._roster:
                title, hint = "No players match", "Try another filter or search."
            else:
                title, hint = "No players yet", "Players show up here once they join, or add one above."
            self._empty_title.configure(text=title)
            self._empty_hint.configure(text=hint)
            self._empty.grid(row=0, column=0, sticky="ew")
            return
        self._empty.grid_remove()

        for index, player in enumerate(visible):
            key = keys[index]
            state = self._row_state(player)
            existing = self._rows.get(key)
            if existing and existing[1] == state:
                existing[0].grid(row=index, column=0, sticky="ew", padx=6, pady=3)
                continue
            row = self._make_row(player)
            row.grid(row=index, column=0, sticky="ew", padx=6, pady=3)
            if existing:
                existing[0].destroy()
            self._rows[key] = [row, state]

    def _make_row(self, player: dict) -> ctk.CTkFrame:
        row = ctk.CTkFrame(self.list_frame, corner_radius=AppConfig.RADIUS_CARD,
                           fg_color=(AppConfig.COLOR_BG_CARD_LIGHT, AppConfig.COLOR_BG_CARD_DARK))
        row.grid_columnconfigure(1, weight=1)
        name = player["name"]

        head = self._heads.get(player["uuid"])
        if head is not None:
            lbl_head = ctk.CTkLabel(row, text="", image=head, width=self._HEAD_SIZE, height=self._HEAD_SIZE)
        else:
            tile = AppConfig.ICON_PLACEHOLDER_COLORS[
                int(hashlib.md5(name.lower().encode()).hexdigest(), 16) % len(AppConfig.ICON_PLACEHOLDER_COLORS)]
            lbl_head = ctk.CTkLabel(
                row, text=name.lstrip(".")[:1].upper() or "?", width=self._HEAD_SIZE, height=self._HEAD_SIZE,
                fg_color=tile, corner_radius=AppConfig.RADIUS_BADGE,
                font=AppConfig.FONT_HEADING_SMALL, text_color=AppConfig.COLOR_TEXT_ON_ACCENT,
            )
        lbl_head.grid(row=0, column=0, rowspan=2, padx=(12, 10), pady=10)

        ctk.CTkLabel(row, text=name, font=AppConfig.FONT_HEADING_SMALL, anchor="w").grid(
            row=0, column=1, sticky="sw", pady=(8, 0))
        detail, detail_color = self._detail(player)
        ctk.CTkLabel(row, text=detail, font=AppConfig.FONT_BODY_SMALL, text_color=detail_color, anchor="w").grid(
            row=1, column=1, sticky="nw", pady=(0, 8))

        chip_specs = []
        if player["op_level"] is not None:
            chip_specs.append((f"Op {player['op_level']}", AppConfig.COLOR_BADGE_BG, AppConfig.COLOR_BADGE_TEXT))
        if player["whitelisted"]:
            chip_specs.append(("Whitelisted", AppConfig.COLOR_BADGE_NEUTRAL_BG, AppConfig.COLOR_BADGE_NEUTRAL_TEXT))
        if player["banned"]:
            chip_specs.append(("Banned", AppConfig.COLOR_BADGE_DANGER_BG, AppConfig.COLOR_BADGE_DANGER_TEXT))
        if chip_specs:
            # Only when there are chips: an empty CTkFrame requests 200x200.
            chips = ctk.CTkFrame(row, fg_color="transparent")
            chips.grid(row=0, column=2, rowspan=2, padx=(8, 8))
            for spec in chip_specs:
                self._chip(chips, *spec)

        btn_more = ctk.CTkButton(
            row, text="", image=icon("more", 16, AppConfig.COLOR_TEXT_PRIMARY), width=32, height=28,
            corner_radius=AppConfig.RADIUS_BTN, fg_color=AppConfig.COLOR_BTN_GHOST,
            hover_color=AppConfig.COLOR_BTN_GHOST_HOVER,
        )
        btn_more.configure(command=lambda b=btn_more, p=player: self._open_row_menu(b, p))
        btn_more.grid(row=0, column=3, rowspan=2, padx=(0, 12))
        ToolTip(btn_more, f"Actions for {name}")
        return row

    @staticmethod
    def _chip(parent, text, bg, fg):
        ctk.CTkLabel(parent, text=text, font=AppConfig.FONT_MICRO, fg_color=bg, text_color=fg,
                     corner_radius=AppConfig.RADIUS_BADGE, padx=8, pady=2).pack(side="left", padx=(0, 4))

    @staticmethod
    def _detail(player: dict) -> tuple:
        if player["banned"] and player["ban_reason"]:
            return f"Banned: {player['ban_reason']}", AppConfig.COLOR_TEXT_GRAY
        if player["online"]:
            return "Online now", AppConfig.COLOR_STATUS_ONLINE
        parts = []
        if player["last_seen"]:
            parts.append(f"Last seen {format_relative(player['last_seen'], datetime.datetime.now())}")
        if player["playtime_seconds"]:
            parts.append(f"{format_duration(player['playtime_seconds'])} played")
        return (" · ".join(parts) if parts else "Hasn't joined since ZBB started tracking"), AppConfig.COLOR_TEXT_GRAY

    # ------------------------------------------------------------------ heads
    def _load_heads(self):
        if not self._online_mode:
            return
        for player in self._roster:
            player_uuid = player["uuid"]
            if (not player_uuid or player["name"].startswith(".") or player_uuid in self._heads
                    or player_uuid in self._heads_pending):
                continue
            self._heads_pending.add(player_uuid)
            self.run_async(lambda u=player_uuid: self._fetch_head(u))

    def _fetch_head(self, player_uuid: str):
        image = None
        path = fetch_head(player_uuid, 64)
        if path:
            try:
                with Image.open(path) as raw:
                    # Pixel art: scale with nearest-neighbor, 2x for HiDPI.
                    face = raw.convert("RGBA").resize((self._HEAD_SIZE * 2,) * 2, Image.NEAREST)
                image = ctk.CTkImage(face, size=(self._HEAD_SIZE, self._HEAD_SIZE))
            except OSError as exc:
                logger.debug("Unreadable head image %s: %s", path, exc)

        def apply():
            self._heads_pending.discard(player_uuid)
            if image is not None and self.winfo_exists():
                self._heads[player_uuid] = image
                self._render()
        self.after(0, apply)

    # ------------------------------------------------------------------ actions
    def _run_action(self, action, *args, clear_entry=False):
        server = self.zbb.current_server
        if not server:
            return
        self._set_status("Working…")

        def work():
            try:
                result = action(server, *args)
            except Exception as exc:
                logger.exception("Player action failed")
                self.after(0, lambda e=exc: self._set_status(f"Failed: {e}", kind="error"))
                return
            self.after(0, lambda: self._on_action_done(result, clear_entry))

        self.run_async(work)

    def _on_action_done(self, result, clear_entry):
        self._set_status(result.message, kind="success" if result.ok else "error")
        if result.ok and clear_entry:
            self.entry_add.delete(0, "end")
        self.refresh()
        if result.ok and self._live:
            self.after(self._RESYNC_MS, self.refresh)

    def _toggle_whitelist(self):
        self._run_action(self.zbb.players.set_whitelist_enabled, bool(self.switch_whitelist.get()))

    def _op_menu(self, parent_menu, name, clear_entry=False):
        """Operator entry: one fixed level while live (/op), a level submenu otherwise."""
        players = self.zbb.players
        if self._live:
            parent_menu.add_command(
                label=f"  Make operator (level {self._default_level})",
                command=lambda: self._run_action(players.op, name, self._default_level, clear_entry=clear_entry))
            return
        sub = themed_menu(parent_menu)
        for level in OP_LEVELS:
            sub.add_command(label=f"  {_OP_LEVEL_LABELS[level]}",
                            command=lambda lv=level: self._run_action(players.op, name, lv, clear_entry=clear_entry))
        parent_menu.add_cascade(label="  Make operator", menu=sub)

    def _open_add_menu(self):
        name = self.entry_add.get().strip()
        if not self.zbb.current_server:
            return
        if not name:
            self._set_status("Type a player name first.", kind="warning")
            self.entry_add.focus_set()
            return
        players = self.zbb.players
        menu = themed_menu(self)
        menu.add_command(label="  Add to whitelist",
                         command=lambda: self._run_action(players.whitelist_add, name, clear_entry=True))
        self._op_menu(menu, name, clear_entry=True)
        menu.add_separator()
        add_danger_command(menu, "  Ban…", lambda: self._ban(name, clear_entry=True))
        self._popup(menu, self.btn_add)

    def _open_row_menu(self, button, player: dict):
        players = self.zbb.players
        name = player["name"]
        menu = themed_menu(self)
        if self._live and player["online"]:
            menu.add_command(label="  Kick…", command=lambda: self._kick(name))
            menu.add_separator()
        if player["op_level"] is None:
            self._op_menu(menu, name)
        else:
            if not self._live:
                sub = themed_menu(menu)
                for level in OP_LEVELS:
                    sub.add_command(label=f"  {_OP_LEVEL_LABELS[level]}",
                                    command=lambda lv=level: self._run_action(players.op, name, lv))
                menu.add_cascade(label="  Change operator level", menu=sub)
            menu.add_command(label="  Remove operator", command=lambda: self._run_action(players.deop, name))
        if player["whitelisted"]:
            menu.add_command(label="  Remove from whitelist",
                             command=lambda: self._run_action(players.whitelist_remove, name))
        else:
            menu.add_command(label="  Add to whitelist", command=lambda: self._run_action(players.whitelist_add, name))
        menu.add_separator()
        if player["banned"]:
            menu.add_command(label="  Unban", command=lambda: self._run_action(players.pardon, name))
        else:
            add_danger_command(menu, "  Ban…", lambda: self._ban(name))
        if player["uuid"]:
            menu.add_separator()
            menu.add_command(label="  Copy UUID", command=lambda: self._copy(player["uuid"]))
        self._popup(menu, button)

    @staticmethod
    def _popup(menu, anchor):
        try:
            menu.tk_popup(anchor.winfo_rootx(), anchor.winfo_rooty() + anchor.winfo_height())
        finally:
            menu.grab_release()

    def _kick(self, name):
        reason = ZBBDialog.ask_string(self.winfo_toplevel(), f"Kick {name}", "Reason shown to the player (optional):",
                                      placeholder="e.g. AFK too long", confirm_text="Kick")
        if reason is not None:
            self._run_action(self.zbb.players.kick, name, reason)

    def _ban(self, name, clear_entry=False):
        reason = ZBBDialog.ask_string(self.winfo_toplevel(), f"Ban {name}", "Reason (optional):",
                                      placeholder="e.g. Griefing", confirm_text="Ban")
        if reason is not None:
            self._run_action(self.zbb.players.ban, name, reason, clear_entry=clear_entry)

    def _copy(self, text):
        self.clipboard_clear()
        self.clipboard_append(text)
        self._set_status("UUID copied.", kind="success")
