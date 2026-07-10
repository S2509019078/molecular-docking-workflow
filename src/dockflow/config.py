from pathlib import Path
import csv
import yaml

from .models import Target

REQUIRED_TARGET_COLUMNS = {"name", "structure_source", "structure", "pocket_strategy"}
SUPPORTED_POCKET_STRATEGIES = {"co_crystal", "explicit_box", "residue_box", "blind"}


def _optional_float(row: dict[str, str], key: str):
    value = (row.get(key) or "").strip()
    return float(value) if value else None


def _optional_int(row: dict[str, str], key: str):
    value = (row.get(key) or "").strip()
    return int(value) if value else None


def _split_csv(value: str | None) -> tuple[str, ...]:
    return tuple(item.strip() for item in (value or "").split(",") if item.strip())


def load_targets(path: Path) -> list[Target]:
    if not path.exists():
        raise FileNotFoundError(path)
    with path.open(encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle, delimiter="\t")
        if reader.fieldnames is None:
            raise ValueError(f"empty target table: {path}")
        missing = REQUIRED_TARGET_COLUMNS - set(reader.fieldnames)
        if missing:
            raise ValueError(f"missing target columns: {', '.join(sorted(missing))}")
        rows = list(reader)
    if not rows:
        raise ValueError(f"target table contains no rows: {path}")

    result: list[Target] = []
    seen: set[str] = set()
    for row in rows:
        name = (row.get("name") or "").strip()
        if not name or name in seen:
            raise ValueError(f"duplicate or empty target name: {name!r}")
        seen.add(name)

        strategy = (row.get("pocket_strategy") or "").strip().lower()
        if strategy not in SUPPORTED_POCKET_STRATEGIES:
            raise ValueError(f"unsupported pocket strategy for {name}: {strategy!r}")

        center_values = tuple(_optional_float(row, f"center_{axis}") for axis in "xyz")
        center = None if any(value is None for value in center_values) else center_values
        size_values = tuple(_optional_float(row, f"size_{axis}") for axis in "xyz")
        size = None if any(value is None for value in size_values) else size_values

        legacy_chain = (row.get("chain") or "").strip()
        receptor_chains = _split_csv(row.get("receptor_chains")) or ((legacy_chain,) if legacy_chain else ())
        ligand_chain = (row.get("ligand_chain") or "").strip() or legacy_chain
        residue_ids = tuple(int(value) for value in _split_csv(row.get("residue_ids")))

        target = Target(
            name=name,
            structure_source=(row.get("structure_source") or "").strip().lower(),
            structure=(row.get("structure") or "").strip(),
            pocket_strategy=strategy,
            receptor_chains=receptor_chains,
            ligand=(row.get("ligand") or "").strip().upper() or None,
            ligand_chain=ligand_chain,
            ligand_residue_id=_optional_int(row, "ligand_residue_id"),
            center=center,
            size=size,
            residue_ids=residue_ids,
            keep_hetero_resnames=tuple(value.upper() for value in _split_csv(row.get("keep_hetero_resnames"))),
        )
        validate_target(target)
        result.append(target)
    return result


def validate_target(target: Target) -> None:
    if target.structure_source not in {"pdb", "local"}:
        raise ValueError(f"unsupported structure source for {target.name}: {target.structure_source!r}")
    if not target.structure:
        raise ValueError(f"missing structure for {target.name}")
    if target.pocket_strategy == "co_crystal" and not target.ligand:
        raise ValueError(f"co_crystal requires ligand for {target.name}")
    if target.pocket_strategy == "explicit_box":
        if target.center is None or target.size is None:
            raise ValueError(f"explicit_box requires center and size for {target.name}")
        if any(value <= 0 for value in target.size):
            raise ValueError(f"box sizes must be positive for {target.name}")
    if target.pocket_strategy == "residue_box" and not target.residue_ids:
        raise ValueError(f"residue_box requires residue_ids for {target.name}")


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
        with path.open(encoding="utf-8") as handle:
            data = yaml.safe_load(handle) or {}
        return cls(data, path)

    def path_value(self, key: str, default: str) -> Path:
        value = self.paths.get(key, default)
        path = Path(value).expanduser()
        return path if path.is_absolute() else (self.root / path)

    @property
    def target_table(self) -> Path:
        return self.path_value("targets", "config/targets.tsv")

    @property
    def ligand_dir(self) -> Path:
        return self.path_value("ligands", "inputs/ligands")

    @property
    def work_dir(self) -> Path:
        return self.path_value("work", "work")

    @property
    def result_dir(self) -> Path:
        return self.path_value("results", "results")
