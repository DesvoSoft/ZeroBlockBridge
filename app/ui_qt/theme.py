"""Light/dark theme from the design tokens in ``AppConfig``.

The tokens are ``(light, dark)`` tuples or ``*_LIGHT`` / ``*_DARK`` pairs;
``tokens(dark)`` flattens them for one mode and ``stylesheet()`` turns them
into QSS. A QPalette with the same colors covers what QSS does not reach
(native dialogs, selection, tooltips), so no widget paints a default white
before the stylesheet applies.
"""

from __future__ import annotations

from PySide6.QtGui import QColor, QFont, QPalette
from PySide6.QtWidgets import QApplication
from PySide6.QtCore import Qt

from app.core.app_config import AppConfig as C


def _pick(value, dark: bool) -> str:
    return value[1 if dark else 0] if isinstance(value, tuple) else value


def tokens(dark: bool) -> dict:
    side = "DARK" if dark else "LIGHT"
    return {
        "bg": getattr(C, f"COLOR_BG_{side}"),
        "sidebar": getattr(C, f"COLOR_BG_SIDEBAR_{side}"),
        "card": getattr(C, f"COLOR_BG_CARD_{side}"),
        "console": getattr(C, f"COLOR_CONSOLE_{side}"),
        "border": getattr(C, f"COLOR_BORDER_{side}"),
        "text": _pick(C.COLOR_TEXT_PRIMARY, dark),
        "muted": _pick(C.COLOR_TEXT_GRAY, dark),
        "primary": _pick(C.COLOR_BTN_PRIMARY, dark),
        "primary_hover": _pick(C.COLOR_BTN_PRIMARY_HOVER, dark),
        "danger": _pick(C.COLOR_BTN_DANGER, dark),
        "danger_hover": _pick(C.COLOR_BTN_DANGER_HOVER, dark),
        "ghost": _pick(C.COLOR_BTN_GHOST, dark),
        "ghost_hover": _pick(C.COLOR_BTN_GHOST_HOVER, dark),
        "on_accent": C.COLOR_TEXT_ON_ACCENT,
        "online": _pick(C.COLOR_STATUS_ONLINE, dark),
        "offline": _pick(C.COLOR_STATUS_OFFLINE, dark),
        "starting": _pick(C.COLOR_STATUS_STARTING, dark),
        "badge_bg": _pick(C.COLOR_BADGE_NEUTRAL_BG, dark),
        "badge_text": _pick(C.COLOR_BADGE_NEUTRAL_TEXT, dark),
    }


def is_dark(setting: str) -> bool:
    """``theme`` setting ("Dark", "Light", "System") -> dark or not."""
    if setting == "System":
        return QApplication.styleHints().colorScheme() != Qt.ColorScheme.Light
    return setting != "Light"


