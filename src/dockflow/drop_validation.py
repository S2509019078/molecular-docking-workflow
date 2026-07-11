from __future__ import annotations

from pathlib import Path

from .ligand_library import SUPPORTED_LIGAND_SUFFIXES


def valid_pdb_drop(paths: list[Path]) -> bool:
    return len(paths) == 1 and paths[0].is_file() and paths[0].suffix.lower() == ".pdb"


def valid_ligand_drop(paths: list[Path]) -> bool:
    return bool(paths) and all(
        path.is_file() and path.suffix.lower() in SUPPORTED_LIGAND_SUFFIXES
        for path in paths
    )
