from math import cos, pi, sin

from .document import PlotDocument
from .geometry.point import Point
from .geometry.polyline import Polyline
from .hard_clip import drawable_area, get_hard_clip
from .paper import get_paper


def _line(doc: PlotDocument, x1: float, y1: float, x2: float, y2: float, pen: int = 1):
    doc.add_polyline(Polyline([Point(x1, y1), Point(x2, y2)], pen=pen))


def _rect(doc: PlotDocument, x0: float, y0: float, x1: float, y1: float, pen: int = 1):
    doc.add_polyline(
        Polyline(
            [
                Point(x0, y0),
                Point(x1, y0),
                Point(x1, y1),
                Point(x0, y1),
                Point(x0, y0),
            ],
            pen=pen,
        )
    )


def _circle(doc: PlotDocument, cx: float, cy: float, radius: float, pen: int = 1):
    points = [
        Point(cx + radius * cos(2 * pi * i / 48), cy + radius * sin(2 * pi * i / 48))
        for i in range(49)
    ]
    doc.add_polyline(Polyline(points, pen=pen))


def create_a3_calibration(window: str = "norm", margin_mm: float = 0.0) -> PlotDocument:
    paper = get_paper("a3")
    profile = get_hard_clip(window)
    hard = drawable_area(paper, profile, 0.0)
    safe = drawable_area(paper, profile, margin_mm)

    doc = PlotDocument(
        metadata={
            "page_width_mm": paper.width_mm,
            "page_height_mm": paper.height_mm,
            "paper": "A3",
            "hard_clip_profile": profile.name,
            "calibration": True,
        }
    )

    # Paper reference, hard clip, and optional safe area.
    _rect(doc, 0, 0, paper.width_mm, paper.height_mm, pen=1)
    _rect(doc, hard.x_min_mm, hard.y_min_mm, hard.x_max_mm, hard.y_max_mm, pen=2)
    if margin_mm > 0:
        _rect(doc, safe.x_min_mm, safe.y_min_mm, safe.x_max_mm, safe.y_max_mm, pen=3)

    # Paper-centre cross and circle.
    cx, cy = paper.width_mm / 2, paper.height_mm / 2
    _line(doc, cx - 30, cy, cx + 30, cy, pen=1)
    _line(doc, cx, cy - 30, cx, cy + 30, pen=1)
    _circle(doc, cx, cy, 10, pen=1)

    # Hard-clip-centre cross.
    hcx, hcy = hard.center_x_mm, hard.center_y_mm
    _line(doc, hcx - 20, hcy, hcx + 20, hcy, pen=2)
    _line(doc, hcx, hcy - 20, hcx, hcy + 20, pen=2)

    # 50, 100 and 200 mm measuring bars inside the hard clip.
    x = hard.x_min_mm + 20
    y = hard.y_min_mm + 25
    for length, pen in [(50, 1), (100, 2), (200, 3)]:
        _line(doc, x, y, x + length, y, pen=pen)
        _line(doc, x, y - 3, x, y + 3, pen=pen)
        _line(doc, x + length, y - 3, x + length, y + 3, pen=pen)
        y += 15

    # Corner and midpoint tick marks at the hard-clip boundaries.
    tick = 6
    for px, py in [
        (hard.x_min_mm, hard.y_min_mm),
        (hard.x_max_mm, hard.y_min_mm),
        (hard.x_min_mm, hard.y_max_mm),
        (hard.x_max_mm, hard.y_max_mm),
    ]:
        _line(doc, px - tick, py, px + tick, py, pen=2)
        _line(doc, px, py - tick, px, py + tick, pen=2)

    _line(doc, hcx - tick, hard.y_min_mm, hcx + tick, hard.y_min_mm, pen=2)
    _line(doc, hcx - tick, hard.y_max_mm, hcx + tick, hard.y_max_mm, pen=2)
    _line(doc, hard.x_min_mm, hcy - tick, hard.x_min_mm, hcy + tick, pen=2)
    _line(doc, hard.x_max_mm, hcy - tick, hard.x_max_mm, hcy + tick, pen=2)

    return doc
