from pathlib import Path

# Application Main Paths
# Using Path for robust and modern path handling
BASE_DIR = Path(__file__).resolve().parent.parent
SERVERS_DIR = BASE_DIR / "servers"
CONFIG_DIR = BASE_DIR / "config"
BIN_DIR = BASE_DIR / "bin"
ASSETS_DIR = BASE_DIR / "assets"
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
PLAYIT_VERSION = "0.17.1"
PLAYIT_URL_WINDOWS = f"https://github.com/playit-cloud/playit-agent/releases/download/v{PLAYIT_VERSION}/playit-windows-x86_64-signed.exe"
PLAYIT_URL_LINUX = f"https://github.com/playit-cloud/playit-agent/releases/download/v{PLAYIT_VERSION}/playit-linux-amd64"
