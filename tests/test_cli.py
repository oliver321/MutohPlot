import pytest

from mutohplot import cli


def test_help_shows_installed_version(monkeypatch):
    monkeypatch.setattr(cli, "package_version", lambda _name: "1.2.3")

    help_text = cli.parser().format_help()

    assert "MutohPlot 1.2.3" in help_text
    assert "--version" in help_text


def test_version_option_prints_installed_version(monkeypatch, capsys):
    monkeypatch.setattr(cli, "package_version", lambda _name: "1.2.3")

    with pytest.raises(SystemExit) as exc:
        cli.parser().parse_args(["--version"])

    assert exc.value.code == 0
    assert capsys.readouterr().out.strip() == "mutohplot 1.2.3"
