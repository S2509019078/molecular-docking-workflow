from __future__ import annotations

import os
import sys
import traceback
from pathlib import Path

from dockflow.cli import main as cli_main


def _default_runs_dir() -> Path:
    documents = Path(os.environ.get("USERPROFILE", Path.home())) / "Documents"
    base = documents if documents.exists() else Path.home()
    return base / "DockFlow" / "runs"


def main(argv=None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    if args == ["--smoke-test"]:
        print("DockFlow executable OK")
        return 0
    if not args:
        args = ["wizard", "--runs-dir", str(_default_runs_dir())]
    try:
        return int(cli_main(args) or 0)
    except KeyboardInterrupt:
        print("\n操作已取消。")
        return 130
    except Exception as error:
        print("\nDockFlow 运行失败：")
        print(str(error))
        if os.environ.get("DOCKFLOW_DEBUG") == "1":
            traceback.print_exc()
        if getattr(sys, "frozen", False) and sys.stdin and sys.stdin.isatty():
            try:
                input("\n按回车键关闭窗口……")
            except EOFError:
                pass
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
