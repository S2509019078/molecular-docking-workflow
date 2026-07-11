from pathlib import Path

import pytest

from dockflow.ligand_library import create_smiles_file, inspect_ligand_file, safe_ligand_name


def test_safe_ligand_name():
    assert safe_ligand_name("Aspirin sodium") == "Aspirin_sodium"
    assert safe_ligand_name("***") == "ligand"


def test_create_smiles_file_records_fragment_warning(tmp_path):
    record = create_smiles_file(tmp_path, "salt", "CCO.[Na+]")
    assert record.path.exists()
    assert record.source == "SMILES"
    assert record.status == "需检查"
    assert "多个片段" in record.warning


def test_create_smiles_rejects_empty_or_extra_fields(tmp_path):
    with pytest.raises(ValueError):
        create_smiles_file(tmp_path, "empty", "")
    with pytest.raises(ValueError):
        create_smiles_file(tmp_path, "bad", "CCO ethanol")


def test_inspect_multimolecule_sdf_warns(tmp_path):
    sdf = tmp_path / "library.sdf"
    sdf.write_text("mol1\n$$$$\nmol2\n$$$$\n", encoding="utf-8")
    record = inspect_ligand_file(sdf)
    assert record.status == "需检查"
    assert "2 个分子" in record.warning


def test_inspect_rejects_unsupported_and_empty(tmp_path):
    unsupported = tmp_path / "ligand.xyz"
    unsupported.write_text("x", encoding="utf-8")
    with pytest.raises(ValueError):
        inspect_ligand_file(unsupported)
    empty = tmp_path / "empty.sdf"
    empty.write_bytes(b"")
    with pytest.raises(ValueError):
        inspect_ligand_file(empty)
