from datetime import datetime

import yaml

from dockflow.wizard import create_run_directory, detect_hetero_residues, write_project


def test_detect_hetero_residues_prioritizes_ligand_over_water_and_ion(tmp_path):
    pdb = tmp_path / "test.pdb"
    lines = [
        "HETATM    1  O   HOH A   1       0.000   0.000   0.000  1.00 20.00           O",
        "HETATM    2 ZN   ZN  A   2       0.000   0.000   0.000  1.00 20.00          ZN",
    ]
    for index in range(3, 10):
        lines.append(f"HETATM{index:5d}  C{index % 10}  LIG B 401      {index:6.3f}   0.000   0.000  1.00 20.00           C")
    pdb.write_text("\n".join(lines) + "\n", encoding="utf-8")
    rows = detect_hetero_residues(pdb)
    assert rows[0]["resname"] == "LIG"
    assert rows[0]["likely_ligand"] is True
    assert all(row["resname"] != "HOH" for row in rows)


def test_create_run_directory_is_isolated(tmp_path):
    now = datetime(2026, 7, 11, 9, 30, 0)
    first = create_run_directory(tmp_path, "my project", now=now)
    second = create_run_directory(tmp_path, "my project", now=now)
    assert first != second
    assert (first / "inputs" / "ligands").is_dir()
    assert second.name.endswith("_01")


def test_write_project_creates_relative_paths(tmp_path):
    run_dir = create_run_directory(tmp_path, "demo", now=datetime(2026, 7, 11, 9, 30, 0))
    target = {
        "name": "demo",
        "structure_source": "local",
        "structure": "inputs/structures/demo.pdb",
        "pocket_strategy": "blind",
    }
    config_path = write_project(run_dir, target)
    config = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    assert config["paths"]["work"] == "work"
    assert (run_dir / "config" / "targets.tsv").exists()
    assert (run_dir / "RUN_INFO.txt").exists()
