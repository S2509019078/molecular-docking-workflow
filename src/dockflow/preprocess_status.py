from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from .commands import discover_tool
from .config import WorkflowConfig, load_targets
from .preparation import discover_ligands


@dataclass(frozen=True)
class PreparationCheck:
    key: str
    stage: str
    label: str
    state: str
    detail: str
    blocking: bool = False


@dataclass(frozen=True)
class PreparationStatus:
    checks: tuple[PreparationCheck, ...]

    @property
    def blockers(self) -> tuple[PreparationCheck, ...]:
        return tuple(item for item in self.checks if item.blocking and item.state not in {"完成", "不适用"})

    @property
    def tools_ready(self) -> bool:
        return not any(item.blocking and item.stage == "环境" and item.state != "完成" for item in self.checks)

    @property
    def complete(self) -> bool:
        required = [item for item in self.checks if item.state not in {"提示", "不适用"}]
        return bool(required) and all(item.state == "完成" for item in required)


def _tool_check(config: WorkflowConfig, key: str, label: str, candidates: tuple[str, ...], required: bool = True) -> PreparationCheck:
    configured = str(config.tools.get(key, "") or "")
    resolved = discover_tool(configured or None, candidates)
    if resolved:
        return PreparationCheck(f"tool:{key}", "环境", label, "完成", str(resolved), required)
    return PreparationCheck(
        f"tool:{key}",
        "环境",
        label,
        "缺失" if required else "提示",
        "未检测到；请在“工具设置”中选择明确路径",
        required,
    )


def _file_check(key: str, stage: str, label: str, path: Path, detail: str = "") -> PreparationCheck:
    complete = path.exists() and path.is_file() and path.stat().st_size > 0
    return PreparationCheck(
        key,
        stage,
        label,
        "完成" if complete else "待处理",
        detail or str(path),
        False,
    )


def build_preparation_status(config_path: Path) -> PreparationStatus:
    config = WorkflowConfig.from_yaml(Path(config_path))
    checks: list[PreparationCheck] = [
        _tool_check(config, "mgltools_pythonsh", "AutoDockTools pythonsh", ("pythonsh.exe", "pythonsh")),
        _tool_check(config, "prepare_receptor4", "prepare_receptor4.py", ("prepare_receptor4.py",)),
        _tool_check(config, "prepare_ligand4", "prepare_ligand4.py", ("prepare_ligand4.py",)),
        _tool_check(config, "obabel", "Open Babel（仅格式转换）", ("obabel.exe", "obabel")),
        _tool_check(config, "vina", "AutoDock Vina", ("vina.exe", "vina")),
        _tool_check(config, "plip", "PLIP（可选）", ("plip.exe", "plip"), required=False),
    ]

    try:
        targets = load_targets(config.target_table)
    except Exception as error:
        checks.append(PreparationCheck("project:targets", "输入", "受体配置", "异常", str(error), True))
        return PreparationStatus(tuple(checks))

    try:
        ligands = discover_ligands(config.ligand_dir)
    except Exception as error:
        checks.append(PreparationCheck("project:ligands", "输入", "配体库", "异常", str(error), True))
        ligands = {}

    for target in targets:
        raw = config.work_dir / "raw" / f"{target.name}.pdb"
        clean = config.work_dir / "receptors_clean" / f"{target.name}.pdb"
        receptor_pdbqt = config.work_dir / "receptors_pdbqt" / f"{target.name}.pdbqt"
        box = config.work_dir / "boxes" / f"{target.name}.json"
        plan = config.result_dir / "preparation" / "receptor_plans" / f"{target.name}.json"
        checks.extend([
            _file_check(f"receptor:{target.name}:raw", "受体", f"原始结构 · {target.name}", raw),
            _file_check(f"receptor:{target.name}:plan", "受体", f"HETATM决策计划 · {target.name}", plan),
            _file_check(f"receptor:{target.name}:clean", "受体", f"清理后PDB · {target.name}", clean),
            _file_check(f"receptor:{target.name}:box", "口袋", f"搜索盒 · {target.name}", box),
            _file_check(
                f"receptor:{target.name}:pdbqt",
                "受体",
                f"AutoDockTools PDBQT · {target.name}",
                receptor_pdbqt,
                "补氢、Gasteiger部分电荷和AutoDock原子类型",
            ),
        ])

    for name, source in ligands.items():
        checks.append(PreparationCheck(f"ligand:{name}:input", "配体", f"输入 · {name}", "完成", source.name))
        if source.suffix.lower() in {".smi", ".smiles"}:
            checks.append(PreparationCheck(
                f"ligand:{name}:3d",
                "配体",
                f"三维化学结构 · {name}",
                "异常",
                "SMILES没有经确认的三维坐标；请提供已核对正式电荷、质子化和手性的3D SDF/MOL2",
                True,
            ))
        converted = config.work_dir / "ligands_converted" / f"{name}.mol2"
        if source.suffix.lower() in {".sdf", ".mol"}:
            checks.append(_file_check(
                f"ligand:{name}:converted",
                "配体",
                f"格式转换 · {name}",
                converted,
                "Open Babel仅转换格式，不改变化学状态",
            ))
        pdbqt = config.work_dir / "ligands_pdbqt" / f"{name}.pdbqt"
        checks.append(_file_check(
            f"ligand:{name}:pdbqt",
            "配体",
            f"AutoDockTools PDBQT · {name}",
            pdbqt,
            "补氢、Gasteiger部分电荷、AutoDock原子类型和可旋转键",
        ))

    summary = config.result_dir / "docking_summary.tsv"
    pose_index = config.result_dir / "docking_poses.tsv"
    checks.append(_file_check("results:summary", "结果", "对接汇总", summary))
    checks.append(_file_check("results:poses", "结果", "多构象索引", pose_index))
    return PreparationStatus(tuple(checks))
