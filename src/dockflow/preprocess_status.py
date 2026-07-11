from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from .commands import discover_tool
from .config import WorkflowConfig, load_targets
from .preparation import discover_ligands
from .structures import WATER_RESNAMES


@dataclass(frozen=True)
class PreparationCheck:
    key: str
    label: str
    state: str
    detail: str
    blocking: bool = False


@dataclass(frozen=True)
class PreparationStatus:
    checks: tuple[PreparationCheck, ...]

    @property
    def blockers(self) -> tuple[PreparationCheck, ...]:
        return tuple(check for check in self.checks if check.blocking and check.state != "完成")

    @property
    def complete(self) -> bool:
        required = [check for check in self.checks if check.state not in {"提示", "不适用"}]
        return bool(required) and all(check.state == "完成" for check in required)

    @property
    def tools_ready(self) -> bool:
        return not any(check.blocking and check.key.startswith("tool:") and check.state != "完成" for check in self.checks)


def _tool_check(config: WorkflowConfig, key: str, label: str, candidates: tuple[str, ...], required: bool = True) -> PreparationCheck:
    configured = str(config.tools.get(key, "") or "")
    resolved = discover_tool(configured or None, candidates)
    if resolved:
        return PreparationCheck(f"tool:{key}", label, "完成", str(resolved))
    detail = "未检测到；请在“工具设置”中选择明确路径"
    return PreparationCheck(f"tool:{key}", label, "缺失" if required else "提示", detail, blocking=required)


def _clean_receptor_checks(path: Path, selected_chains: tuple[str, ...]) -> list[PreparationCheck]:
    if not path.exists() or path.stat().st_size == 0:
        return [PreparationCheck("receptor:clean", "受体清理", "待处理", "尚未生成去水、去配体并按链筛选的受体PDB")]
    lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    atom_lines = [line for line in lines if line.startswith("ATOM")]
    hetero_lines = [line for line in lines if line.startswith("HETATM")]
    water_count = sum(1 for line in hetero_lines if line[17:20].strip().upper() in WATER_RESNAMES)
    chains = sorted({line[21:22].strip() for line in atom_lines if line[21:22].strip()})
    checks = [
        PreparationCheck("receptor:clean", "受体清理", "完成", f"{len(atom_lines)}个蛋白原子；{len(hetero_lines)}个保留异原子"),
        PreparationCheck(
            "receptor:water",
            "去除结晶水",
            "完成" if water_count == 0 else "异常",
            "未检测到水分子" if water_count == 0 else f"仍检测到{water_count}条水分子记录",
            blocking=water_count > 0,
        ),
    ]
    expected = tuple(chain for chain in selected_chains if chain)
    if expected:
        matched = set(chains) == set(expected)
        checks.append(PreparationCheck(
            "receptor:chains",
            "保留受体链",
            "完成" if matched else "异常",
            f"当前链：{', '.join(chains) or '无'}；目标链：{', '.join(expected)}",
            blocking=not matched,
        ))
    else:
        checks.append(PreparationCheck("receptor:chains", "保留受体链", "提示", f"当前链：{', '.join(chains) or '无'}；项目未限定单链"))
    return checks


def build_preparation_status(config_path: Path) -> PreparationStatus:
    config = WorkflowConfig.from_yaml(Path(config_path))
    checks: list[PreparationCheck] = [
        _tool_check(config, "mgltools_pythonsh", "AutoDockTools pythonsh", ("pythonsh.exe", "pythonsh")),
        _tool_check(config, "prepare_receptor4", "prepare_receptor4.py", ("prepare_receptor4.py",)),
        _tool_check(config, "prepare_ligand4", "prepare_ligand4.py", ("prepare_ligand4.py",)),
        _tool_check(config, "obabel", "Open Babel（仅格式转换）", ("obabel.exe", "obabel")),
        _tool_check(config, "vina", "AutoDock Vina", ("vina.exe", "vina")),
    ]

    try:
        targets = load_targets(config.target_table)
    except Exception as error:
        checks.append(PreparationCheck("project:targets", "受体配置", "异常", str(error), blocking=True))
        return PreparationStatus(tuple(checks))
    try:
        ligands = discover_ligands(config.ligand_dir)
    except Exception as error:
        checks.append(PreparationCheck("project:ligands", "配体输入", "异常", str(error), blocking=True))
        ligands = {}

    for target in targets:
        raw = config.work_dir / "raw" / f"{target.name}.pdb"
        clean = config.work_dir / "receptors_clean" / f"{target.name}.pdb"
        receptor_pdbqt = config.work_dir / "receptors_pdbqt" / f"{target.name}.pdbqt"
        checks.append(PreparationCheck(
            f"receptor:{target.name}:raw",
            f"受体原始结构 · {target.name}",
            "完成" if raw.exists() and raw.stat().st_size > 0 else "待处理",
            str(raw),
        ))
        checks.extend(_clean_receptor_checks(clean, target.receptor_chains))
        checks.append(PreparationCheck(
            f"receptor:{target.name}:pdbqt",
            "受体补氢、电荷与PDBQT",
            "完成" if receptor_pdbqt.exists() and receptor_pdbqt.stat().st_size > 0 else "待处理",
            "由AutoDockTools prepare_receptor4.py生成" if receptor_pdbqt.exists() else "等待AutoDockTools预处理",
        ))

    for name, source in ligands.items():
        suffix = source.suffix.lower()
        if suffix in {".smi", ".smiles"}:
            checks.append(PreparationCheck(
                f"ligand:{name}:3d",
                f"配体三维结构 · {name}",
                "异常",
                "SMILES没有经确认的三维坐标；请改用具有正确正式电荷和质子化状态的3D SDF/MOL2",
                blocking=True,
            ))
        else:
            checks.append(PreparationCheck(f"ligand:{name}:input", f"配体输入 · {name}", "完成", source.name))
        if suffix in {".sdf", ".mol"}:
            converted = config.work_dir / "ligands_converted" / f"{name}.mol2"
            checks.append(PreparationCheck(
                f"ligand:{name}:conversion",
                f"格式转换 · {name}",
                "完成" if converted.exists() and converted.stat().st_size > 0 else "待处理",
                "Open Babel仅转换为MOL2，不补氢、不最小化",
            ))
        pdbqt = config.work_dir / "ligands_pdbqt" / f"{name}.pdbqt"
        checks.append(PreparationCheck(
            f"ligand:{name}:pdbqt",
            f"配体补氢、电荷、转动键与PDBQT · {name}",
            "完成" if pdbqt.exists() and pdbqt.stat().st_size > 0 else "待处理",
            "由AutoDockTools prepare_ligand4.py生成" if pdbqt.exists() else "等待AutoDockTools预处理",
        ))

    checks.append(PreparationCheck(
        "chemistry:minimization",
        "配体能量最小化",
        "提示",
        "AutoDockTools不执行可靠的几何能量最小化；DockFlow不会伪装为已完成。请导入已优化并确认化学状态的3D结构。",
    ))
    return PreparationStatus(tuple(checks))
