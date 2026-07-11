from datetime import datetime
from pathlib import Path

import yaml

from dockflow.desktop import create_gui_project, inspect_structure, load_summary, recent_configs


def _pdb_line(record, serial, atom, resname, chain, resid):
    return f"{record:<6}{serial:>5} {atom:<4} {resname:>3} {chain:1}{resid:>4}    {0.0:>8.3f}{0.0:>8.3f}{0.0:>8.3f}  1.00 20.00           C\n"


def test_inspect_structure_detects_chains_and_ligands(tmp_path):
    pdb = tmp_path / "protein.pdb"
    text = _pdb_line("ATOM", 1, "CA", "ALA", "A", 1)
    text += _pdb_line("ATOM", 2, "CA", "GLY", "B", 2)
    for serial in range(3, 9):
        text += _pdb_line("HETATM", serial, f"C{serial}", "LIG", "A", 101)
    pdb.write_text(text, encoding="utf-8")
    inspection = inspect_structure(pdb)
    assert inspection.chains == ("A", "B")
    assert inspection.ligands[0]["resname"] == "LIG"


def test_create_gui_project_copies_inputs_and_settings(tmp_path):
    pdb = tmp_path / "protein.pdb"
    pdb.write_text(_pdb_line("ATOM", 1, "CA", "ALA", "A", 1), encoding="utf-8")
    ligand = tmp_path / "compound.sdf"
    ligand.write_text("ligand", encoding="utf-8")
    config = create_gui_project(
        base_dir=tmp_path / "runs",
        project_name="GUI project",
        pdb_path=pdb,
        receptor_chains=("A",),
        selected_ligand=None,
        ligand_files=[ligand],
        tools={"vina": "vina"},
        settings={"exhaustiveness": 24, "cpu": 3},
    )
    run_dir = config.parent.parent
    assert (run_dir / "inputs" / "structures" / "GUI_project.pdb").exists()
    assert (run_dir / "inputs" / "ligands" / "compound.sdf").exists()
    data = yaml.safe_load(config.read_text(encoding="utf-8"))
    assert data["settings"]["exhaustiveness"] == 24
    assert data["settings"]["cpu"] == 3


def test_load_summary_and_recent_configs(tmp_path):
    run = tmp_path / "runs" / "20260101_demo"
    (run / "config").mkdir(parents=True)
    config = run / "config" / "config.yaml"
    config.write_text("paths: {}\n", encoding="utf-8")
    results = run / "results"
    results.mkdir()
    summary = results / "docking_summary.tsv"
    summary.write_text("target\tligand\taffinity_kcal_mol\nT\tL\t-8.5\n", encoding="utf-8")
    assert load_summary(summary)[0]["affinity_kcal_mol"] == "-8.5"
    assert recent_configs(tmp_path / "runs") == [config]
