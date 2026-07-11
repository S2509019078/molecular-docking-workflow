from pathlib import Path

import yaml

from dockflow.preprocess_status import build_preparation_status
from dockflow.tooling import find_autodocktools_components


def test_find_autodocktools_components_in_classic_layout(tmp_path):
    root = tmp_path / "AutoDockTools-1.5.7"
    pythonsh = root / "pythonsh.exe"
    utilities = root / "MGLToolsPckgs" / "AutoDockTools" / "Utilities24"
    receptor = utilities / "prepare_receptor4.py"
    ligand = utilities / "prepare_ligand4.py"
    utilities.mkdir(parents=True)
    pythonsh.write_bytes(b"x")
    receptor.write_text("# receptor\n", encoding="utf-8")
    ligand.write_text("# ligand\n", encoding="utf-8")

    result = find_autodocktools_components(root)

    assert result["mgltools_pythonsh"] == pythonsh.resolve()
    assert result["prepare_receptor4"] == receptor.resolve()
    assert result["prepare_ligand4"] == ligand.resolve()


def test_mol2_project_does_not_require_openbabel_for_preparation_status(tmp_path):
    root = tmp_path / "project"
    config_dir = root / "config"
    ligand_dir = root / "inputs" / "ligands"
    structure_dir = root / "inputs" / "structures"
    config_dir.mkdir(parents=True)
    ligand_dir.mkdir(parents=True)
    structure_dir.mkdir(parents=True)

    receptor = structure_dir / "receptor.pdb"
    receptor.write_text(
        "ATOM      1  CA  ALA A   1       0.000   0.000   0.000  1.00 20.00           C\nEND\n",
        encoding="utf-8",
    )
    (ligand_dir / "ligand.mol2").write_text(
        "@<TRIPOS>MOLECULE\nligand\n1 0 0 0 0\nSMALL\nNO_CHARGES\n\n"
        "@<TRIPOS>ATOM\n1 C1 0.0 0.0 1.0 C.3 1 LIG 0.0\n",
        encoding="utf-8",
    )
    (config_dir / "targets.tsv").write_text(
        "name\tstructure_source\tstructure\tpocket_strategy\treceptor_chains\n"
        "target\tlocal\tinputs/structures/receptor.pdb\tblind\tA\n",
        encoding="utf-8",
    )

    pythonsh = tmp_path / "pythonsh.exe"
    prepare_receptor = tmp_path / "prepare_receptor4.py"
    prepare_ligand = tmp_path / "prepare_ligand4.py"
    vina = tmp_path / "vina.exe"
    for path in (pythonsh, prepare_receptor, prepare_ligand, vina):
        path.write_bytes(b"x")

    config = config_dir / "config.yaml"
    config.write_text(
        yaml.safe_dump(
            {
                "tools": {
                    "mgltools_pythonsh": str(pythonsh),
                    "prepare_receptor4": str(prepare_receptor),
                    "prepare_ligand4": str(prepare_ligand),
                    "vina": str(vina),
                    "obabel": "",
                },
                "paths": {
                    "targets": "config/targets.tsv",
                    "ligands": "inputs/ligands",
                    "work": "work",
                    "results": "results",
                },
            },
            sort_keys=False,
        ),
        encoding="utf-8",
    )

    status = build_preparation_status(config)
    openbabel = next(item for item in status.checks if item.key == "tool:obabel")

    assert openbabel.blocking is False
    assert openbabel.state == "提示"
