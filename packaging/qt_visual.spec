# -*- mode: python ; coding: utf-8 -*-
# Visual-ceiling spike (docs/QT-SPIKE.md): one-file exe of one variant.
#   set ZBB_QT_VARIANT=qml (or widgets) && pyinstaller packaging/qt_visual.spec
import os

ROOT = os.path.dirname(SPECPATH)
VARIANT = os.environ.get('ZBB_QT_VARIANT', 'qml')
QML = VARIANT == 'qml'

entry = os.path.join(workpath, 'qt_visual_entry.py')
with open(os.path.join(ROOT, 'packaging', 'qt_visual_entry.py'), encoding='utf-8') as src:
    text = src.read().replace('VARIANT = "qml"', f'VARIANT = "{VARIANT}"')
os.makedirs(workpath, exist_ok=True)
with open(entry, 'w', encoding='utf-8') as dst:
    dst.write(text)

# Never loaded by either variant: see qt_spike.spec. For QML, keep only
# QtQml/QtQuick (+ Window, Layouts, Effects, Shapes) and drop every Controls
# style, Dialogs, 3D, Pdf, Particles, Timeline, VirtualKeyboard...
DROP = [
    'opengl32sw.dll', 'Qt6Pdf', 'Qt6VirtualKeyboard', 'PySide6/translations',
    'qtvirtualkeyboard', 'qpdf', 'qnetworklistmanager', 'qtuiotouchplugin', 'qcertonlybackend',
    'qopensslbackend', 'qschannelbackend', 'qwebp', 'qtiff', 'qgif', 'qicns', 'qtga', 'qwbmp',
    'qjpeg', 'qdirect2d', '_avif',
    'Qt6QuickControls2', 'Qt6QuickDialogs2', 'Qt6QuickTemplates2', 'Qt6QuickParticles',
    'Qt6QuickTimeline', 'Qt6QuickVectorImage', 'Qt6QuickTest', 'Qt6QuickWidgets', 'Qt6QuickNativeStyle',
    'Qt6QmlCompiler', 'Qt6QmlDesignSupport', 'Qt6QmlLocalStorage', 'Qt6QmlXmlListModel', 'Qt6QmlNetwork',
    'Qt6QuickShapesDesignHelpers', 'Qt6LabsAnimation', 'Qt6LabsFolderListModel', 'Qt6LabsPlatform',
    'Qt6LabsQmlModels', 'Qt6LabsSettings', 'Qt6LabsSharedImage', 'Qt6LabsWavefrontMesh', 'Qt6LabsSynchronizer',
    'qml/QtQuick/Controls', 'qml/QtQuick/Dialogs', 'qml/QtQuick/Pdf', 'qml/QtQuick/Scene2D',
    'qml/QtQuick/Scene3D', 'qml/QtQuick/Particles', 'qml/QtQuick/Timeline', 'qml/QtQuick/VirtualKeyboard',
    'qml/QtQuick/LocalStorage', 'qml/QtQuick/NativeStyle', 'qml/QtQuick/VectorImage', 'qml/QtQuick/Templates',
    'qml/QtQuick/tooling', 'qml/Qt/labs', 'qml/QtQml/XmlListModel', 'qml/QtCore', 'qml/QtNetwork',
    'qml/QtTest', 'qml/QtWebView', 'qml/QtTextToSpeech', 'qml/QtLocation', 'qml/QtPositioning',
]
if not QML:
    DROP += ['Qt6Qml', 'Qt6Quick', 'PySide6/qml', 'Qt6Network']  # Qt6Qml links Qt6Network

excludes = ['tkinter', '_tkinter', 'customtkinter', 'darkdetect', 'pystray', 'app.ui.main',
            'PySide6.QtPdf', 'PIL.AvifImagePlugin']
if not QML:
    # Importing PySide6.QtQuick loads QtNetwork and QtOpenGL too (checked with
    # sys.modules), so only the Widgets build may leave them out.
    excludes += ['PySide6.QtQml', 'PySide6.QtQuick', 'PySide6.QtNetwork', 'PySide6.QtOpenGL']

a = Analysis(
    [entry],
    pathex=[ROOT],
    datas=[(os.path.join(ROOT, 'assets'), 'assets'),
           (os.path.join(ROOT, 'app', 'ui_qt', 'visual', 'qml'), os.path.join('app', 'ui_qt', 'visual', 'qml'))],
    hiddenimports=['app.launcher', 'app.ui_qt.app', 'app.ui_qt.visual.launch', 'app.ui_qt.visual.qml_main',
                   'app.ui_qt.visual.widgets_main', 'PySide6.QtSvg', 'app.core', 'app.services', 'app.api',
                   'psutil', 'requests', 'packaging'] + (['PySide6.QtQml', 'PySide6.QtQuick'] if QML else []),
    excludes=excludes,
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
    name=f'ZeroBlockBridge-qt-{VARIANT}',
    debug=False, strip=False, upx=False, runtime_tmpdir=None, console=False,
    icon=os.path.join(ROOT, 'assets', 'logo.ico'),
    version=os.path.join(ROOT, 'packaging', 'version_info.txt'),
)
