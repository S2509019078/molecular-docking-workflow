from pathlib import Path

import pytest

from dockflow import preparation


class Result:
    returncode = 0


def _tools(tmp_path):
    obabel = tmp_path / "obabel.exe"
    pythonsh = tmp_path / "pythonsh.exe"
    receptor = tmp_path / "prepare_receptor4.py"
    ligand = tmp_path / "prepare_ligand4.py"
    for path in (obabel, pythonsh, receptor, ligand):
        path.write_bytes(b"x")
    return {
        "obabel": str(obabel),
        "mgltools_pythonsh": str(pythonsh),
        "prepare_receptor4": str(receptor),
        "prepare_ligand4": str(ligand),
    }


def test_auto_backend_requires_autodocktools(tmp_path):
    tools = _tools(tmp_path)
    assert preparation.resolve_preparation_backend(tools, "auto") == "mgltools"
    assert preparation.resolve_preparation_backend(tools, "autodocktools") == "mgltools"


def test_openbabel_and_meeko_backends_are_rejected(tmp_path):
    tools = _tools(tmp_path)
    with pytest.raises(ValueError, match="restricted to AutoDockTools"):
        preparation.resolve_preparation_backend(tools, "openbabel")
    with pytest.raises(ValueError, match="restricted to AutoDockTools"):
        preparation.resolve_preparation_backend(tools, "meeko")


def test_autodocktools_backend_requires_complete_toolchain():
    with pytest.raises(FileNotFoundError, match="pythonsh"):
        preparation.resolve_preparation_backend({}, "mgltools")


def test_autodocktools_receptor_command(monkeypatch, tmp_path):
    clean = tmp_path / "receptor.pdb"
    clean.write_text("ATOM\n", encoding="utf-8")
    output = tmp_path / "receptor.pdbqt"
    tools = _tools(tmp_path)
    captured = {}

    def fake_run(command, _log):
        captured["command"] = command
        output.write_text("ATOM\n", encoding="utf-8")
        return Result()

    monkeypatch.setattr(preparation, "run_command", fake_run)
    preparation.prepare_receptor(clean, output, tools, tmp_path / "receptor.log")
    command = captured["command"]
    assert command[0].endswith("pythonsh.exe")
    assert command[1].endswith("prepare_receptor4.py")
    assert command[command.index("-r") + 1] == str(clean)
    assert "hydrogens" in command
    assert "nphs_lps_waters" in command


def test_autodocktools_ligand_command_uses_mol2_conversion(monkeypatch, tmp_path):
    source = tmp_path / "ligand.sdf"
    source.write_text("ligand\n", encoding="utf-8")
    tools = _tools(tmp_path)
    commands = []

    def fake_run(command, _log):
        commands.append(command)
        output_flag = "-O" if "-O" in command else "-o"
        output = Path(command[command.index(output_flag) + 1])
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text("ATOM\n", encoding="utf-8")
        return Result()

    monkeypatch.setattr(preparation, "run_command", fake_run)
    output = preparation.prepare_ligand(
        source,
        "ligand",
        tmp_path / "pdb",
        tmp_path / "pdbqt",
        tools,
        tmp_path / "logs",
        settings={"preparation_backend": "mgltools"},
    )
    assert output.exists()
    assert commands[0] == [str(Path(tools["obabel"])), str(source), "-O", str(tmp_path / "ligands_converted" / "ligand.mol2")]
    prepare = commands[-1]
    assert prepare[0].endswith("pythonsh.exe")
    assert prepare[1].endswith("prepare_ligand4.py")
    assert prepare[prepare.index("-l") + 1].endswith("ligand.mol2")
    assert "hydrogens" in prepare


def test_smiles_is_rejected_without_reviewed_3d_coordinates(tmp_path):
    source = tmp_path / "ligand.smi"
    source.write_text("CCO\n", encoding="utf-8")
    with pytest.raises(ValueError, match="3D coordinates"):
        preparation.ligand_input_for_autodocktools(source, "ligand", tmp_path, _tools(tmp_path), tmp_path)
