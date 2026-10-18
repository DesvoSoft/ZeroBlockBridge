"""Custom title bar for a Qt Widgets top-level window on Windows 11.

The window keeps its native styles (WS_THICKFRAME | WS_CAPTION | min/max
boxes), so Windows still gives it the drop shadow, rounded corners, open/
minimize animations, Aero Snap and edge resizing. Only the non-client area
is removed (WM_NCCALCSIZE) and WM_NCHITTEST says what each point is:

- the caption strip (minus the buttons)  -> HTCAPTION (drag, double-click)
- the window edges                       -> HTLEFT/HTTOP/... (resize)
- the maximize button                    -> HTMAXBUTTON (Windows 11 shows
  its Snap Layouts flyout on hover), so its hover/press/click arrive as
  non-client messages and are handled here
- everything else                        -> HTCLIENT (Qt handles it)

Off Windows nothing is installed and the native frame stays.
"""

from __future__ import annotations

import ctypes
import sys
from ctypes import wintypes

from PySide6.QtCore import QRectF, QSize, Qt
from PySide6.QtGui import QColor, QFont, QPainter
from PySide6.QtWidgets import QAbstractButton, QHBoxLayout, QWidget

WM_NCCALCSIZE, WM_NCHITTEST = 0x0083, 0x0084
WM_NCMOUSEMOVE, WM_NCLBUTTONDOWN, WM_NCLBUTTONUP, WM_NCMOUSELEAVE = 0x00A0, 0x00A1, 0x00A2, 0x02A2
WM_MOUSEMOVE = 0x0200
HTCLIENT, HTCAPTION, HTMAXBUTTON = 1, 2, 9
HTLEFT, HTRIGHT, HTTOP, HTTOPLEFT, HTTOPRIGHT, HTBOTTOM, HTBOTTOMLEFT, HTBOTTOMRIGHT = 10, 11, 12, 13, 14, 15, 16, 17
GWL_STYLE = -16
WS_CAPTION, WS_THICKFRAME, WS_SYSMENU = 0x00C00000, 0x00040000, 0x00080000
WS_MINIMIZEBOX, WS_MAXIMIZEBOX = 0x00020000, 0x00010000
SM_CXFRAME, SM_CYFRAME, SM_CXPADDEDBORDER = 32, 33, 92
SWP_FRAMECHANGED, SWP_NOMOVE, SWP_NOSIZE, SWP_NOZORDER = 0x0020, 0x0002, 0x0001, 0x0004

CAPTION_HEIGHT = 40
BUTTON_SIZE = QSize(46, 40)
EDGE = 6  # resize band, logical px
GLYPHS = {"min": "", "max": "", "restore": "", "close": ""}  # Segoe Fluent Icons


class _NCCALCSIZE_PARAMS(ctypes.Structure):
    _fields_ = [("rgrc", wintypes.RECT * 3), ("lppos", ctypes.c_void_p)]


def supported() -> bool:
    return sys.platform == "win32" and sys.getwindowsversion().build >= 22000


class CaptionButton(QAbstractButton):
    """Windows 11-style caption button: Segoe Fluent Icons glyph, subtle
    hover fill, red fill for close. Hover/press may also be driven from
    non-client messages (the maximize button)."""

    def __init__(self, kind: str, t: dict, parent=None):
        super().__init__(parent)
        self.kind = kind
        self._t = t
        self.nc_hover = False
        self.nc_down = False
        self.setFixedSize(BUTTON_SIZE)
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.setAccessibleName({"min": "Minimize", "max": "Maximize", "close": "Close"}[kind])

    def paintEvent(self, _e) -> None:
        p = QPainter(self)
        hover = self.underMouse() or self.nc_hover
        down = self.isDown() or self.nc_down
        fg = QColor(self._t["text"])
        if self.kind == "close" and (hover or down):
            p.fillRect(self.rect(), QColor("#c42b1c") if not down else QColor("#b0281a"))
            fg = QColor("#ffffff")
        elif hover or down:
            fill = QColor(self._t["text"])
            fill.setAlphaF(0.06 if not down else 0.04)
            p.fillRect(self.rect(), fill)
        if not self.window().isActiveWindow():
            fg.setAlphaF(0.45)
        glyph = self.kind
        if glyph == "max" and self.window().isMaximized():
            glyph = "restore"
        font = QFont("Segoe Fluent Icons")
        font.setPixelSize(10)
        p.setFont(font)
        p.setPen(fg)
        p.drawText(QRectF(self.rect()), Qt.AlignmentFlag.AlignCenter, GLYPHS[glyph])


class CaptionButtons(QWidget):
    def __init__(self, window, t: dict, parent=None):
        super().__init__(parent)
        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)
        self.btn_min = CaptionButton("min", t)
        self.btn_max = CaptionButton("max", t)
        self.btn_close = CaptionButton("close", t)
        self.btn_min.clicked.connect(window.showMinimized)
        self.btn_max.clicked.connect(lambda: toggle_maximized(window))
        self.btn_close.clicked.connect(window.close)
        for b in (self.btn_min, self.btn_max, self.btn_close):
            lay.addWidget(b)


def toggle_maximized(window) -> None:
    window.showNormal() if window.isMaximized() else window.showMaximized()


