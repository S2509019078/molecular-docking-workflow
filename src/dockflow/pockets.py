from .models import Atom, DockingBox, PocketDefinition, Target


def box_from_atoms(atoms, padding=4.0, minimum_size=12.0):
    if not atoms:
        raise ValueError("no atoms available to define docking box")
    xs, ys, zs = zip(*[(a.x, a.y, a.z) for a in atoms])
    center = tuple((lo + hi) / 2 for lo, hi in zip((min(xs), min(ys), min(zs)), (max(xs), max(ys), max(zs))))
    size = tuple(max(minimum_size, hi - lo + 2 * padding) for lo, hi in zip((min(xs), min(ys), min(zs)), (max(xs), max(ys), max(zs))))
    return DockingBox(center, size)


def _selected(atoms, target):
    return [a for a in atoms if a.record == "HETATM" and (not target.ligand_chain or a.chain == target.ligand_chain) and (not target.ligand or a.residue == target.ligand) and (target.ligand_residue_id is None or a.residue_id == target.ligand_residue_id)]


def resolve_pocket(target: Target, atoms: list[Atom], padding=4.0) -> PocketDefinition:
    strategy = target.pocket_strategy
    if strategy == "co_crystal":
        selected = _selected(atoms, target)
        if not selected:
            raise ValueError(f"co-crystal ligand {target.ligand!r} not found for {target.name}")
        box = box_from_atoms(selected, padding=padding)
        return PocketDefinition(strategy, "reference", box, box.center, "box from co-crystal ligand")
    if strategy == "explicit_box":
        if target.center is None or target.size is None:
            raise ValueError("explicit_box requires center and size")
        return PocketDefinition(strategy, "informed", DockingBox(target.center, target.size), target.center, "user-provided coordinates")
    if strategy == "residue_box":
        selected = [a for a in atoms if (not target.receptor_chains or a.chain in target.receptor_chains) and a.record == "ATOM" and a.residue_id in target.residue_ids]
        box = box_from_atoms(selected, padding=padding)
        return PocketDefinition(strategy, "informed", box, box.center, "box from user residue IDs")
    if strategy == "blind":
        box = box_from_atoms([a for a in atoms if a.record == "ATOM"], padding=8.0, minimum_size=24.0)
        return PocketDefinition(strategy, "exploratory", box, None, "exploratory blind box")
    raise ValueError(f"unsupported pocket strategy: {strategy}")
