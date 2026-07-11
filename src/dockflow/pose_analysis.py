from __future__ import annotations

from pathlib import Path

from .commands import require_tool, run_command
from .config import WorkflowConfig, load_targets
from .poses import PoseRecord, load_pose_index, split_vina_poses, write_pose_index
from .preparation import discover_ligands
from .state import outputs_are_complete


def index_project_poses(config_path: Path) -> list[PoseRecord]:
    config = WorkflowConfig.from_yaml(Path(config_path))
    targets = load_targets(config.target_table)
    ligands = discover_ligands(config.ligand_dir)
    records: list[PoseRecord] = []
    for target in targets:
        for ligand in (target.ligands or tuple(ligands)):
            source = config.work_dir / "poses" / target.name / f"{ligand}.pdbqt"
            if not source.exists():
                continue
            output_dir = config.result_dir / "poses" / target.name / ligand
            records.extend(split_vina_poses(source, output_dir, target.name, ligand))
    write_pose_index(records, config.result_dir / "docking_poses.tsv", root=config.root)
    return records


def project_pose_records(config_path: Path, target: str = "", ligand: str = "") -> list[PoseRecord]:
    config = WorkflowConfig.from_yaml(Path(config_path))
    index = config.result_dir / "docking_poses.tsv"
    records = load_pose_index(index, root=config.root)
    if not records:
        records = index_project_poses(config_path)
    return [
        record for record in records
        if (not target or record.target == target) and (not ligand or record.ligand == ligand)
    ]


def _make_complex(receptor_pdb: Path, ligand_pdb: Path, output: Path) -> None:
    receptor_lines = [
        line for line in receptor_pdb.read_text(errors="replace").splitlines()
        if line[:6].strip() in {"ATOM", "HETATM"}
    ]
    ligand_lines = []
    serial = len(receptor_lines) + 1
    for line in ligand_pdb.read_text(errors="replace").splitlines():
        if line.startswith("ENDMDL"):
            break
        if line[:6].strip() in {"ATOM", "HETATM"}:
            element = line[76:78] if len(line) >= 78 else "  "
            ligand_lines.append(f"HETATM{serial:5d}" + line[11:17] + "LIG Z   1" + line[26:76] + element)
            serial += 1
    if not ligand_lines:
        raise ValueError(f"converted ligand contains no atoms: {ligand_pdb}")
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text("\n".join(receptor_lines + ["TER"] + ligand_lines) + "\nEND\n", encoding="utf-8")


def run_plip_for_pose(config_path: Path, target: str, ligand: str, pose_rank: int, force: bool = False) -> Path:
    config = WorkflowConfig.from_yaml(Path(config_path))
    matches = [record for record in project_pose_records(config_path, target, ligand) if record.rank == int(pose_rank)]
    if not matches:
        raise ValueError(f"pose not found: {target}/{ligand}/mode {pose_rank}")
    pose = matches[0].path
    output_dir = config.result_dir / "plip" / target / ligand / f"mode_{pose_rank:02d}"
    report = output_dir / "report.txt"
    if report.exists() and report.stat().st_size > 0 and not force:
        return report

    obabel = require_tool(config.tools.get("obabel"), ("obabel.exe", "obabel"), "Open Babel")
    plip = require_tool(config.tools.get("plip"), ("plip.exe", "plip"), "PLIP")
    ligand_pdb = config.work_dir / "plip_ligands" / target / ligand / f"mode_{pose_rank:02d}.pdb"
    conversion_log = config.work_dir / "logs" / "plip" / target / ligand / f"mode_{pose_rank:02d}_obabel.log"
    conversion = run_command([str(obabel), str(pose), "-O", str(ligand_pdb)], conversion_log)
    if conversion.returncode != 0 or not outputs_are_complete([ligand_pdb]):
        raise RuntimeError(f"failed to convert selected Vina pose for PLIP; see {conversion_log}")

    receptor = config.work_dir / "receptors_clean" / f"{target}.pdb"
    complex_pdb = config.work_dir / "complexes" / target / ligand / f"mode_{pose_rank:02d}.pdb"
    _make_complex(receptor, ligand_pdb, complex_pdb)
    output_dir.mkdir(parents=True, exist_ok=True)
    plip_log = config.work_dir / "logs" / "plip" / target / ligand / f"mode_{pose_rank:02d}.log"
    result = run_command([str(plip), "-f", str(complex_pdb), "-o", str(output_dir), "--txt", "--xml"], plip_log)
    if result.returncode != 0:
        raise RuntimeError(f"PLIP failed for {target}/{ligand}/mode {pose_rank}; see {plip_log}")
    if not report.exists():
        report.write_text(result.stdout or "PLIP completed; inspect generated files.\n", encoding="utf-8")
    return report
