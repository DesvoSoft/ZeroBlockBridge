"""PlayerOrchestrator — whitelist, operators, bans, kicks and the player roster.

While the selected server runs it owns whitelist.json / ops.json /
banned-players.json (it rewrites them from memory), so changes go through its
console commands. While it is stopped ZBB writes the files itself — always
with a resolved UUID (see services/player_identity), because the server
ignores entries whose UUID doesn't parse.

Methods can block on a Mojang lookup: call them from a worker thread.
"""

import datetime
import logging
import re
from dataclasses import dataclass
from typing import Optional

from app.core.constants import BANNED_PLAYERS_FILE, OPS_FILE, WHITELIST_FILE
from app.services.player_files import add_entry, load_json_list, remove_entry
from app.services.player_history import load_history
from app.services.player_identity import (
    PlayerLookupError, is_valid_player_name, load_usercache, resolve_player,
)
from app.services.server_properties import load_server_properties, save_server_properties

logger = logging.getLogger(__name__)

OP_LEVELS = (1, 2, 3, 4)
# Kick/ban reasons end up in a console command: plain text only.
_REASON_RE = re.compile(r"^[\w .,!?'()\-]{0,100}$")


@dataclass(frozen=True)
class PlayerResult:
    ok: bool
    message: str


class PlayerOrchestrator:
    def __init__(self, manager):
        self.manager = manager

    # ------------------------------------------------------------------ state
    def is_live(self, server_name: str) -> bool:
        """True when the server itself owns the player files right now."""
        return server_name == self.manager.current_server and self.manager.is_running()

    @staticmethod
    def online_mode(server_name: str) -> bool:
        return load_server_properties(server_name).get("online-mode", "true").strip().lower() == "true"

    @staticmethod
    def default_op_level(server_name: str) -> int:
        try:
            level = int(load_server_properties(server_name).get("op-permission-level", 4))
        except (TypeError, ValueError):
            return 4
        return level if level in OP_LEVELS else 4

    @staticmethod
    def whitelist_enabled(server_name: str) -> bool:
        return load_server_properties(server_name).get("white-list", "false").strip().lower() == "true"

    def online_players(self, server_name: str) -> list[str]:
        runner = self.manager.server_runner
        if not self.is_live(server_name) or runner is None:
            return []
        return sorted(runner.connected_players)

    def roster(self, server_name: str) -> list[dict]:
        """Every player ZBB knows for this server, merged by name: online
        players, usercache, whitelist, operators, bans and play history."""
        players: dict[str, dict] = {}

        def entry(name: str) -> dict:
            key = name.lower()
            if key not in players:
                players[key] = {
                    "name": name, "uuid": "", "online": False, "op_level": None,
                    "whitelisted": False, "banned": False, "ban_reason": "",
                    "first_seen": None, "last_seen": None, "playtime_seconds": 0,
                }
            return players[key]

        for cached in load_usercache(server_name):
            entry(cached["name"])["uuid"] = cached["uuid"]
        for item in load_json_list(server_name, WHITELIST_FILE):
            if item.get("name"):
                e = entry(item["name"])
                e["whitelisted"] = True
                e["uuid"] = e["uuid"] or item.get("uuid", "")
        for item in load_json_list(server_name, OPS_FILE):
            if item.get("name"):
                e = entry(item["name"])
                e["op_level"] = item.get("level", 4)
                e["uuid"] = e["uuid"] or item.get("uuid", "")
        for item in load_json_list(server_name, BANNED_PLAYERS_FILE):
            if item.get("name"):
                e = entry(item["name"])
                e["banned"] = True
                e["ban_reason"] = item.get("reason", "")
                e["uuid"] = e["uuid"] or item.get("uuid", "")
        for name, record in load_history(server_name).items():
            e = entry(name)
            e["first_seen"] = record.get("first_seen")
            e["last_seen"] = record.get("last_seen")
            e["playtime_seconds"] = record.get("playtime_seconds", 0)
        for name in self.online_players(server_name):
            entry(name)["online"] = True

        return sorted(players.values(), key=lambda p: (not p["online"], p["name"].lower()))

    # ---------------------------------------------------------------- helpers
    def _check_name(self, name: str) -> Optional[PlayerResult]:
        if not is_valid_player_name(name):
            return PlayerResult(False, f"'{name}' isn't a valid player name (3-16 letters, numbers or _).")
        return None

    def _command(self, command: str, message: str) -> PlayerResult:
        self.manager.send_command(command)
        return PlayerResult(True, message)

    def _resolve(self, server_name: str, name: str):
        return resolve_player(server_name, name, self.online_mode(server_name))

    # ---------------------------------------------------------------- actions
    def set_whitelist_enabled(self, server_name: str, enabled: bool) -> PlayerResult:
        save_server_properties(server_name, new_properties={"white-list": "true" if enabled else "false"})
        if self.is_live(server_name):
            self.manager.send_command(f"whitelist {'on' if enabled else 'off'}")
        return PlayerResult(True, f"Whitelist {'enabled' if enabled else 'disabled'}.")

    def whitelist_add(self, server_name: str, name: str) -> PlayerResult:
        name = name.strip()
        if error := self._check_name(name):
            return error
        if self.is_live(server_name):
            return self._command(f"whitelist add {name}", f"Added {name} to the whitelist.")
        try:
            ident = self._resolve(server_name, name)
        except PlayerLookupError as exc:
            return PlayerResult(False, str(exc))
        add_entry(server_name, WHITELIST_FILE, {"uuid": ident.uuid, "name": ident.name})
        return PlayerResult(True, f"Added {ident.name} to the whitelist.")

    def whitelist_remove(self, server_name: str, name: str) -> PlayerResult:
        if self.is_live(server_name):
            return self._command(f"whitelist remove {name}", f"Removed {name} from the whitelist.")
        remove_entry(server_name, WHITELIST_FILE, name)
        return PlayerResult(True, f"Removed {name} from the whitelist.")

    def op(self, server_name: str, name: str, level: int) -> PlayerResult:
        name = name.strip()
        if error := self._check_name(name):
            return error
        if self.is_live(server_name):
            # /op always grants op-permission-level; a specific level can only
            # be written to ops.json while the server is stopped.
            default = self.default_op_level(server_name)
            note = "" if level == default else f" (level {default}, the server's op-permission-level; " \
                                              f"stop the server to set level {level})"
            return self._command(f"op {name}", f"Made {name} an operator{note}.")
        if level not in OP_LEVELS:
            return PlayerResult(False, f"Operator level must be 1-4, not {level}.")
        try:
            ident = self._resolve(server_name, name)
        except PlayerLookupError as exc:
            return PlayerResult(False, str(exc))
        add_entry(server_name, OPS_FILE, {
            "uuid": ident.uuid, "name": ident.name, "level": level, "bypassesPlayerLimit": False,
        })
        return PlayerResult(True, f"Made {ident.name} an operator (level {level}).")

    def deop(self, server_name: str, name: str) -> PlayerResult:
        if self.is_live(server_name):
            return self._command(f"deop {name}", f"{name} is no longer an operator.")
        remove_entry(server_name, OPS_FILE, name)
        return PlayerResult(True, f"{name} is no longer an operator.")

    def ban(self, server_name: str, name: str, reason: str = "") -> PlayerResult:
        name, reason = name.strip(), " ".join(reason.split())
        if error := self._check_name(name):
            return error
        if not _REASON_RE.match(reason):
            return PlayerResult(False, "Use letters, numbers and basic punctuation in the reason (max 100).")
        if self.is_live(server_name):
            return self._command(f"ban {name} {reason}".rstrip(), f"Banned {name}.")
        try:
            ident = self._resolve(server_name, name)
        except PlayerLookupError as exc:
            return PlayerResult(False, str(exc))
        add_entry(server_name, BANNED_PLAYERS_FILE, {
            "uuid": ident.uuid, "name": ident.name,
            "created": datetime.datetime.now().astimezone().strftime("%Y-%m-%d %H:%M:%S %z"),
            "source": "Server", "expires": "forever",
            "reason": reason or "Banned by an operator.",
        })
        return PlayerResult(True, f"Banned {ident.name}.")

    def pardon(self, server_name: str, name: str) -> PlayerResult:
        if self.is_live(server_name):
            return self._command(f"pardon {name}", f"Unbanned {name}.")
        remove_entry(server_name, BANNED_PLAYERS_FILE, name)
        return PlayerResult(True, f"Unbanned {name}.")

    def kick(self, server_name: str, name: str, reason: str = "") -> PlayerResult:
        reason = " ".join(reason.split())
        if not self.is_live(server_name):
            return PlayerResult(False, "The server isn't running.")
        if not _REASON_RE.match(reason):
            return PlayerResult(False, "Use letters, numbers and basic punctuation in the reason (max 100).")
        return self._command(f"kick {name} {reason}".rstrip(), f"Kicked {name}.")
