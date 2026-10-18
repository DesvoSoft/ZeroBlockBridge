"""Line icons in the website's style (24x24, 2px stroke, round caps and
joins), rendered with QtSvg at the device pixel ratio so they stay crisp
at any scaling."""

from __future__ import annotations

from functools import lru_cache

from PySide6.QtCore import QByteArray, QRectF, QSize, Qt
from PySide6.QtGui import QIcon, QImage, QPainter, QPixmap
from PySide6.QtSvg import QSvgRenderer

PATHS = {
    # From the site (origin/site index.html symbols).
    "layers": '<path d="M12 3 2 8l10 5 10-5-10-5z"/><path d="m2 13 10 5 10-5"/>',
    "globe": '<circle cx="12" cy="12" r="9"/><path d="M3 12h18M12 3a14 14 0 0 1 0 18M12 3a14 14 0 0 0 0 18"/>',
    "pulse": '<path d="M3 12h4l2-6 4 12 2-6h6"/>',
    "package": '<path d="M21 8 12 3 3 8v8l9 5 9-5V8z"/><path d="m3 8 9 5 9-5M12 13v8"/>',
    "users": '<circle cx="9" cy="8" r="3.5"/><path d="M2.5 20a6.5 6.5 0 0 1 13 0"/>'
             '<path d="M16 4.5a3.5 3.5 0 0 1 0 7M18 14a6 6 0 0 1 3.5 6"/>',
    "grid": '<rect x="3" y="3" width="7" height="7" rx="1"/><rect x="14" y="3" width="7" height="7" rx="1"/>'
            '<rect x="3" y="14" width="7" height="7" rx="1"/><path d="M14 17.5h7M17.5 14v7"/>',
    "arrow": '<path d="M5 12h14M13 6l6 6-6 6"/>',
    # Same grammar, for the app.
    "play": '<path d="M7 4.5v15l12-7.5z"/>',
    "stop": '<rect x="6" y="6" width="12" height="12" rx="2"/>',
    "plus": '<path d="M12 5v14M5 12h14"/>',
    "terminal": '<path d="m5 8 4 4-4 4M12 16h7"/>',
    "cpu": '<rect x="6" y="6" width="12" height="12" rx="2"/>'
           '<path d="M9 2v4M15 2v4M9 18v4M15 18v4M2 9h4M2 15h4M18 9h4M18 15h4"/>',
}


def svg(name: str, color: str) -> bytes:
    return (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="{color}" '
            f'stroke-width="2" stroke-linecap="round" stroke-linejoin="round">{PATHS[name]}</svg>').encode()


def image(name: str, color: str, size: int) -> QImage:
    img = QImage(size, size, QImage.Format.Format_ARGB32_Premultiplied)
    img.fill(Qt.GlobalColor.transparent)
    painter = QPainter(img)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    QSvgRenderer(QByteArray(svg(name, color))).render(painter, QRectF(0, 0, size, size))
    painter.end()
    return img


@lru_cache(maxsize=256)
def pixmap(name: str, color: str, size: int, dpr: float = 1.0) -> QPixmap:
    pm = QPixmap.fromImage(image(name, color, round(size * dpr)))
    pm.setDevicePixelRatio(dpr)
    return pm


def icon(name: str, color: str, size: int = 18, dpr: float = 1.0) -> QIcon:
    ic = QIcon()
    ic.addPixmap(pixmap(name, color, size, dpr))
    return ic


def qsize(size: int) -> QSize:
    return QSize(size, size)
