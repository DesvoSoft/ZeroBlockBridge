"""server.properties catalog: what each key means, how risky changing it
is, which tab and section shows it, its label and the kind of control.

Plain data and pure functions shared by every UI (CustomTkinter today, Qt
in 8d). The labels and descriptions are still English-only; they are
marked for translation when the properties screen is ported (8d).
"""

from __future__ import annotations

from app.core.i18n import N_

SETTINGS_METADATA = {
    # General
    "max-players": {"desc": "Maximum number of players allowed online.", "impact": "Low"},
    "gamemode": {"desc": "The default game mode for new players.", "impact": "Low"},
    "force-gamemode": {"desc": "Forces players to join in the default game mode.", "impact": "Low"},
    "difficulty": {"desc": "Overall game difficulty. Affects damage and mob behavior.", "impact": "Low"},
    "hardcore": {"desc": "Players are banned upon death. One life only.", "impact": "Medium"},
    "enable-command-block": {"desc": "Allows the use of command blocks in-game.", "impact": "Low"},
    
    # World
    "level-seed": {"desc": "The unique code used to generate the world. Leave empty for random.", "impact": "Low"},
    "level-name": {"desc": "The name of the world folder on disk.", "impact": "Low"},
    "level-type": {"desc": "The type of world generation (Flat, Large Biomes, etc).", "impact": "Medium"},
    "generate-structures": {"desc": "Whether to generate villages, dungeons, etc.", "impact": "Medium"},
    "spawn-npcs": {"desc": "Whether to spawn villagers.", "impact": "Low"},
    "spawn-animals": {"desc": "Whether to spawn passive mobs like cows and sheep.", "impact": "Medium"},
    "spawn-monsters": {"desc": "Whether to spawn hostile mobs.", "impact": "Medium"},
    "view-distance": {"desc": "How many chunks are visible to players. Higher = More RAM usage.", "impact": "High"},
    "simulation-distance": {"desc": "How many chunks process active ticks (crops, mobs).", "impact": "High"},
    
    # Network
    "server-port": {"desc": "The port the server listens on (Default: 25565).", "impact": "Low"},
    "server-ip": {"desc": "The network interface to bind to. Leave empty to listen on all interfaces.", "impact": "Medium"},
    "white-list": {"desc": "Only allowed players can join the server.", "impact": "Low"},
    "enforce-whitelist": {"desc": "Kicks non-whitelisted players immediately when the whitelist is reloaded, instead of waiting for their next join attempt.", "impact": "Medium"},
    "online-mode": {"desc": "Checks players against Mojang accounts. Disable for 'cracked' servers.", "impact": "Medium"},
    "network-compression-threshold": {"desc": "Size at which packets are compressed. Lower = More CPU usage.", "impact": "Medium"},
    "rcon.password": {"desc": "Password required to authenticate remote console (RCON) connections.", "impact": "Medium"},
    "rcon.port": {"desc": "The port used for remote console (RCON) connections (Default: 25575).", "impact": "Low"},

    # Advanced
    "sync-chunk-writes": {"desc": "Ensures world data is saved safely. Disabling can boost performance but risks corruption.", "impact": "High"},
    "op-permission-level": {"desc": "Default permission level for operators: 1 bypasses spawn protection, 2 unlocks cheat commands and command blocks, 3 adds player management (kick/ban/op), 4 grants full access including /stop.", "impact": "Medium"},
    "prevent-proxy-connections": {"desc": "Blocks players using VPNs or Proxies.", "impact": "Low"},
    "enforce-secure-profile": {"desc": "Requires Mojang-signed public keys for players.", "impact": "Low"},
    "enable-rcon": {"desc": "Allows remote console access (for bots/panels).", "impact": "Medium"},
    "enable-query": {"desc": "Allows external tools to see server status.", "impact": "Low"},

    # Other Properties (vanilla keys with no dedicated tab section)
    "pvp": {"desc": "Allows players to damage each other.", "impact": "Medium"},
    "allow-flight": {"desc": "Allows use of flight mods/hacks in Survival. Disabling risks kicking legitimate players with high-latency connections (anti-cheat false positives).", "impact": "High"},
    "allow-nether": {"desc": "Allows players to travel to the Nether dimension.", "impact": "Low"},
    "spawn-protection": {"desc": "Radius around spawn (in blocks) where only operators can build. A large value can lock new players out of building anywhere reachable.", "impact": "High"},
    "max-tick-time": {"desc": "Milliseconds a single tick can take before the server watchdog force-kills it as hung. Setting to -1 disables the watchdog entirely, letting a frozen server run forever undetected.", "impact": "High"},
    "player-idle-timeout": {"desc": "Minutes of inactivity before an idle player is kicked. 0 disables the timeout.", "impact": "Low"},
    "max-world-size": {"desc": "Maximum radius (in blocks) the world border can expand to.", "impact": "Medium"},
    "entity-broadcast-range-percentage": {"desc": "Percentage of the default entity tracking range. Lower values reduce network traffic but may make entities pop in late.", "impact": "Medium"},
    "rate-limit": {"desc": "Maximum packets per second a player can send before being kicked. 0 disables the limit.", "impact": "Medium"},
    "function-permission-level": {"desc": "Permission level (1-4) required for datapack functions to run operator-level commands.", "impact": "Medium"},
    "hide-online-players": {"desc": "Hides the player list from the server status response (server list ping).", "impact": "Low"},
    "log-ips": {"desc": "Whether player IP addresses are written to the server log.", "impact": "Low"},
    "broadcast-console-to-ops": {"desc": "Sends console command output to online operators as chat messages.", "impact": "Low"},
    "broadcast-rcon-to-ops": {"desc": "Sends RCON command output to online operators as chat messages.", "impact": "Low"},
    "max-chained-neighbor-updates": {"desc": "Limits chained block updates (e.g. large redstone contraptions) before the server stops propagating them, to prevent lag or crashes.", "impact": "Medium"},
    "require-resource-pack": {"desc": "Forces players to accept the server resource pack or be disconnected.", "impact": "Medium"},
    "resource-pack": {"desc": "URL of a resource pack players will be prompted to download when joining.", "impact": "Low"},
    "resource-pack-prompt": {"desc": "Custom message shown in the resource pack download prompt.", "impact": "Low"},
    "motd": {"desc": "Message shown in the multiplayer server list. Supports § color codes.", "impact": "Low"},
    "use-native-transport": {"desc": "Uses optimized Linux network transport (epoll) when available. Has no effect on Windows.", "impact": "Low"},
    "enable-jmx-monitoring": {"desc": "Exposes server metrics via JMX for monitoring tools.", "impact": "Low"},
    "enable-status": {"desc": "Whether the server responds to server list pings (status queries).", "impact": "Low"},
    "pause-when-empty-seconds": {"desc": "Seconds of no players online before the server pauses ticking to save CPU. 0 disables pausing.", "impact": "Medium"},
    "accepts-transfers": {"desc": "Allows players to be transferred in from other servers via the transfer packet.", "impact": "Low"},
    "region-file-compression": {"desc": "Compression algorithm used for region files on disk (e.g. deflate, none).", "impact": "Medium"},
    "entity-activation-range": {"desc": "Distance around a player at which entities become active and start ticking.", "impact": "Medium"},
}

