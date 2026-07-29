from mutohplot.geometry.point import Point
from mutohplot.transform.coordinate import CoordinateTransform


def test_svg_to_mutoh_center():
    t = CoordinateTransform.svg_to_mutoh(420, 594)
    assert t.apply(Point(210, 297)) == Point(0, 0)
    assert t.apply(Point(0, 0)) == Point(-297, -210)
