from pathlib import Path
import argparse

from .config import WorkflowConfig
from .pipeline import DockingWorkflow


def main(argv=None):
    parser = argparse.ArgumentParser(prog="dockflow", description="可复用 AutoDock/Vina 分子对接流程")
    parser.add_argument("command", choices=["check", "pockets", "prepare-receptors", "prepare-ligands", "dock", "summarize", "plip", "all", "status"])
    parser.add_argument("--config", type=Path, default=Path("config/config.yaml"))
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--with-plip", action="store_true")
    args = parser.parse_args(argv)

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
        return 0
    if args.command == "summarize":
        print(workflow.summarize())
        return 0
    if args.command == "plip":
        workflow.plip(force=args.force)
        return 0
    if args.command == "all":
        print(workflow.run_all(force=args.force, with_plip=args.with_plip))
        return 0

    return 1


if __name__ == "__main__":
    raise SystemExit(main())
