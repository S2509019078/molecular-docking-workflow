from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Iterable
import csv
import json
import math
import re

from .config import WorkflowConfig, load_targets
from .models import Atom, Target
from .preparation import discover_ligands
from .structures import WATER_RESNAMES, read_atoms

STANDARD_AMINO_ACIDS = {
    "ALA", "ARG", "ASN", "ASP", "CYS", "GLN", "GLU", "GLY", "HIS", "ILE",
    "LEU", "LYS", "MET", "PHE", "PRO", "SER", "THR", "TRP", "TYR", "VAL",
    "SEC", "PYL",
}
COMMON_MODIFIED_RESIDUES = {"MSE", "SEP", "TPO", "PTR", "CSO", "HYP"}
COMMON_METALS = {
    "LI", "NA", "K", "MG", "CA", "MN", "FE", "CO", "NI", "CU", "ZN", "CD", "HG",
}
COMMON_COFACTORS = {
    "HEM", "HEC", "HEA", "FAD", "FMN", "NAD", "NAP", "NDP", "PLP", "SAM", "SAH",
    "ATP", "ADP", "AMP", "GTP", "GDP", "COA", "TPP", "B12", "CLA", "SF4", "FES",
}


@dataclass(frozen=True)
class QCIssue:
    code: str
    level: str
    subject: str
    message: str
    recommendation: str = ""


@dataclass(frozen=True)
class ReceptorQC:
    target: str
    source: str
    atom_count: int
    protein_atom_count: int
    hetero_atom_count: int
    hydrogen_count: int
    model_count: int
    chains: tuple[str, ...]
    residue_count: int
    water_residue_count: int
    hetero_residues: tuple[str, ...]
    metal_residues: tuple[str, ...]
    cofactor_residues: tuple[str, ...]
    altloc_count: int
    insertion_code_count: int
    backbone_gap_count: int
    reference_ligand_atom_count: int
    pocket_water_count: int
    omitted_chain_contact_count: int
    issues: tuple[QCIssue, ...]


@dataclass(frozen=True)
class LigandQC:
    name: str
    source: str
    file_format: str
    molecule_count: int
    atom_count: int
    heavy_atom_count: int
    hydrogen_count: int
    has_3d_coordinates: bool
    z_span_angstrom: float | None
    formal_charge: int | None
    partial_charge_sum: float | None
    rotatable_bond_markers: int | None
    fragment_count: int | None
    issues: tuple[QCIssue, ...]


@dataclass(frozen=True)
class ProjectQC:
    config: str
    mode: str
    receptors: tuple[ReceptorQC, ...]
    ligands: tuple[LigandQC, ...]
    project_issues: tuple[QCIssue, ...]

    @property
    def issues(self) -> tuple[QCIssue, ...]:
        result = list(self.project_issues)
        for receptor in self.receptors:
            result.extend(receptor.issues)
        for ligand in self.ligands:
            result.extend(ligand.issues)
        return tuple(result)

    @property
    def blockers(self) -> tuple[QCIssue, ...]:
        return tuple(issue for issue in self.issues if issue.level == "blocker")

    @property
    def warnings(self) -> tuple[QCIssue, ...]:
        return tuple(issue for issue in self.issues if issue.level in {"warning", "confirm"})

    @property
    def ready(self) -> bool:
        return not self.blockers


def _element_from_pdb_line(line: str) -> str:
    element = line[76:78].strip().upper() if len(line) >= 78 else ""
    if element:
        return element
    name = re.sub(r"[^A-Za-z]", "", line[12:16]).upper()
    if not name:
        return ""
    if name[:2] in COMMON_METALS or name[:2] in {"CL", "BR"}:
        return name[:2]
    return name[:1]


def _distance(first: Atom, second: Atom) -> float:
    return math.sqrt((first.x - second.x) ** 2 + (first.y - second.y) ** 2 + (first.z - second.z) ** 2)


def _residue_key(atom: Atom) -> tuple[str, int, str, str]:
    return atom.chain, atom.residue_id, atom.insertion_code, atom.residue


def _reference_ligand_atoms(atoms: Iterable[Atom], target: Target) -> list[Atom]:
    if not target.ligand:
        return []
    return [
        atom
        for atom in atoms
        if atom.record == "HETATM"
        and atom.residue == target.ligand
        and (not target.ligand_chain or atom.chain == target.ligand_chain)
        and (target.ligand_residue_id is None or atom.residue_id == target.ligand_residue_id)
    ]


