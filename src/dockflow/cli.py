from pathlib import Path
import argparse, json
from .config import WorkflowConfig, load_targets
from .structures import acquire_structure, read_atoms
from .pockets import resolve_pocket

def main(argv=None):
    ap=argparse.ArgumentParser(prog="dockflow", description="可复用分子对接流程")
    ap.add_argument("command", choices=["check","pockets","status"])
    ap.add_argument("--config", type=Path, default=Path("config/config.yaml"))
    args=ap.parse_args(argv)
    if args.command == "check":
        print(f"config: {args.config} {'OK' if args.config.exists() else 'MISSING'}")
        return 0 if args.config.exists() else 2
    if args.command == "status":
        path=Path("work/state.json"); print(path.read_text(encoding="utf-8") if path.exists() else "no tasks")
        return 0
    targets=load_targets(args.config.parent / "targets.tsv")
    for t in targets:
        path=acquire_structure(t, Path("work/raw")); pocket=resolve_pocket(t, read_atoms(path)); print(t.name, pocket.strategy, pocket.box.center, pocket.evidence)
    return 0

if __name__ == "__main__":
    raise SystemExit(main())

