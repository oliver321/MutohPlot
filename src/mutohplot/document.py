from dataclasses import dataclass, field
from math import hypot

from .geometry.polyline import Polyline


@dataclass(slots=True)
class PlotDocument:
    polylines: list[Polyline] = field(default_factory=list)
    metadata: dict[str, object] = field(default_factory=dict)

    def add_polyline(self, polyline: Polyline) -> None:
        if len(polyline.points) >= 2:
            self.polylines.append(polyline)

    def drawing_distance_mm(self) -> float:
        return sum(
            hypot(b.x - a.x, b.y - a.y)
            for p in self.polylines
            for a, b in zip(p.points, p.points[1:])
        )

    def pen_up_distance_mm(self) -> float:
        total = 0.0
        current = None
        for p in self.polylines:
            if current is not None:
                total += hypot(p.points[0].x - current.x, p.points[0].y - current.y)
            current = p.points[-1]
        return total

    def bounds(self):
        pts = [q for p in self.polylines for q in p.points]
        if not pts:
            return None
        xs = [q.x for q in pts]
        ys = [q.y for q in pts]
        return min(xs), min(ys), max(xs), max(ys)
