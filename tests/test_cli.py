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


def test_hpgl_fit_scales_bottom_left_input_into_a3_norm_area(tmp_path, monkeypatch, capsys):
    source = tmp_path / "input.hpgl"
    output = tmp_path / "output.hpgl"
    source.write_text("IN;SP1;PU0,0;PD4000,0,4000,2000,0,2000,0,0;", encoding="ascii")
    monkeypatch.setattr(
        "sys.argv",
        [
            "mutohplot",
            "hpgl",
            str(source),
            str(output),
            "--paper",
            "a3",
            "--window",
            "norm",
            "--fit",
            "--margin",
            "5",
            "--report",
        ],
    )

    cli.main()

    converted = cli.HPGLParser(0.01).parse_text(output.read_text(encoding="ascii"))
    assert converted.bounds() == pytest.approx((-64.25, -128.5, 64.25, 128.5))
    report = capsys.readouterr().out
    assert "Fit scale: 2.570000" in report
    assert "Bounds check: inside drawable area" in report


def test_hpgl_fit_rejects_manual_axis_options(tmp_path, monkeypatch):
    source = tmp_path / "input.hpgl"
    source.write_text("IN;PU0,0;PD100,100;", encoding="ascii")
    monkeypatch.setattr(
        "sys.argv",
        [
            "mutohplot",
            "hpgl",
            str(source),
            str(tmp_path / "output.hpgl"),
            "--fit",
            "--swap-axes",
        ],
    )

    with pytest.raises(SystemExit, match="determines axis swapping"):
        cli.main()


def test_hpgl_auto_rotate_uses_a3_height_for_landscape_input(
    tmp_path, monkeypatch, capsys
):
    source = tmp_path / "input.hpgl"
    output = tmp_path / "output.hpgl"
    # A4 landscape: 297 x 210 mm.
    source.write_text(
        "IN;SP1;PU0,0;PD11880,0,11880,8400,0,8400,0,0;",
        encoding="ascii",
    )
    monkeypatch.setattr(
        "sys.argv",
        [
            "mutohplot",
            "hpgl",
            str(source),
            str(output),
            "--paper",
            "a3",
            "--window",
            "norm",
            "--fit",
            "--margin",
            "5",
            "--auto-rotate",
            "--stats",
        ],
    )

    cli.main()

    converted = cli.HPGLParser(0.01).parse_text(output.read_text(encoding="ascii"))
    assert converted.bounds() == pytest.approx((-180.0, -127.27, 180.0, 127.27), abs=0.02)
    stats = capsys.readouterr().out
    assert "Fit scale: 1.212121 (121.21%)" in stats
    assert "Fit rotation: 90 degrees" in stats


def test_hpgl_auto_rotate_keeps_better_orientation(tmp_path, monkeypatch, capsys):
    source = tmp_path / "input.hpgl"
    output = tmp_path / "output.hpgl"
    source.write_text("IN;SP1;PU0,0;PD8400,0,8400,11880,0,11880,0,0;", encoding="ascii")
    monkeypatch.setattr(
        "sys.argv",
        [
            "mutohplot",
            "hpgl",
            str(source),
            str(output),
            "--fit",
            "--auto-rotate",
            "--stats",
        ],
    )

    cli.main()

    stats = capsys.readouterr().out
    assert "Fit rotation: 0 degrees" in stats


def test_hpgl_rotation_requires_fit(tmp_path, monkeypatch):
    source = tmp_path / "input.hpgl"
    source.write_text("IN;PU0,0;PD100,100;", encoding="ascii")
    monkeypatch.setattr(
        "sys.argv",
        [
            "mutohplot",
            "hpgl",
            str(source),
            str(tmp_path / "output.hpgl"),
            "--rotate",
            "90",
        ],
    )

    with pytest.raises(SystemExit, match="require --fit"):
        cli.main()


