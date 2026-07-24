import pytest

from mutohplot.hpgl.parser import HPGLParser


def test_absolute_pen_down_path():
    doc = HPGLParser(0.025).parse_text("IN;SP2;PU100,200;PD300,400,500,600;PU;")
    assert len(doc.polylines) == 1
    poly = doc.polylines[0]
    assert poly.pen == 2
    assert [(p.x, p.y) for p in poly.points] == [
        (2.5, 5.0), (7.5, 10.0), (12.5, 15.0)
    ]

def test_relative_mode():
    doc = HPGLParser(1.0).parse_text("IN;PA10,20;PD;PR5,-2,5,2;PU;")
    assert [(p.x, p.y) for p in doc.polylines[0].points] == [
        (10.0, 20.0), (15.0, 18.0), (20.0, 20.0)
    ]


def test_unsupported_text_command_is_reported_without_numeric_parsing():
    doc = HPGLParser(1.0).parse_text(
        "IN;PA0,0;LBBristol Hackspace;PD10,0;PU;"
    )

    assert doc.metadata["unsupported_commands"] == ["LB"]
    assert [(p.x, p.y) for p in doc.polylines[0].points] == [(0.0, 0.0), (10.0, 0.0)]


def test_arc_absolute_uses_chord_angle_and_updates_position():
    doc = HPGLParser(1.0).parse_text(
        "IN;SP2;PU10,0;PD;AA0,0,90,45;PD0,20;PU;"
    )

    points = doc.polylines[0].points
    assert doc.metadata.get("unsupported_commands") is None
    assert doc.polylines[0].pen == 2
    assert len(points) == 4
    assert (points[0].x, points[0].y) == (10.0, 0.0)
    assert points[1].x == pytest.approx(2**0.5 * 5)
    assert points[1].y == pytest.approx(2**0.5 * 5)
    assert points[2].x == pytest.approx(0.0, abs=1e-12)
    assert points[2].y == pytest.approx(10.0)
    assert (points[3].x, points[3].y) == (0.0, 20.0)


def test_arc_relative_supports_negative_sweep():
    doc = HPGLParser(1.0).parse_text(
        "IN;PU10,0;PD;AR-10,0,-90,45;PU;"
    )

    points = doc.polylines[0].points
    assert len(points) == 3
    assert points[-1].x == pytest.approx(0.0, abs=1e-12)
    assert points[-1].y == pytest.approx(-10.0)


def test_pen_up_arc_moves_without_drawing():
    doc = HPGLParser(1.0).parse_text(
        "IN;PU10,0;AA0,0,90,45;PD0,20;PU;"
    )

    assert len(doc.polylines) == 1
    points = doc.polylines[0].points
    assert points[0].x == pytest.approx(0.0, abs=1e-12)
    assert points[0].y == pytest.approx(10.0)
    assert (points[1].x, points[1].y) == (0.0, 20.0)


def test_circle_draws_automatically_and_preserves_center_position():
    doc = HPGLParser(1.0).parse_text(
        "IN;SP3;PU5,6;CI2,90;PD7,6;PU;"
    )

    circle, line = doc.polylines
    assert circle.pen == 3
    assert len(circle.points) == 5
    assert (circle.points[0].x, circle.points[0].y) == (7.0, 6.0)
    assert circle.points[-1].x == pytest.approx(circle.points[0].x)
    assert circle.points[-1].y == pytest.approx(circle.points[0].y)
    assert [(p.x, p.y) for p in line.points] == [(5.0, 6.0), (7.0, 6.0)]


def test_negative_circle_radius_starts_at_180_degrees():
    doc = HPGLParser(1.0).parse_text("IN;PA5,6;CI-2,180;")

    circle = doc.polylines[0]
    assert circle.points[0].x == pytest.approx(3.0)
    assert circle.points[0].y == pytest.approx(6.0)


@pytest.mark.parametrize("command", ["AA0,0;", "AA0,0,90,5,1;", "CI;", "CI1,5,2;"])
def test_arc_commands_reject_invalid_parameter_counts(command):
    with pytest.raises(ValueError):
        HPGLParser(1.0).parse_text(f"IN;{command}")
