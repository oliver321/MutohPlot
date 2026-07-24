import pytest

from mutohplot import cli
from mutohplot.document import PlotDocument
from mutohplot.geometry.point import Point
from mutohplot.geometry.polyline import Polyline
from mutohplot.transform.coordinate import CoordinateTransform


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


def test_stats_shows_input_and_transformed_output_bounds(capsys):
    document = PlotDocument([Polyline([Point(0.0, 0.0), Point(10.0, 20.0)], 1)])
    transform = CoordinateTransform(
        a=0.0,
        b=-1.0,
        c=1.0,
        d=0.0,
        tx=30.0,
        ty=-5.0,
    )

    cli.stats(document, transform)

    output = capsys.readouterr().out
    assert "Input bounds: x=0.00..10.00 mm, y=0.00..20.00 mm" in output
    assert "Output bounds: first=10.00..30.00 mm, second=-5.00..5.00 mm" in output
