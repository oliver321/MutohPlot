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


def test_label_is_converted_to_polylines_and_advances_position():
    doc = HPGLParser(1.0).parse_text(
        "IN;PA0,0;LBAB\x03;PD10,0;PU;"
    )

    assert doc.metadata.get("unsupported_commands") is None
    assert len(doc.polylines) > 2
    assert doc.polylines[-1].points[0].x == pytest.approx(6.84)
    assert (doc.polylines[-1].points[-1].x, doc.polylines[-1].points[-1].y) == (
        10.0,
        0.0,
    )


def test_unsupported_commands_are_collected_for_reporting():
    doc = HPGLParser(1.0).parse_text("IN;VS10;VS20;IP0,0,100,100;")

    assert doc.metadata["unsupported_commands"] == ["VS", "VS", "IP"]


def test_all_tokenized_commands_are_recorded_in_source_order():
    doc = HPGLParser().parse_text("IN;SP2;PU0,0;PD10,10;VS5;")

    assert doc.metadata["hpgl_commands"] == ["IN", "SP", "PU", "PD", "VS"]


def test_label_honours_absolute_size_and_direction():
    doc = HPGLParser(1.0).parse_text(
        "IN;PA10,20;SI0.5,1;DI0,1;LBA\x03;PD10,30;PU;"
    )

    assert doc.metadata.get("unsupported_commands") is None
    assert doc.bounds() == pytest.approx((10.0 / 7.0, 20.0, 10.0, 30.0))
    assert [(point.x, point.y) for point in doc.polylines[-1].points] == [
        (10.0, 26.0),
        (10.0, 30.0),
    ]


def test_character_slant_shears_label_and_resets_without_parameters():
    upright = HPGLParser(1.0).parse_text("IN;SI0.5,1;SL;LBA\x03")
    slanted = HPGLParser(1.0).parse_text("IN;SI0.5,1;SL0.5;LBA\x03")

    assert slanted.metadata.get("unsupported_commands") is None
    assert slanted.polylines[0].points[0].x == pytest.approx(
        upright.polylines[0].points[0].x + 30.0 / 7.0
    )
    assert slanted.polylines[0].points[0].y == pytest.approx(
        upright.polylines[0].points[0].y
    )


def test_character_plot_moves_in_character_cells_and_preserves_pen_state():
    doc = HPGLParser(1.0).parse_text(
        "IN;PA10,20;SI0.5,1;PD;CP2,1;PD30,40;PU;"
    )

    assert doc.metadata.get("unsupported_commands") is None
    assert [(point.x, point.y) for point in doc.polylines[-1].points] == [
        (22.0, 34.0),
        (30.0, 40.0),
    ]


def test_character_plot_without_parameters_returns_and_advances_one_line():
    doc = HPGLParser(1.0).parse_text(
        "IN;PA10,20;SI0.5,1;LBA\x03;CP;PD20,20;PU;"
    )

    assert doc.metadata.get("unsupported_commands") is None
    assert [(point.x, point.y) for point in doc.polylines[-1].points] == [
        (10.0, 6.0),
        (20.0, 20.0),
    ]


@pytest.mark.parametrize("command", ["SL1,2;", "CP1;"])
def test_character_commands_reject_invalid_parameter_counts(command):
    with pytest.raises(ValueError):
        HPGLParser(1.0).parse_text(f"IN;{command}")


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


def test_edge_rectangle_absolute_draws_outline_and_restores_position_and_pen():
    doc = HPGLParser(1.0).parse_text(
        "IN;SP2;PA10,20;PD;EA30,50;PD40,20;PU;"
    )

    rectangle, line = doc.polylines
    assert doc.metadata.get("unsupported_commands") is None
    assert rectangle.pen == 2
    assert [(point.x, point.y) for point in rectangle.points] == [
        (10.0, 20.0),
        (30.0, 20.0),
        (30.0, 50.0),
        (10.0, 50.0),
        (10.0, 20.0),
    ]
    assert [(point.x, point.y) for point in line.points] == [
        (10.0, 20.0),
        (40.0, 20.0),
    ]


def test_fill_rectangle_absolute_uses_dense_serpentine_and_restores_position():
    doc = HPGLParser(1.0).parse_text(
        "IN;PA1,2;RA2,2.5;PD3,2;PU;"
    )

    fill, line = doc.polylines
    assert doc.metadata.get("unsupported_commands") is None
    assert (fill.points[0].x, fill.points[0].y) == pytest.approx((1.0, 2.0))
    assert (fill.points[-1].x, fill.points[-1].y) == pytest.approx((2.0, 2.5))
    assert doc.bounds() == pytest.approx((1.0, 2.0, 3.0, 2.5))
    assert [(point.x, point.y) for point in line.points] == [
        (1.0, 2.0),
        (3.0, 2.0),
    ]
    row_positions = {round(point.y, 6) for point in fill.points}
    assert max(
        upper - lower
        for lower, upper in zip(
            sorted(row_positions),
            sorted(row_positions)[1:],
        )
    ) <= HPGLParser.SOLID_FILL_SPACING_MM


def test_fill_rectangle_uses_spacing_for_active_pen():
    doc = HPGLParser(
        1.0,
        solid_fill_spacing_mm_by_pen={3: 0.2},
    ).parse_text("IN;SP3;PA0,0;RA1,1;")

    fill = doc.polylines[0]
    row_positions = sorted({round(point.y, 6) for point in fill.points})
    assert len(row_positions) == 6
    assert max(
        upper - lower
        for lower, upper in zip(row_positions, row_positions[1:])
    ) <= 0.2 + 1e-9
    assert doc.metadata["ra_pens"] == [3]


@pytest.mark.parametrize("command", ["EA;", "EA1;", "EA1,2,3;", "RA;", "RA1;"])
def test_absolute_rectangle_commands_require_one_coordinate_pair(command):
    with pytest.raises(ValueError):
        HPGLParser(1.0).parse_text(f"IN;{command}")


@pytest.mark.parametrize("command", ["AA0,0;", "AA0,0,90,5,1;", "CI;", "CI1,5,2;"])
def test_arc_commands_reject_invalid_parameter_counts(command):
    with pytest.raises(ValueError):
        HPGLParser(1.0).parse_text(f"IN;{command}")
