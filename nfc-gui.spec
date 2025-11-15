# -*- mode: python ; coding: utf-8 -*-


a = Analysis(
    ['build/run_nfc_gui.py'],
    pathex=[],
    binaries=[],
    datas=[('nfc_gui', 'nfc_gui')],
    hiddenimports=['PyQt5.QtWidgets', 'PyQt5.QtCore', 'PyQt5.QtGui', 'smartcard', 'smartcard.System', 'smartcard.CardMonitoring', 'smartcard.CardConnection', 'pyperclip', 'ndef', 'ndef.uri', 'ndef.record'],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name='nfc-gui',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
