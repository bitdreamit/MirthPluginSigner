# -*- mode: python ; coding: utf-8 -*-
# PyInstaller spec file for MirthPluginSigner
# 
# Build on Windows:
#   pip install pyinstaller
#   pyinstaller MirthPluginSigner.spec
#
# Build on Linux/macOS:
#   pip install pyinstaller
#   pyinstaller MirthPluginSigner.spec

import sys
block_cipher = None

a = Analysis(
    ['mirth_plugin_signer.py'],
    pathex=[],
    binaries=[],
    datas=[],
    hiddenimports=['tkinter', 'tkinter.ttk', 'tkinter.scrolledtext',
                   'tkinter.messagebox', 'tkinter.filedialog'],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=['numpy', 'pandas', 'matplotlib', 'PIL', 'cv2'],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
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
    name='MirthPluginSigner',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,          # no black CMD window on Windows
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    # icon='icon.ico',      # uncomment + add icon.ico for custom icon
)
