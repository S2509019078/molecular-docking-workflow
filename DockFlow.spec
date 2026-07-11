# -*- mode: python ; coding: utf-8 -*-

from PyInstaller.utils.hooks import collect_submodules

all_dockflow = collect_submodules("dockflow")
gui_hiddenimports = [name for name in all_dockflow if not name.startswith("dockflow.meeko_")]
cli_hiddenimports = [
    name for name in all_dockflow
    if name not in {"dockflow.gui", "dockflow.gui_launcher"}
    and not name.startswith("dockflow.meeko_")
]

common = dict(
    pathex=["src"],
    binaries=[],
    datas=[],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    noarchive=False,
    optimize=0,
)

gui_analysis = Analysis(
    ["src/dockflow/gui_launcher.py"],
    hiddenimports=gui_hiddenimports,
    **common,
)
gui_pyz = PYZ(gui_analysis.pure)
gui_exe = EXE(
    gui_pyz,
    gui_analysis.scripts,
    gui_analysis.binaries,
    gui_analysis.datas,
    [],
    name="DockFlow",
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

cli_analysis = Analysis(
    ["src/dockflow/windows_launcher.py"],
    hiddenimports=cli_hiddenimports,
    excludes=["PySide6"],
    **common,
)
cli_pyz = PYZ(cli_analysis.pure)
cli_exe = EXE(
    cli_pyz,
    cli_analysis.scripts,
    cli_analysis.binaries,
    cli_analysis.datas,
    [],
    name="DockFlow-CLI",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=True,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
