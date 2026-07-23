from mutohplot.geometry.point import Point
from mutohplot.hard_clip import get_hard_clip
from mutohplot.paper import get_paper
from mutohplot.transform.coordinate import CoordinateTransform
from mutohplot.transform.hard_clip import hard_clip_center_correction


def test_a3_norm_top_left_maps_with_automatic_offset():
    paper = get_paper("a3")
    profile = get_hard_clip("norm")
    base = CoordinateTransform.svg_to_mutoh(paper.width_mm, paper.height_mm)
    correction = hard_clip_center_correction(profile)
    transform = CoordinateTransform(
        base.a, base.b, base.c, base.d,
        base.tx + correction.first_mm,
        base.ty + correction.second_mm,
    )

    # Hard-clip centre is x=148.5, y=220 mm on A3 Norm.
    mapped = transform.apply(Point(148.5, 220.0))
    assert mapped == Point(0.0, 0.0)
