from pathlib import Path
import shutil, subprocess
from .models import CommandResult

def discover_tool(configured, candidates):
    if configured:
        p = Path(configured).expanduser()
        return p if p.exists() else None
    for name in candidates:
        p = shutil.which(name)
        if p: return Path(p)
    return None

def run_command(argv: list[str], log_path: Path) -> CommandResult:
    log_path.parent.mkdir(parents=True, exist_ok=True)
    p = subprocess.run(argv, text=True, capture_output=True, check=False)
    log_path.write_text(p.stdout + ("\nSTDERR\n" + p.stderr if p.stderr else ""), encoding="utf-8", errors="replace")
    return CommandResult(tuple(argv), p.returncode, p.stdout, p.stderr)

