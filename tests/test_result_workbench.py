from pathlib import Path

import yaml

from dockflow.result_workbench import ResultFilter, build_3dmol_preview, export_results_csv, filter_results


def test_filter_results_search_classification_and_affinity():
    rows = [
        {"target": "A", "ligand": "aspirin", "affinity_kcal_mol": "-8.2", "classification": "reference_consistent"},
        {"target": "B", "ligand": "caffeine", "affinity_kcal_mol": "-6.1", "classification": "exploratory"},
    ]
    filtered = filter_results(rows, ResultFilter(query="asp", max_affinity=-7.0, classification="reference_consistent"))
    assert [row["ligand"] for row in filtered] == ["aspirin"]


def test_export_results_csv(tmp_path):
    output = export_results_csv([{"target": "A", "ligand": "L", "affinity_kcal_mol": "-9.0"}], tmp_path / "results.csv")
    text = output.read_text(encoding="utf-8-sig")
    assert "target,ligand,affinity_kcal_mol" in text
    assert "A,L,-9.0" in text


def test_build_3dmol_preview(tmp_path):
    (tmp_path / "config").mkdir()
    (tmp_path / "results").mkdir()
    (tmp_path / "work" / "receptors_clean").mkdir(parents=True)
    (tmp_path / "work" / "poses" / "T").mkdir(parents=True)
    config = {
        "tools": {},
        "paths": {
            "targets": "config/targets.tsv",
            "ligands": "inputs/ligands",
            "work": "work",
            "results": "results",
        },
    }
    config_path = tmp_path / "config" / "config.yaml"
    config_path.write_text(yaml.safe_dump(config), encoding="utf-8")
    (tmp_path / "config" / "targets.tsv").write_text("name\tstructure_source\tstructure\tpocket_strategy\n", encoding="utf-8")
    (tmp_path / "work" / "receptors_clean" / "T.pdb").write_text("ATOM      1  CA  ALA A   1       0.000   0.000   0.000\n", encoding="utf-8")
    pose = tmp_path / "work" / "poses" / "T" / "L.pdbqt"
    pose.write_text("ATOM      1  C1  LIG Z   1       1.000   1.000   1.000\n", encoding="utf-8")
    (tmp_path / "results" / "docking_summary.tsv").write_text(
        "target\tligand\taffinity_kcal_mol\tpose\nT\tL\t-8.1\twork/poses/T/L.pdbqt\n",
        encoding="utf-8",
    )
    output = build_3dmol_preview(config_path, "T", "L")
    html = output.read_text(encoding="utf-8")
    assert "3Dmol-min.js" in html
    assert "-8.1 kcal/mol" in html
    assert "greenCarbon" in html
