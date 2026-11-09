# -*- mode: python ; coding: utf-8 -*-
# Build .exe Windows 11:  pyinstaller DiskGuardPro.spec
block_cipher = None

a = Analysis(
    ['app.py'],
    pathex=[],
    binaries=[],
    datas=[],
    hiddenimports=['wmi', 'win32com', 'customtkinter', 'psutil', 'matplotlib', 'PIL'],
    hookspath=[],
    noarchive=False,
)
pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)
exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    name='DiskGuardPro',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,               # app con finestra (no console)
    uac_admin=True,              # richiede privilegi admin (necessario per SMART/dischi raw)
    icon=None,
    target_arch=None,
)
