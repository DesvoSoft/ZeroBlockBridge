"""Variant A: the main screen in Qt Widgets, polished as far as Widgets go.

Painted buttons with animated hover/press colors, an animated status pill,
a sliding sidebar selection indicator, real drop shadows on the cards, a
fade/slide header transition on server switch, skeleton placeholders while
a server loads, line icons, and a Mica backdrop behind translucent panels.
"""

from __future__ import annotations

from PySide6.QtCore import (
    QEasingCurve, QPointF, QRectF, QSize, Qt, QTimer, QVariantAnimation,
)
from PySide6.QtGui import QColor, QFont, QFontMetrics, QLinearGradient, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import (
    QAbstractButton, QFrame, QGraphicsDropShadowEffect,
    QHBoxLayout, QLabel, QLineEdit, QListWidget, QMainWindow, QPlainTextEdit,
    QVBoxLayout, QWidget,
)

from app.core.app_config import AppConfig as C
from app.core.i18n import _
from app.ui_qt import theme
from app.ui_qt.visual import backdrop, icons, titlebar


def _mix(a: QColor, b: QColor, t: float) -> QColor:
    return QColor.fromRgbF(*(x + (y - x) * t for x, y in zip(a.getRgbF(), b.getRgbF())))


def _alpha(color: str, a: float) -> QColor:
    c = QColor(color)
    c.setAlphaF(a)
    return c


class AnimatedButton(QAbstractButton):
    """Rounded button whose fill animates on hover, press and role change."""

    def __init__(self, text: str, icon_name: str | None, t: dict, role: str = "ghost", parent=None):
        super().__init__(parent)
        self._t, self._role, self._icon = t, role, icon_name
        self.setText(text)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setMinimumHeight(36)
        self._color = self._target()
        self._anim = QVariantAnimation(self, duration=140, easingCurve=QEasingCurve.Type.OutCubic)
        self._anim.valueChanged.connect(self._set_color)

    def _base(self) -> tuple[str, str, str]:
        t = self._t
        return {"primary": (t["primary"], t["primary_hover"], t["on_accent"]),
                "danger": (t["danger"], t["danger_hover"], t["on_accent"]),
                "ghost": (t["ghost"], t["ghost_hover"], t["text"])}[self._role]

    def _target(self) -> QColor:
        base, hover, _fg = self._base()
        if not self.isEnabled():
            return QColor(self._t["ghost"])
        if self.isDown():
            return QColor(hover).darker(110)
        return QColor(hover if self.underMouse() else base)

    def _animate(self) -> None:
        self._anim.stop()
        self._anim.setStartValue(self._color)
        self._anim.setEndValue(self._target())
        self._anim.start()

    def _set_color(self, c) -> None:
        self._color = c
        self.update()

    def set_role(self, role: str) -> None:
        if role != self._role:
            self._role = role
            self._anim.setDuration(260)
            self._animate()
            self._anim.setDuration(140)

    def enterEvent(self, e):
        self._animate()
        super().enterEvent(e)

    def leaveEvent(self, e):
        self._animate()
        super().leaveEvent(e)

    def mousePressEvent(self, e):
        super().mousePressEvent(e)
        self._animate()

    def mouseReleaseEvent(self, e):
        super().mouseReleaseEvent(e)
        self._animate()

    def changeEvent(self, e):
        super().changeEvent(e)
        self._animate()

    def sizeHint(self) -> QSize:
        fm = self.fontMetrics()
        return QSize(fm.horizontalAdvance(self.text()) + (52 if self._icon else 32), 38)

    def paintEvent(self, _e) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        r = QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5)
        path = QPainterPath()
        path.addRoundedRect(r, 9, 9)
        p.fillPath(path, self._color)
        if self._role == "ghost":
            p.setPen(QPen(QColor(self._t["border"]), 1))
            p.drawPath(path)
        if self.hasFocus():
            p.setPen(QPen(QColor(self._t["primary"]), 2))
            p.drawRoundedRect(r.adjusted(1.5, 1.5, -1.5, -1.5), 8, 8)
        fg = QColor(self._base()[2] if self.isEnabled() else self._t["muted"])
        font = QFont(C.FONT_FAMILY_DISPLAY, 10)
        font.setWeight(QFont.Weight.DemiBold)
        p.setFont(font)
        text_w = p.fontMetrics().horizontalAdvance(self.text())
        x = (self.width() - text_w - (24 if self._icon else 0)) / 2
        if self._icon:
            pm = icons.pixmap(self._icon, fg.name(), 16, self.devicePixelRatioF())
            p.drawPixmap(QPointF(x, (self.height() - 16) / 2), pm)
            x += 24
        p.setPen(fg)
        p.drawText(QRectF(x, 0, text_w + 2, self.height()), Qt.AlignmentFlag.AlignVCenter, self.text())


