from pathlib import Path
import os
import shutil
import subprocess
import sys

from .models import CommandResult


def _common_tool_roots() -> list[Path]:
    values = [
        os.environ.get("DOCKFLOW_TOOLS_DIR"),
        os.environ.get("PROGRAMFILES"),
        os.environ.get("PROGRAMFILES(X86)"),
        os.environ.get("LOCALAPPDATA"),
        str(Path(sys.executable).resolve().parent),
        "/usr/local/bin",
        "/opt",
        str(Path.home() / "bin"),
        str(Path.home() / "tools"),
    ]
    roots = []
    for value in values:
        if value:
            path = Path(value).expanduser()
            if path.exists() and path not in roots:
                roots.append(path)
    return roots


def discover_tool(configured: str | None, candidates: tuple[str, ...] = ()) -> Path | None:
    names = []
    if configured:
        expanded = Path(os.path.expandvars(configured)).expanduser()
        if expanded.is_file():
            return expanded.resolve()
        found = shutil.which(configured)
        if found:
            return Path(found).resolve()
        names.append(expanded.name)
    names.extend(name for name in candidates if name not in names)
    for candidate in candidates:
        found = shutil.which(candidate)
        if found:
            return Path(found).resolve()
    matches = []
    for root in _common_tool_roots():
        for name in names:
            direct = root / name
            if direct.is_file():
                matches.append(direct.resolve())
            for subdir in ("bin", "AutoDockTools", "MGLTools", "OpenBabel", "Vina", "PLIP", "DockFlow"):
                candidate = root / subdir / name
                if candidate.is_file():
                    matches.append(candidate.resolve())
    unique = list(dict.fromkeys(matches))
    return unique[0] if len(unique) == 1 else None


def require_tool(configured: str | None, candidates: tuple[str, ...], label: str) -> Path:
    path = discover_tool(configured, candidates)
    if path is None:
        supplied = configured or "/".join(candidates)
        raise FileNotFoundError(f"required tool not found or ambiguous: {label} ({supplied}); configure an explicit path or add it to PATH")
    return path


def run_command(argv: list[str], log_path: Path, cwd: Path | None = None) -> CommandResult:
    log_path.parent.mkdir(parents=True, exist_ok=True)
    process = subprocess.run(argv, cwd=cwd, text=True, capture_output=True, check=False)
    text = process.stdout
    if process.stderr:
        text += ("\n" if text else "") + "STDERR\n" + process.stderr
    log_path.write_text(text, encoding="utf-8", errors="replace")
    return CommandResult(tuple(argv), process.returncode, process.stdout, process.stderr)
