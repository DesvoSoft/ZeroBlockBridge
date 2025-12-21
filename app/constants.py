from pathlib import Path

# Rutas principales de la aplicación
# Usamos Path para un manejo de rutas más robusto y moderno
BASE_DIR = Path(__file__).resolve().parent.parent
SERVERS_DIR = BASE_DIR / "servers"
CONFIG_DIR = BASE_DIR / "config"
BIN_DIR = BASE_DIR / "bin"
BACKUPS_DIR = BASE_DIR / "backups"
ASSETS_DIR = BASE_DIR / "assets"
APP_CONFIG_PATH = CONFIG_DIR / "config.json" # Ruta al config.json principal

# Versiones y URLs para descargas de servidores
MINECRAFT_VERSIONS = {
    "Vanilla": {
        "1.21.11": "https://piston-data.mojang.com/v1/objects/64bb6d763bed0a9f1d632ec347938594144943ed/server.jar",
        "1.20.4": "https://piston-data.mojang.com/v1/objects/8dd1a28015f51b1803213892b50b7b4fc76e594d/server.jar",
        "1.20.1": "https://piston-data.mojang.com/v1/objects/84194a2f286ef7c14ed7ce0090dba59902951553/server.jar",
        "1.19.4": "https://piston-data.mojang.com/v1/objects/8f3112a1049751cc472ec13e397eade5336ca7ae/server.jar",
        "1.18.2": "https://piston-data.mojang.com/v1/objects/c8f83c5655308435b3dcf03c06d9fe8740a77469/server.jar",
        "1.16.5": "https://piston-data.mojang.com/v1/objects/1b557e7b033b583cd9f66746b7a9ab1ec1673ced/server.jar"
    },
    "Fabric": {
        "1.20.1": "https://maven.fabricmc.net/net/fabricmc/fabric-installer/1.0.1/fabric-installer-1.0.1.jar"
    }
}

# Configuración de Playit
PLAYIT_VERSION = "0.16.5"
PLAYIT_URL_WINDOWS = f"https://github.com/playit-cloud/playit-agent/releases/download/v{PLAYIT_VERSION}/playit-windows-x86_64-signed.exe"
PLAYIT_URL_LINUX = f"https://github.com/playit-cloud/playit-agent/releases/download/v{PLAYIT_VERSION}/playit-linux-amd64"