# Define the layout for the complex tabs
TAB_LAYOUTS = {
    "World": {
        "Environment & Generation": [
            "level-seed", "level-name", "level-type", "generate-structures"
        ],
        "Entities & Spawning": [
            "spawn-npcs", "spawn-animals", "spawn-monsters"
        ],
        "Performance": [
            "view-distance", "simulation-distance"
        ]
    },
    "Network": {
        "Connectivity": ["server-port", "server-ip"],
        "Access Control": ["white-list", "enforce-whitelist", "online-mode"],
        "Optimization": ["network-compression-threshold"],
        "Remote Access": ["enable-rcon", "rcon.password", "rcon.port"]
    },
    "Advanced": {
        "Gameplay Rules": ["pvp", "allow-flight", "allow-nether", "spawn-protection"],
        "Server Behavior": [
            "max-tick-time", "player-idle-timeout", "function-permission-level",
            "hide-online-players", "log-ips", "broadcast-console-to-ops",
            "broadcast-rcon-to-ops", "require-resource-pack",
        ],
        "System Performance": ["sync-chunk-writes"],
        "Security & Permissions": [
            "op-permission-level", "prevent-proxy-connections", "enforce-secure-profile"
        ]
    }
}

_LABEL_WORDS = {
    "npcs": "NPCs", "ip": "IP", "ips": "IPs", "rcon": "RCON", "pvp": "PvP",
    "op": "Operator", "ops": "Operators", "to": "to",
}
_LABEL_OVERRIDES = {"white-list": "Whitelist"}
# SETTINGS_METADATA "impact" keys -> labels shown in the impact dot's tooltip.
IMPACT_LABELS = {"Low": N_("Low"), "Medium": N_("Medium"), "High": N_("High")}


# Keys shown as on/off switches although their name doesn't say "enable".
BOOLEAN_KEYS = {
    "pvp", "allow-flight", "allow-nether", "hide-online-players", "log-ips",
    "broadcast-console-to-ops", "broadcast-rcon-to-ops", "require-resource-pack",
    "generate-structures", "sync-chunk-writes", "prevent-proxy-connections",
}
_BOOLEAN_KEY_PARTS = ("enable", "spawn-npcs", "spawn-animals", "spawn-monsters", "white-list",
                      "hardcore", "enforce", "online")
DROPDOWN_OPTIONS = {
    "gamemode": ["survival", "creative", "adventure", "spectator"],
    "difficulty": ["peaceful", "easy", "normal", "hard"],
    "level-type": ["minecraft:normal", "minecraft:flat", "minecraft:large_biomes"],
    "op-permission-level": ["1", "2", "3", "4"],
    "function-permission-level": ["1", "2", "3", "4"],
}


def property_control(key: str) -> tuple[str, list | None]:
    """("checkbox" | "dropdown" | "entry", dropdown options or None) for a key.
    "level-name" is an entry here; a UI offers the server's worlds instead."""
    if key in BOOLEAN_KEYS or any(part in key for part in _BOOLEAN_KEY_PARTS):
        return "checkbox", None
    if key in DROPDOWN_OPTIONS:
        return "dropdown", list(DROPDOWN_OPTIONS[key])
    return "entry", None


def property_label(key: str) -> str:
    """Human label for a server.properties key ("spawn-npcs" -> "Spawn NPCs")."""
    if key in _LABEL_OVERRIDES:
        return _LABEL_OVERRIDES[key]
    words = [_LABEL_WORDS.get(w, w.capitalize()) for w in key.replace(".", "-").split("-")]
    label = " ".join(words)
    return label[0].upper() + label[1:]
