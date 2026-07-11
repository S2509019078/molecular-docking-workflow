from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import os
import shutil
import sys

from .commands import discover_tool


@dataclass(frozen=True)
class ToolSpec:
    key: str
    label: str
    candidates: tuple[str, ...]
    required: bool
    relative_paths: tuple[str, ...] = ()


TOOL_SPECS: tuple[ToolSpec, ...] = (
    ToolSpec(
        "mgltools_pythonsh",
        "AutoDockTools pythonsh",
        ("pythonsh.exe", "pythonsh"),
        True,
        (
            "pythonsh.exe",
            "bin/pythonsh.exe",
            "MGLTools-1.5.7/pythonsh.exe",
            "MGLTools-1.5.6/pythonsh.exe",
        ),
    ),
    ToolSpec(
        "prepare_receptor4",
        "prepare_receptor4.py",
        ("prepare_receptor4.py",),
        True,
        (
            "MGLToolsPckgs/AutoDockTools/Utilities24/prepare_receptor4.py",
            "AutoDockTools/Utilities24/prepare_receptor4.py",
            "Utilities24/prepare_receptor4.py",
        ),
    ),
    ToolSpec(
        "prepare_ligand4",
        "prepare_ligand4.py",
        ("prepare_ligand4.py",),
        True,
        (
            "MGLToolsPckgs/AutoDockTools/Utilities24/prepare_ligand4.py",
            "AutoDockTools/Utilities24/prepare_ligand4.py",
            "Utilities24/prepare_ligand4.py",
        ),
    ),
    ToolSpec(
        "obabel",
        "Open Babel",
        ("obabel.exe", "obabel"),
        True,
        (
            "bin/obabel.exe",
            "OpenBabel-3.1.1/bin/obabel.exe",
            "OpenBabel/bin/obabel.exe",
        ),
    ),
    ToolSpec(
        "vina",
        "AutoDock Vina",
        ("vina.exe", "vina"),
        True,
        ("vina.exe", "bin/vina.exe", "Vina/vina.exe"),
    ),
    ToolSpec(
        "plip",
        "PLIP",
        ("plip.exe", "plip"),
        False,
        ("plip.exe", "bin/plip.exe"),
    ),
)


def common_discovery_roots() -> list[Path]:
    values = [
        os.environ.get("DOCKFLOW_TOOLS_DIR"),
        os.environ.get("PROGRAMFILES"),
        os.environ.get("PROGRAMFILES(X86)"),
        os.environ.get("LOCALAPPDATA"),
        os.environ.get("USERPROFILE"),
        str(Path(sys.executable).resolve().parent),
        str(Path.home() / "Desktop"),
        str(Path.home() / "Downloads"),
        str(Path.home() / "Documents"),
        str(Path.home() / "tools"),
        "/usr/local/bin",
        "/opt",
    ]
    roots: list[Path] = []
    for value in values:
        if not value:
            continue
        path = Path(value).expanduser()
        if path.exists() and path not in roots:
            roots.append(path)
    return roots


def _known_candidate_paths(root: Path, spec: ToolSpec) -> list[Path]:
    candidates: list[Path] = []
    for relative in spec.relative_paths:
        candidates.append(root / Path(relative))
    for child_name in (
        "MGLTools-1.5.7",
        "MGLTools-1.5.6",
        "MGLTools",
        "AutoDockTools",
        "OpenBabel-3.1.1",
        "OpenBabel",
        "Vina",
        "PLIP",
        "DockFlowTools",
        "tools",
    ):
        child = root / child_name
        for relative in spec.relative_paths:
            candidates.append(child / Path(relative))
    return candidates


def find_in_directory(root: Path, spec: ToolSpec, *, recursive: bool = True) -> Path | None:
    root = Path(root).expanduser()
    if not root.exists():
        return None
    for candidate in _known_candidate_paths(root, spec):
        if candidate.is_file():
            return candidate.resolve()
    if not recursive:
        return None

    names = {name.lower() for name in spec.candidates}
    max_depth = 8
    root_depth = len(root.parts)
    skip_names = {".git", "node_modules", "site-packages", "windows", "$recycle.bin"}
    try:
        for current, directories, files in os.walk(root):
            current_path = Path(current)
            depth = len(current_path.parts) - root_depth
            directories[:] = [
                name for name in directories
                if depth < max_depth and name.lower() not in skip_names
            ]
            file_map = {name.lower(): name for name in files}
            for name in names:
                if name in file_map:
                    return (current_path / file_map[name]).resolve()
    except (OSError, PermissionError):
        return None
    return None


def discover_tools(
    configured: dict[str, str] | None = None,
    *,
    extra_roots: tuple[Path, ...] = (),
) -> dict[str, Path | None]:
    configured = configured or {}
    roots = list(extra_roots) + common_discovery_roots()
    result: dict[str, Path | None] = {}
    for spec in TOOL_SPECS:
        value = configured.get(spec.key, "").strip()
        resolved = discover_tool(value or None, spec.candidates)
        if resolved is None:
            for root in roots:
                resolved = find_in_directory(root, spec, recursive=False)
                if resolved:
                    break
        result[spec.key] = resolved
    return result


def discover_tools_in_directory(root: Path) -> dict[str, Path | None]:
    """Recursively scan a user-selected directory for all supported external tools."""
    root = Path(root).expanduser()
    return {
        spec.key: find_in_directory(root, spec, recursive=True)
        for spec in TOOL_SPECS
    }


def find_mgltools_components(root: Path) -> dict[str, Path | None]:
    root = Path(root).expanduser()
    wanted = {spec.key: spec for spec in TOOL_SPECS if spec.key in {
        "mgltools_pythonsh", "prepare_receptor4", "prepare_ligand4"
    }}
    return {key: find_in_directory(root, spec, recursive=True) for key, spec in wanted.items()}


def required_tool_problems(configured: dict[str, str] | None = None) -> list[str]:
    resolved = discover_tools(configured)
    labels = {spec.key: spec.label for spec in TOOL_SPECS}
    required = {spec.key for spec in TOOL_SPECS if spec.required}
    return [labels[key] for key in required if resolved.get(key) is None]


def executable_version(path: Path) -> str:
    path = Path(path)
    if not path.exists():
        return ""
    if path.suffix.lower() == ".py":
        return "Python script"
    found = shutil.which(str(path))
    return str(Path(found).resolve()) if found else str(path.resolve())
