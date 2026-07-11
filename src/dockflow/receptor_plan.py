from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path
import csv
import json
import math

from .models import Atom, Target
from .scientific_qc import COMMON_COFACTORS, COMMON_METALS
from .structures import WATER_RESNAMES, read_atoms


@dataclass(frozen=True)
class HeteroDecision:
    residue: str
    chain: str
    residue_id: int
    insertion_code: str
    atom_count: int
    category: str
    action: str
    min_distance_to_reference_angstrom: float | None
    reason: str
    requires_confirmation: bool = False

    @property
    def key(self) -> tuple[str, int, str, str]:
        return self.chain, self.residue_id, self.insertion_code, self.residue


@dataclass(frozen=True)
class ReceptorPreparationPlan:
    target: str
    source: str
    receptor_chains: tuple[str, ...]
    pocket_water_cutoff_angstrom: float
    decisions: tuple[HeteroDecision, ...]
    warnings: tuple[str, ...]

    @property
    def unresolved(self) -> tuple[HeteroDecision, ...]:
        return tuple(item for item in self.decisions if item.action == "review" or item.requires_confirmation)

    @property
    def kept(self) -> tuple[HeteroDecision, ...]:
        return tuple(item for item in self.decisions if item.action == "keep")

    @property
    def removed(self) -> tuple[HeteroDecision, ...]:
        return tuple(item for item in self.decisions if item.action == "remove")


@dataclass(frozen=True)
class ReceptorCleaningSummary:
    target: str
    output: str
    protein_atom_count: int
    hetero_atom_count: int
    removed_hetero_atom_count: int
    removed_water_residue_count: int
    retained_hetero_residue_count: int
    review_residue_count: int
    review_action: str


def _residue_key(atom: Atom) -> tuple[str, int, str, str]:
    return atom.chain, atom.residue_id, atom.insertion_code, atom.residue


def _distance(first: Atom, second: Atom) -> float:
    return math.sqrt((first.x - second.x) ** 2 + (first.y - second.y) ** 2 + (first.z - second.z) ** 2)


def _reference_atoms(atoms: list[Atom], target: Target) -> list[Atom]:
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


def _minimum_distance(atoms: list[Atom], reference: list[Atom]) -> float | None:
    if not atoms or not reference:
        return None
    return min(_distance(first, second) for first in atoms for second in reference)


def _setting_bool(settings: dict, key: str, default: bool) -> bool:
    value = settings.get(key, default)
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() not in {"0", "false", "no", "off", "none", ""}


