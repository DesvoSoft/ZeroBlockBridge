"""Players of a server: roster, whitelist, operators, bans, kicks, skin heads."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Optional

from PIL import Image

from app.core.players import OP_LEVELS  # noqa: F401  (re-exported for UIs)
from app.services.player_heads import fetch_head

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class PlayersSnapshot:
    roster: list                 # dicts: name, uuid, online, op_level, whitelisted, banned, ...
    online_mode: bool
    whitelist_enabled: bool
    live: bool                   # the server runs: changes go through console commands
    default_op_level: int


class PlayersApi:
    """Actions return a PlayerResult (``ok``, ``message``); all block (files,
    console round trips, Mojang lookups): call them off the UI thread."""

    def __init__(self, orchestrator):
        self._players = orchestrator

    def snapshot(self, server_name: str) -> PlayersSnapshot:
        p = self._players
        return PlayersSnapshot(roster=p.roster(server_name), online_mode=p.online_mode(server_name),
                               whitelist_enabled=p.whitelist_enabled(server_name),
                               live=p.is_live(server_name), default_op_level=p.default_op_level(server_name))

    def set_whitelist_enabled(self, server_name: str, enabled: bool):
        return self._players.set_whitelist_enabled(server_name, enabled)

    def whitelist_add(self, server_name: str, name: str):
        return self._players.whitelist_add(server_name, name)

    def whitelist_remove(self, server_name: str, name: str):
        return self._players.whitelist_remove(server_name, name)

    def op(self, server_name: str, name: str, level: int):
        return self._players.op(server_name, name, level)

    def deop(self, server_name: str, name: str):
        return self._players.deop(server_name, name)

    def ban(self, server_name: str, name: str, reason: str = ""):
        return self._players.ban(server_name, name, reason)

    def pardon(self, server_name: str, name: str):
        return self._players.pardon(server_name, name)

    def kick(self, server_name: str, name: str, reason: str = ""):
        return self._players.kick(server_name, name, reason)

    @staticmethod
    def head_image(player_uuid: str, size: int) -> Optional[Image.Image]:
        """The player's skin head scaled to ``size`` px (nearest neighbour,
        it is pixel art), or None. Downloads on first use (cached)."""
        path = fetch_head(player_uuid, 64)
        if not path:
            return None
        try:
            with Image.open(path) as raw:
                return raw.convert("RGBA").resize((size, size), Image.NEAREST)
        except OSError as exc:
            logger.debug("Unreadable head image %s: %s", path, exc)
            return None
