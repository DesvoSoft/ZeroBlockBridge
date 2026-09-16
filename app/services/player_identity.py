"""Player name validation and UUID resolution for whitelist/ops/bans entries.

Minecraft identifies players in those files by UUID; an entry whose UUID
doesn't parse is ignored when the server loads the file, so ZBB never writes
one with an empty UUID. Resolution order:

1. the server's own usercache.json (players that already joined — no network)
2. online-mode servers: Mojang's profile API (the real account UUID)
3. offline-mode servers: the offline UUID the server itself derives from the name
"""

import hashlib
import json
import logging
import os
import re
import uuid
from dataclasses import dataclass
from typing import Optional

import requests

from app.core.app_config import AppConfig
from app.core.constants import SERVERS_DIR

logger = logging.getLogger(__name__)

MOJANG_PROFILE_URL = "https://api.mojang.com/users/profiles/minecraft/{name}"
_TIMEOUT = 6

# Java Edition: 3-16 letters, digits, underscore. Bedrock players joining
# through Geyser/Floodgate get a "." prefix (spaces become "_").
_JAVA_NAME_RE = re.compile(r"^[A-Za-z0-9_]{3,16}$")
_BEDROCK_NAME_RE = re.compile(r"^\.[A-Za-z0-9_]{1,16}$")


class PlayerLookupError(Exception):
    """The name can't be turned into a real player entry (message is user-facing)."""


@dataclass(frozen=True)
class PlayerIdentity:
    name: str
    uuid: str
    source: str  # "usercache" | "mojang" | "offline"


def is_valid_player_name(name: str) -> bool:
    return bool(_JAVA_NAME_RE.match(name) or _BEDROCK_NAME_RE.match(name))


def offline_uuid(name: str) -> str:
    """UUID an offline-mode server assigns: v3 of "OfflinePlayer:<name>"
    (Java's UUID.nameUUIDFromBytes — MD5 with the version/variant bits set)."""
    digest = bytearray(hashlib.md5(f"OfflinePlayer:{name}".encode("utf-8")).digest())
    digest[6] = (digest[6] & 0x0F) | 0x30
    digest[8] = (digest[8] & 0x3F) | 0x80
    return str(uuid.UUID(bytes=bytes(digest)))


def _dashed(raw: str) -> str:
    return str(uuid.UUID(raw))


def load_usercache(server_name: str) -> list[dict]:
    path = os.path.join(SERVERS_DIR, server_name, "usercache.json")
    if not os.path.exists(path):
        return []
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, json.JSONDecodeError) as exc:
        logger.warning("Failed to read usercache for %s: %s", server_name, exc)
        return []
    return [e for e in data if isinstance(e, dict) and e.get("name") and e.get("uuid")] if isinstance(data, list) else []


def mojang_profile(name: str) -> Optional[tuple[str, str]]:
    """(uuid, canonical name) for a Java account, None if no such account.
    Raises requests.RequestException on network/HTTP failure."""
    resp = requests.get(MOJANG_PROFILE_URL.format(name=name), timeout=_TIMEOUT,
                        headers={"User-Agent": AppConfig.USER_AGENT})
    if resp.status_code in (204, 404):
        return None
    resp.raise_for_status()
    data = resp.json()
    return _dashed(data["id"]), data.get("name", name)


def resolve_player(server_name: str, name: str, online_mode: bool) -> PlayerIdentity:
    name = name.strip()
    if not is_valid_player_name(name):
        raise PlayerLookupError(
            f"'{name}' isn't a valid player name (3-16 letters, numbers or _).")

    wanted = name.lower()
    for entry in load_usercache(server_name):
        if entry["name"].lower() == wanted:
            return PlayerIdentity(entry["name"], entry["uuid"], "usercache")

    if name.startswith("."):
        # Floodgate players have no Java account; their UUID only exists once
        # they have joined (and then usercache has it).
        raise PlayerLookupError(
            f"Bedrock player '{name}' hasn't joined this server yet — ask them to join once first.")

    if not online_mode:
        return PlayerIdentity(name, offline_uuid(name), "offline")

    try:
        profile = mojang_profile(name)
    except (requests.RequestException, ValueError, KeyError) as exc:
        logger.warning("Mojang lookup failed for %s: %s", name, exc)
        raise PlayerLookupError(
            f"Couldn't look up '{name}' (no connection to Mojang). Try again, or add them while the server runs.")
    if profile is None:
        raise PlayerLookupError(f"No Minecraft account named '{name}'.")
    return PlayerIdentity(profile[1], profile[0], "mojang")