class StatusPill(QWidget):
    """Tinted pill with a dot that pulses while the server starts or runs;
    its color cross-fades between phases."""

    COLORS = {"offline": "offline", "starting": "starting", "running": "online"}

    def __init__(self, t: dict, parent=None):
        super().__init__(parent)
        self._t = t
        self._text = ""
        self._phase = "offline"
        self._color = QColor(t["offline"])
        self._pulse = 0.0
        self.setMinimumHeight(30)
        self._fade = QVariantAnimation(self, duration=300, easingCurve=QEasingCurve.Type.OutCubic)
        self._fade.valueChanged.connect(lambda c: (setattr(self, "_color", c), self.update()))
        self._beat = QVariantAnimation(self, startValue=0.0, endValue=1.0, duration=1600, loopCount=-1)
        self._beat.valueChanged.connect(lambda v: (setattr(self, "_pulse", v), self.update()))

    def set_state(self, phase: str, text: str) -> None:
        if phase != self._phase:
            self._phase = phase
            self._fade.stop()
            self._fade.setStartValue(self._color)
            self._fade.setEndValue(QColor(self._t[self.COLORS[phase]]))
            self._fade.start()
            if phase == "offline":
                self._beat.stop()
                self._pulse = 0.0
            else:
                self._beat.start()
        if text != self._text:
            self._text = text
            self.setAccessibleName(text)
            self.updateGeometry()
            self.update()

    def sizeHint(self) -> QSize:
        return QSize(self.fontMetrics().horizontalAdvance(self._text) + 50, 30)

    def paintEvent(self, _e) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        r = QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(_alpha(self._color.name(), 0.16))
        p.drawRoundedRect(r, r.height() / 2, r.height() / 2)
        c = QPointF(17, r.center().y())
        if self._pulse:
            p.setBrush(_alpha(self._color.name(), 0.45 * (1 - self._pulse)))
            p.drawEllipse(c, 4 + 7 * self._pulse, 4 + 7 * self._pulse)
        p.setBrush(self._color)
        p.drawEllipse(c, 4, 4)
        font = QFont(C.FONT_FAMILY_DISPLAY, 10)
        font.setWeight(QFont.Weight.DemiBold)
        p.setFont(font)
        p.setPen(self._color if self._phase != "offline" else QColor(self._t["muted"]))
        p.drawText(r.adjusted(30, 0, -10, 0), Qt.AlignmentFlag.AlignVCenter, self._text)


class Chip(QWidget):
    """Rounded badge (painted: QSS radius is lost inside a shadowed card)."""

    def __init__(self, t: dict, parent=None):
        super().__init__(parent)
        self._t = t
        self._text = ""

    def setText(self, text: str) -> None:  # noqa: N802 - QLabel-like
        self._text = text
        self.setAccessibleName(text)
        self.updateGeometry()
        self.update()

    def text(self) -> str:
        return self._text

    def sizeHint(self) -> QSize:
        return QSize(QFontMetrics(_chip_font()).horizontalAdvance(self._text) + 26, 28)

    def paintEvent(self, _e) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        r = QRectF(self.rect()).adjusted(0.5, 1.5, -0.5, -1.5)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor(self._t["badge_bg"]))
        p.drawRoundedRect(r, r.height() / 2, r.height() / 2)
        p.setFont(_chip_font())
        p.setPen(QColor(self._t["badge_text"]))
        p.drawText(r, Qt.AlignmentFlag.AlignCenter, self._text)


def _chip_font() -> QFont:
    font = QFont(C.FONT_FAMILY_DISPLAY, 9)
    font.setWeight(QFont.Weight.DemiBold)
    return font


