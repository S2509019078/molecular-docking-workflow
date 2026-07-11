from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import math
import re


@dataclass(frozen=True)
class SceneAtom:
    x: float
    y: float
    z: float
    element: str
    name: str = ""
    chain: str = ""
    residue: str = ""
    residue_id: str = ""
    hetero: bool = False


@dataclass(frozen=True)
class StructureScene:
    atoms: tuple[SceneAtom, ...]
    bonds: tuple[tuple[int, int], ...]
    source_format: str
    representation: str

    @property
    def center(self) -> tuple[float, float, float]:
        if not self.atoms:
            return (0.0, 0.0, 0.0)
        count = len(self.atoms)
        return (
            sum(atom.x for atom in self.atoms) / count,
            sum(atom.y for atom in self.atoms) / count,
            sum(atom.z for atom in self.atoms) / count,
        )

    @property
    def radius(self) -> float:
        cx, cy, cz = self.center
        return max(
            (math.sqrt((atom.x - cx) ** 2 + (atom.y - cy) ** 2 + (atom.z - cz) ** 2) for atom in self.atoms),
            default=1.0,
        )


_COVALENT_RADII = {
    "H": 0.31,
    "C": 0.76,
    "N": 0.71,
    "O": 0.66,
    "F": 0.57,
    "P": 1.07,
    "S": 1.05,
    "CL": 1.02,
    "BR": 1.20,
    "I": 1.39,
    "B": 0.85,
    "SI": 1.11,
    "FE": 1.24,
    "ZN": 1.22,
    "MG": 1.30,
    "CA": 1.74,
    "MN": 1.39,
    "CU": 1.32,
}

_WATER = {"HOH", "WAT", "H2O", "DOD"}
_TWO_LETTER = {"CL", "BR", "SI", "FE", "ZN", "MG", "MN", "CU", "NA"}


def _element(value: str, atom_name: str = "", *, protein_atom: bool = False) -> str:
    explicit = re.sub(r"[^A-Za-z]", "", value or "").upper()
    if explicit:
        return explicit[:2] if explicit[:2] in _TWO_LETTER or explicit[:2] == "CA" else explicit[:1]
    name = re.sub(r"[^A-Za-z]", "", atom_name or "").upper()
    if not name:
        return "C"
    if protein_atom and name == "CA":
        return "C"
    return name[:2] if name[:2] in _TWO_LETTER else name[:1]


def _infer_bonds(atoms: list[SceneAtom], limit: int = 500) -> list[tuple[int, int]]:
    if len(atoms) > limit:
        return []
    bonds: list[tuple[int, int]] = []
    for i, first in enumerate(atoms):
        radius_a = _COVALENT_RADII.get(first.element.upper(), 0.77)
        for j in range(i + 1, len(atoms)):
            second = atoms[j]
            dx = first.x - second.x
            dy = first.y - second.y
            dz = first.z - second.z
            distance2 = dx * dx + dy * dy + dz * dz
            if distance2 < 0.16:
                continue
            radius_b = _COVALENT_RADII.get(second.element.upper(), 0.77)
            threshold = radius_a + radius_b + 0.45
            if distance2 <= threshold * threshold:
                bonds.append((i, j))
    return bonds


def _parse_pdb(path: Path, ligand_only: bool) -> StructureScene:
    atoms: list[SceneAtom] = []
    serial_to_index: dict[int, int] = {}
    conect: list[tuple[int, int]] = []
    lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    for line in lines:
        record = line[:6].strip().upper()
        if record not in {"ATOM", "HETATM"}:
            continue
        try:
            serial = int(line[6:11].strip())
            x = float(line[30:38])
            y = float(line[38:46])
            z = float(line[46:54])
        except (ValueError, IndexError):
            fields = line.split()
            if len(fields) < 9:
                continue
            try:
                serial = int(fields[1])
                x, y, z = map(float, fields[6:9])
            except (ValueError, IndexError):
                continue
        name = line[12:16].strip() if len(line) >= 16 else ""
        residue = line[17:20].strip().upper() if len(line) >= 20 else ""
        chain = line[21:22].strip() if len(line) >= 22 else ""
        residue_id = line[22:27].strip() if len(line) >= 27 else ""
        hetero = record == "HETATM"
        explicit = line[76:78].strip() if len(line) >= 78 else ""
        if path.suffix.lower() == ".pdbqt" and not explicit:
            fields = line.split()
            explicit = fields[-1] if fields else ""
        atom = SceneAtom(
            x,
            y,
            z,
            _element(explicit, name, protein_atom=not hetero),
            name,
            chain,
            residue,
            residue_id,
            hetero,
        )
        serial_to_index[serial] = len(atoms)
        atoms.append(atom)
    for line in lines:
        if not line.startswith("CONECT"):
            continue
        try:
            values = [int(value) for value in line[6:].split()]
        except ValueError:
            continue
        if len(values) < 2:
            continue
        source = serial_to_index.get(values[0])
        for serial in values[1:]:
            target = serial_to_index.get(serial)
            if source is not None and target is not None and source != target:
                conect.append(tuple(sorted((source, target))))

    if ligand_only:
        bonds = sorted(set(conect)) or _infer_bonds(atoms)
        return StructureScene(tuple(atoms), tuple(bonds), path.suffix.lower().lstrip("."), "ball-and-stick")

    selected: list[SceneAtom] = []
    source_indices: list[int] = []
    for index, atom in enumerate(atoms):
        is_trace = not atom.hetero and atom.name.upper() in {"CA", "P"}
        is_ligand = atom.hetero and atom.residue not in _WATER
        if is_trace or is_ligand:
            source_indices.append(index)
            selected.append(atom)
    if not selected:
        selected = atoms[:2000]
        source_indices = list(range(len(selected)))

    index_map = {source: target for target, source in enumerate(source_indices)}
    bonds: list[tuple[int, int]] = []
    last_by_chain: dict[str, int] = {}
    for index, atom in enumerate(selected):
        if atom.hetero:
            continue
        previous = last_by_chain.get(atom.chain)
        if previous is not None:
            other = selected[previous]
            distance = math.dist((atom.x, atom.y, atom.z), (other.x, other.y, other.z))
            if distance <= 5.0:
                bonds.append((previous, index))
        last_by_chain[atom.chain] = index
    for first, second in conect:
        if first in index_map and second in index_map:
            bonds.append((index_map[first], index_map[second]))
    hetero_indices = [index for index, atom in enumerate(selected) if atom.hetero]
    hetero_atoms = [selected[index] for index in hetero_indices]
    for first, second in _infer_bonds(hetero_atoms):
        bonds.append((hetero_indices[first], hetero_indices[second]))
    return StructureScene(
        tuple(selected),
        tuple(sorted(set(tuple(sorted(bond)) for bond in bonds))),
        path.suffix.lower().lstrip("."),
        "backbone-and-ligand",
    )


