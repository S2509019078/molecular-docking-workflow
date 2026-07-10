from pathlib import Path

from dockflow import windows_launcher


def test_launcher_defaults_to_wizard(monkeypatch, tmp_path):
    captured = {}

    def fake_cli(args):
        captured["args"] = args
        return 0

    monkeypatch.setattr(windows_launcher, "cli_main", fake_cli)
    monkeypatch.setattr(windows_launcher, "_default_runs_dir", lambda: tmp_path / "runs")
    assert windows_launcher.main([]) == 0
    assert captured["args"] == ["wizard", "--runs-dir", str(tmp_path / "runs")]


def test_launcher_forwards_explicit_arguments(monkeypatch):
    captured = {}

    def fake_cli(args):
        captured["args"] = args
        return 2

    monkeypatch.setattr(windows_launcher, "cli_main", fake_cli)
    assert windows_launcher.main(["check", "--config", "x.yaml"]) == 2
    assert captured["args"] == ["check", "--config", "x.yaml"]


def test_launcher_returns_nonzero_on_failure(monkeypatch, capsys):
    def fail(_args):
        raise RuntimeError("broken")

    monkeypatch.setattr(windows_launcher, "cli_main", fail)
    assert windows_launcher.main(["check"]) == 1
    assert "broken" in capsys.readouterr().out


def test_default_runs_dir_is_under_documents(monkeypatch, tmp_path):
    documents = tmp_path / "Documents"
    documents.mkdir()
    monkeypatch.setenv("USERPROFILE", str(tmp_path))
    assert windows_launcher._default_runs_dir() == documents / "DockFlow" / "runs"
