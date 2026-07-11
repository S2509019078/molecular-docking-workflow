from pathlib import Path
import os
import re
import shutil

from .commands import discover_tool, require_tool, run_command

SUPPORTED_LIGAND_EXTENSIONS = {".sdf", ".mol2", ".mol", ".pdb", ".smi", ".smiles", ".pdbqt"}
SUPPORTED_PREPARATION_BACKENDS = {"auto", "meeko", "mgltools"}


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


def _meeko_paths(tools: dict) -> tuple[Path | None, Path | None]:
    receptor = discover_tool(
        tools.get("meeko_receptor"),
        ("DockFlow-Meeko-Receptor.exe", "mk_prepare_receptor.py", "mk_prepare_receptor"),
    )
    ligand = discover_tool(
        tools.get("meeko_ligand"),
        ("DockFlow-Meeko-Ligand.exe", "mk_prepare_ligand.py", "mk_prepare_ligand"),
    )
    return receptor, ligand


def resolve_preparation_backend(tools: dict, requested: str | None = None) -> str:
    backend = (requested or "auto").strip().lower()
    if backend == "openbabel":
        raise ValueError(
            "Open Babel direct PDBQT generation is no longer supported. "
            "Use Meeko or AutoDockTools; Open Babel remains available for format conversion and 3D optimization."
        )
    if backend not in SUPPORTED_PREPARATION_BACKENDS:
        raise ValueError(f"unsupported preparation backend: {backend}")
    if backend == "meeko":
        if not all(_meeko_paths(tools)):
            raise FileNotFoundError("Meeko backend selected, but receptor/ligand preparation helpers are incomplete")
        return "meeko"
    if backend == "mgltools":
        if not all(_mgltools_paths(tools)):
            raise FileNotFoundError("MGLTools backend selected, but pythonsh/prepare_receptor4.py/prepare_ligand4.py is incomplete")
        return "mgltools"
    if all(_meeko_paths(tools)):
        return "meeko"
    if all(_mgltools_paths(tools)):
        return "mgltools"
    raise FileNotFoundError(
        "No valid PDBQT preparation backend found. Install/use bundled Meeko or configure complete MGLTools."
    )


def preparation_backend_warning(tools: dict, requested: str | None = None) -> str | None:
    backend = resolve_preparation_backend(tools, requested)
    if backend == "mgltools":
        return "当前使用经典 AutoDockTools/MGLTools 生成 PDBQT；建议优先使用随软件提供的 Meeko 后端"
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
    backend = resolve_preparation_backend(tools, str(settings.get("preparation_backend", "auto")))
    output_pdbqt.parent.mkdir(parents=True, exist_ok=True)
    if backend == "meeko":
        receptor_helper, _ = _meeko_paths(tools)
        command = [str(receptor_helper), "--read_pdb", str(clean_pdb), "-p", str(output_pdbqt)]
        result = run_command(command, log_path)
        return _check_output(output_pdbqt, result, "Meeko receptor preparation", log_path)

    pythonsh, script, _ = _mgltools_paths(tools)
    command = [
        str(pythonsh), str(script), "-r", str(clean_pdb), "-o", str(output_pdbqt),
        "-A", "hydrogens", "-U", "nphs_lps_waters",
    ]
    result = run_command(command, log_path)
    return _check_output(output_pdbqt, result, "prepare_receptor4", log_path)


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
    obabel = require_tool(tools.get("obabel"), ("obabel.exe", "obabel"), "Open Babel")
    command = [str(obabel), str(source), "-O", str(output_pdb)]
    if source.suffix.lower() in {".smi", ".smiles"}:
        command.append("--gen3d")
    if protonation_ph is not None:
        command.extend(["-p", f"{float(protonation_ph):g}"])
    if minimize:
        command.extend(["--minimize", "--ff", str(forcefield), "--steps", str(int(minimization_steps))])
    result = run_command(command, log_path)
    return _check_output(output_pdb, result, "Open Babel conversion", log_path)


def convert_ligand_to_sdf(source_pdb: Path, output_sdf: Path, tools: dict, log_path: Path) -> Path:
    output_sdf.parent.mkdir(parents=True, exist_ok=True)
    obabel = require_tool(tools.get("obabel"), ("obabel.exe", "obabel"), "Open Babel")
    command = [str(obabel), str(source_pdb), "-O", str(output_sdf), "-h"]
    result = run_command(command, log_path)
    return _check_output(output_sdf, result, "Open Babel SDF conversion", log_path)


def _env_settings() -> dict:
    ph_value = os.environ.get("DOCKFLOW_LIGAND_PH", "7.4").strip()
    return {
        "ligand_protonation_ph": None if ph_value.lower() in {"", "none", "off"} else float(ph_value),
        "ligand_minimize": os.environ.get("DOCKFLOW_LIGAND_MINIMIZE", "1").strip().lower() not in {"0", "false", "no", "off"},
        "ligand_forcefield": os.environ.get("DOCKFLOW_LIGAND_FORCEFIELD", "MMFF94"),
        "ligand_minimization_steps": int(os.environ.get("DOCKFLOW_LIGAND_STEPS", "250")),
    }


def prepare_ligand(
    source: Path,
    ligand_name: str,
    pdb_dir: Path,
    pdbqt_dir: Path,
    tools: dict,
    log_dir: Path,
    settings: dict | None = None,
) -> Path:
    settings = settings or _env_settings()
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

    backend = resolve_preparation_backend(tools, str(settings.get("preparation_backend", "auto")))
    prepare_log = log_dir / f"{ligand_name}_prepare.log"
    if backend == "meeko":
        sdf_dir = pdb_dir.parent / "ligands_sdf"
        output_sdf = sdf_dir / f"{ligand_name}.sdf"
        convert_ligand_to_sdf(
            output_pdb,
            output_sdf,
            tools,
            log_dir / f"{ligand_name}_sdf.log",
        )
        _, ligand_helper = _meeko_paths(tools)
        command = [str(ligand_helper), "-i", str(output_sdf), "-o", str(output_pdbqt)]
    else:
        pythonsh, _, script = _mgltools_paths(tools)
        command = [str(pythonsh), str(script), "-l", str(output_pdb), "-o", str(output_pdbqt), "-A", "hydrogens"]
    result = run_command(command, prepare_log)
    return _check_output(output_pdbqt, result, f"{backend} ligand preparation", prepare_log)
