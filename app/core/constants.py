import platform
import subprocess
import shutil
import re
import os
import sys
import logging
from enum import Enum, auto
from pathlib import Path

logger = logging.getLogger(__name__)


class ServerState(Enum):
    OFFLINE = auto()
    STARTING = auto()
    ONLINE = auto()
    STOPPING = auto()


def subprocess_flags() -> dict:
    """Return kwargs to suppress console windows on Windows.

    Usage::

        subprocess.run(cmd, **subprocess_flags())
        subprocess.Popen(cmd, **subprocess_flags())

    On Windows this returns ``{'creationflags': CREATE_NO_WINDOW}``
    so that helper processes (taskkill, java -version, playit version, …)
    never flash a visible terminal.  On other platforms it returns ``{}``.
    """
    if platform.system() == "Windows":
        return {"creationflags": subprocess.CREATE_NO_WINDOW}
    return {}


# Application Main Paths
# Using Path for robust and modern path handling
#
# In a PyInstaller onefile build, __file__ resolves inside the temp
# _MEIPASS extraction dir (wiped on exit, heavily AV-scanned). Anchor
# to the real .exe's directory instead so servers/config persist and
# aren't executed straight out of a hot temp folder (WinError 5/32).
_data_dir_override = os.environ.get("ZBB_DATA_DIR")
if _data_dir_override:
    # Set by app.core.bootstrap.resolve_data_dir() before this module is
    # first imported -- lets the user relocate servers/config/etc. away
    # from the .exe's own folder (first-run picker or migrated marker).
    BASE_DIR = Path(_data_dir_override)
    _RESOURCE_DIR = Path(getattr(sys, "_MEIPASS", BASE_DIR))
elif getattr(sys, "frozen", False):
    BASE_DIR = Path(sys.executable).resolve().parent
    # Read-only bundled data (PyInstaller `datas`) lives under the onefile
    # temp extraction dir, not next to the .exe.
    _RESOURCE_DIR = Path(getattr(sys, "_MEIPASS", BASE_DIR))
else:
    # Anchor to the repo root (parent of app/), matching the frozen build's
    # exe-dir anchoring and the documented project layout (README "Project
    # Structure") -- generated dirs (servers/, config/, bin/, .zbb_cache/)
    # must not land inside app/, which is source-only and gets wiped/copied
    # as a unit during packaging and cleanup.
    BASE_DIR = Path(__file__).resolve().parent.parent.parent
    _RESOURCE_DIR = BASE_DIR
SERVERS_DIR = BASE_DIR / "servers"
CONFIG_DIR = BASE_DIR / "config"
BIN_DIR = BASE_DIR / "bin"
ASSETS_DIR = _RESOURCE_DIR / "assets"
APP_CONFIG_PATH = CONFIG_DIR / "config.json" # Path to main config.json

# Versions and URLs for server downloads
VERSIONS_CACHE_FILE = CONFIG_DIR / "versions_cache.json"

# API Endpoints
VANILLA_MANIFEST_URL = "https://piston-meta.mojang.com/mc/game/version_manifest_v2.json"
FABRIC_META_URL = "https://meta.fabricmc.net/v2/versions/game"
FORGE_PROMOTIONS_URL = "https://files.minecraftforge.net/net/minecraftforge/forge/promotions_slim.json"

# JDK Cache
JDK_CACHE_DIR = BASE_DIR / ".zbb_cache" / "jdks"

# Playit Configuration
# v1.0+ release assets ship the playitd daemon binary (the old playit-cli
# standalone agent was retired; 0.17.x agents can no longer register
# tunnels — allocation stays "pending" forever).
PLAYIT_VERSION = "1.0.10"
PLAYIT_URL_WINDOWS = f"https://github.com/playit-cloud/playit-agent/releases/download/v{PLAYIT_VERSION}/playit-windows-x86_64-signed.exe"
PLAYIT_URL_LINUX = f"https://github.com/playit-cloud/playit-agent/releases/download/v{PLAYIT_VERSION}/playit-linux-amd64"

# Global Patterns and Timers
ANSI_ESCAPE_RE = re.compile(r'\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])')
META_CACHE_TTL = 5.0
STDERR_BUFFER_MAX = 100
STDERR_SNAPSHOT_SIZE = 50

# Minecraft server player-management JSON files (vanilla schema)
OPS_FILE = "ops.json"
BANNED_PLAYERS_FILE = "banned-players.json"
BANNED_IPS_FILE = "banned-ips.json"
WHITELIST_FILE = "whitelist.json"

def check_disk_space(min_gb=1, target_dir=None):
    """Check if there is at least min_gb of free disk space on the drive containing target_dir."""
    try:
        path = target_dir if target_dir else str(SERVERS_DIR)
        drive = os.path.splitdrive(os.path.abspath(path))[0]
        if not drive:
            drive = "/"
        total, used, free = shutil.disk_usage(drive)
        free_gb = free / (2**30)
        return free_gb >= min_gb
    except Exception as e:
        logger.debug("Failed to check disk space: %s", e)
        return True # Default to true if we can't check
