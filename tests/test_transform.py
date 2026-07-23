from mutohplot.geometry.point import Point
from mutohplot.transform.coordinate import CoordinateTransform

def test_svg_to_mutoh_a2():
    t = CoordinateTransform.svg_to_mutoh(420.0, 594.0)
    assert t.apply(Point(210.0, 297.0)) == Point(0.0, 0.0)
    assert t.apply(Point(0.0, 0.0)) == Point(-297.0, -210.0)