def test_hpgl_warns_with_unsupported_command_counts(tmp_path, monkeypatch, capsys):
    source = tmp_path / "input.hpgl"
    source.write_text("IN;VS10;VS20;IP0,0,100,100;PU0,0;PD10,10;", encoding="ascii")
    monkeypatch.setattr(
        "sys.argv",
        ["mutohplot", "hpgl", str(source), str(tmp_path / "output.hpgl")],
    )

    cli.main()

    assert (
        "Warning: Unsupported HP-GL commands: IP (1), VS (2)"
        in capsys.readouterr().err
    )


def test_inspect_reports_commands_pens_geometry_and_unsupported(
    tmp_path, monkeypatch, capsys
):
    source = tmp_path / "input.hpgl"
    source.write_text(
        "IN;SP2;PU0,0;PD400,0,400,200;VS10;VS20;",
        encoding="ascii",
    )
    monkeypatch.setattr("sys.argv", ["mutohplot", "inspect", str(source)])

    cli.main()

    output = capsys.readouterr().out
    assert "Commands: IN (1), SP (1), PU (1), PD (1), VS (2)" in output
    assert "Unsupported: VS (2)" in output
    assert "Pens used: 2" in output
    assert "Polylines: 1" in output
    assert "Size: 10.00 x 5.00 mm" in output
    assert "Drawing distance: 15.0 mm" in output


def test_inspect_strict_exits_with_status_2_for_unsupported_command(
    tmp_path, monkeypatch, capsys
):
    source = tmp_path / "input.hpgl"
    source.write_text("IN;VS10;", encoding="ascii")
    monkeypatch.setattr(
        "sys.argv", ["mutohplot", "inspect", str(source), "--strict"]
    )

    with pytest.raises(SystemExit) as error:
        cli.main()

    assert error.value.code == 2
    assert "Unsupported: VS (1)" in capsys.readouterr().out


def test_inspect_accepts_quoted_wildcard(tmp_path, monkeypatch, capsys):
    (tmp_path / "Input1.hpgl").write_text("IN;SP1;PU0,0;PD100,100;", encoding="ascii")
    (tmp_path / "Input2.hpgl").write_text("IN;SP2;PU0,0;PD200,100;", encoding="ascii")
    monkeypatch.setattr(
        "sys.argv",
        ["mutohplot", "inspect", str(tmp_path / "Input*.hpgl")],
    )

    cli.main()

    output = capsys.readouterr().out
    assert "Input1.hpgl" in output
    assert "Input2.hpgl" in output
    assert output.count("Polylines: 1") == 2


def test_plot_no_send_saves_converted_hpgl_and_preview(
    tmp_path, monkeypatch, capsys
):
    source = tmp_path / "Input.hpgl"
    saved = tmp_path / "Input_mutoh.hpgl"
    preview = tmp_path / "Input_preview.svg"
    source.write_text(
        "IN;SP1;PU0,0;PD11880,0,11880,8400,0,8400,0,0;",
        encoding="ascii",
    )
    monkeypatch.setattr(
        "sys.argv",
        [
            "mutohplot",
            "plot",
            str(source),
            "--no-send",
            "--fit",
            "--auto-rotate",
            "--margin",
            "5",
            "--save-hpgl",
            str(saved),
            "--preview",
            str(preview),
        ],
    )

    cli.main()

    assert saved.read_text(encoding="ascii").startswith("IN;")
    assert preview.read_text(encoding="utf-8").startswith("<svg")
    assert f"Wrote {saved}" in capsys.readouterr().out


def test_plot_batch_converts_wildcard_to_named_outputs(
    tmp_path, monkeypatch, capsys
):
    for name in ("Input1.hpgl", "Input2.hpgl"):
        (tmp_path / name).write_text("IN;SP1;PU0,0;PD100,100;", encoding="ascii")
    converted = tmp_path / "converted"
    previews = tmp_path / "previews"
    monkeypatch.setattr(
        "sys.argv",
        [
            "mutohplot",
            "plot",
            str(tmp_path / "Input*.hpgl"),
            "--no-send",
            "--save-hpgl-dir",
            str(converted),
            "--preview",
            str(previews),
        ],
    )

    cli.main()

    assert (converted / "Input1_mutoh.hpgl").is_file()
    assert (converted / "Input2_mutoh.hpgl").is_file()
    assert (previews / "Input1_preview.svg").is_file()
    assert (previews / "Input2_preview.svg").is_file()
    output = capsys.readouterr().out
    assert "[1/2]" in output
    assert "[2/2]" in output


