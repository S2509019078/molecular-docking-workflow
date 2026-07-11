from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from .config import WorkflowConfig, load_targets
from .pipeline import DockingWorkflow
from .preparation import discover_ligands, preparation_backend_warning


@dataclass(frozen=True)
class PreflightReport:
    target_count: int
    ligand_count: int
    docking_task_count: int
    preparation_backend: str
    problems: tuple[str, ...]
    warnings: tuple[str, ...]

    @property
    def ready(self) -> bool:
        return not self.problems


def build_preflight(config_path: Path, require_plip: bool = False) -> PreflightReport:
    config = WorkflowConfig.from_yaml(Path(config_path))
    workflow = DockingWorkflow(config)
    problems = list(workflow.check(require_plip=require_plip))
    warnings: list[str] = []
    try:
        backend = workflow.preparation_backend()
        backend_warning = preparation_backend_warning(
            config.tools,
            str(config.settings.get("preparation_backend", "auto")),
        )
        if backend_warning:
            warnings.append(backend_warning)
    except Exception:
        backend = "unavailable"
    targets = load_targets(config.target_table)
    try:
        ligands = discover_ligands(config.ligand_dir)
    except Exception as error:
        ligands = {}
        if str(error) not in problems:
            problems.append(str(error))
    task_count = 0
    for target in targets:
        selected = target.ligands or tuple(ligands)
        task_count += len(selected)
        if target.pocket_strategy == "blind":
            warnings.append(f"{target.name}: 使用盲对接，结果仅适合探索性筛选")
    if task_count == 0 and not problems:
        problems.append("没有可执行的受体-配体组合")
    if task_count > 500:
        warnings.append(f"任务数为 {task_count}，运行时间和磁盘占用可能较大")
    return PreflightReport(
        len(targets),
        len(ligands),
        task_count,
        backend,
        tuple(problems),
        tuple(warnings),
    )
