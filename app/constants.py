from pathlib import Path

# Rutas principales de la aplicación
# Usamos Path para un manejo de rutas más robusto y moderno
BASE_DIR = Path(__file__).resolve().parent.parent
SERVERS_DIR = BASE_DIR / "servers"
CONFIG_DIR = BASE_DIR / "config"
BIN_DIR = BASE_DIR / "bin"
ASSETS_DIR = BASE_DIR / "assets"
APP_CONFIG_PATH = CONFIG_DIR / "config.json" # Ruta al config.json principal

# Versiones y URLs para descargas de servidores
VERSIONS_CACHE_FILE = CONFIG_DIR / "versions_cache.json"

# API Endpoints
VANILLA_MANIFEST_URL = "https://piston-meta.mojang.com/mc/game/version_manifest_v2.json"
FABRIC_META_URL = "https://meta.fabricmc.net/v2/versions/game"
FORGE_PROMOTIONS_URL = "https://files.minecraftforge.net/net/minecraftforge/forge/promotions_slim.json"

# Configuración de Playit
PLAYIT_VERSION = "0.16.5"
PLAYIT_URL_WINDOWS = f"https://github.com/playit-cloud/playit-agent/releases/download/v{PLAYIT_VERSION}/playit-windows-x86_64-signed.exe"
PLAYIT_URL_LINUX = f"https://github.com/playit-cloud/playit-agent/releases/download/v{PLAYIT_VERSION}/playit-linux-amd64"
