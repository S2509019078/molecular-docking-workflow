# -*- mode: python ; coding: utf-8 -*-

from PyInstaller.utils.hooks import collect_all, collect_submodules

all_dockflow = collect_submodules("dockflow")
helper_modules = {
    "dockflow.meeko_ligand_launcher",
    "dockflow.meeko_receptor_launcher",
}
gui_hiddenimports = [name for name in all_dockflow if name not in helper_modules]
cli_hiddenimports = [
    name for name in all_dockflow
    if name not in {"dockflow.gui", "dockflow.gui_launcher", *helper_modules}
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
    excludes=["meeko", "rdkit", "gemmi"],
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
    excludes=["PySide6", "meeko", "rdkit", "gemmi"],
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

meeko_datas, meeko_bins, meeko_hidden = collect_all("meeko")
rdkit_datas, rdkit_bins, rdkit_hidden = collect_all("rdkit")
gemmi_datas, gemmi_bins, gemmi_hidden = collect_all("gemmi")
chem_datas = meeko_datas + rdkit_datas + gemmi_datas
chem_bins = meeko_bins + rdkit_bins + gemmi_bins
chem_hidden = meeko_hidden + rdkit_hidden + gemmi_hidden

ligand_analysis = Analysis(
    ["src/dockflow/meeko_ligand_launcher.py"],
    hiddenimports=chem_hidden,
    binaries=chem_bins,
    datas=chem_datas,
    pathex=["src"],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=["PySide6"],
    noarchive=False,
    optimize=0,
)
ligand_pyz = PYZ(ligand_analysis.pure)
ligand_exe = EXE(
    ligand_pyz,
    ligand_analysis.scripts,
    ligand_analysis.binaries,
    ligand_analysis.datas,
    [],
    name="DockFlow-Meeko-Ligand",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=True,
)

receptor_analysis = Analysis(
    ["src/dockflow/meeko_receptor_launcher.py"],
    hiddenimports=chem_hidden,
    binaries=chem_bins,
    datas=chem_datas,
    pathex=["src"],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=["PySide6"],
    noarchive=False,
    optimize=0,
)
receptor_pyz = PYZ(receptor_analysis.pure)
receptor_exe = EXE(
    receptor_pyz,
    receptor_analysis.scripts,
    receptor_analysis.binaries,
    receptor_analysis.datas,
    [],
    name="DockFlow-Meeko-Receptor",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=True,
)