def stylesheet(t: dict) -> str:
    font, display, mono = C.FONT_FAMILY, C.FONT_FAMILY_DISPLAY, C.FONT_FAMILY_MONO
    return f"""
* {{ font-family: "{font}"; font-size: {C.FONT_BODY[1]}px; color: {t['text']}; }}
QMainWindow, QDialog, QWidget#root {{ background: {t['bg']}; }}
QWidget#sidebar {{ background: {t['sidebar']}; border-right: 1px solid {t['border']}; }}
QFrame#card {{ background: {t['card']}; border: 1px solid {t['border']}; border-radius: 10px; }}
QLabel {{ background: transparent; }}
QLabel#title {{ font-family: "{display}"; font-size: {C.FONT_TITLE[1]}px; font-weight: bold; }}
QLabel#heading {{ font-family: "{display}"; font-size: {C.FONT_HEADING_SMALL[1]}px; font-weight: bold; }}
QLabel#muted {{ color: {t['muted']}; font-size: {C.FONT_CAPTION[1]}px; }}
QLabel#badge {{ background: {t['badge_bg']}; color: {t['badge_text']}; border-radius: 9px;
               padding: 2px 10px; font-family: "{display}"; font-size: {C.FONT_BADGE[1]}px; font-weight: bold; }}
QLabel#status[phase="running"] {{ color: {t['online']}; font-weight: bold; }}
QLabel#status[phase="starting"] {{ color: {t['starting']}; font-weight: bold; }}
QLabel#status[phase="offline"] {{ color: {t['offline']}; font-weight: bold; }}
QPushButton {{ background: {t['ghost']}; border: 1px solid {t['border']}; border-radius: 8px; padding: 6px 14px; }}
QPushButton:hover {{ background: {t['ghost_hover']}; }}
QPushButton:disabled {{ color: {t['muted']}; }}
QPushButton#primary {{ background: {t['primary']}; color: {t['on_accent']}; border: none; font-weight: bold; }}
QPushButton#primary:hover {{ background: {t['primary_hover']}; }}
QPushButton#danger {{ background: {t['danger']}; color: {t['on_accent']}; border: none; font-weight: bold; }}
QPushButton#danger:hover {{ background: {t['danger_hover']}; }}
QPushButton#primary:disabled, QPushButton#danger:disabled {{ background: {t['ghost']}; color: {t['muted']}; }}
QLineEdit {{ background: {t['card']}; border: 1px solid {t['border']}; border-radius: 8px; padding: 6px 8px; }}
QLineEdit:focus {{ border-color: {t['primary']}; }}
QListWidget {{ background: transparent; border: none; outline: 0; }}
QListWidget::item {{ padding: 8px 10px; border-radius: 8px; margin: 1px 6px; }}
QListWidget::item:hover {{ background: {t['ghost_hover']}; }}
QListWidget::item:selected {{ background: {t['primary']}; color: {t['on_accent']}; }}
QListWidget#versions {{ background: {t['card']}; border: 1px solid {t['border']}; border-radius: 8px; }}
QPlainTextEdit#console {{ background: {t['console']}; border: 1px solid {t['border']}; border-radius: 10px;
                          font-family: "{mono}"; font-size: {C.FONT_MONO[1]}px; padding: 6px; }}
QRadioButton, QCheckBox {{ spacing: 8px; background: transparent; }}
QRadioButton::indicator, QCheckBox::indicator {{ width: 14px; height: 14px; border: 2px solid {t['muted']};
                                               background: {t['card']}; }}
QRadioButton::indicator {{ border-radius: 9px; }}
QCheckBox::indicator {{ border-radius: 4px; }}
QRadioButton::indicator:checked, QCheckBox::indicator:checked {{ background: {t['primary']}; border-color: {t['primary']}; }}
QRadioButton::indicator:disabled {{ border-color: {t['border']}; }}
QRadioButton:disabled {{ color: {t['muted']}; }}
QScrollBar:vertical {{ background: transparent; width: 10px; }}
QScrollBar::handle:vertical {{ background: {t['border']}; border-radius: 5px; min-height: 24px; }}
QScrollBar::add-line, QScrollBar::sub-line {{ height: 0; }}
QMenu {{ background: {t['card']}; border: 1px solid {t['border']}; padding: 4px; }}
QMenu::item {{ padding: 6px 18px; border-radius: 6px; }}
QMenu::item:selected {{ background: {t['ghost_hover']}; }}
QToolTip {{ background: {t['card']}; color: {t['text']}; border: 1px solid {t['border']}; }}
"""


def palette(t: dict) -> QPalette:
    p = QPalette()
    roles = {
        QPalette.ColorRole.Window: t["bg"], QPalette.ColorRole.Base: t["card"],
        QPalette.ColorRole.AlternateBase: t["sidebar"], QPalette.ColorRole.Button: t["ghost"],
        QPalette.ColorRole.WindowText: t["text"], QPalette.ColorRole.Text: t["text"],
        QPalette.ColorRole.ButtonText: t["text"], QPalette.ColorRole.Highlight: t["primary"],
        QPalette.ColorRole.HighlightedText: t["on_accent"], QPalette.ColorRole.ToolTipBase: t["card"],
        QPalette.ColorRole.ToolTipText: t["text"], QPalette.ColorRole.PlaceholderText: t["muted"],
    }
    for role, color in roles.items():
        p.setColor(role, QColor(color))
    return p


def apply(app: QApplication, setting: str) -> bool:
    """Theme the whole app; returns whether it is dark."""
    dark = is_dark(setting)
    # Qt 6.8+: also switches the native title bar (DWM dark mode) on Windows.
    app.styleHints().setColorScheme(Qt.ColorScheme.Dark if dark else Qt.ColorScheme.Light)
    app.setStyle("Fusion")
    t = tokens(dark)
    app.setPalette(palette(t))
    app.setFont(QFont(C.FONT_FAMILY, C.FONT_BODY[1]))
    app.setStyleSheet(stylesheet(t))
    return dark
