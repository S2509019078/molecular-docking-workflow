from pathlib import Path

import pytest

from dockflow import preparation


class Result:
    returncode = 0


def test_auto_backend_falls_back_to_openbabel(tmp_path):
    obabel = tmp_path / "obabel.exe"
    obabel.write_bytes(b"x")
    tools = {
        "obabel": str(obabel),
        "mgltools_pythonsh": "missing-pythonsh.exe",
        "prepare_receptor4": "missing-prepare-receptor.py",
        "prepare_ligand4": "missing-prepare-ligand.py",
    }
    assert preparation.resolve_preparation_backend(tools, "auto") == "openbabel"
    assert "自动使用 Open Babel" in preparation.preparation_backend_warning(tools, "auto")


def test_explicit_mgltools_backend_requires_complete_toolchain(tmp_path):
    obabel = tmp_path / "obabel.exe"
    obabel.write_bytes(b"x")
    with pytest.raises(FileNotFoundError):
        preparation.resolve_preparation_backend({"obabel": str(obabel)}, "mgltools")


def test_openbabel_receptor_preparation_command(monkeypatch, tmp_path):
    clean = tmp_path / "receptor.pdb"
    clean.write_text("ATOM\n", encoding="utf-8")
    output = tmp_path / "receptor.pdbqt"
    obabel = tmp_path / "obabel.exe"
    obabel.write_bytes(b"x")
    captured = {}

    def fake_run(command, _log):
        captured["command"] = command
        output.write_text("ATOM\n", encoding="utf-8")
        return Result()

    monkeypatch.setattr(preparation, "run_command", fake_run)
    preparation.prepare_receptor(
        clean,
        output,
        {"obabel": str(obabel)},
        tmp_path / "receptor.log",
        settings={"preparation_backend": "openbabel", "receptor_protonation_ph": 7.4},
    )
    command = captured["command"]
    assert command[0] == str(obabel)
    assert "-xr" in command
    assert "-xh" in command
    assert command[command.index("-p") + 1] == "7.4"


def test_openbabel_ligand_pdbqt_fallback(monkeypatch, tmp_path):
    source = tmp_path / "ligand.sdf"
    source.write_text("ligand\n", encoding="utf-8")
    obabel = tmp_path / "obabel.exe"
    obabel.write_bytes(b"x")
    commands = []

    def fake_run(command, _log):
        commands.append(command)
        output = Path(command[command.index("-O") + 1])
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text("ATOM\n", encoding="utf-8")
        return Result()

    monkeypatch.setattr(preparation, "run_command", fake_run)
    output = preparation.prepare_ligand(
        source,
        "ligand",
        tmp_path / "pdb",
        tmp_path / "pdbqt",
        {"obabel": str(obabel)},
        tmp_path / "logs",
        settings={
            "preparation_backend": "openbabel",
            "ligand_protonation_ph": 7.4,
            "ligand_minimize": False,
            "ligand_forcefield": "MMFF94",
            "ligand_minimization_steps": 250,
        },
    )
    assert output.exists()
    assert commands[-1][commands[-1].index("-O") + 1].endswith("ligand.pdbqt")
    assert "-xh" in commands[-1]
