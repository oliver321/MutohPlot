from dataclasses import dataclass
from math import hypot

from ..document import PlotDocument
from ..geometry.point import Point
from ..geometry.polyline import Polyline


@dataclass(frozen=True, slots=True)
class QualityProfile:
    name: str
    tolerance_mm: float
    minimum_segment_mm: float
    quantize_mm: float


QUALITY_PROFILES = {
    "precise": QualityProfile("precise", 0.02, 0.01, 0.01),
    "normal": QualityProfile("normal", 0.05, 0.05, 0.01),
    "fast": QualityProfile("fast", 0.10, 0.10, 0.02),
    "draft": QualityProfile("draft", 0.20, 0.20, 0.05),
}


@dataclass(frozen=True, slots=True)
class OptimizationStats:
    polylines_before: int
    polylines_after: int
    points_before: int
    points_after: int

    @property
    def reduction_percent(self):
        return (
            0.0
            if not self.points_before
            else 100 * (self.points_before - self.points_after) / self.points_before
        )


def point_count(doc):
    return sum(len(p.points) for p in doc.polylines)


def dist(a, b):
    return hypot(b.x - a.x, b.y - a.y)


def quant(v, g):
    return v if g <= 0 else round(v / g) * g


def remove_duplicate_points(points):
    out = []
    for p in points:
        if not out or p != out[-1]:
            out.append(p)
    return out


def remove_short_segments(points, minimum):
    if len(points) <= 2 or minimum <= 0:
        return points[:]
    closed = points[0] == points[-1]
    out = [points[0]]
    for p in points[1:-1]:
        if dist(out[-1], p) >= minimum:
            out.append(p)
    if points[-1] != out[-1]:
        out.append(points[-1])
    if closed and out[-1] != out[0]:
        out.append(out[0])
    return out


def point_line_distance(p, a, b):
    dx = b.x - a.x
    dy = b.y - a.y
    if dx == 0 and dy == 0:
        return dist(p, a)
    return abs(dy * p.x - dx * p.y + b.x * a.y - b.y * a.x) / hypot(dx, dy)


def douglas_peucker(points, tolerance):
    if len(points) <= 2 or tolerance <= 0:
        return points[:]
    closed = points[0] == points[-1]
    work = points[:-1] if closed else points

    def simp(seq):
        if len(seq) <= 2:
            return seq[:]
        ds = [point_line_distance(p, seq[0], seq[-1]) for p in seq[1:-1]]
        if not ds or max(ds) <= tolerance:
            return [seq[0], seq[-1]]
        i = 1 + max(range(len(ds)), key=ds.__getitem__)
        return simp(seq[: i + 1])[:-1] + simp(seq[i:])

    if closed:
        split = max(range(1, len(work)), key=lambda i: dist(work[0], work[i]))
        out = simp(work[: split + 1])[:-1] + simp(work[split:] + [work[0]])
        if out[-1] != out[0]:
            out.append(out[0])
        return out
    return simp(work)


def optimize_geometry(doc, quality="normal"):
    profile = QUALITY_PROFILES[quality]
    before = point_count(doc)
    out = PlotDocument(metadata=dict(doc.metadata))
    for poly in doc.polylines:
        pts = [
            Point(quant(p.x, profile.quantize_mm), quant(p.y, profile.quantize_mm))
            for p in poly.points
        ]
        pts = remove_duplicate_points(pts)
        pts = remove_short_segments(pts, profile.minimum_segment_mm)
        pts = douglas_peucker(pts, profile.tolerance_mm)
        pts = remove_duplicate_points(pts)
        if len(pts) >= 2:
            out.add_polyline(Polyline(pts, poly.pen, poly.source_color))
    stats = OptimizationStats(len(doc.polylines), len(out.polylines), before, point_count(out))
    out.metadata["geometry_optimization"] = {
        "quality": quality,
        "points_before": before,
        "points_after": stats.points_after,
        "reduction_percent": stats.reduction_percent,
    }
    return out, stats
