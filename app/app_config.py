class AppConfig:
    """Application-wide configuration and constants."""

    # Window Configuration
    WINDOW_TITLE = "Zero Block Bridge"
    DEFAULT_WIDTH = 1000
    DEFAULT_HEIGHT = 650
    MIN_WIDTH = 800
    MIN_HEIGHT = 550

    # Colors - UI Theme
    COLOR_BG_LIGHT = "white"
    COLOR_BG_DARK = "gray17"
    COLOR_BG_SIDEBAR_LIGHT = "gray92"
    COLOR_BG_SIDEBAR_DARK = "gray14"
    COLOR_CONSOLE_LIGHT = "gray95"
    COLOR_CONSOLE_DARK = "gray10"
    COLOR_BORDER_LIGHT = "gray80"
    COLOR_BORDER_DARK = "gray25"
    
    # Colors - Status
    COLOR_STATUS_ONLINE = "#22c55e"  # Green
    COLOR_STATUS_OFFLINE = "white"
    COLOR_STATUS_STARTING = "orange"
    COLOR_STATUS_ERROR = "red"
    COLOR_TEXT_GRAY = "gray"

    # Colors - Buttons
    COLOR_BTN_PRIMARY = "#3b82f6"
    COLOR_BTN_PRIMARY_HOVER = "#2563eb"
    COLOR_BTN_SUCCESS = "#22c55e"
    COLOR_BTN_SUCCESS_HOVER = "#16a34a"
    COLOR_BTN_DANGER = "#ef4444"
    COLOR_BTN_DANGER_HOVER = "#dc2626"
    COLOR_BTN_WARNING = "#f97316"
    COLOR_BTN_WARNING_HOVER = "#ea580c"
    COLOR_BTN_INFO = "#34d399"
    COLOR_BTN_INFO_HOVER = "#10b981"
    COLOR_BTN_SECONDARY = "#6366f1"
    COLOR_BTN_SECONDARY_HOVER = "#4f46e5"

    # Fonts
    FONT_MONO = ("Consolas", 12)
    FONT_BODY = ("Roboto", 13)
    FONT_BODY_SMALL = ("Roboto", 11)
    FONT_HEADING = ("Roboto Medium", 18)
    FONT_HEADING_SMALL = ("Roboto Medium", 14)
    FONT_TITLE = ("Roboto Medium", 20)

    # Scheduler
    SCHEDULER_CHECK_INTERVAL = 30  # seconds
    DEFAULT_RESTART_TIME = "03:00"
    DEFAULT_INTERVAL_HOURS = 6

    # Timeouts
    SERVER_STOP_TIMEOUT = 30
    SERVER_START_WAIT = 10
    RESTART_COOLDOWN = 5
