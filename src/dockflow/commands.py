from pathlib import Path
import os
import shutil
import subprocess

from .models import CommandResult


def discover_tool(configured: str | None, candidates: tuple[str, ...] = ()) -> Path | None:
    if configured:
        expanded = Path(os.path.expandvars(configured)).expanduser()
        if expanded.is_file():
            return expanded.resolve()
        found = shutil.which(configured)
        return Path(found).resolve() if found else None
    for candidate in candidates:
        found = shutil.which(candidate)
        if found:
            return Path(found).resolve()
    return None


def require_tool(configured: str | None, candidates: tuple[str, ...], label: str) -> Path:
    path = discover_tool(configured, candidates)
    if path is None:
        supplied = configured or "/".join(candidates)
        raise FileNotFoundError(f"required tool not found: {label} ({supplied})")
    return path


def run_command(argv: list[str], log_path: Path, cwd: Path | None = None) -> CommandResult:
    log_path.parent.mkdir(parents=True, exist_ok=True)
    process = subprocess.run(argv, cwd=cwd, text=True, capture_output=True, check=False)
    text = process.stdout
    if process.stderr:
        text += ("\n" if text else "") + "STDERR\n" + process.stderr
    log_path.write_text(text, encoding="utf-8", errors="replace")
    return CommandResult(tuple(argv), process.returncode, process.stdout, process.stderr)
