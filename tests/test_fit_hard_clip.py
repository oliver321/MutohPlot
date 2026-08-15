from mutohplot.document import PlotDocument
from mutohplot.geometry.point import Point
from mutohplot.geometry.polyline import Polyline
from mutohplot.hard_clip import drawable_area, get_hard_clip
from mutohplot.paper import get_paper
from mutohplot.transform.fit import apply_fit, fit_document_to_area


def test_fit_centres_inside_asymmetric_norm_clip_area():
    doc = PlotDocument([Polyline([Point(0, 0), Point(100, 100)])])
    paper = get_paper("a3")
    area = drawable_area(paper, get_hard_clip("norm"))
    fit = fit_document_to_area(doc, area, paper.width_mm, paper.height_mm)
    out = apply_fit(doc, fit)

    # Width limits the 100x100 square: 267 mm wide, centred vertically
    # inside y=35..405 (370 mm high).
    assert out.bounds() == (15.0, 86.5, 282.0, 353.5)


def test_fit_with_additional_margin():
    doc = PlotDocument([Polyline([Point(0, 0), Point(100, 50)])])
    paper = get_paper("a2")
    area = drawable_area(paper, get_hard_clip("exp"), 10.0)
    fit = fit_document_to_area(doc, area, paper.width_mm, paper.height_mm)
    out = apply_fit(doc, fit)
    x0, y0, x1, y1 = out.bounds()
    assert x0 >= area.x_min_mm
    assert y0 >= area.y_min_mm
    assert x1 <= area.x_max_mm
    assert y1 <= area.y_max_mm
