from pathlib import Path

from dockflow.structure_preview import build_structure_preview


def test_build_receptor_preview(tmp_path):
    pdb = tmp_path / "protein.pdb"
    pdb.write_text("ATOM      1  CA  ALA A   1       0.000   0.000   0.000\n", encoding="utf-8")
    output = build_structure_preview(pdb, tmp_path / "protein.html", title="Protein")
    html = output.read_text(encoding="utf-8")
    assert "3Dmol-min.js" in html
    assert "cartoon" in html
    assert "Protein" in html


def test_build_ligand_preview(tmp_path):
    sdf = tmp_path / "ligand.sdf"
    sdf.write_text("ligand\n  DockFlow\n\n  0  0  0  0  0  0            999 V2000\nM  END\n$$$$\n", encoding="utf-8")
    output = build_structure_preview(sdf, tmp_path / "ligand.html", title="Ligand", ligand_only=True)
    html = output.read_text(encoding="utf-8")
    assert "greenCarbon" in html
    assert "Ligand" in html
    assert "'sdf'" in html
