from pathlib import Path

import pytest

from mutohplot import cli
from mutohplot.document import PlotDocument
from mutohplot.geometry.point import Point
from mutohplot.geometry.polyline import Polyline
from mutohplot.pen_config import (
    PenConfigError,
    apply_pen_colors,
    load_pen_profile,
)


def write_profile(path: Path, *, duplicate_pen: bool = False) -> None:
    second_group = """
[pen-groups.duplicate]
pens = [1]
type = "fiber"
width-mm = 0.3
color = "red"
""" if duplicate_pen else ""
    path.write_text(
        f"""
[profile]
name = "Draft"

[fill]
spacing-factor = 0.5

[pens]
default-width-mm = 0.7
default-color = "black"
default-type = "other"

[pen-groups.pencil-wide]
pens = [1, 2]
type = "pencil"
width-mm = 1.0
color = "blue"
speed-mm-s = 12.5
{second_group}
""",
        encoding="utf-8",
    )


def test_installed_standard_profile_contains_grouped_pencils():
    profile = load_pen_profile()

    assert profile.name == "Standard"
    assert profile.fill_spacing_factor == pytest.approx(0.85)
    assert profile.pen(1).group == "pencil-05"
    assert profile.pen(1).pen_type == "pencil"
    assert profile.pen(1).width_mm == pytest.approx(0.5)
    assert profile.pen(2).width_mm == pytest.approx(0.5)
    assert profile.pen(3).group == "pencil-03"
    assert profile.pen(3).width_mm == pytest.approx(0.3)
    assert profile.pen(4).width_mm == pytest.approx(0.3)
    assert profile.pen(5).group == "default"


def test_alternative_profile_replaces_standard_and_drives_ra_spacing(tmp_path):
    config = tmp_path / "Standard_draft.toml"
    write_profile(config)
    args = cli.parser().parse_args(
        [
            "hpgl",
            "input.hpgl",
            "output.hpgl",
            "--config",
            str(config),
        ]
    )

    profile = cli.pen_profile(args)
    spacings = cli.ra_fill_spacings(args)

    assert profile.name == "Draft"
    assert profile.pen(1).speed_mm_s == pytest.approx(12.5)
    assert spacings[1] == pytest.approx(0.5)
    assert spacings[5] == pytest.approx(0.35)


def test_cli_pen_width_overrides_selected_profile(tmp_path):
    config = tmp_path / "Standard_draft.toml"
    write_profile(config)
    args = cli.parser().parse_args(
        [
            "hpgl",
            "input.hpgl",
            "output.hpgl",
            "--config",
            str(config),
            "--pen-width",
            "1=1.5",
        ]
    )

    assert cli.configured_pen_widths(args)[1] == pytest.approx(1.5)
    assert cli.configured_pen_widths(args)[2] == pytest.approx(1.0)


def test_profile_color_is_applied_to_hpgl_geometry(tmp_path):
    config = tmp_path / "Standard_draft.toml"
    write_profile(config)
    profile = load_pen_profile(config)
    document = PlotDocument(
        [
            Polyline([Point(0, 0), Point(1, 1)], pen=1),
            Polyline([Point(0, 0), Point(2, 2)], pen=5),
        ]
    )

    apply_pen_colors(document, profile)

    assert document.polylines[0].source_color == "blue"
    assert document.polylines[1].source_color == "black"


def test_missing_alternative_profile_is_an_error(tmp_path):
    with pytest.raises(PenConfigError, match="configuration file not found"):
        load_pen_profile(tmp_path / "missing.toml")


def test_duplicate_pen_group_assignment_is_an_error(tmp_path):
    config = tmp_path / "duplicate.toml"
    write_profile(config, duplicate_pen=True)

    with pytest.raises(PenConfigError, match="pen 1 is assigned"):
        load_pen_profile(config)


def test_main_reports_configuration_error_for_missing_file(
    tmp_path, monkeypatch
):
    source = tmp_path / "input.hpgl"
    source.write_text("IN;PU0,0;PD10,10;", encoding="ascii")
    missing = tmp_path / "missing.toml"
    monkeypatch.setattr(
        "sys.argv",
        [
            "mutohplot",
            "hpgl",
            str(source),
            str(tmp_path / "output.hpgl"),
            "--config",
            str(missing),
        ],
    )

    with pytest.raises(SystemExit, match="Pen configuration error"):
        cli.main()
