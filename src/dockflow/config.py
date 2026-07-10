from pathlib import Path
import csv
try:
    import yaml
except ImportError:  # optional for target-table and structure-only commands
    yaml = None
from .models import Target

REQUIRED = {"name", "structure_source", "structure", "pocket_strategy"}

def _float(row, key):
    value = row.get(key, "").strip()
    return float(value) if value else None

def load_targets(path: Path) -> list[Target]:
    with path.open(encoding="utf-8-sig", newline="") as fh:
        rows = list(csv.DictReader(fh, delimiter="\t"))
    missing = REQUIRED - set(rows[0] if rows else [])
    if missing:
        raise ValueError(f"missing target columns: {', '.join(sorted(missing))}")
    seen, result = set(), []
    for row in rows:
        name = row["name"].strip()
        if not name or name in seen:
            raise ValueError(f"duplicate or empty target name: {name!r}")
        seen.add(name)
        center = tuple(_float(row, f"center_{axis}") for axis in "xyz")
        center = None if any(v is None for v in center) else center
        size = tuple(_float(row, f"size_{axis}") for axis in "xyz")
        size = None if any(v is None for v in size) else size
        result.append(Target(name, row["structure_source"].strip().lower(), row["structure"].strip(), row["pocket_strategy"].strip().lower(), row.get("chain", "").strip(), row.get("ligand", "").strip() or None, center, size, tuple(int(x) for x in row.get("residue_ids", "").split(",") if x.strip()), row.get("reference_ligand", "").strip() or None, row.get("predicted_pocket", "").strip() or None))
    return result

class WorkflowConfig:
    def __init__(self, data: dict, root: Path):
        self.data, self.root = data, root
        self.tools = data.get("tools", {})
        self.settings = data.get("settings", {})

    @classmethod
    def from_yaml(cls, path: Path):
        if yaml is None:
            raise RuntimeError("PyYAML is required to load config YAML; install with pip install PyYAML")
        with path.open(encoding="utf-8") as fh:
            return cls(yaml.safe_load(fh) or {}, path.parent.parent)

