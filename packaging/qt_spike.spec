# -*- mode: python ; coding: utf-8 -*-
# Roadmap 8c spike: one-file exe of the PySide6 UI (docs/QT-SPIKE.md).
# Build with requirements-qt.txt installed:  pyinstaller packaging/qt_spike.spec
import os

ROOT = os.path.dirname(SPECPATH)

# Qt parts the Widgets UI never loads. opengl32sw.dll alone is ~20 MB (the
# software OpenGL fallback); translations are Qt's own, ZBB uses gettext.
DROP = (
    'opengl32sw.dll', 'Qt6Pdf', 'Qt6Qml', 'Qt6Quick', 'Qt6VirtualKeyboard',
    'Qt6OpenGL', 'Qt6Svg', 'Qt6Network', 'PySide6/translations', 'qdirect2d', '_avif',
    'qtvirtualkeyboard', 'qpdf', 'qsvg', 'qnetworklistmanager', 'qtuiotouchplugin',
    'qcertonlybackend', 'qopensslbackend', 'qschannelbackend', 'qwebp', 'qtiff', 'qgif',
    'qicns', 'qtga', 'qwbmp', 'qjpeg',
)

a = Analysis(
    [os.path.join(ROOT, 'packaging', 'qt_spike_entry.py')],
    pathex=[ROOT],
    datas=[(os.path.join(ROOT, 'assets'), 'assets')],
    hiddenimports=['app.launcher', 'app.ui_qt', 'app.ui_qt.app', 'app.core', 'app.services',
                   'app.api', 'psutil', 'requests', 'packaging'],
    excludes=['tkinter', '_tkinter', 'customtkinter', 'darkdetect', 'pystray', 'app.ui.main',
              'PySide6.QtNetwork', 'PySide6.QtQml', 'PySide6.QtQuick', 'PySide6.QtOpenGL',
              'PySide6.QtSvg', 'PySide6.QtPdf', 'PIL.AvifImagePlugin'],
    noarchive=False,
)


def keep(entry):
    name = entry[0].replace(os.sep, '/')
    return not any(d in name for d in DROP)


a.binaries = [b for b in a.binaries if keep(b)]
a.datas = [d for d in a.datas if keep(d)]

pyz = PYZ(a.pure, a.zipped_data)

exe = EXE(
    pyz, a.scripts, a.binaries, a.zipfiles, a.datas, [],
    name='ZeroBlockBridge-qt-spike',
    debug=False, strip=False, upx=False, runtime_tmpdir=None, console=False,
    icon=os.path.join(ROOT, 'assets', 'logo.ico'),
    version=os.path.join(ROOT, 'packaging', 'version_info.txt'),
)
