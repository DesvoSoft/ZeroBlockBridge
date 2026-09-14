import logging
import re
from enum import Enum
from typing import Optional

logger = logging.getLogger(__name__)


class BlockedReason(str, Enum):
    """Why a console command was blocked. Values are user-facing text."""
    # str mixin keeps `"empty" in reason` / f-string use working; explicit
    # __str__ because Enum's default renders "BlockedReason.EMPTY" on 3.12+.
    EMPTY = "empty command"
    SHELL_METACHARACTERS = "contains shell metacharacters"
    INJECTION_PATTERN = "contains shell injection pattern"
    SUSPICIOUS_UNKNOWN = "unknown command with suspicious characters"

    def __str__(self) -> str:
        return self.value

INJECTION_CHARS = set(';|&`$')
INJECTION_PATTERNS = [
    re.compile(r'\$\(.*?\)'),
    re.compile(r'`.*?`'),
    re.compile(r'\$\{.*?\}'),
    re.compile(r'\|{2,}'),
    re.compile(r'>{2,}'),
    re.compile(r'<{2,}'),
    re.compile(r'\n'),
]

ALLOWLISTED_COMMANDS = {
    "op", "deop",
    "say", "tell", "msg", "w", "me",
    "gamemode", "gamerule", "difficulty",
    "kick", "ban", "ban-ip", "pardon", "pardon-ip",
    "whitelist", "list",
    "tp", "teleport",
    "give", "clear",
    "setblock", "fill", "clone", "replaceitem",
    "summon", "kill", "effect",
    "time", "weather", "seed",
    "save-all", "save-off", "save-on",
    "stop", "restart",
    "help", "?", "version",
    "reload", "datapack",
    "advancement", "attribute", "bossbar",
    "damage", "data", "datapack", "defaultgamemode",
    "enchant", "execute", "experience",
    "function", "item", "jfr", "loot",
    "particle", "playsound", "recipe",
    "ride", "schedule", "scoreboard",
    "setidletimeout", "spawnpoint", "spectate",
    "spreadplayers", "stopsound", "tag",
    "team", "teammsg", "title", "trigger",
    "warden_spawn_tracker", "worldborder",
    "xp",
}


def is_safe_command(command: str) -> tuple[bool, Optional[BlockedReason]]:
    """Check if a command is safe to send to the server process.

    Returns (is_safe, reason). If safe, reason is None.
    """
    stripped = command.lstrip()
    if not stripped:
        return False, BlockedReason.EMPTY
    if stripped.startswith("/"):
        stripped = stripped[1:]

    if any(ch in stripped for ch in INJECTION_CHARS):
        return False, BlockedReason.SHELL_METACHARACTERS

    for pattern in INJECTION_PATTERNS:
        if pattern.search(stripped):
            return False, BlockedReason.INJECTION_PATTERN

    first_word = stripped.split()[0].lower() if stripped.split() else ""
    if first_word in ALLOWLISTED_COMMANDS:
        return True, None

    if not _looks_like_minecraft_command(stripped):
        return False, BlockedReason.SUSPICIOUS_UNKNOWN

    return True, None


def describe_blocked(command: str, reason: BlockedReason, max_len: int = 40) -> str:
    """User-facing explanation, e.g. "Blocked `op x; rm -rf /`: contains shell metacharacters"."""
    shown = " ".join(command.split())  # newlines would break the toast layout
    if len(shown) > max_len:
        shown = shown[:max_len - 1] + "…"
    return f"Blocked `{shown}`: {reason}" if shown else f"Blocked: {reason}"


def _looks_like_minecraft_command(text: str) -> bool:
    """Weak check: unknown commands are allowed if they look safe."""
    allowed_re = re.compile(r'^[a-zA-Z0-9_ ./@\-\"\'=:+,!?]+$')
    return bool(allowed_re.match(text))
