from dockflow.models import Atom, Target
from dockflow.pockets import box_from_atoms, resolve_pocket

def atoms():
    return [Atom("C", "LIG", "A", 1, x, 2.0, 3.0, "HETATM") for x in (0.0, 2.0)]

def test_co_crystal_box_uses_ligand_coordinates():
    t = Target("x", "local", "x.pdb", "co_crystal", ligand="LIG")
    p = resolve_pocket(t, atoms())
    assert p.strategy == "co_crystal"
    assert p.box.center == (1.0, 2.0, 3.0)

def test_blind_mode_has_no_reference_distance():
    t = Target("x", "local", "x.pdb", "blind")
    p = resolve_pocket(t, atoms())
    assert p.evidence == "exploratory"
    assert p.reference_center is None

