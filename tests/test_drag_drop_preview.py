from pathlib import Path

from dockflow.gui_preview import DockFlowPreviewWindow


def test_valid_pdb_drop_requires_one_pdb(tmp_path):
    pdb = tmp_path / "protein.pdb"
    pdb.write_text("ATOM\n", encoding="utf-8")
    txt = tmp_path / "protein.txt"
    txt.write_text("ATOM\n", encoding="utf-8")
    assert DockFlowPreviewWindow._valid_pdb_drop([pdb])
    assert not DockFlowPreviewWindow._valid_pdb_drop([txt])
    assert not DockFlowPreviewWindow._valid_pdb_drop([pdb, pdb])


def test_valid_ligand_drop_accepts_supported_formats(tmp_path):
    sdf = tmp_path / "a.sdf"
    mol2 = tmp_path / "b.mol2"
    sdf.write_text("x", encoding="utf-8")
    mol2.write_text("x", encoding="utf-8")
    assert DockFlowPreviewWindow._valid_ligand_drop([sdf, mol2])


def test_valid_ligand_drop_rejects_unsupported(tmp_path):
    xyz = tmp_path / "a.xyz"
    xyz.write_text("x", encoding="utf-8")
    assert not DockFlowPreviewWindow._valid_ligand_drop([xyz])
    assert not DockFlowPreviewWindow._valid_ligand_drop([])
