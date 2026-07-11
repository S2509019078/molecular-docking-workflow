from pathlib import Path

import pytest

from dockflow import preparation


class Result:
    returncode = 0


def _tools(tmp_path):
    obabel = tmp_path / "obabel.exe"
    receptor = tmp_path / "DockFlow-Meeko-Receptor.exe"
    ligand = tmp_path / "DockFlow-Meeko-Ligand.exe"
    for path in (obabel, receptor, ligand):
        path.write_bytes(b"x")
    return {
        "obabel": str(obabel),
        "meeko_receptor": str(receptor),
        "meeko_ligand": str(ligand),
    }


def test_auto_backend_prefers_meeko(tmp_path):
    tools = _tools(tmp_path)
    assert preparation.resolve_preparation_backend(tools, "auto") == "meeko"
    assert preparation.preparation_backend_warning(tools, "auto") is None


def test_openbabel_direct_pdbqt_backend_is_rejected(tmp_path):
    tools = _tools(tmp_path)
    with pytest.raises(ValueError, match="no longer supported"):
        preparation.resolve_preparation_backend(tools, "openbabel")


def test_explicit_mgltools_backend_requires_complete_toolchain(tmp_path):
    with pytest.raises(FileNotFoundError):
        preparation.resolve_preparation_backend({}, "mgltools")


def test_meeko_receptor_preparation_command(monkeypatch, tmp_path):
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
    preparation.prepare_receptor(
        clean,
        output,
        tools,
        tmp_path / "receptor.log",
        settings={"preparation_backend": "meeko"},
    )
    command = captured["command"]
    assert command[0].endswith("DockFlow-Meeko-Receptor.exe")
    assert command[1:3] == ["--read_pdb", str(clean)]
    assert command[-2:] == ["-p", str(output)]


def test_meeko_ligand_preparation_uses_sdf(monkeypatch, tmp_path):
    source = tmp_path / "ligand.mol2"
    source.write_text("@<TRIPOS>MOLECULE\n", encoding="utf-8")
    tools = _tools(tmp_path)
    commands = []

    def fake_run(command, _log):
        commands.append(command)
        if "-O" in command:
            output = Path(command[command.index("-O") + 1])
        else:
            output = Path(command[command.index("-o") + 1])
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
        settings={
            "preparation_backend": "meeko",
            "ligand_protonation_ph": 7.4,
            "ligand_minimize": False,
            "ligand_forcefield": "MMFF94",
            "ligand_minimization_steps": 250,
        },
    )
    assert output.exists()
    meeko_command = commands[-1]
    assert meeko_command[0].endswith("DockFlow-Meeko-Ligand.exe")
    assert meeko_command[1] == "-i"
    assert meeko_command[2].endswith("ligand.sdf")
    assert meeko_command[-2:] == ["-o", str(output)]