def inspect_receptor(path: Path, target: Target) -> ReceptorQC:
    path = Path(path)
    lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    atoms = read_atoms(path)
    issues: list[QCIssue] = []

    model_numbers = []
    altloc_count = 0
    insertion_code_count = 0
    hydrogen_count = 0
    hetero_residue_keys: set[tuple[str, int, str, str]] = set()
    water_keys: set[tuple[str, int, str, str]] = set()
    metal_keys: set[tuple[str, int, str, str]] = set()
    cofactor_keys: set[tuple[str, int, str, str]] = set()
    nonstandard_polymer: set[str] = set()

    for line in lines:
        if line.startswith("MODEL"):
            model_numbers.append(line[10:14].strip() or str(len(model_numbers) + 1))
        record = line[:6].strip()
        if record not in {"ATOM", "HETATM"}:
            continue
        altloc = line[16:17].strip()
        insertion = line[26:27].strip()
        residue = line[17:20].strip().upper()
        chain = line[21:22].strip()
        try:
            residue_id = int(line[22:26])
        except ValueError:
            residue_id = 0
        key = (chain, residue_id, insertion, residue)
        element = _element_from_pdb_line(line)
        if altloc and altloc != "A":
            altloc_count += 1
        if insertion:
            insertion_code_count += 1
        if element == "H":
            hydrogen_count += 1
        if record == "ATOM" and residue not in STANDARD_AMINO_ACIDS:
            nonstandard_polymer.add(residue)
        if record == "HETATM":
            hetero_residue_keys.add(key)
            if residue in WATER_RESNAMES:
                water_keys.add(key)
            if residue in COMMON_METALS or element in COMMON_METALS:
                metal_keys.add(key)
            if residue in COMMON_COFACTORS:
                cofactor_keys.add(key)

    model_count = max(1, len(model_numbers))
    protein_atoms = [atom for atom in atoms if atom.record == "ATOM"]
    hetero_atoms = [atom for atom in atoms if atom.record == "HETATM"]
    chains = tuple(sorted({atom.chain or "(blank)" for atom in protein_atoms}))
    residues = {_residue_key(atom) for atom in protein_atoms}

    backbone_gap_count = 0
    by_chain: dict[str, list[tuple[int, str]]] = {}
    for chain, residue_id, insertion, _residue in residues:
        by_chain.setdefault(chain, []).append((residue_id, insertion))
    for chain_residues in by_chain.values():
        ordered = sorted(set(chain_residues))
        for first, second in zip(ordered, ordered[1:]):
            if second[0] - first[0] > 1:
                backbone_gap_count += 1

    reference = _reference_ligand_atoms(atoms, target)
    water_atoms = [atom for atom in hetero_atoms if atom.residue in WATER_RESNAMES]
    pocket_water_keys = {
        _residue_key(water)
        for water in water_atoms
        if reference and any(_distance(water, ligand_atom) <= 4.0 for ligand_atom in reference)
    }

    selected_chains = set(target.receptor_chains)
    omitted_atoms = [atom for atom in protein_atoms if selected_chains and atom.chain not in selected_chains]
    omitted_contact_keys = {
        _residue_key(atom)
        for atom in omitted_atoms
        if reference and any(_distance(atom, ligand_atom) <= 5.0 for ligand_atom in reference)
    }

    if not protein_atoms:
        issues.append(QCIssue("receptor.no_protein", "blocker", target.name, "未检测到蛋白ATOM记录", "确认输入是否为受体PDB"))
    if model_count > 1:
        issues.append(QCIssue("receptor.multiple_models", "confirm", target.name, f"检测到{model_count}个MODEL", "明确选择单个模型或建立受体构象集合"))
    if len(chains) > 1 and not target.receptor_chains:
        issues.append(QCIssue("receptor.chains_unselected", "confirm", target.name, f"检测到多条蛋白链：{', '.join(chains)}", "依据生物学组装和活性位点选择链，不要只按最长链自动决定"))
    if omitted_contact_keys:
        issues.append(QCIssue("receptor.omitted_chain_contact", "blocker", target.name, f"被排除链中有{len(omitted_contact_keys)}个残基位于参考配体5 Å内", "该位点可能位于链界面，应保留相关亚基"))
    if altloc_count:
        issues.append(QCIssue("receptor.altloc", "confirm", target.name, f"检测到{altloc_count}条非主替代构象记录", "按占有率和局部结构一致性选择altloc，并记录选择"))
    if insertion_code_count:
        issues.append(QCIssue("receptor.insertion_codes", "warning", target.name, f"检测到{insertion_code_count}条插入码记录", "后续残基选择必须保留插入码，避免编号错位"))
    if backbone_gap_count:
        issues.append(QCIssue("receptor.sequence_gaps", "warning", target.name, f"按残基编号检测到至少{backbone_gap_count}处链缺口", "检查缺失片段是否靠近口袋；靠近口袋时应阻断并修模"))
    if nonstandard_polymer:
        issues.append(QCIssue("receptor.nonstandard_polymer", "confirm", target.name, f"检测到非标准聚合物残基：{', '.join(sorted(nonstandard_polymer))}", "确认是修饰残基、工程残基还是应标准化的残基"))
    if hydrogen_count == 0:
        issues.append(QCIssue("receptor.no_hydrogens", "confirm", target.name, "原始结构未检测到氢原子", "在明确pH、His状态、金属和氢键网络后加氢"))
    if pocket_water_keys:
        issues.append(QCIssue("receptor.pocket_waters", "confirm", target.name, f"参考配体4 Å内检测到{len(pocket_water_keys)}个水分子", "逐个判断催化水、桥联水和可替代水，不应全部自动删除"))
    if metal_keys:
        issues.append(QCIssue("receptor.metals", "confirm", target.name, f"检测到金属/金属离子：{', '.join(sorted({key[3] for key in metal_keys}))}", "检查配位、参数化和是否需要专门金属对接方案"))
    if cofactor_keys:
        issues.append(QCIssue("receptor.cofactors", "confirm", target.name, f"检测到常见辅因子：{', '.join(sorted({key[3] for key in cofactor_keys}))}", "确认辅因子是否参与口袋并在清理时保留"))
    if target.pocket_strategy == "blind":
        issues.append(QCIssue("pocket.blind", "warning", target.name, "当前使用盲对接", "结果仅作为探索性线索；优先使用共晶配体、关键残基或实验位点"))
    if target.pocket_strategy == "co_crystal" and not reference:
        issues.append(QCIssue("pocket.reference_missing", "blocker", target.name, "配置为共晶口袋但未找到参考配体", "检查配体残基名、链和残基编号"))

    return ReceptorQC(
        target=target.name,
        source=str(path.resolve()),
        atom_count=len(atoms),
        protein_atom_count=len(protein_atoms),
        hetero_atom_count=len(hetero_atoms),
        hydrogen_count=hydrogen_count,
        model_count=model_count,
        chains=chains,
        residue_count=len(residues),
        water_residue_count=len(water_keys),
        hetero_residues=tuple(sorted({key[3] for key in hetero_residue_keys})),
        metal_residues=tuple(sorted({key[3] for key in metal_keys})),
        cofactor_residues=tuple(sorted({key[3] for key in cofactor_keys})),
        altloc_count=altloc_count,
        insertion_code_count=insertion_code_count,
        backbone_gap_count=backbone_gap_count,
        reference_ligand_atom_count=len(reference),
        pocket_water_count=len(pocket_water_keys),
        omitted_chain_contact_count=len(omitted_contact_keys),
        issues=tuple(issues),
    )


