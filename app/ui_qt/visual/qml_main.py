"""Variant B: the main screen in Qt Quick/QML over the same backend.

Python exposes the backend (properties, signals, slots), the console list
model, the theme tokens as colors, the translated labels (QML has no
gettext, so the strings stay in Python where pybabel extracts them) and
an ``image://icons/<name>/<rrggbb>`` provider for the line icons.
"""

from __future__ import annotations

import logging
from pathlib import Path

from PySide6.QtCore import QSize, QUrl
from PySide6.QtGui import QColor
from PySide6.QtQml import QQmlApplicationEngine
from PySide6.QtQuick import QQuickImageProvider, QQuickWindow

from app.core.i18n import _
from app.ui_qt import theme
from app.ui_qt.visual import backdrop, icons

logger = logging.getLogger(__name__)
QML = Path(__file__).with_name("qml") / "Main.qml"


class IconProvider(QQuickImageProvider):
    def __init__(self):
        super().__init__(QQuickImageProvider.ImageType.Image)

    def requestImage(self, id_: str, size, requested: QSize):  # noqa: N802 - Qt API
        name, _sep, color = id_.partition("/")
        px = max(requested.width(), requested.height(), 16) if requested.isValid() else 32
        img = icons.image(name, "#" + (color or "ffffff"), px)
        if size is not None:
            size.setWidth(px)
            size.setHeight(px)
        return img


def labels() -> dict:
    return {
        "servers": _("Servers"), "newServer": _("New server…"), "console": _("Console"),
        "command": _("Command"), "commandHint": _("Type a command (e.g. say hello)…"),
        "send": _("Send"), "selectServer": _("Select a server"), "noServers": _("No servers yet."),
    }


def create_qml_window(app, backend, dark: bool, use_backdrop: bool = True):
    t = theme.tokens(dark)
    # ClearType-like glyphs, as in the Widgets UI (the default distance-field
    # text looks soft and mis-kerned at body sizes on Windows).
    QQuickWindow.setTextRenderType(QQuickWindow.TextRenderType.NativeTextRendering)
    engine = QQmlApplicationEngine(app)
    engine.addImageProvider("icons", IconProvider())
    ctx = engine.rootContext()
    ctx.setContextProperty("backend", backend)
    ctx.setContextProperty("consoleModel", backend.console)
    ctx.setContextProperty("theme", {k: QColor(v) for k, v in t.items()})
    ctx.setContextProperty("labels", labels())
    ctx.setContextProperty("isDark", dark)
    ctx.setContextProperty("micaOn", False)
    problems: list[str] = []
    engine.warnings.connect(lambda ws: problems.extend(w.toString() for w in ws))
    engine.load(QUrl.fromLocalFile(str(QML)))
    if not engine.rootObjects():
        raise RuntimeError("Main.qml failed to load: " + " | ".join(problems))
    for problem in problems:
        logger.warning("QML: %s", problem)
    window = engine.rootObjects()[0]
    window._engine = engine  # keep the engine alive with the window
    if use_backdrop:
        ok = backdrop.apply(int(window.winId()), dark)
        ctx.setContextProperty("micaOn", ok)
    backend.refresh()
    return window