class Skeleton(QWidget):
    """Shimmering placeholder bar shown while data loads."""

    def __init__(self, t: dict, width: int, height: int = 12, parent=None):
        super().__init__(parent)
        self._t = t
        self.setFixedSize(width, height)
        self._x = 0.0
        self._anim = QVariantAnimation(self, startValue=-0.5, endValue=1.5, duration=1100, loopCount=-1)
        self._anim.valueChanged.connect(lambda v: (setattr(self, "_x", v), self.update()))

    def showEvent(self, e):
        self._anim.start()
        super().showEvent(e)

    def hideEvent(self, e):
        self._anim.stop()
        super().hideEvent(e)

    def paintEvent(self, _e) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        base = QColor(self._t["ghost_hover"])
        g = QLinearGradient(0, 0, self.width(), 0)
        hi = base.lighter(125) if QColor(self._t["bg"]).lightness() < 128 else base.darker(108)
        for stop, color in ((self._x - 0.3, base), (self._x, hi), (self._x + 0.3, base)):
            g.setColorAt(min(max(stop, 0.0), 1.0), color)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(g)
        p.drawRoundedRect(QRectF(self.rect()), self.height() / 2, self.height() / 2)


class ServerList(QListWidget):
    """QListWidget (keeps keyboard and accessibility) with a painted
    selection indicator that slides to the selected row."""

    def __init__(self, t: dict, parent=None):
        super().__init__(parent)
        self._t = t
        self._ind = QRectF()
        self.setObjectName("servers")
        self.setIconSize(QSize(18, 18))
        self.setSpacing(2)
        self._anim = QVariantAnimation(self, duration=240, easingCurve=QEasingCurve.Type.OutCubic)
        self._anim.valueChanged.connect(self._move)
        self.currentRowChanged.connect(self._slide)

    def _move(self, r) -> None:
        self._ind = r
        self.viewport().update()

    def _slide(self, row: int) -> None:
        item = self.item(row)
        if item is None:
            return
        target = QRectF(self.visualItemRect(item)).adjusted(4, 1, -4, -1)
        if self._ind.isNull():
            self._move(target)
            return
        self._anim.stop()
        self._anim.setStartValue(self._ind)
        self._anim.setEndValue(target)
        self._anim.start()

    def resizeEvent(self, e):
        super().resizeEvent(e)
        self._ind = QRectF()
        self._slide(self.currentRow())

    def paintEvent(self, e) -> None:
        if not self._ind.isNull():
            p = QPainter(self.viewport())
            p.setRenderHint(QPainter.RenderHint.Antialiasing)
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(_alpha(self._t["primary"], 0.22))
            p.drawRoundedRect(self._ind, 9, 9)
            p.setBrush(QColor(self._t["primary"]))
            p.drawRoundedRect(QRectF(self._ind.left(), self._ind.top() + 9, 3, self._ind.height() - 18), 1.5, 1.5)
            p.end()
        super().paintEvent(e)


SHADOWS = True  # the visual bench turns them off to measure their cost


def _card(t: dict, dark: bool) -> QFrame:
    card = QFrame(objectName="vcard")
    if not SHADOWS:
        return card
    shadow = QGraphicsDropShadowEffect(card, blurRadius=28, offset=QPointF(0, 6))
    shadow.setColor(QColor(0, 0, 0, 110 if dark else 40))
    card.setGraphicsEffect(shadow)
    return card