def _mol_counts(lines: list[str]) -> tuple[int, int, int]:
    counts_index = next((index for index, line in enumerate(lines[:12]) if "V2000" in line), -1)
    if counts_index < 0:
        return -1, 0, 0
    line = lines[counts_index]
    try:
        atom_count = int(line[:3])
        bond_count = int(line[3:6])
    except ValueError:
        fields = line.split()
        atom_count = int(fields[0]) if fields else 0
        bond_count = int(fields[1]) if len(fields) > 1 else 0
    return counts_index, atom_count, bond_count


def _inspect_mol_block(text: str) -> tuple[int, int, int, bool, float | None, int | None]:
    lines = text.splitlines()
    counts_index, atom_count, _bond_count = _mol_counts(lines)
    if counts_index < 0:
        return 0, 0, 0, False, None, None
    heavy = 0
    hydrogens = 0
    z_values: list[float] = []
    formal_charge = 0
    for line in lines[counts_index + 1: counts_index + 1 + atom_count]:
        try:
            z = float(line[20:30])
            element = line[31:34].strip().upper()
        except (ValueError, IndexError):
            fields = line.split()
            if len(fields) < 4:
                continue
            z = float(fields[2])
            element = fields[3].upper()
        z_values.append(z)
        if element == "H":
            hydrogens += 1
        else:
            heavy += 1
    for line in lines:
        if not line.startswith("M  CHG"):
            continue
        fields = line.split()[3:]
        for index in range(1, len(fields), 2):
            try:
                formal_charge += int(fields[index])
            except (ValueError, IndexError):
                pass
    z_span = max(z_values) - min(z_values) if z_values else None
    has_3d = bool(z_values) and (abs(z_span or 0.0) > 1e-3 or any("3D" in line.upper() for line in lines[:4]))
    return atom_count, heavy, hydrogens, has_3d, z_span, formal_charge


