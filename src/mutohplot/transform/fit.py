from dataclasses import dataclass

from ..document import PlotDocument
from ..geometry.point import Point
from ..geometry.polyline import Polyline
from ..hard_clip import DrawableArea


@dataclass(frozen=True, slots=True)
class FitResult:
    scale: float
    offset_x: float
    offset_y: float
    target_width_mm: float
    target_height_mm: float
    area_x_min_mm: float = 0.0
    area_y_min_mm: float = 0.0
    area_x_max_mm: float | None = None
    area_y_max_mm: float | None = None


def fit_document(
    document: PlotDocument,
    width_mm: float,
    height_mm: float,
    margin_mm: float = 0.0,
) -> FitResult:
    """Backward-compatible fit to a page rectangle."""

    area = DrawableArea(
        margin_mm,
        margin_mm,
        width_mm - margin_mm,
        height_mm - margin_mm,
    )
    return fit_document_to_area(document, area, width_mm, height_mm)


def fit_document_to_area(
    document: PlotDocument,
    area: DrawableArea,
    page_width_mm: float,
    page_height_mm: float,
) -> FitResult:
    bounds = document.bounds()
    if bounds is None:
        return FitResult(
            1.0,
            0.0,
            0.0,
            page_width_mm,
            page_height_mm,
            area.x_min_mm,
            area.y_min_mm,
            area.x_max_mm,
            area.y_max_mm,
        )

    x0, y0, x1, y1 = bounds
    source_w = x1 - x0
    source_h = y1 - y0
    target_w = area.width_mm
    target_h = area.height_mm

    if target_w <= 0 or target_h <= 0:
        raise ValueError("Target area has no drawable size")

    sx = target_w / source_w if source_w else float("inf")
    sy = target_h / source_h if source_h else float("inf")
    scale = min(sx, sy)
    if scale == float("inf"):
        scale = 1.0

    drawn_w = source_w * scale
    drawn_h = source_h * scale
    offset_x = area.x_min_mm + (target_w - drawn_w) / 2.0 - x0 * scale
    offset_y = area.y_min_mm + (target_h - drawn_h) / 2.0 - y0 * scale

    return FitResult(
        scale,
        offset_x,
        offset_y,
        page_width_mm,
        page_height_mm,
        area.x_min_mm,
        area.y_min_mm,
        area.x_max_mm,
        area.y_max_mm,
    )


def apply_fit(document: PlotDocument, fit: FitResult) -> PlotDocument:
    polylines = []
    for poly in document.polylines:
        points = [
            Point(
                p.x * fit.scale + fit.offset_x,
                p.y * fit.scale + fit.offset_y,
            )
            for p in poly.points
        ]
        polylines.append(Polyline(points, poly.pen, poly.source_color))

    metadata = dict(document.metadata)
    metadata.update(
        {
            "fit_scale": fit.scale,
            "page_width_mm": fit.target_width_mm,
            "page_height_mm": fit.target_height_mm,
            "fit_area": (
                fit.area_x_min_mm,
                fit.area_y_min_mm,
                fit.area_x_max_mm,
                fit.area_y_max_mm,
            ),
        }
    )
    return PlotDocument(polylines, metadata)
