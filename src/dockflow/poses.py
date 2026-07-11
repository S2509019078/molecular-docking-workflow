from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import csv
import re


@dataclass(frozen=True)
class PoseRecord:
    target: str
    ligand: str
    rank: int
    affinity: float | None
    path: Path


def split_vina_poses(source: Path, output_dir: Path, target: str, ligand: str) -> list[PoseRecord]:
    source = Path(source)
    if not source.is_file():
        raise FileNotFoundError(source)
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    lines = source.read_text(encoding="utf-8", errors="replace").splitlines()
    blocks: list[list[str]] = []
    current: list[str] = []
    in_model = False
    for line in lines:
        if line.startswith("MODEL"):
            if current:
                blocks.append(current)
            current = [line]
            in_model = True
        elif line.startswith("ENDMDL"):
            current.append(line)
            blocks.append(current)
            current = []
            in_model = False
        elif in_model:
            current.append(line)
        elif not blocks:
            current.append(line)
    if current:
        blocks.append(current)
    if not blocks:
        blocks = [lines]

    records: list[PoseRecord] = []
    for rank, block in enumerate(blocks, start=1):
        affinity = None
        for line in block:
            match = re.search(r"REMARK\s+VINA\s+RESULT:\s+(-?\d+(?:\.\d+)?)", line)
            if match:
                affinity = float(match.group(1))
                break
        path = output_dir / f"mode_{rank:02d}.pdbqt"
        path.write_text("\n".join(block).rstrip() + "\n", encoding="utf-8")
        records.append(PoseRecord(target, ligand, rank, affinity, path))
    return records


def write_pose_index(records: list[PoseRecord], destination: Path, root: Path | None = None) -> Path:
    destination = Path(destination)
    destination.parent.mkdir(parents=True, exist_ok=True)
    with destination.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle, delimiter="\t")
        writer.writerow(["target", "ligand", "pose_rank", "affinity_kcal_mol", "pose"])
        for record in records:
            path = record.path
            if root is not None:
                try:
                    path = path.resolve().relative_to(Path(root).resolve())
                except ValueError:
                    pass
            writer.writerow([
                record.target,
                record.ligand,
                record.rank,
                "" if record.affinity is None else f"{record.affinity:.3f}",
                path,
            ])
    return destination


def load_pose_index(path: Path, root: Path | None = None) -> list[PoseRecord]:
    path = Path(path)
    if not path.exists():
        return []
    rows: list[PoseRecord] = []
    with path.open("r", encoding="utf-8", newline="") as handle:
        for row in csv.DictReader(handle, delimiter="\t"):
            pose = Path(row["pose"])
            if root is not None and not pose.is_absolute():
                pose = Path(root) / pose
            affinity_text = row.get("affinity_kcal_mol", "")
            rows.append(PoseRecord(
                row.get("target", ""),
                row.get("ligand", ""),
                int(row.get("pose_rank", "1")),
                float(affinity_text) if affinity_text else None,
                pose.resolve(),
            ))
    return rows