def build_receptor_preparation_plan(
    source: Path,
    target: Target,
    settings: dict | None = None,
) -> ReceptorPreparationPlan:
    settings = settings or {}
    atoms = read_atoms(Path(source))
    reference = _reference_atoms(atoms, target)
    cutoff = float(settings.get("pocket_water_cutoff_angstrom", 4.0))
    keep_pocket_waters = _setting_bool(settings, "keep_pocket_waters", False)
    auto_keep_metals = _setting_bool(settings, "auto_keep_metals", True)
    auto_keep_cofactors = _setting_bool(settings, "auto_keep_cofactors", True)
    unknown_policy = str(settings.get("unknown_hetero_policy", "review")).strip().lower()
    if unknown_policy not in {"keep", "remove", "review"}:
        raise ValueError(f"unsupported unknown_hetero_policy: {unknown_policy}")

    groups: dict[tuple[str, int, str, str], list[Atom]] = {}
    for atom in atoms:
        if atom.record == "HETATM":
            groups.setdefault(_residue_key(atom), []).append(atom)

    explicit_keep = set(target.keep_hetero_resnames)
    selected_chains = set(target.receptor_chains)
    decisions: list[HeteroDecision] = []
    warnings: list[str] = []

    for key, group in sorted(groups.items(), key=lambda item: (item[0][0], item[0][1], item[0][2], item[0][3])):
        chain, residue_id, insertion, residue = key
        minimum = _minimum_distance(group, reference)
        category = "unknown"
        action = unknown_policy
        reason = "未识别的HETATM，需根据生物学功能确认"
        requires_confirmation = action == "review"

        is_reference = bool(reference) and key in {_residue_key(atom) for atom in reference}
        if selected_chains and chain and chain not in selected_chains:
            category = "excluded_chain"
            action = "remove"
            reason = "位于未选择的受体链"
            requires_confirmation = False
        elif is_reference:
            category = "reference_ligand"
            action = "remove"
            reason = "共晶参考配体从受体中移除，并单独保存用于口袋和回对接"
            requires_confirmation = False
        elif residue in explicit_keep:
            category = "explicit_keep"
            action = "keep"
            reason = "目标表keep_hetero_resnames明确要求保留"
            requires_confirmation = False
        elif residue in WATER_RESNAMES:
            category = "water"
            if minimum is not None and minimum <= cutoff:
                action = "keep" if keep_pocket_waters else "review"
                reason = (
                    f"位于参考配体{minimum:.2f} Å内，可能是桥联水或催化水；"
                    + ("项目设置要求保留口袋水" if keep_pocket_waters else "需人工确认")
                )
                requires_confirmation = not keep_pocket_waters
            else:
                action = "remove"
                reason = "远离参考配体的结晶水，自动建议删除"
                requires_confirmation = False
        elif residue in COMMON_METALS:
            category = "metal"
            action = "keep" if auto_keep_metals else "review"
            reason = "金属可能参与配位或催化，默认保留并要求检查参数化"
            requires_confirmation = True
        elif residue in COMMON_COFACTORS:
            category = "cofactor"
            action = "keep" if auto_keep_cofactors else "review"
            reason = "常见辅因子可能构成活性位点，默认保留并要求确认"
            requires_confirmation = True
        elif minimum is not None and minimum <= 5.0:
            category = "pocket_hetero"
            action = "review"
            reason = f"未知HETATM位于参考配体{minimum:.2f} Å内，不能自动删除"
            requires_confirmation = True

        decisions.append(
            HeteroDecision(
                residue=residue,
                chain=chain,
                residue_id=residue_id,
                insertion_code=insertion,
                atom_count=len(group),
                category=category,
                action=action,
                min_distance_to_reference_angstrom=minimum,
                reason=reason,
                requires_confirmation=requires_confirmation,
            )
        )

    if not reference and target.pocket_strategy == "co_crystal":
        warnings.append("配置为co_crystal，但未找到参考配体；清理前必须修正配体标识")
    if not groups:
        warnings.append("未检测到HETATM；仍需检查缺失辅因子、金属或水是否因输入结构不完整而缺失")
    if any(item.category == "metal" for item in decisions):
        warnings.append("检测到金属：经典Vina/AutoDockTools参数可能不足，应检查配位体系和适用性")
    if any(item.action == "review" for item in decisions):
        warnings.append("存在待确认HETATM；自动执行时必须明确review_action，且报告中保留该决定")

    return ReceptorPreparationPlan(
        target=target.name,
        source=str(Path(source).resolve()),
        receptor_chains=target.receptor_chains,
        pocket_water_cutoff_angstrom=cutoff,
        decisions=tuple(decisions),
        warnings=tuple(warnings),
    )