def _inspect_mol2(text: str) -> tuple[int, int, int, bool, float | None, float | None]:
    atom_lines: list[list[str]] = []
    section = ""
    for line in text.splitlines():
        if line.startswith("@<TRIPOS>"):
            section = line.strip().upper()
            continue
        if section == "@<TRIPOS>ATOM":
            fields = line.split()
            if len(fields) >= 6:
                atom_lines.append(fields)
    heavy = 0
    hydrogens = 0
    z_values: list[float] = []
    charge_sum = 0.0
    has_charge = False
    for fields in atom_lines:
        atom_type = fields[5].split(".", 1)[0].upper()
        if atom_type == "H":
            hydrogens += 1
        else:
            heavy += 1
        try:
            z_values.append(float(fields[4]))
        except ValueError:
            pass
        if len(fields) >= 9:
            try:
                charge_sum += float(fields[8])
                has_charge = True
            except ValueError:
                pass
    z_span = max(z_values) - min(z_values) if z_values else None
    has_3d = bool(z_values) and abs(z_span or 0.0) > 1e-3
    return len(atom_lines), heavy, hydrogens, has_3d, z_span, charge_sum if has_charge else None


def _inspect_pdb_like(text: str, pdbqt: bool) -> tuple[int, int, int, bool, float | None, float | None, int | None]:
    atoms = []
    charge_sum = 0.0
    has_charge = False
    branch_count = 0
    for line in text.splitlines():
        if line.startswith("BRANCH"):
            branch_count += 1
        if line[:6].strip() not in {"ATOM", "HETATM"}:
            continue
        try:
            x = float(line[30:38])
            y = float(line[38:46])
            z = float(line[46:54])
        except ValueError:
            continue
        element = _element_from_pdb_line(line)
        atoms.append((x, y, z, element))
        if pdbqt:
            fields = line.split()
            if len(fields) >= 2:
                try:
                    charge_sum += float(fields[-2])
                    has_charge = True
                except ValueError:
                    pass
    z_values = [atom[2] for atom in atoms]
    z_span = max(z_values) - min(z_values) if z_values else None
    heavy = sum(1 for atom in atoms if atom[3] != "H")
    hydrogens = sum(1 for atom in atoms if atom[3] == "H")
    has_3d = bool(atoms) and (abs(z_span or 0.0) > 1e-3 or len({(atom[0], atom[1], atom[2]) for atom in atoms}) > 1)
    return len(atoms), heavy, hydrogens, has_3d, z_span, charge_sum if has_charge else None, branch_count if pdbqt else None