def stylesheet(t: dict, dark: bool, mica: bool) -> str:
    a_main = 0.72 if mica else 1.0
    a_side = 0.38 if mica else 1.0
    bg = _alpha(t["bg"], a_main).name(QColor.NameFormat.HexArgb)
    side = _alpha(t["sidebar"], a_side).name(QColor.NameFormat.HexArgb)
    card = _alpha(t["card"], 0.92 if mica else 1.0).name(QColor.NameFormat.HexArgb)
    return f"""
* {{ font-family: "{C.FONT_FAMILY}"; font-size: 13px; color: {t['text']}; }}
QWidget#vroot {{ background: {bg}; }}
QWidget#vside {{ background: {side}; border-right: 1px solid {_alpha(t['border'], 0.6).name(QColor.NameFormat.HexArgb)}; }}
QFrame#vcard {{ background: {card}; border: 1px solid {_alpha(t['border'], 0.7).name(QColor.NameFormat.HexArgb)};
               border-radius: 14px; }}
QLabel {{ background: transparent; }}
QLabel#brand {{ font-family: "{C.FONT_FAMILY_DISPLAY}"; font-size: 16px; font-weight: 700; }}
QLabel#title {{ font-family: "{C.FONT_FAMILY_DISPLAY}"; font-size: 22px; font-weight: 700; }}
QLabel#muted {{ color: {t['muted']}; font-size: 12px; }}
QLabel#section {{ color: {t['muted']}; font-size: 11px; font-weight: 600; letter-spacing: 0.6px; }}
QLabel#chip {{ background: {t['badge_bg']}; color: {t['badge_text']}; border-radius: 13px; padding: 4px 12px;
              font-family: "{C.FONT_FAMILY_DISPLAY}"; font-size: 12px; font-weight: 600; }}
QListWidget#servers {{ background: transparent; border: none; outline: 0; }}
QListWidget#servers::item {{ padding: 9px 10px; border-radius: 9px; margin: 0 4px; }}
QListWidget#servers::item:hover {{ background: {_alpha(t['ghost_hover'], 0.6).name(QColor.NameFormat.HexArgb)}; }}
QListWidget#servers::item:selected {{ background: transparent; color: {t['text']}; font-weight: 600; }}
QPlainTextEdit#vconsole {{ background: transparent; border: none; font-family: "{C.FONT_FAMILY_MONO}";
                          font-size: 12px; selection-background-color: {t['primary']}; }}
QLineEdit#vcmd {{ background: {card}; border: 1px solid {t['border']}; border-radius: 10px; padding: 8px 10px;
                 font-size: 13px; }}
QLineEdit#vcmd:focus {{ border: 2px solid {t['primary']}; padding: 7px 9px; }}
QScrollBar:vertical {{ background: transparent; width: 8px; margin: 4px; }}
QScrollBar::handle:vertical {{ background: {_alpha(t['muted'], 0.4).name(QColor.NameFormat.HexArgb)};
                               border-radius: 4px; min-height: 30px; }}
QScrollBar::add-line, QScrollBar::sub-line, QScrollBar::add-page, QScrollBar::sub-page {{ height: 0; background: none; }}
"""


