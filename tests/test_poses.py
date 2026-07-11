from pathlib import Path

from dockflow.poses import load_pose_index, split_vina_poses, write_pose_index


def test_split_vina_poses_and_index(tmp_path):
    source = tmp_path / "docked.pdbqt"
    source.write_text(
        "MODEL 1\n"
        "REMARK VINA RESULT: -8.200 0.000 0.000\n"
        "ATOM      1  C1  LIG Z   1       0.000   0.000   0.000\n"
        "ENDMDL\n"
        "MODEL 2\n"
        "REMARK VINA RESULT: -7.600 1.200 2.000\n"
        "ATOM      1  C1  LIG Z   1       1.000   0.000   0.000\n"
        "ENDMDL\n",
        encoding="utf-8",
    )
    records = split_vina_poses(source, tmp_path / "poses", "target", "ligand")
    assert [record.rank for record in records] == [1, 2]
    assert [record.affinity for record in records] == [-8.2, -7.6]
    assert all(record.path.exists() for record in records)

    index = write_pose_index(records, tmp_path / "docking_poses.tsv", root=tmp_path)
    loaded = load_pose_index(index, root=tmp_path)
    assert [(record.rank, record.affinity) for record in loaded] == [(1, -8.2), (2, -7.6)]
    assert loaded[1].path.name == "mode_02.pdbqt"


def test_split_single_pose_without_model_records(tmp_path):
    source = tmp_path / "single.pdbqt"
    source.write_text(
        "REMARK VINA RESULT: -6.100 0.000 0.000\n"
        "ATOM      1  C1  LIG Z   1       0.000   0.000   0.000\n",
        encoding="utf-8",
    )
    records = split_vina_poses(source, tmp_path / "poses", "target", "ligand")
    assert len(records) == 1
    assert records[0].rank == 1
    assert records[0].affinity == -6.1
