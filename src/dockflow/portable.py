from __future__ import annotations

from contextlib import redirect_stderr, redirect_stdout
from importlib.util import find_spec
from pathlib import Path
import os
import sys


def meeko_available() -> bool:
    """Return whether the in-process Meeko preparation backend is available."""
    return find_spec("meeko") is not None and find_spec("rdkit") is not None


def runtime_roots() -> tuple[Path, ...]:
    """Locations that may contain files bundled by PyInstaller or next to the EXE."""
    roots: list[Path] = []
    meipass = getattr(sys, "_MEIPASS", None)
    for value in (
        meipass,
        Path(sys.executable).resolve().parent if getattr(sys, "frozen", False) else None,
        Path(__file__).resolve().parents[2],
    ):
        if not value:
            continue
        path = Path(value)
        if path.exists() and path not in roots:
            roots.append(path)
    return tuple(roots)


def bundled_vina_path() -> Path | None:
    names = (
        Path("tools") / "vina.exe",
        Path("tools") / "vina",
        Path("vina.exe"),
        Path("vina"),
        Path("vendor") / "vina.exe",
    )
    for root in runtime_roots():
        for relative in names:
            candidate = root / relative
            if candidate.is_file():
                return candidate.resolve()
    return None


def _run_python_cli(main_function, argv: list[str], log_path: Path) -> None:
    log_path = Path(log_path)
    log_path.parent.mkdir(parents=True, exist_ok=True)
    previous_argv = sys.argv[:]
    previous_cwd = Path.cwd()
    try:
        sys.argv = argv
        with log_path.open("w", encoding="utf-8", errors="replace") as handle:
            with redirect_stdout(handle), redirect_stderr(handle):
                try:
                    main_function()
                except SystemExit as error:
                    code = error.code
                    if code not in (None, 0):
                        raise RuntimeError(f"embedded command exited with code {code}") from error
    finally:
        sys.argv = previous_argv
        os.chdir(previous_cwd)


def prepare_receptor_with_meeko(clean_pdb: Path, output_pdbqt: Path, log_path: Path) -> Path:
    if not meeko_available():
        raise RuntimeError("Portable Meeko backend is not included in this build")
    from meeko.cli.mk_prepare_receptor import main as meeko_receptor_main

    clean_pdb = Path(clean_pdb).resolve()
    output_pdbqt = Path(output_pdbqt).resolve()
    output_pdbqt.parent.mkdir(parents=True, exist_ok=True)
    argv = [
        "mk_prepare_receptor.py",
        "--read_pdb",
        str(clean_pdb),
        "--output_basename",
        str(output_pdbqt.with_suffix("")),
        "--write_pdbqt",
        str(output_pdbqt),
    ]
    _run_python_cli(meeko_receptor_main, argv, log_path)
    if not output_pdbqt.is_file() or output_pdbqt.stat().st_size == 0:
        raise RuntimeError(f"Meeko receptor preparation produced no PDBQT; see {log_path}")
    return output_pdbqt


def prepare_ligand_with_meeko(source: Path, output_pdbqt: Path, log_path: Path) -> Path:
    if not meeko_available():
        raise RuntimeError("Portable Meeko backend is not included in this build")
    from meeko.cli.mk_prepare_ligand import main as meeko_ligand_main

    source = Path(source).resolve()
    output_pdbqt = Path(output_pdbqt).resolve()
    suffix = source.suffix.lower()
    if suffix not in {".sdf", ".mol", ".mol2"}:
        raise ValueError(
            f"Portable Meeko preparation supports SDF, MOL and MOL2, not {suffix or source.name}. "
            "Use a chemically reviewed 3D SDF/MOL2 file or select the AutoDockTools compatibility backend."
        )
    output_pdbqt.parent.mkdir(parents=True, exist_ok=True)
    argv = [
        "mk_prepare_ligand.py",
        "--input_molecule_file",
        str(source),
        "--output_pdbqt_filename",
        str(output_pdbqt),
    ]
    _run_python_cli(meeko_ligand_main, argv, log_path)
    if not output_pdbqt.is_file() or output_pdbqt.stat().st_size == 0:
        raise RuntimeError(f"Meeko ligand preparation produced no PDBQT; see {log_path}")
    return output_pdbqt
