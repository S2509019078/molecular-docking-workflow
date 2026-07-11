from __future__ import annotations

import os
import sys
import tempfile
import traceback
from pathlib import Path


def _default_runs_dir() -> Path:
    documents = Path(os.environ.get("USERPROFILE", Path.home())) / "Documents"
    base = documents if documents.exists() else Path.home()
    return base / "DockFlow" / "runs"


def _error_log_path() -> Path:
    return Path(tempfile.gettempdir()) / "DockFlow-gui-error.txt"


def main(argv=None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    smoke_test = args == ["--gui-smoke-test"]
    try:
        from dockflow.gui_viewers import run_gui

        return int(run_gui(_default_runs_dir(), smoke_test=smoke_test) or 0)
    except Exception:
        details = traceback.format_exc()
        _error_log_path().write_text(details, encoding="utf-8", errors="replace")
        if smoke_test:
            print(details, file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
