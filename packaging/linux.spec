# -*- mode: python ; coding: utf-8 -*-
import os

from PyInstaller.utils.hooks import collect_all

# Relative paths in a spec resolve against the spec's own directory, not the
# working directory. This file lives in packaging/, so anchor to the repo root.
ROOT = os.path.dirname(SPECPATH)

block_cipher = None

ctk_datas, ctk_binaries, ctk_hiddenimports = collect_all('customtkinter')

a = Analysis(
    [os.path.join(ROOT, 'app', 'launcher.py')],
    pathex=[ROOT],
    binaries=ctk_binaries,
    datas=[
        (os.path.join(ROOT, 'assets'), 'assets'),
    ] + ctk_datas,
    hiddenimports=[
        'customtkinter',
        'PIL',
        'PIL._tkinter_finder',
        'psutil',
        'requests',
        'packaging',
        'tkinter',
        'tkinter.ttk',
        'tkinter.messagebox',
        'tkinter.filedialog',
        'app.core',
        'app.services',
        'app.ui',
    ] + ctk_hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name='zeroblockbridge',
    debug=False,
    bootloader_ignore_signals=False,
    strip=True,
    upx=False,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