def test_plot_batch_send_requires_explicit_permission(tmp_path, monkeypatch):
    for name in ("Input1.hpgl", "Input2.hpgl"):
        (tmp_path / name).write_text("IN;PU0,0;PD100,100;", encoding="ascii")
    monkeypatch.setattr(
        "sys.argv",
        [
            "mutohplot",
            "plot",
            str(tmp_path / "Input*.hpgl"),
            "/dev/ttyUSB0",
        ],
    )

    with pytest.raises(SystemExit, match="--batch-send"):
        cli.main()


def test_plot_saved_hpgl_is_exactly_what_gets_sent(tmp_path, monkeypatch):
    source = tmp_path / "Input.hpgl"
    saved = tmp_path / "Input_mutoh.hpgl"
    source.write_text("IN;SP1;PU0,0;PD400,200;", encoding="ascii")
    transmitted = {}

    def fake_send_bytes(data, settings, profile, progress):
        transmitted["data"] = data
        transmitted["port"] = settings.port
        return len(data)

    monkeypatch.setattr(cli, "send_bytes", fake_send_bytes)
    monkeypatch.setattr(
        "sys.argv",
        [
            "mutohplot",
            "plot",
            str(source),
            "/dev/ttyUSB0",
            "--save-hpgl",
            str(saved),
        ],
    )

    cli.main()

    assert transmitted["port"] == "/dev/ttyUSB0"
    assert saved.read_bytes() == transmitted["data"]


def test_hpgl_preview_contains_a3_areas_origin_and_fitted_geometry(
    tmp_path, monkeypatch
):
    source = tmp_path / "input.hpgl"
    output = tmp_path / "output.hpgl"
    preview = tmp_path / "preview.svg"
    source.write_text(
        "IN;SP2;PU0,0;PD11880,0,11880,8400,0,8400,0,0;",
        encoding="ascii",
    )
    monkeypatch.setattr(
        "sys.argv",
        [
            "mutohplot",
            "hpgl",
            str(source),
            str(output),
            "--fit",
            "--auto-rotate",
            "--margin",
            "5",
            "--preview",
            str(preview),
        ],
    )

    cli.main()

    svg = preview.read_text(encoding="utf-8")
    assert 'width="297.0mm" height="420.0mm"' in svg
    assert 'x="15.0" y="35.0" width="267.0" height="370.0"' in svg
    assert 'x="20.0" y="40.0" width="257.0" height="360.0"' in svg
    assert '<circle cx="148.5" cy="210.0"' in svg
    assert 'stroke="#d22"' in svg
    assert "21.2273" in svg
    assert "275.7727" in svg
    assert "40.0000" in svg
    assert "400.0000" in svg


def test_stats_shows_original_bounds_fit_scale_and_mutoh_bounds(capsys):
    document = PlotDocument([Polyline([Point(15.0, 66.5), Point(282.0, 333.5)], 1)])
    transform = CoordinateTransform(
        a=0.0,
        b=-1.0,
        c=1.0,
        d=0.0,
        tx=200.0,
        ty=-148.5,
    )

    cli.stats(
        document,
        transform,
        original_bounds=(63.75, 0.0, 335.5, 271.75),
        fit_scale=267.0 / 271.75,
    )

    output = capsys.readouterr().out
    assert "Original input bounds: x=63.75..335.50 mm, y=0.00..271.75 mm" in output
    assert "Fit scale: 0.982521 (98.25%)" in output
    assert "Fitted page bounds: x=15.00..282.00 mm, y=66.50..333.50 mm" in output
    assert "Mutoh output bounds: first=-133.50..133.50 mm, second=-133.50..133.50 mm" in output
