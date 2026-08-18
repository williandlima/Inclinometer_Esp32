# -*- mode: python ; coding: utf-8 -*-
# Spec do PyInstaller para gerar um executavel Windows autonomo do
# Inclinometro Avibras Aeroco. Gerar com: windows\build_exe.bat
# (precisa ser executado em uma maquina Windows — o PyInstaller nao
# faz cross-compilacao de Linux/macOS para .exe).

import os

block_cipher = None

project_root = os.path.abspath(os.path.join(os.path.dirname(SPEC), ".."))

a = Analysis(
    [os.path.join(project_root, "main.py")],
    pathex=[project_root],
    binaries=[],
    datas=[
        (os.path.join(project_root, "assets"), "assets"),
    ],
    hiddenimports=[
        "bleak.backends.winrt",
        "pymodbus.client",
    ],
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
    [],
    exclude_binaries=True,
    name="Inclinometro",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
    icon=os.path.join(project_root, "assets", "logo.ico"),
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name="Inclinometro",
)
