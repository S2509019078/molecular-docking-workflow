from pathlib import Path
import re
import shutil

from .commands import require_tool, run_command

SUPPORTED_LIGAND_EXTENSIONS = {".sdf", ".mol2", ".mol", ".pdb", ".smi", ".smiles", ".pdbqt"}


def safe_name(value: str) -> str:
    name = re.sub(r"[^A-Za-z0-9_.-]+", "_", value.strip()).strip("._")
    if not name:
        raise ValueError(f"cannot derive a safe name from {value!r}")
    return name


def discover_ligands(directory: Path) -> dict[str, Path]:
    if not directory.exists():
        raise FileNotFoundError(directory)
    result: dict[str, Path] = {}
    for path in sorted(item for item in directory.iterdir() if item.is_file() and item.suffix.lower() in SUPPORTED_LIGAND_EXTENSIONS):
        name = safe_name(path.stem)
        if name in result:
            raise ValueError(f"duplicate ligand name after normalization: {name}")
        result[name] = path
    if not result:
        raise ValueError(f"no supported ligand files found in {directory}")
    return result


def prepare_receptor(clean_pdb: Path, output_pdbqt: Path, tools: dict, log_path: Path) -> Path:
    pythonsh = require_tool(tools.get("mgltools_pythonsh"), ("pythonsh",), "MGLTools pythonsh")
    script = require_tool(tools.get("prepare_receptor4"), (), "prepare_receptor4.py")
    output_pdbqt.parent.mkdir(parents=True, exist_ok=True)
    result = run_command([str(pythonsh), str(script), "-r", str(clean_pdb), "-o", str(output_pdbqt), "-A", "hydrogens", "-U", "nphs_lps_waters"], log_path)
    if result.returncode != 0 or not output_pdbqt.exists() or output_pdbqt.stat().st_size == 0:
        raise RuntimeError(f"prepare_receptor4 failed; see {log_path}")
    return output_pdbqt


def convert_ligand_to_pdb(
    source: Path,
    output_pdb: Path,
    tools: dict,
    log_path: Path,
    *,
    protonation_ph: float | None = 7.4,
    minimize: bool = True,
    forcefield: str = "MMFF94",
    minimization_steps: int = 250,
) -> Path:
    output_pdb.parent.mkdir(parents=True, exist_ok=True)
    obabel = require_tool(tools.get("obabel"), ("obabel",), "Open Babel")
    command = [str(obabel), str(source), "-O", str(output_pdb)]
    if source.suffix.lower() in {".smi", ".smiles"}:
        command.append("--gen3d")
    if protonation_ph is not None:
        command.extend(["-p", f"{float(protonation_ph):g}"])
    if minimize:
        command.extend(["--minimize", "--ff", str(forcefield), "--steps", str(int(minimization_steps))])
    result = run_command(command, log_path)
    if result.returncode != 0 or not output_pdb.exists() or output_pdb.stat().st_size == 0:
        raise RuntimeError(f"Open Babel conversion failed; see {log_path}")
    return output_pdb


def prepare_ligand(
    source: Path,
    ligand_name: str,
    pdb_dir: Path,
    pdbqt_dir: Path,
    tools: dict,
    log_dir: Path,
    settings: dict | None = None,
) -> Path:
    settings = settings or {}
    output_pdbqt = pdbqt_dir / f"{ligand_name}.pdbqt"
    output_pdbqt.parent.mkdir(parents=True, exist_ok=True)
    if source.suffix.lower() == ".pdbqt":
        shutil.copyfile(source, output_pdbqt)
        return output_pdbqt
    output_pdb = pdb_dir / f"{ligand_name}.pdb"
    convert_ligand_to_pdb(
        source,
        output_pdb,
        tools,
        log_dir / f"{ligand_name}_obabel.log",
        protonation_ph=settings.get("ligand_protonation_ph", 7.4),
        minimize=bool(settings.get("ligand_minimize", True)),
        forcefield=str(settings.get("ligand_forcefield", "MMFF94")),
        minimization_steps=int(settings.get("ligand_minimization_steps", 250)),
    )
    pythonsh = require_tool(tools.get("mgltools_pythonsh"), ("pythonsh",), "MGLTools pythonsh")
    script = require_tool(tools.get("prepare_ligand4"), (), "prepare_ligand4.py")
    prepare_log = log_dir / f"{ligand_name}_prepare.log"
    result = run_command([str(pythonsh), str(script), "-l", str(output_pdb), "-o", str(output_pdbqt), "-A", "hydrogens"], prepare_log)
    if result.returncode != 0 or not output_pdbqt.exists() or output_pdbqt.stat().st_size == 0:
        raise RuntimeError(f"prepare_ligand4 failed; see {prepare_log}")
    return output_pdbqt
