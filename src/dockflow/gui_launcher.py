from __future__ import annotations

import os
import sys
from pathlib import Path


def _default_runs_dir() -> Path:
    documents = Path(os.environ.get("USERPROFILE", Path.home())) / "Documents"
    base = documents if documents.exists() else Path.home()
    return base / "DockFlow" / "runs"


def main(argv=None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    smoke_test = args == ["--gui-smoke-test"]
    from dockflow.gui import run_gui

    return int(run_gui(_default_runs_dir(), smoke_test=smoke_test) or 0)


if __name__ == "__main__":
    raise SystemExit(main())
