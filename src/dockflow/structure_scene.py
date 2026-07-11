from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from functools import cached_property
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
    model_count: int = 1
    model_index: int = 0
    hidden_atom_count: int = 0

    @cached_property
    def center(self) -> tuple[float, float, float]:
        if not self.atoms:
            return (0.0, 0.0, 0.0)
        count = len(self.atoms)
        return (
            sum(atom.x for atom in self.atoms) / count,
            sum(atom.y for atom in self.atoms) / count,
            sum(atom.z for atom in self.atoms) / count,
        )

    @cached_property
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
_COMMON_ADDITIVES = {
    "SO4", "PO4", "GOL", "EDO", "PEG", "PG4", "PGE", "ACT", "ACY", "DMS",
    "MES", "TRS", "HEP", "CIT", "FMT", "EOH", "IPA", "MPD", "BME", "ACE",
}
_TWO_LETTER = {"CL", "BR", "SI", "FE", "ZN", "MG", "MN", "CU", "NA"}
_METALS = {"FE", "ZN", "MG", "MN", "CU", "CA", "CO", "NI"}


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


def _infer_bonds(atoms: list[SceneAtom], limit: int = 350) -> list[tuple[int, int]]:
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


def _split_models(lines: list[str]) -> list[list[str]]:
    models: list[list[str]] = []
    current: list[str] = []
    in_model = False
    saw_model = False
    for line in lines:
        record = line[:6].strip().upper()
        if record == "MODEL":
            saw_model = True
            if current and in_model:
                models.append(current)
            current = []
            in_model = True
            continue
        if record == "ENDMDL":
            if in_model:
                models.append(current)
                current = []
                in_model = False
            continue
        if not saw_model or in_model:
            current.append(line)
    if current:
        models.append(current)
    return models or [lines]


def _parse_pdb_atoms(lines: list[str], suffix: str) -> tuple[list[SceneAtom], dict[int, int], list[tuple[int, int]]]:
    atoms: list[SceneAtom] = []
    serial_to_index: dict[int, int] = {}
    conect: list[tuple[int, int]] = []
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
        if suffix == ".pdbqt" and not explicit:
            fields = line.split()
            explicit = fields[-1] if fields else ""
        serial_to_index[serial] = len(atoms)
        atoms.append(
            SceneAtom(
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
        )
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
    return atoms, serial_to_index, conect


def _sample_trace(atoms: list[SceneAtom], maximum: int = 2400) -> list[int]:
    by_chain: dict[str, list[int]] = defaultdict(list)
    for index, atom in enumerate(atoms):
        if not atom.hetero and atom.name.upper() in {"CA", "P"}:
            by_chain[atom.chain].append(index)
    total = sum(len(indices) for indices in by_chain.values())
    if total <= maximum:
        return [index for indices in by_chain.values() for index in indices]
    sampled: list[int] = []
    for indices in by_chain.values():
        allocation = max(2, round(maximum * len(indices) / total))
        step = max(1, math.ceil(len(indices) / allocation))
        selected = indices[::step]
        if indices and selected[-1] != indices[-1]:
            selected.append(indices[-1])
        sampled.extend(selected)
    return sampled[:maximum]


def _select_hetero_groups(atoms: list[SceneAtom], maximum_atoms: int = 220) -> list[int]:
    groups: dict[tuple[str, str, str], list[int]] = defaultdict(list)
    for index, atom in enumerate(atoms):
        if atom.hetero and atom.residue not in _WATER:
            groups[(atom.chain, atom.residue, atom.residue_id)].append(index)
    ranked = sorted(
        groups.items(),
        key=lambda item: (
            item[0][1] in _COMMON_ADDITIVES,
            -sum(atoms[index].element.upper() != "H" for index in item[1]),
            item[0],
        ),
    )
    selected: list[int] = []
    selected_groups = 0
    for (_key, indices) in ranked:
        heavy = sum(atoms[index].element.upper() != "H" for index in indices)
        if heavy < 4 and selected_groups > 0:
            continue
        if selected and len(selected) + len(indices) > maximum_atoms:
            continue
        selected.extend(indices)
        selected_groups += 1
        if selected_groups >= 4 or len(selected) >= maximum_atoms:
            break
    if not selected:
        for (_key, indices) in ranked[:12]:
            selected.extend(indices[: max(0, maximum_atoms - len(selected))])
            if len(selected) >= maximum_atoms:
                break
    if selected:
        selected_atoms = [atoms[index] for index in selected]
        for index, atom in enumerate(atoms):
            if not atom.hetero or atom.element.upper() not in _METALS or index in selected:
                continue
            if any(math.dist((atom.x, atom.y, atom.z), (other.x, other.y, other.z)) <= 5.0 for other in selected_atoms):
                selected.append(index)
    return sorted(set(selected))


def _parse_pdb(path: Path, ligand_only: bool, model_index: int = 0) -> StructureScene:
    all_lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    models = _split_models(all_lines)
    selected_model = min(max(int(model_index), 0), len(models) - 1)
    lines = models[selected_model]
    atoms, _serial_to_index, conect = _parse_pdb_atoms(lines, path.suffix.lower())

    if ligand_only:
        bonds = sorted(set(conect)) or _infer_bonds(atoms)
        return StructureScene(
            tuple(atoms),
            tuple(bonds),
            path.suffix.lower().lstrip("."),
            "ball-and-stick",
            len(models),
            selected_model,
            0,
        )

    trace_indices = _sample_trace(atoms)
    hetero_indices = _select_hetero_groups(atoms)
    source_indices = trace_indices + [index for index in hetero_indices if index not in set(trace_indices)]
    if not source_indices:
        source_indices = list(range(min(len(atoms), 1200)))
    selected = [atoms[index] for index in source_indices]
    index_map = {source: target for target, source in enumerate(source_indices)}
    bonds: list[tuple[int, int]] = []

    last_by_chain: dict[str, int] = {}
    for index, atom in enumerate(selected):
        if atom.hetero:
            continue
        previous = last_by_chain.get(atom.chain)
        if previous is not None:
            other = selected[previous]
            if math.dist((atom.x, atom.y, atom.z), (other.x, other.y, other.z)) <= 7.5:
                bonds.append((previous, index))
        last_by_chain[atom.chain] = index

    for first, second in conect:
        if first in index_map and second in index_map:
            bonds.append((index_map[first], index_map[second]))

    grouped_selected: dict[tuple[str, str, str], list[int]] = defaultdict(list)
    for selected_index, atom in enumerate(selected):
        if atom.hetero:
            grouped_selected[(atom.chain, atom.residue, atom.residue_id)].append(selected_index)
    for indices in grouped_selected.values():
        group_atoms = [selected[index] for index in indices]
        for first, second in _infer_bonds(group_atoms):
            bonds.append((indices[first], indices[second]))

    return StructureScene(
        tuple(selected),
        tuple(sorted(set(tuple(sorted(bond)) for bond in bonds))),
        path.suffix.lower().lstrip("."),
        "protein-trace",
        len(models),
        selected_model,
        max(0, len(atoms) - len(selected)),
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


def load_structure_scene(path: Path, *, ligand_only: bool = False, model_index: int = 0) -> StructureScene:
    path = Path(path)
    if not path.is_file():
        raise FileNotFoundError(path)
    suffix = path.suffix.lower()
    if suffix in {".pdb", ".pdbqt"}:
        scene = _parse_pdb(path, ligand_only, model_index=model_index)
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
