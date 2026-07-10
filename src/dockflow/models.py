from dataclasses import dataclass
from pathlib import Path
from typing import Optional

@dataclass(frozen=True)
class Atom:
    name: str; residue: str; chain: str; residue_id: int; x: float; y: float; z: float; record: str = "ATOM"

@dataclass(frozen=True)
class DockingBox:
    center: tuple[float, float, float]; size: tuple[float, float, float]

@dataclass(frozen=True)
class Target:
    name: str; structure_source: str; structure: str; pocket_strategy: str
    chain: str = ""; ligand: Optional[str] = None
    center: Optional[tuple[float, float, float]] = None
    size: Optional[tuple[float, float, float]] = None
    residue_ids: tuple[int, ...] = ()
    reference_ligand: Optional[str] = None
    predicted_pocket: Optional[str] = None

@dataclass(frozen=True)
class PocketDefinition:
    strategy: str; evidence: str; box: DockingBox
    reference_center: Optional[tuple[float, float, float]] = None
    rationale: str = ""

@dataclass(frozen=True)
class CommandResult:
    argv: tuple[str, ...]; returncode: int; stdout: str; stderr: str

@dataclass(frozen=True)
class StageSummary:
    stage: str; success: int; failed: int; skipped: int

