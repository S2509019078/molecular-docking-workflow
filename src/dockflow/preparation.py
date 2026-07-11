from pathlib import Path
import re
import shutil

from .commands import discover_tool, require_tool, run_command

SUPPORTED_LIGAND_EXTENSIONS = {".sdf", ".mol2", ".mol", ".pdb", ".pdbqt", ".smi", ".smiles"}
SUPPORTED_PREPARATION_BACKENDS = {"auto", "mgltools", "autodocktools"}


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


def _mgltools_paths(tools: dict) -> tuple[Path | None, Path | None, Path | None]:
    pythonsh = discover_tool(tools.get("mgltools_pythonsh"), ("pythonsh.exe", "pythonsh"))
    receptor_script = discover_tool(tools.get("prepare_receptor4"), ("prepare_receptor4.py",))
    ligand_script = discover_tool(tools.get("prepare_ligand4"), ("prepare_ligand4.py",))
    return pythonsh, receptor_script, ligand_script


def resolve_preparation_backend(tools: dict, requested: str | None = None) -> str:
    backend = (requested or "auto").strip().lower()
    if backend == "autodocktools":
        backend = "mgltools"
    if backend in {"openbabel", "meeko"}:
        raise ValueError(
            "PDBQT generation is restricted to AutoDockTools/MGLTools. "
            "Open Babel is used only for file-format conversion."
        )
    if backend not in {"auto", "mgltools"}:
        raise ValueError(f"unsupported preparation backend: {backend}")
    if not all(_mgltools_paths(tools)):
        raise FileNotFoundError(
            "AutoDockTools backend is incomplete: configure pythonsh, prepare_receptor4.py, and prepare_ligand4.py"
        )
    return "mgltools"


def preparation_backend_warning(tools: dict, requested: str | None = None) -> str | None:
    resolve_preparation_backend(tools, requested)
    return None


def _check_output(output: Path, result, label: str, log_path: Path) -> Path:
    if result.returncode != 0 or not output.exists() or output.stat().st_size == 0:
        raise RuntimeError(f"{label} failed; see {log_path}")
    return output


def prepare_receptor(
    clean_pdb: Path,
    output_pdbqt: Path,
    tools: dict,
    log_path: Path,
    settings: dict | None = None,
) -> Path:
    settings = settings or {}
    resolve_preparation_backend(tools, str(settings.get("preparation_backend", "auto")))
    output_pdbqt.parent.mkdir(parents=True, exist_ok=True)
    pythonsh, script, _ = _mgltools_paths(tools)
    command = [
        str(pythonsh),
        str(script),
        "-r",
        str(clean_pdb),
        "-o",
        str(output_pdbqt),
        "-A",
        "hydrogens",
        "-U",
        "nphs_lps_waters",
    ]
    result = run_command(command, log_path)
    return _check_output(output_pdbqt, result, "AutoDockTools prepare_receptor4", log_path)


def convert_ligand_format(source: Path, output_mol2: Path, tools: dict, log_path: Path) -> Path:
    """Convert a coordinate-bearing ligand to MOL2 without chemical modification."""
    source = Path(source)
    suffix = source.suffix.lower()
    if suffix in {".smi", ".smiles"}:
        raise ValueError(
            f"{source.name} contains no validated 3D coordinates. "
            "Provide a chemically reviewed 3D SDF or MOL2 before docking."
        )
    output_mol2.parent.mkdir(parents=True, exist_ok=True)
    obabel = require_tool(tools.get("obabel"), ("obabel.exe", "obabel"), "Open Babel")
    command = [str(obabel), str(source), "-O", str(output_mol2)]
    result = run_command(command, log_path)
    return _check_output(output_mol2, result, "Open Babel format conversion", log_path)


def ligand_input_for_autodocktools(
    source: Path,
    ligand_name: str,
    converted_dir: Path,
    tools: dict,
    log_dir: Path,
) -> Path:
    source = Path(source)
    suffix = source.suffix.lower()
    if suffix in {".pdb", ".mol2", ".pdbqt"}:
        return source
    if suffix in {".sdf", ".mol"}:
        return convert_ligand_format(
            source,
            converted_dir / f"{ligand_name}.mol2",
            tools,
            log_dir / f"{ligand_name}_format_conversion.log",
        )
    if suffix in {".smi", ".smiles"}:
        raise ValueError(
            f"{source.name} has no validated 3D coordinates. "
            "Export a 3D SDF/MOL2 with the intended formal charge and protonation state first."
        )
    raise ValueError(f"unsupported ligand format for AutoDockTools: {suffix}")


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

    resolve_preparation_backend(tools, str(settings.get("preparation_backend", "auto")))
    prepared_input = ligand_input_for_autodocktools(
        source,
        ligand_name,
        pdb_dir.parent / "ligands_converted",
        tools,
        log_dir,
    )
    pythonsh, _, script = _mgltools_paths(tools)
    prepare_log = log_dir / f"{ligand_name}_prepare.log"
    command = [
        str(pythonsh),
        str(script),
        "-l",
        str(prepared_input),
        "-o",
        str(output_pdbqt),
        "-A",
        "hydrogens",
    ]
    result = run_command(command, prepare_log)
    return _check_output(output_pdbqt, result, "AutoDockTools prepare_ligand4", prepare_log)
