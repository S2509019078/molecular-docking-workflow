from pathlib import Path

import pytest

from dockflow import preparation


class Result:
    returncode = 0


def test_openbabel_conversion_has_no_chemistry_modifying_flags(monkeypatch, tmp_path):
    source = tmp_path / "ligand.sdf"
    source.write_text("ligand\n", encoding="utf-8")
    output = tmp_path / "ligand.mol2"
    captured = {}

    monkeypatch.setattr(preparation, "require_tool", lambda *_args, **_kwargs: Path("obabel"))

    def fake_run(command, _log):
        captured["command"] = command
        output.write_text("@<TRIPOS>MOLECULE\n", encoding="utf-8")
        return Result()

    monkeypatch.setattr(preparation, "run_command", fake_run)
    preparation.convert_ligand_format(source, output, {}, tmp_path / "log.txt")
    assert captured["command"] == ["obabel", str(source), "-O", str(output)]
    forbidden = {"--gen3d", "-p", "--minimize", "--ff", "--steps", "-h"}
    assert forbidden.isdisjoint(captured["command"])


def test_mol2_and_pdb_pass_directly_to_autodocktools(tmp_path):
    tools = {}
    mol2 = tmp_path / "ligand.mol2"
    pdb = tmp_path / "ligand.pdb"
    mol2.write_text("@<TRIPOS>MOLECULE\n", encoding="utf-8")
    pdb.write_text("ATOM\n", encoding="utf-8")
    assert preparation.ligand_input_for_autodocktools(mol2, "ligand", tmp_path, tools, tmp_path) == mol2
    assert preparation.ligand_input_for_autodocktools(pdb, "ligand", tmp_path, tools, tmp_path) == pdb


def test_smiles_cannot_be_silently_converted_to_3d(tmp_path):
    source = tmp_path / "ligand.smi"
    source.write_text("CCO\n", encoding="utf-8")
    with pytest.raises(ValueError, match="validated 3D coordinates"):
        preparation.convert_ligand_format(source, tmp_path / "ligand.mol2", {}, tmp_path / "log.txt")
