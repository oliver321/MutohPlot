from dataclasses import dataclass
from ..document import PlotDocument
from ..geometry.point import Point

@dataclass(frozen=True, slots=True)
class FitResult:
    scale: float
    offset_x: float
    offset_y: float
    target_width_mm: float
    target_height_mm: float


def fit_document(document: PlotDocument, width_mm: float, height_mm: float, margin_mm: float = 0.0) -> FitResult:
    bounds = document.bounds()
    if bounds is None:
        return FitResult(1.0, 0.0, 0.0, width_mm, height_mm)
    x0, y0, x1, y1 = bounds
    source_w = x1 - x0
    source_h = y1 - y0
    target_w = width_mm - 2 * margin_mm
    target_h = height_mm - 2 * margin_mm
    if target_w <= 0 or target_h <= 0:
        raise ValueError("Margin leaves no drawable area")
    sx = target_w / source_w if source_w else float("inf")
    sy = target_h / source_h if source_h else float("inf")
    scale = min(sx, sy)
    if scale == float("inf"):
        scale = 1.0
    drawn_w = source_w * scale
    drawn_h = source_h * scale
    offset_x = margin_mm + (target_w - drawn_w) / 2 - x0 * scale
    offset_y = margin_mm + (target_h - drawn_h) / 2 - y0 * scale
    return FitResult(scale, offset_x, offset_y, width_mm, height_mm)


def apply_fit(document: PlotDocument, fit: FitResult) -> PlotDocument:
    from ..geometry.polyline import Polyline
    from ..document import PlotDocument
    polylines = []
    for poly in document.polylines:
        points = [Point(p.x * fit.scale + fit.offset_x, p.y * fit.scale + fit.offset_y) for p in poly.points]
        polylines.append(Polyline(points, poly.pen, poly.source_color))
    metadata = dict(document.metadata)
    metadata.update({"fit_scale": fit.scale, "page_width_mm": fit.target_width_mm, "page_height_mm": fit.target_height_mm})
    return PlotDocument(polylines, metadata)
