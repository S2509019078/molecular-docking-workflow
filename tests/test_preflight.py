from pathlib import Path

import yaml

from dockflow.preflight import build_preflight


def _write_project(tmp_path: Path, pocket_strategy: str = "blind") -> Path:
    (tmp_path / "config").mkdir()
    (tmp_path / "inputs" / "ligands").mkdir(parents=True)
    (tmp_path / "inputs" / "structures").mkdir(parents=True)
    (tmp_path / "work").mkdir()
    (tmp_path / "results").mkdir()
    (tmp_path / "inputs" / "ligands" / "a.pdbqt").write_text("ATOM\n", encoding="utf-8")
    (tmp_path / "inputs" / "ligands" / "b.pdbqt").write_text("ATOM\n", encoding="utf-8")
    (tmp_path / "inputs" / "structures" / "protein.pdb").write_text("ATOM\n", encoding="utf-8")
    (tmp_path / "config" / "targets.tsv").write_text(
        "name\tstructure_source\tstructure\tpocket_strategy\n"
        f"target\tlocal\tinputs/structures/protein.pdb\t{pocket_strategy}\n",
        encoding="utf-8",
    )
    config = {
        "tools": {
            "mgltools_pythonsh": "python",
            "prepare_receptor4": "python",
            "prepare_ligand4": "python",
            "obabel": "python",
            "vina": "python",
        },
        "paths": {
            "targets": "config/targets.tsv",
            "ligands": "inputs/ligands",
            "work": "work",
            "results": "results",
        },
    }
    config_path = tmp_path / "config" / "config.yaml"
    config_path.write_text(yaml.safe_dump(config), encoding="utf-8")
    return config_path


def test_preflight_counts_tasks_and_blind_warning(tmp_path):
    report = build_preflight(_write_project(tmp_path))
    assert report.target_count == 1
    assert report.ligand_count == 2
    assert report.docking_task_count == 2
    assert any("盲对接" in warning for warning in report.warnings)


def test_preflight_ready_when_tools_and_inputs_exist(tmp_path):
    report = build_preflight(_write_project(tmp_path, pocket_strategy="blind"))
    assert report.ready
