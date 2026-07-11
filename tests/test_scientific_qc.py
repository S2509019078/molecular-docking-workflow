from pathlib import Path

import yaml

from dockflow.models import Target
from dockflow.scientific_qc import build_project_qc, inspect_ligand, inspect_receptor, write_project_qc


def pdb_atom(serial, name, residue, chain, residue_id, x, y, z, record="ATOM", element="C", altloc=" "):
    return (
        f"{record:<6}{serial:>5} {name:<4}{altloc}{residue:>3} {chain:1}{residue_id:>4}    "
        f"{x:>8.3f}{y:>8.3f}{z:>8.3f}{1.00:>6.2f}{20.00:>6.2f}          {element:>2}"
    )


def test_receptor_qc_detects_interface_chain_and_pocket_water(tmp_path):
    pdb = tmp_path / "receptor.pdb"
    pdb.write_text(
        "\n".join(
            [
                pdb_atom(1, "CA", "ALA", "A", 1, 0, 0, 0),
                pdb_atom(2, "CA", "GLY", "A", 2, 1, 0, 0),
                pdb_atom(3, "CA", "SER", "B", 1, 2, 0, 0),
                pdb_atom(4, "C1", "LIG", "A", 900, 1.5, 0, 0, record="HETATM"),
                pdb_atom(5, "O", "HOH", "A", 901, 1.5, 2.5, 0, record="HETATM", element="O"),
                pdb_atom(6, "ZN", "ZN", "A", 902, 2.0, 1.0, 0, record="HETATM", element="ZN"),
                "END",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    target = Target(
        name="target",
        structure_source="local",
        structure=str(pdb),
        pocket_strategy="co_crystal",
        receptor_chains=("A",),
        ligand="LIG",
        ligand_chain="A",
        ligand_residue_id=900,
    )
    report = inspect_receptor(pdb, target)
    codes = {issue.code for issue in report.issues}
    assert report.reference_ligand_atom_count == 1
    assert report.pocket_water_count == 1
    assert report.omitted_chain_contact_count == 1
    assert "receptor.pocket_waters" in codes
    assert "receptor.metals" in codes
    assert "receptor.omitted_chain_contact" in codes
    assert any(issue.level == "blocker" for issue in report.issues)


def test_ligand_qc_blocks_smiles_and_pdb_without_reliable_chemistry(tmp_path):
    smiles = tmp_path / "salt.smi"
    smiles.write_text("CC[NH3+].[Cl-]\n", encoding="utf-8")
    smiles_report = inspect_ligand(smiles)
    smiles_codes = {issue.code for issue in smiles_report.issues}
    assert "ligand.no_3d" in smiles_codes
    assert "ligand.multiple_fragments" in smiles_codes
    assert any(issue.level == "blocker" for issue in smiles_report.issues)

    pdb = tmp_path / "ligand.pdb"
    pdb.write_text(
        pdb_atom(1, "C1", "LIG", "A", 1, 0, 0, 0, record="HETATM")
        + "\n"
        + pdb_atom(2, "O1", "LIG", "A", 1, 1, 1, 1, record="HETATM", element="O")
        + "\nEND\n",
        encoding="utf-8",
    )
    pdb_report = inspect_ligand(pdb)
    assert pdb_report.has_3d_coordinates
    assert any(issue.code == "ligand.pdb_format" for issue in pdb_report.issues)


def test_project_qc_writes_machine_and_human_reports(tmp_path):
    root = tmp_path / "project"
    (root / "config").mkdir(parents=True)
    (root / "inputs" / "structures").mkdir(parents=True)
    (root / "inputs" / "ligands").mkdir(parents=True)
    receptor = root / "inputs" / "structures" / "receptor.pdb"
    receptor.write_text(
        pdb_atom(1, "CA", "ALA", "A", 1, 0, 0, 0) + "\nEND\n",
        encoding="utf-8",
    )
    ligand = root / "inputs" / "ligands" / "ligand.sdf"
    ligand.write_text(
        "ligand\n  DockFlow\n  3D\n"
        "  2  1  0  0  0  0            999 V2000\n"
        "    0.0000    0.0000    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\n"
        "    1.0000    1.0000    1.0000 O   0  0  0  0  0  0  0  0  0  0  0  0\n"
        "  1  2  1  0  0  0  0\nM  END\n$$$$\n",
        encoding="utf-8",
    )
    targets = root / "config" / "targets.tsv"
    targets.write_text(
        "name\tstructure_source\tstructure\tpocket_strategy\treceptor_chains\n"
        "target\tlocal\tinputs/structures/receptor.pdb\tblind\tA\n",
        encoding="utf-8",
    )
    config = root / "config" / "config.yaml"
    config.write_text(
        yaml.safe_dump(
            {
                "settings": {"scientific_mode": "standard"},
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
    report = build_project_qc(config)
    assert len(report.receptors) == 1
    assert len(report.ligands) == 1
    assert any(issue.code == "project.standard_blind" for issue in report.issues)
    outputs = write_project_qc(report, root / "results" / "qc")
    assert outputs["json"].exists()
    assert outputs["tsv"].exists()
    assert "DockFlow 项目质量控制报告" in outputs["markdown"].read_text(encoding="utf-8")
