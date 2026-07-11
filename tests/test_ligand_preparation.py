from pathlib import Path

from dockflow import preparation


class Result:
    returncode = 0


def test_convert_ligand_adds_ph_and_minimization(monkeypatch, tmp_path):
    source = tmp_path / "ligand.smi"
    source.write_text("CCO\n", encoding="utf-8")
    output = tmp_path / "ligand.pdb"
    captured = {}

    monkeypatch.setattr(preparation, "require_tool", lambda *_args, **_kwargs: Path("obabel"))

    def fake_run(command, _log):
        captured["command"] = command
        output.write_text("ATOM\n", encoding="utf-8")
        return Result()

    monkeypatch.setattr(preparation, "run_command", fake_run)
    preparation.convert_ligand_to_pdb(
        source,
        output,
        {},
        tmp_path / "log.txt",
        protonation_ph=6.5,
        minimize=True,
        forcefield="UFF",
        minimization_steps=400,
    )
    command = captured["command"]
    assert "--gen3d" in command
    assert command[command.index("-p") + 1] == "6.5"
    assert "--minimize" in command
    assert command[command.index("--ff") + 1] == "UFF"
    assert command[command.index("--steps") + 1] == "400"


def test_environment_settings(monkeypatch):
    monkeypatch.setenv("DOCKFLOW_LIGAND_PH", "5.5")
    monkeypatch.setenv("DOCKFLOW_LIGAND_MINIMIZE", "0")
    monkeypatch.setenv("DOCKFLOW_LIGAND_FORCEFIELD", "GAFF")
    monkeypatch.setenv("DOCKFLOW_LIGAND_STEPS", "120")
    settings = preparation._env_settings()
    assert settings == {
        "ligand_protonation_ph": 5.5,
        "ligand_minimize": False,
        "ligand_forcefield": "GAFF",
        "ligand_minimization_steps": 120,
    }