def inspect_ligand(path: Path, name: str | None = None) -> LigandQC:
    path = Path(path)
    suffix = path.suffix.lower()
    text = path.read_text(encoding="utf-8", errors="replace")
    issues: list[QCIssue] = []
    molecule_count = 1
    atom_count = heavy = hydrogens = 0
    has_3d = False
    z_span = None
    formal_charge = None
    partial_charge_sum = None
    rotatable = None
    fragment_count = None

    if suffix == ".sdf":
        molecule_count = max(1, text.count("$$$$"))
        first_block = text.split("$$$$", 1)[0]
        atom_count, heavy, hydrogens, has_3d, z_span, formal_charge = _inspect_mol_block(first_block)
    elif suffix == ".mol":
        atom_count, heavy, hydrogens, has_3d, z_span, formal_charge = _inspect_mol_block(text)
    elif suffix == ".mol2":
        atom_count, heavy, hydrogens, has_3d, z_span, partial_charge_sum = _inspect_mol2(text)
    elif suffix in {".pdb", ".pdbqt"}:
        atom_count, heavy, hydrogens, has_3d, z_span, partial_charge_sum, rotatable = _inspect_pdb_like(text, suffix == ".pdbqt")
    elif suffix in {".smi", ".smiles"}:
        rows = [line.strip() for line in text.splitlines() if line.strip() and not line.lstrip().startswith("#")]
        molecule_count = len(rows)
        if rows:
            smiles = rows[0].split()[0]
            fragment_count = smiles.count(".") + 1
        issues.append(QCIssue("ligand.no_3d", "blocker", name or path.stem, "SMILES输入没有经过确认的三维坐标", "先确认盐/片段、手性、互变异构体、质子化状态并生成3D SDF或MOL2"))
    else:
        issues.append(QCIssue("ligand.unsupported_format", "blocker", name or path.stem, f"不支持的格式：{suffix}", "转换为SDF或MOL2"))

    subject = name or path.stem
    if molecule_count != 1:
        issues.append(QCIssue("ligand.multiple_molecules", "blocker", subject, f"文件包含{molecule_count}个分子", "拆分为单分子文件并逐一记录化学身份"))
    if suffix == ".pdb":
        issues.append(QCIssue("ligand.pdb_format", "warning", subject, "PDB不可靠保存小分子的键级和正式电荷", "优先使用SDF；至少人工核对键级、芳香性和正式电荷"))
    if suffix == ".pdbqt":
        issues.append(QCIssue("ligand.external_pdbqt", "confirm", subject, "输入已经是PDBQT，无法从该文件完整恢复原始键级和正式电荷", "保留对应SDF/MOL2和生成工具、版本、命令"))
    if suffix not in {".smi", ".smiles"} and atom_count == 0:
        issues.append(QCIssue("ligand.no_atoms", "blocker", subject, "未解析到原子", "检查文件完整性和格式"))
    if suffix not in {".smi", ".smiles"} and not has_3d:
        issues.append(QCIssue("ligand.planar_or_missing_3d", "blocker", subject, "没有检测到可信的三维坐标", "生成并检查3D构象后再对接"))
    if hydrogens == 0 and suffix not in {".smi", ".smiles", ".pdbqt"}:
        issues.append(QCIssue("ligand.no_hydrogens", "confirm", subject, "输入结构未显式包含氢", "在确定质子化和互变异构体后加氢"))
    if fragment_count and fragment_count > 1:
        issues.append(QCIssue("ligand.multiple_fragments", "blocker", subject, f"SMILES包含{fragment_count}个片段", "确认主化合物、去除对离子或明确多组分对接方案"))
    if formal_charge is None and suffix in {".sdf", ".mol"}:
        issues.append(QCIssue("ligand.formal_charge_unresolved", "confirm", subject, "未从MOL/SDF电荷记录中得到明确正式电荷", "人工核对正式电荷与实验pH"))
    if heavy > 0 and heavy >= 60:
        issues.append(QCIssue("ligand.large", "warning", subject, f"配体含{heavy}个重原子", "检查采样空间、柔性和是否需要更高采样或其他方法"))
    if rotatable is not None and rotatable >= 15:
        issues.append(QCIssue("ligand.high_flexibility", "warning", subject, f"PDBQT包含至少{rotatable}个BRANCH标记", "增加重复运行和采样，并检查构象收敛"))

    return LigandQC(
        name=subject,
        source=str(path.resolve()),
        file_format=suffix.lstrip(".").upper(),
        molecule_count=molecule_count,
        atom_count=atom_count,
        heavy_atom_count=heavy,
        hydrogen_count=hydrogens,
        has_3d_coordinates=has_3d,
        z_span_angstrom=z_span,
        formal_charge=formal_charge,
        partial_charge_sum=partial_charge_sum,
        rotatable_bond_markers=rotatable,
        fragment_count=fragment_count,
        issues=tuple(issues),
    )


