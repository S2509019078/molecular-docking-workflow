from pathlib import Path

import yaml

from dockflow.reporting import build_project_report, parse_plip_report, summarize_rows


def _project(tmp_path: Path) -> Path:
    (tmp_path / "config").mkdir()
    (tmp_path / "results" / "viewer").mkdir(parents=True)
    (tmp_path / "results" / "plip" / "T" / "L1").mkdir(parents=True)
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
    (tmp_path / "results" / "docking_summary.tsv").write_text(
        "target\tligand\taffinity_kcal_mol\treference_center_distance_angstrom\tclassification\tevidence\tpose\n"
        "T\tL1\t-9.1\t2.1\treference_consistent\thigh\twork/poses/T/L1.pdbqt\n"
        "T\tL2\t-7.0\t\texploratory\tlow\twork/poses/T/L2.pdbqt\n",
        encoding="utf-8",
    )
    (tmp_path / "results" / "viewer" / "T__L1.html").write_text("viewer", encoding="utf-8")
    (tmp_path / "results" / "plip" / "T" / "L1" / "report.txt").write_text(
        "HYDROGEN BONDS\nHYDROPHOBIC INTERACTIONS\nSALT BRIDGES\n",
        encoding="utf-8",
    )
    return config_path


def test_summarize_rows_selects_best_and_counts():
    summary = summarize_rows([
        {"target": "A", "ligand": "x", "affinity_kcal_mol": "-6.0", "classification": "exploratory"},
        {"target": "B", "ligand": "y", "affinity_kcal_mol": "-9.0", "classification": "reference_consistent"},
    ])
    assert summary.best_target == "B"
    assert summary.best_ligand == "y"
    assert summary.best_affinity == -9.0
    assert summary.result_count == 2


def test_parse_plip_report(tmp_path):
    report = tmp_path / "report.txt"
    report.write_text("HYDROGEN BONDS\nPI-STACKING\nMETAL COMPLEXES\n", encoding="utf-8")
    counts = parse_plip_report(report)
    assert counts["hydrogen_bonds"] == 1
    assert counts["pi_stacking"] == 1
    assert counts["metal_complexes"] == 1


def test_build_project_report(tmp_path):
    output = build_project_report(_project(tmp_path))
    html = output.read_text(encoding="utf-8")
    csv_path = output.parent / "docking_results.csv"
    assert output.exists()
    assert csv_path.exists()
    assert "DockFlow 分子对接项目报告" in html
    assert "-9.10" in html
    assert "hydrogen_bonds: 1" in html
    assert "../viewer/T__L1.html" in html
