from __future__ import annotations

from pathlib import Path
from dataclasses import dataclass
import json

from .config import WorkflowConfig
from .preprocess_status import build_preparation_status
from .receptor_plan import build_receptor_preparation_plan, write_receptor_preparation_plan
from .config import load_targets


@dataclass(frozen=True)
class StageReport:
    stage: str
    status: str
    message: str
    files: tuple[str, ...] = ()


def build_preparation_report(config_path: Path) -> Path:
    config = WorkflowConfig.from_yaml(Path(config_path))
    stages: list[StageReport] = []

    status = build_preparation_status(config_path)
    stages.append(
        StageReport(
            "environment",
            "ready" if status.tools_ready else "blocked",
            f"{len(status.blockers)} blocking tool checks",
        )
    )

    plans_dir = config.result_dir / "preparation" / "receptor_plans"
    targets = load_targets(config.target_table)
    plan_files = []
    for target in targets:
        if target.structure_source == "local":
            source = Path(target.structure).expanduser()
            if not source.is_absolute():
                source = config.root / source
        else:
            source = config.work_dir / "raw" / f"{target.name}.pdb"
        if not source.exists():
            stages.append(StageReport("receptor", "blocked", f"missing structure: {source}"))
            continue
        plan = build_receptor_preparation_plan(source, target, config.settings)
        outputs = write_receptor_preparation_plan(plan, None, plans_dir)
        plan_files.extend(str(path) for path in outputs.values())
        stages.append(
            StageReport(
                f"receptor:{target.name}",
                "review" if plan.unresolved else "ready",
                f"keep={len(plan.kept)}, remove={len(plan.removed)}, review={len(plan.unresolved)}",
                tuple(str(path) for path in outputs.values()),
            )
        )

    output = config.result_dir / "preparation_report.json"
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps(
            {
                "config": str(config.path),
                "stages": [stage.__dict__ for stage in stages],
                "files": plan_files,
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    return output
