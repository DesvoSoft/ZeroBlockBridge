class AppConfig:
    """Application-wide configuration and constants."""

    # Window Configuration
    WINDOW_TITLE = "Zero Block Bridge"
    DEFAULT_WIDTH = 1150
    DEFAULT_HEIGHT = 700
    MIN_WIDTH = 900
    MIN_HEIGHT = 580

    # Colors - UI Theme ("Dirt Block" palette)
    # Backgrounds — slate propio, no gray genérico de CTK
    COLOR_BG_LIGHT = "#f8fafc"        # slate-50  (light mode main bg)
    COLOR_BG_DARK = "#111827"         # gray-900  (dark mode main bg)
    COLOR_BG_SIDEBAR_LIGHT = "#f1f5f9" # slate-100 (light sidebar)
    COLOR_BG_SIDEBAR_DARK = "#0f172a"  # slate-950 (dark sidebar — más profundo)
    COLOR_BG_CARD_DARK = "#1e293b"     # slate-800 (cards, panels, status bar)
    COLOR_BG_CARD_LIGHT = "#ffffff"
    COLOR_CONSOLE_LIGHT = "#f8fafc"   # slate-50
    COLOR_CONSOLE_DARK = "#0d1117"    # casi negro — contraste máximo para logs
    COLOR_BORDER_LIGHT = "#cbd5e1"    # slate-300
    COLOR_BORDER_DARK = "#334155"     # slate-700

    # Colors - Accent ("Dirt Block" — tierra, pasto, ámbar)
    COLOR_ACCENT_BROWN = "#92400e"        # amber-800 (marrón tierra)
    COLOR_ACCENT_BROWN_HOVER = "#78350f"  # amber-900
    COLOR_ACCENT_GREEN = "#4d7c0f"        # lime-800 (verde pasto apagado)
    COLOR_ACCENT_GREEN_HOVER = "#3f6212"  # lime-900
    COLOR_ACCENT_AMBER = "#d97706"        # amber-600 (highlight cálido)
    COLOR_ACCENT_AMBER_HOVER = "#b45309"  # amber-700

    # Colors - Status
    COLOR_STATUS_ONLINE = "#84cc16"    # lime-400 (verde MC)
    COLOR_STATUS_OFFLINE = "#64748b"   # slate-500
    COLOR_STATUS_STARTING = "#f59e0b"  # amber-400
    COLOR_STATUS_ERROR = "#f87171"     # red-400

    COLOR_TEXT_PRIMARY = "#f1f5f9"  # slate-100
    COLOR_TEXT_GRAY = "#94a3b8"     # slate-400
    COLOR_TEXT_NOTE = "#64748b"     # slate-500
    COLOR_TEXT_MUTED = "#475569"    # slate-600

    # Colors - Link/highlight (verde pasto vivo — reemplaza el azul #3b82f6)
    COLOR_LINK = ("#4d7c0f", "#a3e635")  # lime-800 light / lime-400 dark

    # Colors - Badges/pills (shared across status bar, mods browser)
    COLOR_BADGE_BG = ("#ecfccb", "#26331c")    # lime-100 / verde oscuro
    COLOR_BADGE_TEXT = ("#3f6212", "#bef264")  # lime-800 / lime-300

    # Colors - Buttons (roles: Primary, Success, Danger, Warning, Ghost)
    COLOR_BTN_PRIMARY = "#65a30d"        # lime-600 (pasto — acción principal)
    COLOR_BTN_PRIMARY_HOVER = "#4d7c0f"  # lime-700
    COLOR_BTN_SUCCESS = "#16a34a"        # green-600
    COLOR_BTN_SUCCESS_HOVER = "#15803d"  # green-700
    COLOR_BTN_DANGER = "#dc2626"         # red-600
    COLOR_BTN_DANGER_HOVER = "#b91c1c"   # red-700
    COLOR_BTN_WARNING = COLOR_ACCENT_AMBER
    COLOR_BTN_WARNING_HOVER = COLOR_ACCENT_AMBER_HOVER
    COLOR_BTN_GHOST = "#1e293b"          # slate-800
    COLOR_BTN_GHOST_HOVER = "#334155"    # slate-700
    # Legacy aliases — mantener para no romper callers existentes
    COLOR_BTN_INFO = "#34d399"
    COLOR_BTN_INFO_HOVER = "#10b981"
    COLOR_BTN_SECONDARY = COLOR_ACCENT_BROWN
    COLOR_BTN_SECONDARY_HOVER = COLOR_ACCENT_BROWN_HOVER

    # Fonts — familias nativas Win11 (Roboto no viene instalada en Windows;
    # Tk sustituía en silencio por la fuente fallback)
    FONT_FAMILY = "Segoe UI Variable Text"
    FONT_FAMILY_DISPLAY = "Segoe UI Variable Display"
    FONT_FAMILY_MONO = "Cascadia Mono"
    FONT_MONO = (FONT_FAMILY_MONO, 12)
    FONT_BODY = (FONT_FAMILY, 13)
    FONT_BODY_SMALL = (FONT_FAMILY, 11)
    FONT_HEADING = (FONT_FAMILY_DISPLAY, 18, "bold")
    FONT_HEADING_SMALL = (FONT_FAMILY_DISPLAY, 14, "bold")
    FONT_TITLE = (FONT_FAMILY_DISPLAY, 20, "bold")
    FONT_NOTE = (FONT_FAMILY, 11, "italic")

    # Radius scale — CTk dibuja esquinas sin antialiasing real: radios grandes
    # en widgets pequeños se ven pixelados. Escala semántica en vez de 12 global.
    RADIUS_CARD = 10
    RADIUS_BTN = 8
    RADIUS_INPUT = 8
    RADIUS_BADGE = 6

    # Scheduler
    SCHEDULER_CHECK_INTERVAL = 30  # seconds
    DEFAULT_RESTART_TIME = "03:00"
    DEFAULT_INTERVAL_HOURS = 6

    # Timeouts
    SERVER_STOP_TIMEOUT = 30
    SERVER_START_WAIT = 10
    RESTART_COOLDOWN = 5
    DEBOUNCE_MS = 200

    # Playit.gg Config
    PLAYIT_BRIDGE_URL = "https://playit.auto-mcs.com/link"
    PLAYIT_WIZARD_URL = "https://playit.gg/account/setup/wizard/new-account/third-party/third-party-code?partner=other"

    # Server Defaults
    DEFAULT_MC_PORT = 25565
    DEFAULT_RAM_MB = 2048
    BACKUP_TIMEOUT = 300
    CONSOLE_BUFFER_SIZE = 1000
    MAX_SUPPORTED_JAVA = 21
