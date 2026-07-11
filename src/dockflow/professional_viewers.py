from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import shutil

from .config import WorkflowConfig
from .desktop import load_summary


@dataclass(frozen=True)
class ViewerLaunch:
    viewer: str
    executable: Path
    script: Path
    command: tuple[str, ...]


def discover_viewer(name: str, configured: str | None = None) -> Path | None:
    candidates = []
    if configured:
        candidates.append(Path(configured).expanduser())
    if name == "pymol":
        which_names = ("pymol.exe", "pymol")
        candidates.extend([
            Path.home() / "AppData/Local/Schrodinger/PyMOL2/PyMOLWin.exe",
            Path("C:/Program Files/PyMOL/PyMOLWin.exe"),
            Path("C:/Program Files/Schrodinger/PyMOL2/PyMOLWin.exe"),
        ])
    elif name == "chimerax":
        which_names = ("ChimeraX.exe", "chimerax")
        candidates.extend([
            Path("C:/Program Files/ChimeraX/bin/ChimeraX.exe"),
            Path("C:/Program Files/ChimeraX/ChimeraX.exe"),
        ])
    else:
        raise ValueError(f"unknown viewer: {name}")
    for candidate in candidates:
        if candidate.is_file():
            return candidate.resolve()
    for executable in which_names:
        found = shutil.which(executable)
        if found:
            return Path(found).resolve()
    return None


def _result_paths(config_path: Path, target: str, ligand: str) -> tuple[WorkflowConfig, Path, Path, dict[str, str]]:
    config = WorkflowConfig.from_yaml(Path(config_path))
    row = next((item for item in load_summary(config.result_dir / "docking_summary.tsv") if item.get("target") == target and item.get("ligand") == ligand), None)
    if not row:
        raise ValueError(f"结果表中未找到 {target}/{ligand}")
    receptor = config.work_dir / "receptors_clean" / f"{target}.pdb"
    pose = Path(row.get("pose", ""))
    if not pose.is_absolute():
        pose = config.root / pose
    if not receptor.exists():
        raise FileNotFoundError(receptor)
    if not pose.exists():
        raise FileNotFoundError(pose)
    return config, receptor.resolve(), pose.resolve(), row


def build_pymol_launch(config_path: Path, target: str, ligand: str, executable: Path) -> ViewerLaunch:
    config, receptor, pose, row = _result_paths(config_path, target, ligand)
    script = config.result_dir / "viewer" / f"{target}__{ligand}.pml"
    script.parent.mkdir(parents=True, exist_ok=True)
    affinity = row.get("affinity_kcal_mol", "")
    script.write_text(
        "\n".join([
            "reinitialize",
            f'load "{receptor.as_posix()}", receptor',
            f'load "{pose.as_posix()}", ligand',
            "hide everything",
            "show cartoon, receptor",
            "color slate, receptor",
            "show sticks, ligand",
            "color green, ligand",
            "select pocket, byres (receptor within 5 of ligand)",
            "show sticks, pocket",
            "color cyan, pocket",
            "distance polar_contacts, (ligand and (donor or acceptor)), (pocket and (donor or acceptor)), mode=2",
            "set dash_color, yellow",
            "set transparency, 0.35",
            "show surface, receptor",
            "zoom ligand, 12",
            f'set_name ligand, "{ligand}"',
            f'python print("DockFlow affinity: {affinity} kcal/mol")',
        ]) + "\n",
        encoding="utf-8",
    )
    return ViewerLaunch("PyMOL", Path(executable), script, (str(executable), "-r", str(script)))


def build_chimerax_launch(config_path: Path, target: str, ligand: str, executable: Path) -> ViewerLaunch:
    config, receptor, pose, row = _result_paths(config_path, target, ligand)
    script = config.result_dir / "viewer" / f"{target}__{ligand}.cxc"
    script.parent.mkdir(parents=True, exist_ok=True)
    affinity = row.get("affinity_kcal_mol", "")
    script.write_text(
        "\n".join([
            f'open "{receptor.as_posix()}"',
            f'open "{pose.as_posix()}"',
            "hide atoms #1",
            "cartoon #1",
            "color #1 cornflowerblue",
            "style #2 stick",
            "color #2 green",
            "select zone #2 5 #1 residues true",
            "show sel atoms",
            "color sel cyan",
            "hbonds #2 restrict #1 reveal true",
            "view #2 pad 0.35",
            f'log DockFlow affinity: {affinity} kcal/mol',
        ]) + "\n",
        encoding="utf-8",
    )
    return ViewerLaunch("ChimeraX", Path(executable), script, (str(executable), str(script)))
