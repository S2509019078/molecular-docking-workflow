from pathlib import Path
from urllib.request import urlopen
import shutil

from .models import Atom, Target

WATER_RESNAMES = {"HOH", "WAT", "DOD"}


def acquire_structure(target: Target, raw_dir: Path, project_root: Path, force: bool = False) -> Path:
    raw_dir.mkdir(parents=True, exist_ok=True)
    output = raw_dir / f"{target.name}.pdb"
    if output.exists() and output.stat().st_size > 0 and not force:
        return output
    if target.structure_source == "local":
        source = Path(target.structure).expanduser()
        if not source.is_absolute():
            source = project_root / source
        if not source.exists():
            raise FileNotFoundError(source)
        shutil.copyfile(source, output)
    elif target.structure_source == "pdb":
        pdb_id = target.structure.strip().upper()
        if len(pdb_id) != 4:
            raise ValueError(f"invalid PDB identifier for {target.name}: {pdb_id!r}")
        with urlopen(f"https://files.rcsb.org/download/{pdb_id}.pdb", timeout=60) as response:
            output.write_bytes(response.read())
    else:
        raise ValueError(f"unsupported structure source: {target.structure_source}")
    if not output.exists() or output.stat().st_size == 0:
        raise ValueError(f"structure is empty or invalid: {output}")
    return output


def read_atoms(path: Path) -> list[Atom]:
    atoms: list[Atom] = []
    with path.open(errors="replace") as handle:
        for line in handle:
            record = line[:6].strip()
            if record not in {"ATOM", "HETATM"}:
                continue
            if line[16:17] not in {" ", "A"}:
                continue
            try:
                atoms.append(Atom(line[12:16].strip(), line[17:20].strip().upper(), line[21:22].strip(), int(line[22:26]), line[26:27].strip(), float(line[30:38]), float(line[38:46]), float(line[46:54]), record))
            except ValueError:
                continue
    if not atoms:
        raise ValueError(f"no parseable atoms in {path}")
    return atoms


def select_reference_ligand(atoms: list[Atom], target: Target) -> list[Atom]:
    return [atom for atom in atoms if atom.record == "HETATM" and atom.residue == target.ligand and (not target.ligand_chain or atom.chain == target.ligand_chain) and (target.ligand_residue_id is None or atom.residue_id == target.ligand_residue_id)]


def extract_reference_ligand(source: Path, target: Target, output: Path) -> Path:
    lines = []
    for line in source.read_text(errors="replace").splitlines():
        if line[:6].strip() != "HETATM" or line[17:20].strip().upper() != target.ligand:
            continue
        if target.ligand_chain and line[21:22].strip() != target.ligand_chain:
            continue
        try:
            residue_id = int(line[22:26])
        except ValueError:
            continue
        if target.ligand_residue_id is not None and residue_id != target.ligand_residue_id:
            continue
        if line[16:17] in {" ", "A"}:
            lines.append(line)
    if not lines:
        raise ValueError(f"reference ligand not found for {target.name}")
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text("\n".join(lines) + "\nEND\n", encoding="utf-8")
    return output


def clean_receptor(source: Path, target: Target, output: Path) -> Path:
    kept: list[str] = []
    receptor_chains = set(target.receptor_chains)
    keep_hetero = set(target.keep_hetero_resnames)
    for line in source.read_text(errors="replace").splitlines():
        record = line[:6].strip()
        if record not in {"ATOM", "HETATM", "TER"}:
            continue
        if record == "TER":
            kept.append(line)
            continue
        chain = line[21:22].strip()
        if receptor_chains and chain not in receptor_chains:
            continue
        residue = line[17:20].strip().upper()
        if record == "HETATM":
            if residue in WATER_RESNAMES:
                continue
            if residue == target.ligand:
                try:
                    residue_id = int(line[22:26])
                except ValueError:
                    residue_id = None
                if (not target.ligand_chain or chain == target.ligand_chain) and (target.ligand_residue_id is None or residue_id == target.ligand_residue_id):
                    continue
            if residue not in keep_hetero:
                continue
        if line[16:17] not in {" ", "A"}:
            continue
        kept.append(line)
    if not any(line.startswith("ATOM") for line in kept):
        raise ValueError(f"cleaned receptor contains no protein atoms: {target.name}")
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text("\n".join(kept) + "\nEND\n", encoding="utf-8")
    return output
