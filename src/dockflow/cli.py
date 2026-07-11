from pathlib import Path
import argparse

from .config import WorkflowConfig
from .pipeline import DockingWorkflow
from .pose_analysis import index_project_poses, run_plip_for_pose
from .scientific_qc import build_project_qc, write_project_qc
from .wizard import interactive_wizard


def _run_qc(config_path: Path) -> int:
    config = WorkflowConfig.from_yaml(config_path)
    report = build_project_qc(config_path)
    outputs = write_project_qc(report, config.result_dir / "qc")
    print(f"scientific mode: {report.mode}")
    print(f"receptors: {len(report.receptors)}")
    print(f"ligands: {len(report.ligands)}")
    print(f"blockers: {len(report.blockers)}")
    print(f"warnings/confirmations: {len(report.warnings)}")
    for issue in report.issues:
        print(f"[{issue.level}] {issue.code} · {issue.subject}: {issue.message}")
        if issue.recommendation:
            print(f"  recommendation: {issue.recommendation}")
    print(f"QC report: {outputs['markdown']}")
    if report.blockers:
        return 2
    if report.warnings:
        return 1
    return 0


def main(argv=None):
    parser = argparse.ArgumentParser(prog="dockflow", description="可复用 AutoDock/Vina 分子对接流程")
    parser.add_argument(
        "command",
        choices=[
            "wizard", "check", "qc", "pockets", "prepare-receptors", "prepare-ligands",
            "dock", "summarize", "index-poses", "plip", "plip-pose", "all", "status",
        ],
    )
    parser.add_argument("--config", type=Path, default=Path("config/config.yaml"))
    parser.add_argument("--runs-dir", type=Path, default=Path("runs"), help="wizard 创建独立运行目录的位置")
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--with-plip", action="store_true")
    parser.add_argument("--target", default="")
    parser.add_argument("--ligand", default="")
    parser.add_argument("--pose-rank", type=int, default=1)
    args = parser.parse_args(argv)

    if args.command == "wizard":
        interactive_wizard(base_dir=args.runs_dir)
        return 0

    config = WorkflowConfig.from_yaml(args.config)
    workflow = DockingWorkflow(config)

    if args.command == "check":
        problems = workflow.check(require_plip=args.with_plip)
        if problems:
            for item in problems:
                print(item)
            return 2
        print("environment OK")
        return 0
    if args.command == "qc":
        return _run_qc(args.config)
    if args.command == "status":
        state = config.work_dir / "state.json"
        print(state.read_text(encoding="utf-8") if state.exists() else "no tasks")
        return 0
    if args.command == "pockets":
        workflow.prepare_structures(force=args.force)
        return 0
    if args.command == "prepare-receptors":
        workflow.prepare_receptors(force=args.force)
        return 0
    if args.command == "prepare-ligands":
        workflow.prepare_ligands(force=args.force)
        return 0
    if args.command == "dock":
        workflow.dock(force=args.force)
        index_project_poses(args.config)
        return 0
    if args.command == "summarize":
        print(workflow.summarize())
        index_project_poses(args.config)
        return 0
    if args.command == "index-poses":
        records = index_project_poses(args.config)
        print(f"indexed {len(records)} poses")
        return 0
    if args.command == "plip":
        workflow.plip(force=args.force)
        return 0
    if args.command == "plip-pose":
        if not args.target or not args.ligand:
            parser.error("plip-pose requires --target and --ligand")
        print(run_plip_for_pose(args.config, args.target, args.ligand, args.pose_rank, force=args.force))
        return 0
    if args.command == "all":
        qc_exit = _run_qc(args.config)
        if qc_exit == 2:
            print("Docking blocked by scientific QC. Resolve blocker issues first.")
            return 2
        print(workflow.run_all(force=args.force, with_plip=args.with_plip))
        index_project_poses(args.config)
        return 0

    return 1


if __name__ == "__main__":
    raise SystemExit(main())