class WidgetsMainWindow(QMainWindow):
    def __init__(self, backend, dark: bool, use_backdrop: bool = True, custom_titlebar: bool = True):
        super().__init__()
        self.backend = backend
        self.dark = dark
        self.t = t = theme.tokens(dark)
        self.setWindowTitle("ZeroBlockBridge")
        self.resize(1180, 760)
        self.mica = False
        self._frameless = None
        self.caption_buttons = None
        self.caption_interactive: list = []
        if custom_titlebar and titlebar.supported():
            # Qt must see no frame (so its geometry matches the client area);
            # FramelessHelper puts the native styles back for snap/resize.
            self.setWindowFlag(Qt.WindowType.FramelessWindowHint)
            self._frameless = titlebar.FramelessHelper(self)
            # Mica + a removed caption: DWM leaves the old caption band
            # (~26 px) without Mica, a visible seam that no DWM setting
            # tried here removed. The custom title bar uses opaque theme
            # backgrounds instead (docs/QT-SPIKE.md, Visual ceiling).
            use_backdrop = False
            backdrop.set_dark_frame(int(self.winId()), dark)
        if use_backdrop:
            self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
            self.mica = backdrop.apply(int(self.winId()), dark)
            if not self.mica:
                self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, False)
        self.setStyleSheet(stylesheet(t, dark, self.mica))
        self._build()
        backend.serversChanged.connect(self._render_servers)
        backend.selectedChanged.connect(self._on_selected)
        backend.changed.connect(self._render_header)
        backend.loadingChanged.connect(self._render_loading)
        backend.linesAppended.connect(self._append_lines)
        backend.refresh()

    # -- layout --------------------------------------------------------------
    def _build(self) -> None:
        t = self.t
        root = QWidget(objectName="vroot")
        self.setCentralWidget(root)
        outer = QHBoxLayout(root)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        side = QWidget(objectName="vside")
        side.setFixedWidth(250)
        sl = QVBoxLayout(side)
        sl.setContentsMargins(12, 10 if self._frameless else 18, 12, 14)
        sl.setSpacing(10)
        brand_row = QHBoxLayout()
        logo = QLabel()
        logo.setPixmap(icons.pixmap("layers", t["primary"], 22, self.devicePixelRatioF()))
        brand_row.addWidget(logo)
        brand_row.addWidget(QLabel("ZeroBlockBridge", objectName="brand"), 1)
        sl.addLayout(brand_row)
        sl.addSpacing(6)
        sl.addWidget(QLabel(_("Servers").upper(), objectName="section"))
        self.server_list = ServerList(t)
        self.server_list.setAccessibleName(_("Servers"))
        self.server_list.currentTextChanged.connect(self.backend.select)
        sl.addWidget(self.server_list, 1)
        self.btn_new = AnimatedButton(_("New server…"), "plus", t, "primary")
        sl.addWidget(self.btn_new)

        main = QWidget()
        ml = QVBoxLayout(main)
        ml.setContentsMargins(22, 0 if self._frameless else 20, 22, 18)
        ml.setSpacing(16)
        if self._frameless:
            # The caption strip: draggable empty space plus the window buttons
            # in the corner (the sidebar runs up to the top edge).
            caption = QHBoxLayout()
            caption.setContentsMargins(0, 0, -22, 0)
            caption.addStretch(1)
            self.caption_buttons = titlebar.CaptionButtons(self, t)
            caption.addWidget(self.caption_buttons, 0, Qt.AlignmentFlag.AlignTop)
            ml.addLayout(caption)
            ml.addSpacing(-8)

        self.header = _card(t, self.dark)
        hl = QHBoxLayout(self.header)
        hl.setContentsMargins(22, 18, 18, 18)
        self.header_body = QWidget()
        tl = QVBoxLayout(self.header_body)
        tl.setContentsMargins(0, 0, 0, 0)
        tl.setSpacing(4)
        self.lbl_name = QLabel(_("Select a server"), objectName="title")
        self.lbl_engine = QLabel("", objectName="muted")
        self.sk_engine = Skeleton(t, 120)
        self.sk_engine.hide()
        tl.addWidget(self.lbl_name)
        row = QHBoxLayout()
        row.setContentsMargins(0, 0, 0, 0)
        row.addWidget(self.lbl_engine)
        row.addWidget(self.sk_engine)
        row.addStretch(1)
        tl.addLayout(row)
        hl.addWidget(self.header_body, 1)
        self.pill = StatusPill(t)
        self.chip_ram = Chip(t)
        self.chip_players = Chip(t)
        for w in (self.pill, self.chip_ram, self.chip_players):
            hl.addWidget(w, 0, Qt.AlignmentFlag.AlignVCenter)
        hl.addSpacing(6)
        self.btn_start = AnimatedButton(_("Start"), "play", t, "primary")
        self.btn_start.setMinimumWidth(124)
        self.btn_start.clicked.connect(self.backend.startStop)
        hl.addWidget(self.btn_start, 0, Qt.AlignmentFlag.AlignVCenter)
        ml.addWidget(self.header)

        console_card = _card(t, self.dark)
        cl = QVBoxLayout(console_card)
        cl.setContentsMargins(16, 12, 8, 12)
        head = QHBoxLayout()
        ic = QLabel()
        ic.setPixmap(icons.pixmap("terminal", t["muted"], 16, self.devicePixelRatioF()))
        head.addWidget(ic)
        head.addWidget(QLabel(_("Console").upper(), objectName="section"), 1)
        cl.addLayout(head)
        self.console = QPlainTextEdit(objectName="vconsole", readOnly=True)
        self.console.setMaximumBlockCount(1000)
        self.console.setAccessibleName(_("Console"))
        cl.addWidget(self.console, 1)
        self.sk_console = QWidget()
        sk = QVBoxLayout(self.sk_console)
        for w in (420, 360, 480, 300):
            sk.addWidget(Skeleton(t, w, 10))
        sk.addStretch(1)
        self.sk_console.hide()
        cl.addWidget(self.sk_console, 1)
        ml.addWidget(console_card, 1)

        bar = QHBoxLayout()
        self.cmd = QLineEdit(objectName="vcmd", placeholderText=_("Type a command (e.g. say hello)…"))
        self.cmd.addAction(icons.icon("terminal", t["muted"], 16, self.devicePixelRatioF()),
                           QLineEdit.ActionPosition.LeadingPosition)
        self.cmd.setAccessibleName(_("Command"))
        self.cmd.returnPressed.connect(self._send)
        self.btn_send = AnimatedButton(_("Send"), "arrow", t, "ghost")
        self.btn_send.clicked.connect(self._send)
        bar.addWidget(self.cmd, 1)
        bar.addWidget(self.btn_send)
        ml.addLayout(bar)

        outer.addWidget(side)
        outer.addWidget(main, 1)
        self._fade = QVariantAnimation(self, startValue=0.0, endValue=1.0, duration=260,
                                       easingCurve=QEasingCurve.Type.OutCubic)
        self._fade.valueChanged.connect(self._fade_step)
        self._render_header()

    # -- native frame ----------------------------------------------------------
    def nativeEvent(self, event_type, message):  # noqa: N802 - Qt API
        if getattr(self, "_frameless", None) is not None and event_type == b"windows_generic_MSG":
            handled, result = self._frameless.handle(message)
            if handled:
                return True, result
        return super().nativeEvent(event_type, message)

    def changeEvent(self, e) -> None:
        super().changeEvent(e)
        buttons = getattr(self, "caption_buttons", None)  # also called during __init__
        if buttons is not None:  # active/inactive tint, max/restore glyph
            for b in (buttons.btn_min, buttons.btn_max, buttons.btn_close):
                b.update()

    # -- rendering -----------------------------------------------------------
    def _render_servers(self) -> None:
        self.server_list.clear()
        for name in self.backend.servers:
            self.server_list.addItem(name)
            self.server_list.item(self.server_list.count() - 1).setIcon(
                icons.icon("package", self.t["muted"], 18, self.devicePixelRatioF()))
        self._on_selected()

    def _on_selected(self) -> None:
        name = self.backend.selected
        items = self.server_list.findItems(name, Qt.MatchFlag.MatchExactly) if name else []
        if items and self.server_list.currentItem() is not items[0]:
            self.server_list.setCurrentItem(items[0])
        self.lbl_name.setText(name or _("Select a server"))
        self._fade.stop()
        self._fade.start()

    def _fade_step(self, v) -> None:
        # A QGraphicsOpacityEffect can't be nested inside the card's shadow
        # effect (Qt renders the child at a wrong offset), so the transition
        # fades the text colors and slides the block instead.
        for label, key in ((self.lbl_name, "text"), (self.lbl_engine, "muted")):
            label.setStyleSheet(f"color: {_alpha(self.t[key], v).name(QColor.NameFormat.HexArgb)};")
        self.header_body.setContentsMargins(0, int(10 * (1 - v)), 0, 0)

    def _render_loading(self) -> None:
        loading = self.backend.loading
        self.sk_engine.setVisible(loading)
        self.lbl_engine.setVisible(not loading)
        if loading:
            self.console.hide()
            self.sk_console.show()
        else:
            QTimer.singleShot(180, lambda: (self.sk_console.hide(), self.console.show()))

    def _render_header(self) -> None:
        b = self.backend
        self.lbl_engine.setText(b.engineText)
        self.pill.set_state(b.phase, b.statusText)
        self.chip_ram.setText(b.ramText)
        self.chip_ram.setVisible(bool(b.ramText))
        self.chip_players.setText(b.playersText)
        self.chip_players.setVisible(bool(b.playersText))
        running = b.phase != "offline"
        self.btn_start.setText(b.startLabel)
        self.btn_start._icon = "stop" if running else "play"
        self.btn_start.set_role("danger" if running else "primary")
        self.btn_start.setEnabled(b.canStart)
        self.cmd.setEnabled(running)
        self.btn_send.setEnabled(running)

    def _append_lines(self, lines: list) -> None:
        bar = self.console.verticalScrollBar()
        follow = bar.value() >= bar.maximum() - 4
        self.console.appendPlainText("\n".join(lines[-1000:]))
        if follow:
            bar.setValue(bar.maximum())

    def _send(self) -> None:
        if self.backend.sendCommand(self.cmd.text()):
            self.cmd.clear()
