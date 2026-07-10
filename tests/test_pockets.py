import pytest

from dockflow.models import Atom, Target
from dockflow.pockets import box_from_atoms, resolve_pocket


def atom(record, residue, chain, residue_id, x, y=2.0, z=3.0):
    return Atom("C", residue, chain, residue_id, "", x, y, z, record)


def test_co_crystal_box_uses_only_requested_ligand_instance():
    atoms = [
        atom("HETATM", "LIG", "A", 101, 0.0),
        atom("HETATM", "LIG", "A", 101, 2.0),
        atom("HETATM", "LIG", "B", 201, 100.0),
    ]
    target = Target("x", "local", "x.pdb", "co_crystal", ligand="LIG", ligand_chain="A", ligand_residue_id=101)
    pocket = resolve_pocket(target, atoms)
    assert pocket.strategy == "co_crystal"
    assert pocket.box.center == (1.0, 2.0, 3.0)
    assert pocket.evidence == "reference"


def test_residue_box_uses_protein_atoms_on_selected_chain():
    atoms = [atom("ATOM", "ALA", "A", 42, 0.0), atom("ATOM", "TYR", "A", 45, 2.0), atom("ATOM", "TYR", "B", 45, 50.0)]
    target = Target("x", "local", "x.pdb", "residue_box", receptor_chains=("A",), residue_ids=(42, 45))
    assert resolve_pocket(target, atoms).box.center == (1.0, 2.0, 3.0)


def test_blind_mode_uses_protein_and_has_no_reference_distance():
    atoms = [atom("ATOM", "ALA", "A", 1, 0.0), atom("ATOM", "GLY", "A", 2, 2.0), atom("HETATM", "LIG", "A", 3, 100.0)]
    target = Target("x", "local", "x.pdb", "blind")
    pocket = resolve_pocket(target, atoms)
    assert pocket.evidence == "exploratory"
    assert pocket.reference_center is None
    assert pocket.box.center == (1.0, 2.0, 3.0)


def test_box_from_atoms_rejects_empty_selection():
    with pytest.raises(ValueError, match="no atoms"):
        box_from_atoms([])
