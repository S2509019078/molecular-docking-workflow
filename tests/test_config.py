import pytest

from dockflow.config import WorkflowConfig, load_targets


def test_load_target_supports_local_source_and_explicit_box(tmp_path):
    path = tmp_path / "targets.tsv"
    path.write_text(
        "name\tstructure_source\tstructure\tpocket_strategy\treceptor_chains\tcenter_x\tcenter_y\tcenter_z\tsize_x\tsize_y\tsize_z\tligands\n"
        "x\tlocal\tinputs/receptor.pdb\texplicit_box\tA,B\t1\t2\t3\t20\t21\t22\tlig1,lig2\n",
        encoding="utf-8",
    )
    target = load_targets(path)[0]
    assert target.name == "x"
    assert target.center == (1.0, 2.0, 3.0)
    assert target.size == (20.0, 21.0, 22.0)
    assert target.receptor_chains == ("A", "B")
    assert target.ligands == ("lig1", "lig2")


def test_config_rejects_missing_target_columns(tmp_path):
    path = tmp_path / "bad.tsv"
    path.write_text("name\nfoo\n", encoding="utf-8")
    with pytest.raises(ValueError, match="structure_source"):
        load_targets(path)


def test_explicit_box_requires_complete_size(tmp_path):
    path = tmp_path / "bad.tsv"
    path.write_text(
        "name\tstructure_source\tstructure\tpocket_strategy\tcenter_x\tcenter_y\tcenter_z\n"
        "x\tlocal\treceptor.pdb\texplicit_box\t1\t2\t3\n",
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="center and size"):
        load_targets(path)


def test_workflow_paths_are_relative_to_project_root(tmp_path):
    config_dir = tmp_path / "config"
    config_dir.mkdir()
    config_path = config_dir / "config.yaml"
    config_path.write_text("paths:\n  work: work\n", encoding="utf-8")
    config = WorkflowConfig.from_yaml(config_path)
    assert config.work_dir == tmp_path / "work"
