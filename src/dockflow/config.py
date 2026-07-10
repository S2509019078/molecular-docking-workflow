from pathlib import Path
import csv
import yaml

from .models import Target

REQUIRED = {"name", "structure_source", "structure", "pocket_strategy"}


def _float(row: dict[str, str], key: str):
    value = (row.get(key) or "").strip()
    return float(value) if value else None


def _int(row: dict[str, str], key: str):
    value = (row.get(key) or "").strip()
    return int(value) if value else None


def load_targets(path: Path) -> list[Target]:
    if not path.exists():
        raise FileNotFoundError(path)
    with path.open(encoding="utf-8-sig", newline="") as fh:
        reader = csv.DictReader(fh, delimiter="\t")
        if reader.fieldnames is None:
            raise ValueError(f"empty target table: {path}")
        missing = REQUIRED - set(reader.fieldnames)
        if missing:
            raise ValueError(f"missing target columns: {', '.join(sorted(missing))}")
        rows = list(reader)
    if not rows:
        raise ValueError(f"target table contains no rows: {path}")

    seen: set[str] = set()
    result: list[Target] = []
    for row in rows:
        name = (row.get("name") or "").strip()
        if not name or name in seen:
            raise ValueError(f"duplicate or empty target name: {name!r}")
        seen.add(name)

        center_values = tuple(_float(row, f"center_{axis}") for axis in "xyz")
        center = None if any(v is None for v in center_values) else center_values
        size_values = tuple(_float(row, f"size_{axis}") for axis in "xyz")
        size = None if any(v is None for v in size_values) else size_values
        residue_ids = tuple(
            int(value.strip())
            for value in (row.get("residue_ids") or "").split(",")
            if value.strip()
        )
        result.append(
            Target(
                name=name,
                structure_source=(row.get("structure_source") or "").strip().lower(),
                structure=(row.get("structure") or "").strip(),
                pocket_strategy=(row.get("pocket_strategy") or "").strip().lower(),
                chain=(row.get("chain") or "").strip(),
                ligand=(row.get("ligand") or "").strip() or None,
                ligand_residue_id=_int(row, "ligand_residue_id"),
                center=center,
                size=size,
                residue_ids=residue_ids,
            )
        )
    return result


class WorkflowConfig:
    def __init__(self, data: dict, config_path: Path):
        self.data = data
        self.path = config_path.resolve()
        self.root = self.path.parent.parent
        self.tools = data.get("tools", {})
        self.settings = data.get("settings", {})
        self.paths = data.get("paths", {})

    @classmethod
    def from_yaml(cls, path: Path):
        if not path.exists():
            raise FileNotFoundError(path)
        with path.open(encoding="utf-8") as fh:
            data = yaml.safe_load(fh) or {}
        return cls(data, path)

    def path_value(self, key: str, default: str) -> Path:
        value = self.paths.get(key, default)
        path = Path(value).expanduser()
        return path if path.is_absolute() else self.root / path
