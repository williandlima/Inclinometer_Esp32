# -*- mode: python ; coding: utf-8 -*-
# Spec do PyInstaller para gerar um executavel Windows autonomo do
# Inclinometro Avibras Aeroco. Gerar com: windows\build_exe.bat
# (precisa ser executado em uma maquina Windows — o PyInstaller nao
# faz cross-compilacao de Linux/macOS para .exe).

import os
import re

from PyInstaller.utils.win32.versioninfo import (
    FixedFileInfo, StringFileInfo, StringStruct, StringTable, VarFileInfo, VarStruct, VSVersionInfo,
)

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
# Recurso de versao do .exe (Propriedades → Detalhes). Um .exe sem
# fabricante/produto/versao e' um dos sinais que o SmartScreen e os antivirus
# usam para marcar programas PyInstaller como suspeitos.
with open(os.path.join(project_root, "app_version.py"), encoding="utf-8") as fh:
    _ver = re.search(r'APP_VERSION = "([0-9.]+)"', fh.read()).group(1)
_v = tuple(int(x) for x in (_ver.split(".") + ["0", "0", "0"])[:4])
version_info = VSVersionInfo(
    ffi=FixedFileInfo(filevers=_v, prodvers=_v, mask=0x3F, flags=0x0, OS=0x40004, fileType=0x1, subtype=0x0, date=(0, 0)),
    kids=[
        StringFileInfo([StringTable("041604B0", [
            StringStruct("CompanyName", "Avibras Aeroco"),
            StringStruct("FileDescription", "Inclinometro 2 Eixos (pan-tilt meter)"),
            StringStruct("FileVersion", _ver),
            StringStruct("InternalName", "Inclinometro2Eixos"),
            StringStruct("LegalCopyright", "Avibras Aeroco"),
            StringStruct("OriginalFilename", "Inclinometro2Eixos.exe"),
            StringStruct("ProductName", "Inclinometro 2 Eixos (Avibras Aeroco)"),
            StringStruct("ProductVersion", _ver),
        ])]),
        VarFileInfo([VarStruct("Translation", [0x0416, 1200])]),
    ],
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="Inclinometro2Eixos",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    # Sem UPX: .exe comprimido com UPX e' o gatilho mais comum de falso
    # positivo de antivirus/SmartScreen em programas PyInstaller.
    upx=False,
    console=False,
    version=version_info,
    icon=os.path.join(project_root, "assets", "logo.ico"),
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name="Inclinometro2Eixos",
)
