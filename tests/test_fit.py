from mutohplot.document import PlotDocument
from mutohplot.geometry.point import Point
from mutohplot.geometry.polyline import Polyline
from mutohplot.transform.fit import apply_fit, fit_document


def test_fit_with_margin():
    doc = PlotDocument([Polyline([Point(0, 0), Point(100, 50)])])
    fit = fit_document(doc, 200, 200, 10)
    assert fit.scale == 1.8
    out = apply_fit(doc, fit)
    assert out.bounds() == (10.0, 55.0, 190.0, 145.0)
