from pathlib import Path

# Rutas principales de la aplicación
# Usamos Path para un manejo de rutas más robusto y moderno
BASE_DIR = Path(__file__).resolve().parent.parent
SERVERS_DIR = BASE_DIR / "servers"
CONFIG_DIR = BASE_DIR / "config"
BIN_DIR = BASE_DIR / "bin"
BACKUPS_DIR = BASE_DIR / "backups"
APP_CONFIG_PATH = CONFIG_DIR / "config.json" # Ruta al config.json principal

# Versiones y URLs para descargas de servidores
MINECRAFT_VERSIONS = {
    "Vanilla": {
        "1.21.1": "https://piston-data.mojang.com/v1/objects/59353fb40c36d304f2035d51e7d6e6baa98dc05c/server.jar"
    },
    "Fabric": {
        "1.20.1": "https://maven.fabricmc.net/net/fabricmc/fabric-installer/1.0.1/fabric-installer-1.0.1.jar"
    }
}

# Configuración de Playit
PLAYIT_VERSION = "0.16.5"
PLAYIT_URL_WINDOWS = f"https://github.com/playit-cloud/playit-agent/releases/download/v{PLAYIT_VERSION}/playit-windows-x86_64-signed.exe"
PLAYIT_URL_LINUX = f"https://github.com/playit-cloud/playit-agent/releases/download/v{PLAYIT_VERSION}/playit-linux-amd64"
