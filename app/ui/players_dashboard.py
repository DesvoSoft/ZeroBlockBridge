import os
import json
import logging
import customtkinter as ctk
from app.core.app_config import AppConfig
from app.core.server_events import ServerEvent
from app.core.constants import SERVERS_DIR
from app.services.server_properties import load_server_properties, save_server_properties
from app.ui.ui_components import center_on_parent

logger = logging.getLogger(__name__)

class PlayersDashboard(ctk.CTkToplevel):
    def __init__(self, master, event_bus, zbb_manager, **kwargs):
        super().__init__(master, **kwargs)
        self.title("Player Management Dashboard")
        self.geometry("600x600")
        center_on_parent(self, master, 600, 600)
        self.minsize(500, 500)
        self.transient(master)
        self.lift()
        self.focus_force()
        self.event_bus = event_bus
        self.zbb_manager = zbb_manager
        
        self.grid_rowconfigure(1, weight=1)
        self.grid_columnconfigure(0, weight=1)
        self.grid_columnconfigure(1, weight=1)
        
        self._build_header()
        self._build_connected_players_section()
        self._build_whitelist_section()
        
        self.connected_players = []
        self.whitelisted_players = []
        
        self._load_data()
        self.event_bus.subscribe(ServerEvent.PLAYER_LIST, self._on_player_list_update)
        
        self.refresh_ui()

    def destroy(self):
        self.event_bus.unsubscribe(ServerEvent.PLAYER_LIST, self._on_player_list_update)
        super().destroy()

    def _load_data(self):
        if self.zbb_manager.is_running() and self.zbb_manager.server_runner:
            self.connected_players = list(self.zbb_manager.server_runner.connected_players)
        
        server_name = self.zbb_manager.current_server
        if not server_name:
            return
        
        props = load_server_properties(server_name)
        whitelist_enabled = props.get("white-list", "").lower() == "true"
        if whitelist_enabled:
            self.switch_whitelist.select()
        else:
            self.switch_whitelist.deselect()
        
        whitelist_path = os.path.join(SERVERS_DIR, server_name, "whitelist.json")
        if os.path.exists(whitelist_path):
            try:
                with open(whitelist_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    self.whitelisted_players = [entry.get("name") for entry in data if entry.get("name")]
            except Exception as e:
                logger.error("Failed to read whitelist: %s", e)

    def _on_player_list_update(self, players):
        self.connected_players = players
        self.after(0, self.refresh_ui)

    def _build_header(self):
        header_frame = ctk.CTkFrame(self, fg_color="transparent")
        header_frame.grid(row=0, column=0, columnspan=2, sticky="ew", padx=20, pady=(20, 10))
        
        self.lbl_player_count = ctk.CTkLabel(
            header_frame, 
            text="Players Online: 0", 
            font=ctk.CTkFont(family=AppConfig.FONT_FAMILY_DISPLAY, size=24, weight="bold")
        )
        self.lbl_player_count.pack(side="left")

    def _build_connected_players_section(self):
        # Section for connected players
        players_frame = ctk.CTkFrame(self)
        players_frame.grid(row=1, column=0, sticky="nsew", padx=(20, 10), pady=(10, 20))
        players_frame.grid_rowconfigure(1, weight=1)
        players_frame.grid_columnconfigure(0, weight=1)
        
        lbl_title = ctk.CTkLabel(players_frame, text="Connected Players", font=ctk.CTkFont(size=16, weight="bold"))
        lbl_title.grid(row=0, column=0, sticky="w", padx=15, pady=(15, 5))
        
        self.scroll_players = ctk.CTkScrollableFrame(players_frame, fg_color="transparent")
        self.scroll_players.grid(row=1, column=0, sticky="nsew", padx=10, pady=(0, 10))

    def _build_whitelist_section(self):
        # Section for whitelist
        whitelist_frame = ctk.CTkFrame(self)
        whitelist_frame.grid(row=1, column=1, sticky="nsew", padx=(10, 20), pady=(10, 20))
        whitelist_frame.grid_rowconfigure(3, weight=1)
        whitelist_frame.grid_columnconfigure(0, weight=1)
        
        # Header and Toggle
        header_frame = ctk.CTkFrame(whitelist_frame, fg_color="transparent")
        header_frame.grid(row=0, column=0, sticky="ew", padx=15, pady=(15, 5))
        header_frame.grid_columnconfigure(0, weight=1)
        
        lbl_title = ctk.CTkLabel(header_frame, text="Whitelist", font=ctk.CTkFont(size=16, weight="bold"))
        lbl_title.grid(row=0, column=0, sticky="w")
        
        self.switch_whitelist = ctk.CTkSwitch(header_frame, text="Enabled", command=self._toggle_whitelist)
        self.switch_whitelist.grid(row=0, column=1, sticky="e")
        
        # Add player to whitelist
        add_frame = ctk.CTkFrame(whitelist_frame, fg_color="transparent")
        add_frame.grid(row=1, column=0, sticky="ew", padx=15, pady=5)
        add_frame.grid_columnconfigure(0, weight=1)
        
        self.entry_whitelist_add = ctk.CTkEntry(add_frame, placeholder_text="Player name...")
        self.entry_whitelist_add.grid(row=0, column=0, sticky="ew", padx=(0, 10))
        
        btn_add = ctk.CTkButton(add_frame, text="Add", width=60, corner_radius=AppConfig.RADIUS_BTN,
                                fg_color=AppConfig.COLOR_BTN_PRIMARY, hover_color=AppConfig.COLOR_BTN_PRIMARY_HOVER,
                                command=self._add_to_whitelist)
        btn_add.grid(row=0, column=1)
        
        # Whitelist player list
        lbl_list_title = ctk.CTkLabel(whitelist_frame, text="Whitelisted Players:", font=ctk.CTkFont(size=12))
        lbl_list_title.grid(row=2, column=0, sticky="w", padx=15, pady=(10, 0))
        
        self.scroll_whitelist = ctk.CTkScrollableFrame(whitelist_frame, fg_color="transparent")
        self.scroll_whitelist.grid(row=3, column=0, sticky="nsew", padx=10, pady=(0, 10))

    def refresh_ui(self):
        self.lbl_player_count.configure(text=f"Players Online: {len(self.connected_players)}")
        self._populate_connected_players()
        self._populate_whitelist()

    def _populate_connected_players(self):
        for widget in self.scroll_players.winfo_children():
            widget.destroy()
            
        if not self.connected_players:
            lbl = ctk.CTkLabel(self.scroll_players, text="No players online", text_color=AppConfig.COLOR_TEXT_GRAY)
            lbl.pack(pady=20)
            return

        for player in self.connected_players:
            item_frame = ctk.CTkFrame(self.scroll_players, fg_color=(AppConfig.COLOR_BG_CARD_LIGHT, AppConfig.COLOR_BG_CARD_DARK), corner_radius=8)
            item_frame.pack(fill="x", pady=2, padx=5)
            
            lbl_name = ctk.CTkLabel(item_frame, text=player, font=ctk.CTkFont(weight="bold"))
            lbl_name.pack(side="left", padx=10, pady=8)
            
            btn_ban = ctk.CTkButton(
                item_frame, text="Ban", width=50, height=24,
                fg_color="#ef4444", hover_color="#dc2626",
                command=lambda p=player: self._ban_player(p)
            )
            btn_ban.pack(side="right", padx=(5, 10), pady=8)
            
            btn_kick = ctk.CTkButton(
                item_frame, text="Kick", width=50, height=24,
                fg_color="#f97316", hover_color="#ea580c",
                command=lambda p=player: self._kick_player(p)
            )
            btn_kick.pack(side="right", padx=5, pady=8)

    def _populate_whitelist(self):
        for widget in self.scroll_whitelist.winfo_children():
            widget.destroy()
            
        if not self.whitelisted_players:
            lbl = ctk.CTkLabel(self.scroll_whitelist, text="Whitelist empty", text_color=AppConfig.COLOR_TEXT_GRAY)
            lbl.pack(pady=20)
            return

        for player in self.whitelisted_players:
            item_frame = ctk.CTkFrame(self.scroll_whitelist, fg_color=(AppConfig.COLOR_BG_CARD_LIGHT, AppConfig.COLOR_BG_CARD_DARK), corner_radius=8)
            item_frame.pack(fill="x", pady=2, padx=5)
            
            lbl_name = ctk.CTkLabel(item_frame, text=player)
            lbl_name.pack(side="left", padx=10, pady=8)
            
            btn_remove = ctk.CTkButton(
                item_frame, text="X", width=28, height=24,
                fg_color="#ef4444", hover_color="#dc2626",
                command=lambda p=player: self._remove_from_whitelist(p)
            )
            btn_remove.pack(side="right", padx=10, pady=8)

    # --- Actions ---
    def _kick_player(self, player):
        if self.zbb_manager.is_running():
            self.zbb_manager.send_command(f"kick {player}")
            logger.info("Kicking player: %s", player)

    def _ban_player(self, player):
        if self.zbb_manager.is_running():
            self.zbb_manager.send_command(f"ban {player}")
            logger.info("Banning player: %s", player)

    def _add_to_whitelist(self):
        player = self.entry_whitelist_add.get().strip()
        if player and player not in self.whitelisted_players:
            if self.zbb_manager.is_running():
                self.zbb_manager.send_command(f"whitelist add {player}")
            self.whitelisted_players.append(player)
            self.entry_whitelist_add.delete(0, "end")
            self.refresh_ui()

    def _remove_from_whitelist(self, player):
        if player in self.whitelisted_players:
            if self.zbb_manager.is_running():
                self.zbb_manager.send_command(f"whitelist remove {player}")
            self.whitelisted_players.remove(player)
            self.refresh_ui()

    def _toggle_whitelist(self):
        is_enabled = bool(self.switch_whitelist.get())
        state = "on" if is_enabled else "off"
        server_name = self.zbb_manager.current_server
        if server_name:
            save_server_properties(server_name, new_properties={"white-list": "true" if is_enabled else "false"})
        if self.zbb_manager.is_running():
            self.zbb_manager.send_command(f"whitelist {state}")
        logger.info("Whitelist turned %s (persisted to server.properties)", state)
