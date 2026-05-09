import logging
import re

logger = logging.getLogger(__name__)

INJECTION_CHARS = set(';|&`$%')
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


def is_safe_command(command: str) -> tuple[bool, str]:
    """Check if a command is safe to send to the server process.

    Returns (is_safe, reason). If safe, reason is empty string.
    """
    stripped = command.lstrip()
    if not stripped:
        return False, "empty command"
    if stripped.startswith("/"):
        stripped = stripped[1:]

    if any(ch in stripped for ch in INJECTION_CHARS):
        return False, "contains shell metacharacters"

    for pattern in INJECTION_PATTERNS:
        if pattern.search(stripped):
            return False, "contains shell injection pattern"

    first_word = stripped.split()[0].lower() if stripped.split() else ""
    if first_word in ALLOWLISTED_COMMANDS:
        return True, ""

    if not _looks_like_minecraft_command(stripped):
        return False, "unknown command with suspicious characters"

    return True, ""


def _looks_like_minecraft_command(text: str) -> bool:
    """Weak check: unknown commands are allowed if they look safe."""
    allowed_re = re.compile(r'^[a-zA-Z0-9_ ./@\-\"\'=:+,!?]+$')
    return bool(allowed_re.match(text))
