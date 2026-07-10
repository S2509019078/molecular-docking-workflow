from dataclasses import dataclass
from pathlib import Path
import math
import re

from .models import PocketDefinition


@dataclass(frozen=True)
class QCRecord:
    affinity: float | None
    distance: float | None
    classification: str
    evidence: str
    reason: str


def parse_vina_affinities(path: Path):
    values = []
    for line in path.read_text(errors="replace").splitlines():
        match = re.match(r"\s*\d+\s+(-?\d+(?:\.\d+)?)\s+", line)
        if match:
            values.append(float(match.group(1)))
    return values


def best_affinity(log_path: Path, pose_path: Path | None = None):
    values = parse_vina_affinities(log_path)
    if values:
        return min(values)
    if pose_path and pose_path.exists():
        values = parse_vina_affinities(pose_path)
        return min(values) if values else None
    return None


def pose_center(path: Path):
    xyz = []
    for line in path.read_text(errors="replace").splitlines():
        if line[:6].strip() in {"ATOM", "HETATM"}:
            try:
                xyz.append(tuple(float(line[i:i + 8]) for i in (30, 38, 46)))
            except ValueError:
                pass
    if not xyz:
        return None
    return tuple(sum(point[i] for point in xyz) / len(xyz) for i in range(3))


def _distance(a, b):
    return math.sqrt(sum((x - y) ** 2 for x, y in zip(a, b)))


def classify_result(affinity, center, pocket: PocketDefinition, threshold=-8.0, distance_limit=5.0):
    if affinity is None:
        return QCRecord(None, None, "failed", pocket.evidence, "missing affinity")
    distance = _distance(center, pocket.reference_center) if center and pocket.reference_center else None
    if pocket.evidence == "reference" and affinity <= threshold and distance is not None and distance <= distance_limit:
        return QCRecord(affinity, distance, "high_confidence", pocket.evidence, "energy and reference distance pass")
    if affinity <= threshold:
        return QCRecord(affinity, distance, "exploratory" if pocket.evidence == "exploratory" else "manual_review", pocket.evidence, "energy passes; geometry requires review")
    return QCRecord(affinity, distance, "manual_review", pocket.evidence, "affinity threshold not met")
