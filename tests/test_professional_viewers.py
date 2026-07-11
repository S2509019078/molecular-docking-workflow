from pathlib import Path

import yaml

from dockflow.professional_viewers import build_chimerax_launch, build_pymol_launch, discover_viewer


def _project(tmp_path: Path) -> Path:
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
    (tmp_path / "work" / "receptors_clean" / "T.pdb").write_text("ATOM\n", encoding="utf-8")
    pose = tmp_path / "work" / "poses" / "T" / "L.pdbqt"
    pose.write_text("ATOM\n", encoding="utf-8")
    (tmp_path / "results" / "docking_summary.tsv").write_text(
        "target\tligand\taffinity_kcal_mol\tpose\nT\tL\t-8.6\twork/poses/T/L.pdbqt\n",
        encoding="utf-8",
    )
    return config_path


def test_discover_viewer_uses_configured_executable(tmp_path):
    executable = tmp_path / "viewer.exe"
    executable.write_bytes(b"x")
    assert discover_viewer("pymol", str(executable)) == executable.resolve()


def test_build_pymol_launch(tmp_path):
    config = _project(tmp_path)
    executable = tmp_path / "PyMOLWin.exe"
    executable.write_bytes(b"x")
    launch = build_pymol_launch(config, "T", "L", executable)
    text = launch.script.read_text(encoding="utf-8")
    assert "select pocket" in text
    assert "polar_contacts" in text
    assert "-8.6" in text
    assert launch.command[0] == str(executable)


def test_build_chimerax_launch(tmp_path):
    config = _project(tmp_path)
    executable = tmp_path / "ChimeraX.exe"
    executable.write_bytes(b"x")
    launch = build_chimerax_launch(config, "T", "L", executable)
    text = launch.script.read_text(encoding="utf-8")
    assert "hbonds" in text
    assert "select zone" in text
    assert "-8.6" in text
    assert launch.command[-1] == str(launch.script)
