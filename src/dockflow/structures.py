from pathlib import Path
from urllib.request import urlopen
from .models import Atom, Target

def acquire_structure(target: Target, raw_dir: Path) -> Path:
    raw_dir.mkdir(parents=True, exist_ok=True)
    out = raw_dir / f"{target.name}.pdb"
    if out.exists() and out.stat().st_size > 100: return out
    if target.structure_source == "local":
        source = Path(target.structure)
        if not source.exists(): raise FileNotFoundError(source)
        out.write_bytes(source.read_bytes())
    elif target.structure_source == "pdb":
        with urlopen(f"https://files.rcsb.org/download/{target.structure.upper()}.pdb", timeout=30) as r: out.write_bytes(r.read())
    else: raise ValueError(f"unsupported structure source: {target.structure_source}")
    if out.stat().st_size < 100: raise ValueError(f"downloaded structure is empty: {out}")
    return out

def read_atoms(path: Path) -> list[Atom]:
    atoms=[]
    with path.open(errors="replace") as fh:
        for line in fh:
            if line[:6].strip() not in {"ATOM", "HETATM"} or line[16:17] not in {" ", "A"}: continue
            try: atoms.append(Atom(line[12:16].strip(), line[17:20].strip(), line[21:22].strip(), int(line[22:26]), float(line[30:38]), float(line[38:46]), float(line[46:54]), line[:6].strip()))
            except ValueError: continue
    if not atoms: raise ValueError(f"no parseable atoms in {path}")
    return atoms