def _parse_mol2(path: Path) -> StructureScene:
    atoms: list[SceneAtom] = []
    bonds: list[tuple[int, int]] = []
    atom_ids: dict[int, int] = {}
    section = ""
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        if line.startswith("@<TRIPOS>"):
            section = line.strip().upper()
            continue
        fields = line.split()
        if section == "@<TRIPOS>ATOM" and len(fields) >= 6:
            try:
                atom_id = int(fields[0])
                x, y, z = map(float, fields[2:5])
            except ValueError:
                continue
            atom_ids[atom_id] = len(atoms)
            atom_type = fields[5].split(".", 1)[0]
            atoms.append(SceneAtom(x, y, z, _element(atom_type, fields[1]), fields[1], residue=fields[7] if len(fields) > 7 else ""))
        elif section == "@<TRIPOS>BOND" and len(fields) >= 4:
            try:
                first = atom_ids[int(fields[1])]
                second = atom_ids[int(fields[2])]
            except (ValueError, KeyError):
                continue
            bonds.append(tuple(sorted((first, second))))
    return StructureScene(tuple(atoms), tuple(sorted(set(bonds)) or _infer_bonds(atoms)), "mol2", "ball-and-stick")


def _parse_mol(path: Path) -> StructureScene:
    lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    counts_index = next((i for i, line in enumerate(lines[:12]) if "V2000" in line or "V3000" in line), 3 if len(lines) > 3 else -1)
    if counts_index < 0 or counts_index >= len(lines):
        return StructureScene((), (), path.suffix.lower().lstrip("."), "ball-and-stick")
    counts = lines[counts_index]
    try:
        atom_count = int(counts[:3])
        bond_count = int(counts[3:6])
    except ValueError:
        fields = counts.split()
        atom_count = int(fields[0])
        bond_count = int(fields[1])
    atoms: list[SceneAtom] = []
    start = counts_index + 1
    for line in lines[start:start + atom_count]:
        try:
            x = float(line[0:10])
            y = float(line[10:20])
            z = float(line[20:30])
            element = line[31:34].strip()
        except (ValueError, IndexError):
            fields = line.split()
            if len(fields) < 4:
                continue
            x, y, z = map(float, fields[:3])
            element = fields[3]
        atoms.append(SceneAtom(x, y, z, _element(element), element))
    bonds: list[tuple[int, int]] = []
    for line in lines[start + atom_count:start + atom_count + bond_count]:
        try:
            first = int(line[:3]) - 1
            second = int(line[3:6]) - 1
        except ValueError:
            fields = line.split()
            if len(fields) < 2:
                continue
            first, second = int(fields[0]) - 1, int(fields[1]) - 1
        if 0 <= first < len(atoms) and 0 <= second < len(atoms):
            bonds.append(tuple(sorted((first, second))))
    return StructureScene(tuple(atoms), tuple(sorted(set(bonds)) or _infer_bonds(atoms)), path.suffix.lower().lstrip("."), "ball-and-stick")


def load_structure_scene(path: Path, *, ligand_only: bool = False) -> StructureScene:
    path = Path(path)
    if not path.is_file():
        raise FileNotFoundError(path)
    suffix = path.suffix.lower()
    if suffix in {".pdb", ".pdbqt"}:
        scene = _parse_pdb(path, ligand_only)
    elif suffix == ".mol2":
        scene = _parse_mol2(path)
    elif suffix in {".mol", ".sdf"}:
        scene = _parse_mol(path)
    elif suffix in {".smi", ".smiles"}:
        raise ValueError("SMILES 文件没有三维坐标；完成 Open Babel 三维化后可在“预处理后”标签中查看")
    else:
        raise ValueError(f"不支持的结构预览格式: {suffix or path.name}")
    if not scene.atoms:
        raise ValueError(f"未从文件中读取到可显示的三维原子坐标: {path.name}")
    return scene
