from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import csv
import shutil
import sys

from .tooling import TOOL_SPECS, discover_tools
from .wizard import create_run_directory, detect_hetero_residues, safe_name, write_project


@dataclass(frozen=True)
class StructureInspection:
    pdb_path: Path
    chains: tuple[str, ...]
    ligands: tuple[dict, ...]


def inspect_structure(pdb_path: Path) -> StructureInspection:
    path = Path(pdb_path)
    if not path.is_file():
        raise FileNotFoundError(path)
    chains = sorted({
        line[21:22].strip()
        for line in path.read_text(errors="replace").splitlines()
        if line.startswith("ATOM") and line[21:22].strip()
    })
    ligands = tuple(item for item in detect_hetero_residues(path) if item["likely_ligand"])
    return StructureInspection(path.resolve(), tuple(chains), ligands)


def default_tools() -> dict[str, str]:
    resolved = discover_tools()
    return {
        spec.key: str(resolved.get(spec.key) or spec.candidates[0])
        for spec in TOOL_SPECS
    }


def create_gui_project(
    *,
    base_dir: Path,
    project_name: str,
    pdb_path: Path,
    receptor_chains: tuple[str, ...],
    selected_ligand: dict | None,
    ligand_files: list[Path],
    tools: dict[str, str],
    settings: dict,
) -> Path:
    if not project_name.strip():
        raise ValueError("项目名称不能为空")
    if not Path(pdb_path).is_file():
        raise FileNotFoundError(pdb_path)
    if not ligand_files:
        raise ValueError("至少添加一个待对接配体文件")

    run_dir = create_run_directory(Path(base_dir), project_name)
    structure_dest = run_dir / "inputs" / "structures" / f"{safe_name(project_name)}.pdb"
    shutil.copy2(pdb_path, structure_dest)

    seen_names = set()
    for source in ligand_files:
        source = Path(source)
        if not source.is_file():
            raise FileNotFoundError(source)
        destination = run_dir / "inputs" / "ligands" / source.name
        if destination.name.lower() in seen_names:
            raise ValueError(f"配体文件名重复: {source.name}")
        seen_names.add(destination.name.lower())
        shutil.copy2(source, destination)

    target_row = {
        "name": safe_name(project_name),
        "structure_source": "local",
        "structure": str(structure_dest.relative_to(run_dir)),
        "pocket_strategy": "co_crystal" if selected_ligand else "blind",
        "receptor_chains": ",".join(receptor_chains),
        "ligand": selected_ligand["resname"] if selected_ligand else "",
        "ligand_chain": selected_ligand["chain"] if selected_ligand else "",
        "ligand_residue_id": selected_ligand["residue_id"] if selected_ligand else "",
    }
    return write_project(run_dir, target_row, tools=tools, settings=settings)


def load_summary(path: Path) -> list[dict[str, str]]:
    path = Path(path)
    if not path.exists():
        return []
    with path.open(encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle, delimiter="\t"))


def recent_configs(base_dir: Path, limit: int = 12) -> list[Path]:
    base = Path(base_dir)
    if not base.exists():
        return []
    configs = [path for path in base.glob("*/config/config.yaml") if path.is_file()]
    return sorted(configs, key=lambda path: path.stat().st_mtime, reverse=True)[:limit]


def cli_program_and_prefix() -> tuple[str, list[str]]:
    if getattr(sys, "frozen", False):
        sibling = Path(sys.executable).with_name("DockFlow-CLI.exe")
        if sibling.exists():
            return str(sibling), []
        return str(sys.executable), []
    return sys.executable, ["-m", "dockflow.cli"]