class FramelessHelper:
    """Installs the frameless behaviour on ``window`` (a QWidget with a
    ``caption_buttons`` attribute set before show) and answers its native
    events through ``handle(message)``."""

    def __init__(self, window):
        self.window = window
        hwnd = int(window.winId())
        self.hwnd = hwnd
        user32 = ctypes.windll.user32
        user32.GetWindowLongPtrW.restype = ctypes.c_ssize_t
        user32.GetWindowLongPtrW.argtypes = [wintypes.HWND, ctypes.c_int]
        user32.SetWindowLongPtrW.restype = ctypes.c_ssize_t
        user32.SetWindowLongPtrW.argtypes = [wintypes.HWND, ctypes.c_int, ctypes.c_ssize_t]
        style = user32.GetWindowLongPtrW(hwnd, GWL_STYLE)
        # No WS_SYSMENU: with it DWM still paints its own caption buttons
        # into the extended (Mica) frame, behind ours.
        style = (style | WS_CAPTION | WS_THICKFRAME | WS_MINIMIZEBOX | WS_MAXIMIZEBOX) & ~WS_SYSMENU
        user32.SetWindowLongPtrW(hwnd, GWL_STYLE, style)
        user32.SetWindowPos(wintypes.HWND(hwnd), None, 0, 0, 0, 0,
                            SWP_FRAMECHANGED | SWP_NOMOVE | SWP_NOSIZE | SWP_NOZORDER)

    # -- helpers ---------------------------------------------------------------
    def _frame_thickness(self) -> tuple[int, int]:
        user32 = ctypes.windll.user32
        dpi = user32.GetDpiForWindow(wintypes.HWND(self.hwnd))
        pad = user32.GetSystemMetricsForDpi(SM_CXPADDEDBORDER, dpi)
        return (user32.GetSystemMetricsForDpi(SM_CXFRAME, dpi) + pad,
                user32.GetSystemMetricsForDpi(SM_CYFRAME, dpi) + pad)

    def _local(self, lparam: int) -> tuple[float, float]:
        """Screen point of a mouse message -> logical window coordinates."""
        x = ctypes.c_short(lparam & 0xFFFF).value
        y = ctypes.c_short((lparam >> 16) & 0xFFFF).value
        rect = wintypes.RECT()
        ctypes.windll.user32.GetWindowRect(wintypes.HWND(self.hwnd), ctypes.byref(rect))
        dpr = self.window.devicePixelRatioF()
        return (x - rect.left) / dpr, (y - rect.top) / dpr

    def _inside(self, widget, lx: float, ly: float) -> bool:
        top_left = widget.mapTo(self.window, widget.rect().topLeft())
        return (top_left.x() <= lx < top_left.x() + widget.width()
                and top_left.y() <= ly < top_left.y() + widget.height())

    def hit_test(self, lx: float, ly: float) -> int:
        w = self.window
        width, height = w.width(), w.height()
        if not w.isMaximized():
            left, right = lx < EDGE, lx >= width - EDGE
            top, bottom = ly < EDGE, ly >= height - EDGE
            if top and left:
                return HTTOPLEFT
            if top and right:
                return HTTOPRIGHT
            if bottom and left:
                return HTBOTTOMLEFT
            if bottom and right:
                return HTBOTTOMRIGHT
            if left:
                return HTLEFT
            if right:
                return HTRIGHT
            if top:
                return HTTOP
            if bottom:
                return HTBOTTOM
        buttons = w.caption_buttons
        if self._inside(buttons.btn_max, lx, ly):
            return HTMAXBUTTON
        if self._inside(buttons.btn_min, lx, ly) or self._inside(buttons.btn_close, lx, ly):
            return HTCLIENT
        if ly < CAPTION_HEIGHT and not self._interactive_at(lx, ly):
            return HTCAPTION
        return HTCLIENT

    def _interactive_at(self, lx: float, ly: float) -> bool:
        for widget in getattr(self.window, "caption_interactive", ()):
            if widget.isVisible() and self._inside(widget, lx, ly):
                return True
        return False

    def _set_max_state(self, hover: bool, down: bool) -> None:
        btn = self.window.caption_buttons.btn_max
        if (btn.nc_hover, btn.nc_down) != (hover, down):
            btn.nc_hover, btn.nc_down = hover, down
            btn.update()

    # -- native events -----------------------------------------------------------
    def handle(self, message) -> tuple[bool, int]:
        msg = wintypes.MSG.from_address(int(message))
        if msg.message == WM_NCCALCSIZE and msg.wParam:
            if self.window.isMaximized():
                # A maximized window overhangs the monitor by its frame;
                # pull the client rect back inside.
                params = _NCCALCSIZE_PARAMS.from_address(msg.lParam)
                fx, fy = self._frame_thickness()
                r = params.rgrc[0]
                r.left += fx
                r.top += fy
                r.right -= fx
                r.bottom -= fy
            return True, 0
        if msg.message == WM_NCHITTEST:
            return True, self.hit_test(*self._local(msg.lParam))
        if msg.message == WM_NCMOUSEMOVE:
            self._set_max_state(msg.wParam == HTMAXBUTTON, self.window.caption_buttons.btn_max.nc_down
                                and msg.wParam == HTMAXBUTTON)
            return False, 0
        if msg.message in (WM_NCMOUSELEAVE, WM_MOUSEMOVE):
            self._set_max_state(False, False)
            return False, 0
        if msg.message == WM_NCLBUTTONDOWN and msg.wParam == HTMAXBUTTON:
            self._set_max_state(True, True)
            return True, 0
        if msg.message == WM_NCLBUTTONUP and msg.wParam == HTMAXBUTTON:
            was_down = self.window.caption_buttons.btn_max.nc_down
            self._set_max_state(False, False)
            if was_down:
                toggle_maximized(self.window)
            return True, 0
        return False, 0
