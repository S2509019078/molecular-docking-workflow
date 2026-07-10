from pathlib import Path
import pytest
from dockflow.config import WorkflowConfig, load_targets

def test_load_target_supports_local_source_and_explicit_box(tmp_path):
    p = tmp_path / "targets.tsv"
    p.write_text("name\tstructure_source\tstructure\tpocket_strategy\tcenter_x\tcenter_y\tcenter_z\n" "x\tlocal\treceptor.pdb\texplicit_box\t1\t2\t3\n", encoding="utf-8")
    rows = load_targets(p)
    assert rows[0].name == "x"
    assert rows[0].center == (1.0, 2.0, 3.0)

def test_config_rejects_missing_target_columns(tmp_path):
    p = tmp_path / "bad.tsv"
    p.write_text("name\nfoo\n", encoding="utf-8")
    with pytest.raises(ValueError, match="structure_source"):
        load_targets(p)

