import logging

import customtkinter as ctk

from app.core.app_config import AppConfig
from app.core.constants import BANNED_PLAYERS_FILE, OPS_FILE, WHITELIST_FILE
from app.core.server_events import ServerEvent
from app.services.player_files import add_entry, load_json_list, remove_entry
from app.services.server_properties import load_server_properties, save_server_properties
from app.ui.icons import icon
from app.ui.ui_components import ToolTip, ZBBDialog, center_on_parent
from app.ui.win_effects import apply_rounded_corners

logger = logging.getLogger(__name__)

_OP_LEVELS = [1, 2, 3, 4]


class PlayersDashboard(ctk.CTkToplevel):
    def __init__(self, master, event_bus, zbb_manager, **kwargs):
        super().__init__(master, **kwargs)
        self.title("Player Management")
        self.geometry("640x620")
        center_on_parent(self, master, 640, 620)
        self.minsize(560, 480)
        self.transient(master)
        self.lift()
        self.focus_force()
        apply_rounded_corners(self)
        self.event_bus = event_bus
        self.zbb_manager = zbb_manager

        self.connected_players = []
        self.whitelisted_players = []
        self.operators = []
        self.banned_players = []

        self.grid_rowconfigure(1, weight=1)
        self.grid_columnconfigure(0, weight=1)

        self._build_header()

        self.tabview = ctk.CTkTabview(self)
        self.tabview.grid(row=1, column=0, sticky="nsew", padx=15, pady=(0, 15))
        self.tab_online = self.tabview.add("Online")
        self.tab_whitelist = self.tabview.add("Whitelist")
        self.tab_operators = self.tabview.add("Operators")
        self.tab_bans = self.tabview.add("Bans")

        self._build_online_tab()
        self._build_whitelist_tab()
        self._build_operators_tab()
        self._build_bans_tab()

        self._load_data()
        self.event_bus.subscribe(ServerEvent.PLAYER_LIST, self._on_player_list_update)

        self.refresh_ui()

    def destroy(self):
        self.event_bus.unsubscribe(ServerEvent.PLAYER_LIST, self._on_player_list_update)
        super().destroy()

    @property
    def server_name(self):
        return self.zbb_manager.current_server

    def _load_data(self):
        if self.zbb_manager.is_running() and self.zbb_manager.server_runner:
            self.connected_players = list(self.zbb_manager.server_runner.connected_players)

        server_name = self.server_name
        if not server_name:
            return

        props = load_server_properties(server_name)
        whitelist_enabled = props.get("white-list", "").lower() == "true"
        if whitelist_enabled:
            self.switch_whitelist.select()
        else:
            self.switch_whitelist.deselect()

        self.whitelisted_players = load_json_list(server_name, WHITELIST_FILE)
        self.operators = load_json_list(server_name, OPS_FILE)
        self.banned_players = load_json_list(server_name, BANNED_PLAYERS_FILE)

    def _on_player_list_update(self, players):
        self.connected_players = list(players)
        self.after(0, self._refresh_online)

    def _build_header(self):
        header_frame = ctk.CTkFrame(self, fg_color="transparent")
        header_frame.grid(row=0, column=0, sticky="ew", padx=20, pady=(20, 10))

        self.lbl_player_count = ctk.CTkLabel(
            header_frame,
            text="Players Online: 0",
            font=(AppConfig.FONT_FAMILY_DISPLAY, 22, "bold")
        )
        self.lbl_player_count.pack(side="left")

    # --- Tab builders ---

    def _build_online_tab(self):
        self.tab_online.grid_rowconfigure(0, weight=1)
        self.tab_online.grid_columnconfigure(0, weight=1)
        self.scroll_players = ctk.CTkScrollableFrame(self.tab_online, fg_color="transparent")
        self.scroll_players.grid(row=0, column=0, sticky="nsew", padx=5, pady=5)

    def _build_whitelist_tab(self):
        self.tab_whitelist.grid_rowconfigure(3, weight=1)
        self.tab_whitelist.grid_columnconfigure(0, weight=1)

        header_frame = ctk.CTkFrame(self.tab_whitelist, fg_color="transparent")
        header_frame.grid(row=0, column=0, sticky="ew", padx=10, pady=(10, 5))
        header_frame.grid_columnconfigure(0, weight=1)

        lbl_title = ctk.CTkLabel(header_frame, text="Whitelist enforcement", font=(AppConfig.FONT_FAMILY, 13, "bold"))
        lbl_title.grid(row=0, column=0, sticky="w")

        self.switch_whitelist = ctk.CTkSwitch(header_frame, text="Enabled", command=self._toggle_whitelist)
        self.switch_whitelist.grid(row=0, column=1, sticky="e")

        add_frame = ctk.CTkFrame(self.tab_whitelist, fg_color="transparent")
        add_frame.grid(row=1, column=0, sticky="ew", padx=10, pady=5)
        add_frame.grid_columnconfigure(0, weight=1)

        self.entry_whitelist_add = ctk.CTkEntry(add_frame, placeholder_text="Player name...")
        self.entry_whitelist_add.grid(row=0, column=0, sticky="ew", padx=(0, 10))

        btn_add = ctk.CTkButton(add_frame, text="Add", width=60, corner_radius=AppConfig.RADIUS_BTN,
                                 fg_color=AppConfig.COLOR_BTN_PRIMARY, hover_color=AppConfig.COLOR_BTN_PRIMARY_HOVER,
                                 command=self._add_to_whitelist)
        btn_add.grid(row=0, column=1)

        lbl_list_title = ctk.CTkLabel(self.tab_whitelist, text="Whitelisted players:", font=AppConfig.FONT_BODY_SMALL)
        lbl_list_title.grid(row=2, column=0, sticky="w", padx=10, pady=(10, 0))

        self.scroll_whitelist = ctk.CTkScrollableFrame(self.tab_whitelist, fg_color="transparent")
        self.scroll_whitelist.grid(row=3, column=0, sticky="nsew", padx=5, pady=(0, 10))

    def _build_operators_tab(self):
        self.tab_operators.grid_rowconfigure(1, weight=1)
        self.tab_operators.grid_columnconfigure(0, weight=1)

        add_frame = ctk.CTkFrame(self.tab_operators, fg_color="transparent")
        add_frame.grid(row=0, column=0, sticky="ew", padx=10, pady=10)
        add_frame.grid_columnconfigure(0, weight=1)

        self.entry_op_add = ctk.CTkEntry(add_frame, placeholder_text="Player name...")
        self.entry_op_add.grid(row=0, column=0, sticky="ew", padx=(0, 10))

        self.op_level_var = ctk.StringVar(value="4")
        level_menu = ctk.CTkOptionMenu(add_frame, values=[str(lvl) for lvl in _OP_LEVELS],
                                        variable=self.op_level_var, width=60)
        level_menu.grid(row=0, column=1, padx=(0, 10))

        btn_add = ctk.CTkButton(add_frame, text="Op", width=60, corner_radius=AppConfig.RADIUS_BTN,
                                 fg_color=AppConfig.COLOR_BTN_PRIMARY, hover_color=AppConfig.COLOR_BTN_PRIMARY_HOVER,
                                 command=self._add_operator)
        btn_add.grid(row=0, column=2)

        self.scroll_operators = ctk.CTkScrollableFrame(self.tab_operators, fg_color="transparent")
        self.scroll_operators.grid(row=1, column=0, sticky="nsew", padx=5, pady=(0, 10))

    def _build_bans_tab(self):
        self.tab_bans.grid_rowconfigure(0, weight=1)
        self.tab_bans.grid_columnconfigure(0, weight=1)
        self.scroll_bans = ctk.CTkScrollableFrame(self.tab_bans, fg_color="transparent")
        self.scroll_bans.grid(row=0, column=0, sticky="nsew", padx=5, pady=5)

    # --- Rendering ---

    def refresh_ui(self):
        self._refresh_online()
        self._populate_whitelist()
        self._populate_operators()
        self._populate_bans()

    def _refresh_online(self):
        if not self.winfo_exists():
            return
        if self.zbb_manager.is_running():
            self.lbl_player_count.configure(
                text=f"Players Online: {len(self.connected_players)}",
                text_color=AppConfig.COLOR_TEXT_PRIMARY,
            )
        else:
            self.lbl_player_count.configure(
                text="Server offline", text_color=AppConfig.COLOR_TEXT_GRAY,
            )
        self._populate_connected_players()

    def _empty_label(self, parent, text):
        lbl = ctk.CTkLabel(parent, text=text, text_color=AppConfig.COLOR_TEXT_GRAY)
        lbl.pack(pady=20)

    def _row_frame(self, parent):
        frame = ctk.CTkFrame(
            parent,
            fg_color=(AppConfig.COLOR_BG_CARD_LIGHT, AppConfig.COLOR_BG_CARD_DARK),
            corner_radius=AppConfig.RADIUS_CARD,
        )
        frame.pack(fill="x", pady=2, padx=5)
        return frame

    def _populate_connected_players(self):
        for widget in self.scroll_players.winfo_children():
            widget.destroy()

        if not self.connected_players:
            msg = ("No players online"
                   if self.zbb_manager.is_running()
                   else "Start the server to see connected players.")
            self._empty_label(self.scroll_players, msg)
            return

        for player in self.connected_players:
            item_frame = self._row_frame(self.scroll_players)

            lbl_name = ctk.CTkLabel(item_frame, text=player, font=(AppConfig.FONT_FAMILY, 13, "bold"))
            lbl_name.pack(side="left", padx=10, pady=8)

            btn_ban = ctk.CTkButton(
                item_frame, text="Ban", width=50, height=24, corner_radius=AppConfig.RADIUS_BTN,
                fg_color=AppConfig.COLOR_BTN_DANGER, hover_color=AppConfig.COLOR_BTN_DANGER_HOVER,
                command=lambda p=player: self._ban_player(p)
            )
            btn_ban.pack(side="right", padx=(5, 10), pady=8)

            btn_kick = ctk.CTkButton(
                item_frame, text="Kick", width=50, height=24, corner_radius=AppConfig.RADIUS_BTN,
                fg_color=AppConfig.COLOR_BTN_WARNING, hover_color=AppConfig.COLOR_BTN_WARNING_HOVER,
                command=lambda p=player: self._kick_player(p)
            )
            btn_kick.pack(side="right", padx=5, pady=8)

    def _populate_whitelist(self):
        for widget in self.scroll_whitelist.winfo_children():
            widget.destroy()

        if not self.whitelisted_players:
            self._empty_label(self.scroll_whitelist, "Whitelist empty")
            return

        for entry in self.whitelisted_players:
            name = entry.get("name", "?")
            item_frame = self._row_frame(self.scroll_whitelist)

            lbl_name = ctk.CTkLabel(item_frame, text=name)
            lbl_name.pack(side="left", padx=10, pady=8)

            btn_remove = ctk.CTkButton(
                item_frame, text="", image=icon("close", 12, "#ffffff"),
                width=28, height=24, corner_radius=AppConfig.RADIUS_BTN,
                fg_color=AppConfig.COLOR_BTN_DANGER, hover_color=AppConfig.COLOR_BTN_DANGER_HOVER,
                command=lambda p=name: self._remove_from_whitelist(p)
            )
            btn_remove.pack(side="right", padx=10, pady=8)
            ToolTip(btn_remove, f"Remove {name} from whitelist")

    def _populate_operators(self):
        for widget in self.scroll_operators.winfo_children():
            widget.destroy()

        if not self.operators:
            self._empty_label(self.scroll_operators, "No operators")
            return

        for entry in self.operators:
            name = entry.get("name", "?")
            level = entry.get("level", 4)
            item_frame = self._row_frame(self.scroll_operators)

            lbl_name = ctk.CTkLabel(item_frame, text=f"{name}  (level {level})")
            lbl_name.pack(side="left", padx=10, pady=8)

            btn_remove = ctk.CTkButton(
                item_frame, text="De-op", width=60, height=24, corner_radius=AppConfig.RADIUS_BTN,
                fg_color=AppConfig.COLOR_BTN_DANGER, hover_color=AppConfig.COLOR_BTN_DANGER_HOVER,
                command=lambda p=name: self._remove_operator(p)
            )
            btn_remove.pack(side="right", padx=10, pady=8)

    def _populate_bans(self):
        for widget in self.scroll_bans.winfo_children():
            widget.destroy()

        if not self.banned_players:
            self._empty_label(self.scroll_bans, "No banned players")
            return

        for entry in self.banned_players:
            name = entry.get("name", "?")
            reason = entry.get("reason", "Banned by an operator")
            item_frame = self._row_frame(self.scroll_bans)

            info_frame = ctk.CTkFrame(item_frame, fg_color="transparent")
            info_frame.pack(side="left", padx=10, pady=8, fill="x", expand=True)

            lbl_name = ctk.CTkLabel(info_frame, text=name, font=(AppConfig.FONT_FAMILY, 13, "bold"), anchor="w")
            lbl_name.pack(anchor="w")
            lbl_reason = ctk.CTkLabel(info_frame, text=reason, text_color=AppConfig.COLOR_TEXT_GRAY,
                                       font=AppConfig.FONT_BODY_SMALL, anchor="w")
            lbl_reason.pack(anchor="w")

            btn_pardon = ctk.CTkButton(
                item_frame, text="Pardon", width=70, height=24, corner_radius=AppConfig.RADIUS_BTN,
                fg_color=AppConfig.COLOR_BTN_PRIMARY, hover_color=AppConfig.COLOR_BTN_PRIMARY_HOVER,
                command=lambda p=name: self._pardon_player(p)
            )
            btn_pardon.pack(side="right", padx=10, pady=8)

    # --- Actions: online players ---

    def _kick_player(self, player):
        if self.zbb_manager.is_running():
            self.zbb_manager.send_command(f"kick {player}")
            logger.info("Kicking player: %s", player)

    def _ban_player(self, player):
        if not ZBBDialog.confirm(self, "Ban Player", f"Ban {player} from this server?", danger=True):
            return
        server_name = self.server_name
        if server_name:
            add_entry(server_name, BANNED_PLAYERS_FILE, {"uuid": "", "name": player, "reason": "Banned by an operator"})
            self.banned_players = load_json_list(server_name, BANNED_PLAYERS_FILE)
        if self.zbb_manager.is_running():
            self.zbb_manager.send_command(f"ban {player}")
        logger.info("Banning player: %s", player)
        self.refresh_ui()

    # --- Actions: whitelist ---

    def _add_to_whitelist(self):
        player = self.entry_whitelist_add.get().strip()
        server_name = self.server_name
        if not player or not server_name:
            return
        if any(e.get("name") == player for e in self.whitelisted_players):
            return
        add_entry(server_name, WHITELIST_FILE, {"uuid": "", "name": player})
        self.whitelisted_players = load_json_list(server_name, WHITELIST_FILE)
        if self.zbb_manager.is_running():
            self.zbb_manager.send_command(f"whitelist add {player}")
        self.entry_whitelist_add.delete(0, "end")
        self.refresh_ui()

    def _remove_from_whitelist(self, player):
        server_name = self.server_name
        if not server_name:
            return
        if not ZBBDialog.confirm(self, "Remove from Whitelist", f"Remove {player} from the whitelist?", danger=True):
            return
        remove_entry(server_name, WHITELIST_FILE, player)
        self.whitelisted_players = load_json_list(server_name, WHITELIST_FILE)
        if self.zbb_manager.is_running():
            self.zbb_manager.send_command(f"whitelist remove {player}")
        self.refresh_ui()

    def _toggle_whitelist(self):
        is_enabled = bool(self.switch_whitelist.get())
        state = "on" if is_enabled else "off"
        server_name = self.server_name
        if server_name:
            save_server_properties(server_name, new_properties={"white-list": "true" if is_enabled else "false"})
        if self.zbb_manager.is_running():
            self.zbb_manager.send_command(f"whitelist {state}")
        logger.info("Whitelist turned %s (persisted to server.properties)", state)

    # --- Actions: operators ---

    def _add_operator(self):
        player = self.entry_op_add.get().strip()
        server_name = self.server_name
        if not player or not server_name:
            return
        if any(e.get("name") == player for e in self.operators):
            return
        level = int(self.op_level_var.get())
        add_entry(server_name, OPS_FILE, {
            "uuid": "", "name": player, "level": level, "bypassesPlayerLimit": False
        })
        self.operators = load_json_list(server_name, OPS_FILE)
        if self.zbb_manager.is_running():
            self.zbb_manager.send_command(f"op {player}")
        self.entry_op_add.delete(0, "end")
        self.refresh_ui()

    def _remove_operator(self, player):
        server_name = self.server_name
        if not server_name:
            return
        if not ZBBDialog.confirm(self, "Remove Operator", f"Revoke operator status for {player}?", danger=True):
            return
        remove_entry(server_name, OPS_FILE, player)
        self.operators = load_json_list(server_name, OPS_FILE)
        if self.zbb_manager.is_running():
            self.zbb_manager.send_command(f"deop {player}")
        self.refresh_ui()

    # --- Actions: bans ---

    def _pardon_player(self, player):
        server_name = self.server_name
        if not server_name:
            return
        remove_entry(server_name, BANNED_PLAYERS_FILE, player)
        self.banned_players = load_json_list(server_name, BANNED_PLAYERS_FILE)
        if self.zbb_manager.is_running():
            self.zbb_manager.send_command(f"pardon {player}")
        logger.info("Pardoning player: %s", player)
        self.refresh_ui()