def build_project_qc(config_path: Path) -> ProjectQC:
    config = WorkflowConfig.from_yaml(Path(config_path))
    mode = str(config.settings.get("scientific_mode", "standard")).strip().lower() or "standard"
    project_issues: list[QCIssue] = []
    receptors: list[ReceptorQC] = []
    ligands: list[LigandQC] = []

    if mode not in {"exploratory", "standard", "expert"}:
        project_issues.append(QCIssue("project.mode", "blocker", "project", f"未知科研模式：{mode}", "使用exploratory、standard或expert"))

    targets = load_targets(config.target_table)
    for target in targets:
        if target.structure_source == "local":
            source = Path(target.structure).expanduser()
            if not source.is_absolute():
                source = config.root / source
        else:
            source = config.work_dir / "raw" / f"{target.name}.pdb"
        if not source.exists():
            project_issues.append(QCIssue("receptor.source_missing", "blocker", target.name, f"受体文件不存在：{source}", "先获取或导入结构"))
            continue
        try:
            receptors.append(inspect_receptor(source, target))
        except Exception as error:
            project_issues.append(QCIssue("receptor.parse_failed", "blocker", target.name, str(error), "检查PDB格式和完整性"))

    try:
        ligand_sources = discover_ligands(config.ligand_dir)
    except Exception as error:
        project_issues.append(QCIssue("ligand.library", "blocker", "project", str(error), "导入至少一个单分子配体"))
        ligand_sources = {}
    for name, source in ligand_sources.items():
        try:
            ligands.append(inspect_ligand(source, name))
        except Exception as error:
            project_issues.append(QCIssue("ligand.parse_failed", "blocker", name, str(error), "检查配体格式和完整性"))

    if mode == "standard":
        if any(target.pocket_strategy == "blind" for target in targets):
            project_issues.append(QCIssue("project.standard_blind", "warning", "project", "标准科研模式包含盲对接任务", "结果等级将降为exploratory，优先补充位点证据"))
        if not any(target.pocket_strategy == "co_crystal" for target in targets):
            project_issues.append(QCIssue("project.no_redocking_reference", "confirm", "project", "没有共晶配体可用于回对接", "说明替代验证方法，如已知活性残基、阳性对照或文献位点"))

    return ProjectQC(
        config=str(Path(config_path).resolve()),
        mode=mode,
        receptors=tuple(receptors),
        ligands=tuple(ligands),
        project_issues=tuple(project_issues),
    )


def _json_ready(value):
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, tuple):
        return [_json_ready(item) for item in value]
    if isinstance(value, list):
        return [_json_ready(item) for item in value]
    if isinstance(value, dict):
        return {key: _json_ready(item) for key, item in value.items()}
    return value


def write_project_qc(report: ProjectQC, output_dir: Path) -> dict[str, Path]:
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    json_path = output_dir / "project_qc.json"
    tsv_path = output_dir / "project_qc_issues.tsv"
    markdown_path = output_dir / "project_qc.md"

    json_path.write_text(json.dumps(_json_ready(asdict(report)), ensure_ascii=False, indent=2), encoding="utf-8")
    with tsv_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle, delimiter="\t")
        writer.writerow(["level", "code", "subject", "message", "recommendation"])
        for issue in report.issues:
            writer.writerow([issue.level, issue.code, issue.subject, issue.message, issue.recommendation])

    lines = [
        "# DockFlow 项目质量控制报告",
        "",
        f"- 配置：`{report.config}`",
        f"- 科研模式：`{report.mode}`",
        f"- 受体：{len(report.receptors)}",
        f"- 配体：{len(report.ligands)}",
        f"- 阻断项：{len(report.blockers)}",
        f"- 警告/待确认：{len(report.warnings)}",
        f"- 是否可继续：{'是' if report.ready else '否'}",
        "",
        "## 问题清单",
        "",
    ]
    if not report.issues:
        lines.append("未发现问题。")
    for issue in report.issues:
        lines.append(f"- **{issue.level.upper()}** `{issue.code}` · {issue.subject}：{issue.message}")
        if issue.recommendation:
            lines.append(f"  - 建议：{issue.recommendation}")
    lines.extend(["", "## 受体摘要", ""])
    for receptor in report.receptors:
        lines.append(
            f"- **{receptor.target}**：{receptor.protein_atom_count}个蛋白原子，"
            f"{receptor.residue_count}个残基，链={', '.join(receptor.chains)}，"
            f"水={receptor.water_residue_count}，口袋水={receptor.pocket_water_count}，"
            f"参考配体原子={receptor.reference_ligand_atom_count}"
        )
    lines.extend(["", "## 配体摘要", ""])
    for ligand in report.ligands:
        lines.append(
            f"- **{ligand.name}**：{ligand.file_format}，{ligand.heavy_atom_count}个重原子，"
            f"3D={'是' if ligand.has_3d_coordinates else '否'}，正式电荷={ligand.formal_charge}，"
            f"部分电荷和={ligand.partial_charge_sum}"
        )
    markdown_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return {"json": json_path, "tsv": tsv_path, "markdown": markdown_path}