def apply_receptor_preparation_plan(
    source: Path,
    target: Target,
    plan: ReceptorPreparationPlan,
    output: Path,
    *,
    review_action: str = "remove",
) -> ReceptorCleaningSummary:
    review_action = str(review_action).strip().lower()
    if review_action not in {"keep", "remove", "error"}:
        raise ValueError(f"unsupported review_action: {review_action}")
    if review_action == "error" and plan.unresolved:
        labels = ", ".join(
            f"{item.residue}:{item.chain or '-'}:{item.residue_id}{item.insertion_code}"
            for item in plan.unresolved
        )
        raise ValueError(f"receptor preparation has unresolved hetero residues: {labels}")

    decision_map = {item.key: item for item in plan.decisions}
    selected_chains = set(target.receptor_chains)
    kept: list[str] = []
    protein_atom_count = 0
    hetero_atom_count = 0
    removed_hetero_atom_count = 0
    removed_water_keys: set[tuple[str, int, str, str]] = set()
    retained_keys: set[tuple[str, int, str, str]] = set()
    review_keys: set[tuple[str, int, str, str]] = set()

    for line in Path(source).read_text(encoding="utf-8", errors="replace").splitlines():
        record = line[:6].strip()
        if record not in {"ATOM", "HETATM", "TER"}:
            continue
        if record == "TER":
            kept.append(line)
            continue
        chain = line[21:22].strip()
        if selected_chains and chain not in selected_chains:
            continue
        if line[16:17] not in {" ", "A"}:
            continue
        if record == "ATOM":
            kept.append(line)
            protein_atom_count += 1
            continue

        hetero_atom_count += 1
        residue = line[17:20].strip().upper()
        insertion = line[26:27].strip()
        try:
            residue_id = int(line[22:26])
        except ValueError:
            residue_id = 0
        key = (chain, residue_id, insertion, residue)
        decision = decision_map.get(key)
        action = decision.action if decision else "review"
        if action == "review":
            review_keys.add(key)
            action = review_action
        if action == "keep":
            kept.append(line)
            retained_keys.add(key)
        else:
            removed_hetero_atom_count += 1
            if residue in WATER_RESNAMES:
                removed_water_keys.add(key)

    if not any(line.startswith("ATOM") for line in kept):
        raise ValueError(f"cleaned receptor contains no protein atoms: {target.name}")
    output = Path(output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text("\n".join(kept) + "\nEND\n", encoding="utf-8")
    return ReceptorCleaningSummary(
        target=target.name,
        output=str(output.resolve()),
        protein_atom_count=protein_atom_count,
        hetero_atom_count=hetero_atom_count,
        removed_hetero_atom_count=removed_hetero_atom_count,
        removed_water_residue_count=len(removed_water_keys),
        retained_hetero_residue_count=len(retained_keys),
        review_residue_count=len(review_keys),
        review_action=review_action,
    )


def write_receptor_preparation_plan(
    plan: ReceptorPreparationPlan,
    summary: ReceptorCleaningSummary | None,
    output_dir: Path,
) -> dict[str, Path]:
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    stem = plan.target
    json_path = output_dir / f"{stem}.json"
    tsv_path = output_dir / f"{stem}.tsv"
    markdown_path = output_dir / f"{stem}.md"

    payload = {"plan": asdict(plan), "summary": asdict(summary) if summary else None}
    json_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    with tsv_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle, delimiter="\t")
        writer.writerow([
            "residue", "chain", "residue_id", "insertion_code", "atom_count", "category",
            "action", "requires_confirmation", "distance_to_reference_angstrom", "reason",
        ])
        for item in plan.decisions:
            writer.writerow([
                item.residue,
                item.chain,
                item.residue_id,
                item.insertion_code,
                item.atom_count,
                item.category,
                item.action,
                str(item.requires_confirmation).lower(),
                "" if item.min_distance_to_reference_angstrom is None else f"{item.min_distance_to_reference_angstrom:.3f}",
                item.reason,
            ])

    lines = [
        f"# 受体预处理计划：{plan.target}",
        "",
        f"- 来源：`{plan.source}`",
        f"- 保留链：{', '.join(plan.receptor_chains) if plan.receptor_chains else '未限定'}",
        f"- 口袋水阈值：{plan.pocket_water_cutoff_angstrom:.2f} Å",
        f"- 保留HETATM残基：{len(plan.kept)}",
        f"- 删除HETATM残基：{len(plan.removed)}",
        f"- 待确认：{len(plan.unresolved)}",
        "",
        "## HETATM决策",
        "",
    ]
    for item in plan.decisions:
        distance = "—" if item.min_distance_to_reference_angstrom is None else f"{item.min_distance_to_reference_angstrom:.2f} Å"
        lines.append(
            f"- **{item.action.upper()}** `{item.residue}:{item.chain or '-'}:{item.residue_id}{item.insertion_code}` "
            f"· {item.category} · 距参考配体 {distance}：{item.reason}"
        )
    if plan.warnings:
        lines.extend(["", "## 警告", ""])
        lines.extend(f"- {warning}" for warning in plan.warnings)
    if summary:
        lines.extend([
            "",
            "## 执行摘要",
            "",
            f"- 蛋白原子：{summary.protein_atom_count}",
            f"- HETATM原子：{summary.hetero_atom_count}",
            f"- 删除HETATM原子：{summary.removed_hetero_atom_count}",
            f"- 删除水残基：{summary.removed_water_residue_count}",
            f"- 保留HETATM残基：{summary.retained_hetero_residue_count}",
            f"- 待确认残基：{summary.review_residue_count}",
            f"- 待确认处理策略：`{summary.review_action}`",
        ])
    markdown_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return {"json": json_path, "tsv": tsv_path, "markdown": markdown_path}
