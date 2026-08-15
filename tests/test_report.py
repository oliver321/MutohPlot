from mutohplot.document import PlotDocument
from mutohplot.geometry.point import Point
from mutohplot.geometry.polyline import Polyline
from mutohplot.hard_clip import drawable_area, get_hard_clip
from mutohplot.paper import get_paper
from mutohplot.report import check_bounds, transformation_report

def test_bounds_report_inside_and_outside():
    paper = get_paper("a3")
    profile = get_hard_clip("norm")
    area = drawable_area(paper, profile)
    inside = PlotDocument([Polyline([Point(20, 40), Point(270, 390)])])
    assert check_bounds(inside, area).inside
    outside = PlotDocument([Polyline([Point(0, 0), Point(270, 390)])])
    result = check_bounds(outside, area)
    assert not result.inside
    assert result.left_over_mm == 15
    assert result.top_over_mm == 35
    text = transformation_report(inside, paper, profile, area, 0)
    assert "Bounds check: inside" in text
