"""Build one variant of the visual-ceiling screen (``--variant=widgets|qml``)."""

from __future__ import annotations

from PySide6.QtWidgets import QApplication

from app.ui_qt import theme
from app.ui_qt.dispatcher import QtDispatcher
from app.ui_qt.visual.backend import MainBackend


def create(app: QApplication, variant: str, theme_setting: str, backdrop: bool = True):
    """Returns (window, backend). The window is a QMainWindow (widgets) or a
    QQuickWindow (qml); call show() on it."""
    from app.api import AppApi
    dispatcher = QtDispatcher(app)
    api = AppApi(dispatcher=dispatcher)
    dark = theme.apply(app, theme_setting)
    app.setStyleSheet("")  # each variant styles itself
    backend = MainBackend(api, dispatcher, app)
    if variant == "qml":
        from app.ui_qt.visual.qml_main import create_qml_window
        return create_qml_window(app, backend, dark, backdrop), backend
    from app.ui_qt.visual.widgets_main import WidgetsMainWindow
    return WidgetsMainWindow(backend, dark, backdrop), backend
