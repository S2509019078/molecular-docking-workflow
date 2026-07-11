from dockflow.structure_scene import load_structure_scene


def test_parse_pdb_backbone_and_ligand(tmp_path):
    pdb = tmp_path / "protein.pdb"
    pdb.write_text(
        "ATOM      1  CA  ALA A   1       0.000   0.000   0.000  1.00 20.00           C\n"
        "ATOM      2  CA  GLY A   2       3.800   0.000   0.000  1.00 20.00           C\n"
        "HETATM    3  C1  LIG B 101       1.000   2.000   0.000  1.00 20.00           C\n"
        "HETATM    4  O1  LIG B 101       2.200   2.000   0.000  1.00 20.00           O\n"
        "END\n",
        encoding="utf-8",
    )
    scene = load_structure_scene(pdb)
    assert len(scene.atoms) == 4
    assert any(atom.hetero for atom in scene.atoms)
    assert (0, 1) in scene.bonds


def test_parse_mol2_ligand(tmp_path):
    mol2 = tmp_path / "ligand.mol2"
    mol2.write_text(
        "@<TRIPOS>MOLECULE\nLIG\n2 1 0 0 0\nSMALL\nNO_CHARGES\n"
        "@<TRIPOS>ATOM\n"
        "1 C1 0.0 0.0 0.0 C.3 1 LIG 0.0\n"
        "2 O1 1.2 0.0 0.0 O.2 1 LIG 0.0\n"
        "@<TRIPOS>BOND\n1 1 2 1\n",
        encoding="utf-8",
    )
    scene = load_structure_scene(mol2, ligand_only=True)
    assert len(scene.atoms) == 2
    assert scene.bonds == ((0, 1),)
    assert scene.atoms[1].element == "O"


def test_parse_sdf_ligand(tmp_path):
    sdf = tmp_path / "ligand.sdf"
    sdf.write_text(
        "ligand\nDockFlow\n\n"
        "  2  1  0  0  0  0            999 V2000\n"
        "    0.0000    0.0000    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\n"
        "    1.2000    0.0000    0.0000 O   0  0  0  0  0  0  0  0  0  0  0  0\n"
        "  1  2  1  0  0  0  0\nM  END\n$$$$\n",
        encoding="utf-8",
    )
    scene = load_structure_scene(sdf, ligand_only=True)
    assert len(scene.atoms) == 2
    assert scene.bonds == ((0, 1),)


def test_smiles_requires_prepared_coordinates(tmp_path):
    smiles = tmp_path / "ligand.smi"
    smiles.write_text("CCO\n", encoding="utf-8")
    try:
        load_structure_scene(smiles, ligand_only=True)
    except ValueError as error:
        assert "没有三维坐标" in str(error)
    else:
        raise AssertionError("SMILES should require prepared coordinates")
