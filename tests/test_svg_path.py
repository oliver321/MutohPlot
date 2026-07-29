from mutohplot.svg.path import parse_path


def test_path_line_and_close():
    polys = parse_path("M0,0 L10,0 L10,10 Z")
    assert len(polys) == 1
    assert len(polys[0].points) == 4
    assert polys[0].points[0] == polys[0].points[-1]


def test_cubic_curve_is_flattened():
    polys = parse_path("M0,0 C0,10 10,10 10,0", curve_steps=8)
    assert len(polys[0].points) == 9
