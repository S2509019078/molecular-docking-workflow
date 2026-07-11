from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from .commands import discover_tool
from .config import WorkflowConfig
from .desktop import load_summary
from .preparation import resolve_preparation_backend


@dataclass(frozen=True)
class ToolDiagnostic:
    key: str
    label: str
    configured: str
    resolved: Path | None
    required: bool
    hint: str

    @property
    def available(self) -> bool:
        return self.resolved is not None


TOOL_SPECS = {
    "vina": ("AutoDock Vina", ("vina.exe", "vina"), True, "安装 AutoDock Vina，并选择 vina.exe"),
    "obabel": ("Open Babel", ("obabel.exe", "obabel"), True, "安装 Open Babel 3，并选择 obabel.exe"),
    "mgltools_pythonsh": ("MGLTools pythonsh", ("pythonsh.exe", "pythonsh"), False, "可选；安装后可使用 AutoDockTools 经典 PDBQT 预处理"),
    "prepare_receptor4": ("prepare_receptor4.py", ("prepare_receptor4.py",), False, "可选；与完整 MGLTools 后端配套使用"),
    "prepare_ligand4": ("prepare_ligand4.py", ("prepare_ligand4.py",), False, "可选；与完整 MGLTools 后端配套使用"),
    "plip": ("PLIP", ("plip.exe", "plip"), False, "仅在需要相互作用分析时安装 PLIP"),
}


def diagnose_tools(config_path: Path) -> list[ToolDiagnostic]:
    config = WorkflowConfig.from_yaml(Path(config_path))
    requested = str(config.settings.get("preparation_backend", "auto"))
    try:
        backend = resolve_preparation_backend(config.tools, requested)
    except Exception:
        backend = requested.lower()
    rows = []
    for key, (label, candidates, required, hint) in TOOL_SPECS.items():
        configured = str(config.tools.get(key, "") or "")
        resolved = discover_tool(configured or None, candidates)
        effective_required = required
        if backend == "mgltools" and key in {"mgltools_pythonsh", "prepare_receptor4", "prepare_ligand4"}:
            effective_required = True
        rows.append(ToolDiagnostic(key, label, configured, resolved, effective_required, hint))
    return rows


def find_result_pose(config_path: Path, target: str, ligand: str) -> Path | None:
    config = WorkflowConfig.from_yaml(Path(config_path))
    rows = load_summary(config.result_dir / "docking_summary.tsv")
    for row in rows:
        if row.get("target") == target and row.get("ligand") == ligand:
            value = row.get("pose", "").strip()
            if not value:
                return None
            path = Path(value)
            if not path.is_absolute():
                path = config.root / path
            return path.resolve()
    return None
