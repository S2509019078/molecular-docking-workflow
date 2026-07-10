from dockflow.models import DockingBox, PocketDefinition
from dockflow.qc import best_affinity, classify_result, pose_center


def test_best_affinity_reads_vina_table(tmp_path):
    log = tmp_path / "vina.log"
    log.write_text("-----+------------+----------+----------\n   1       -7.4      0.000      0.000\n   2       -6.8      1.200      2.300\n", encoding="utf-8")
    assert best_affinity(log) == -7.4


def test_pose_center_uses_only_first_vina_model(tmp_path):
    pose = tmp_path / "pose.pdbqt"
    pose.write_text(
        "MODEL 1\n"
        "ATOM      1  C1  LIG A   1       0.000   0.000   0.000  1.00  0.00\n"
        "ATOM      2  C2  LIG A   1       2.000   0.000   0.000  1.00  0.00\n"
        "ENDMDL\n"
        "MODEL 2\n"
        "ATOM      1  C1  LIG A   1     100.000   0.000   0.000  1.00  0.00\n"
        "ENDMDL\n",
        encoding="utf-8",
    )
    assert pose_center(pose) == (1.0, 0.0, 0.0)


def test_reference_classification_is_not_overstated(tmp_path):
    pose = tmp_path / "pose.pdbqt"
    pose.write_text(
        "ATOM      1  C1  LIG A   1       0.000   0.000   0.000  1.00  0.00\n"
        "ATOM      2  C2  LIG A   1       2.000   0.000   0.000  1.00  0.00\n",
        encoding="utf-8",
    )
    center = pose_center(pose)
    pocket = PocketDefinition("co_crystal", "reference", DockingBox((1.0, 0.0, 0.0), (20.0, 20.0, 20.0)), (1.0, 0.0, 0.0))
    record = classify_result(-8.5, center, pocket)
    assert record.classification == "reference_consistent"


def test_blind_result_is_never_reference_consistent():
    pocket = PocketDefinition("blind", "exploratory", DockingBox((0.0, 0.0, 0.0), (30.0, 30.0, 30.0)))
    record = classify_result(-10.0, (0.0, 0.0, 0.0), pocket)
    assert record.classification == "exploratory"
