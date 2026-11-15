# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller 打包設定。

用法（在專案根目錄）：

    pyinstaller packaging/openconvert.spec --noconfirm

產物：``dist/OpenConvert/``（onedir），內含兩個執行檔：

- ``OpenConvert.exe``：圖形介面
- ``OpenConvertCLI.exe``：命令列（與 GUI 共用同一份 Python/Qt/Pillow 函式庫）

FFmpeg 不內嵌，使用者可放到 ``dist/OpenConvert/tools/`` 或使用系統安裝的版本。
"""

from pathlib import Path

from PyInstaller.utils.hooks import collect_dynamic_libs

ROOT = Path(SPECPATH).resolve().parent  # noqa: F821 - SPECPATH 由 PyInstaller 注入

binaries = collect_dynamic_libs("pypdfium2_raw")  # pypdfium2 原生函式庫不會自動收集

EXCLUDES = [
    "tkinter",
    "unittest",
    "PySide6.QtWebEngineCore",
    "PySide6.QtWebEngineWidgets",
    "PySide6.QtQml",
    "PySide6.QtQuick",
    "PySide6.QtQuick3D",
    "PySide6.Qt3DCore",
    "PySide6.QtCharts",
    "PySide6.QtDataVisualization",
    "PySide6.QtMultimedia",
    "PySide6.QtMultimediaWidgets",
    "PySide6.QtBluetooth",
    "PySide6.QtDesigner",
    "PySide6.QtHelp",
    "PySide6.QtPositioning",
    "PySide6.QtSensors",
    "PySide6.QtSerialPort",
    "PySide6.QtSql",
    "PySide6.QtTest",
    "PySide6.QtWebSockets",
]


def analyse(script: str):
    return Analysis(  # noqa: F821
        [str(ROOT / "packaging" / script)],
        pathex=[str(ROOT)],
        binaries=binaries,
        datas=[],
        hiddenimports=["pypdfium2_raw"],
        hookspath=[],
        hooksconfig={},
        runtime_hooks=[],
        excludes=EXCLUDES,
        noarchive=False,
        optimize=0,
    )


a_gui = analyse("entry.py")
pyz_gui = PYZ(a_gui.pure)  # noqa: F821
exe_gui = EXE(  # noqa: F821
    pyz_gui,
    a_gui.scripts,
    [],
    exclude_binaries=True,
    name="OpenConvert",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
    disable_windowed_traceback=False,
)

a_cli = analyse("entry_cli.py")
pyz_cli = PYZ(a_cli.pure)  # noqa: F821
exe_cli = EXE(  # noqa: F821
    pyz_cli,
    a_cli.scripts,
    [],
    exclude_binaries=True,
    name="OpenConvertCLI",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=True,
)

coll = COLLECT(  # noqa: F821
    exe_gui,
    exe_cli,
    a_gui.binaries,
    a_gui.datas,
    a_cli.binaries,
    a_cli.datas,
    strip=False,
    upx=False,
    name="OpenConvert",
)
