from collections.abc import Callable
from itertools import pairwise
from math import floor, hypot, sqrt

from ..document import PlotDocument
from ..geometry.point import Point
from ..geometry.polyline import Polyline


def dist(a, b):
    return hypot(b.x - a.x, b.y - a.y)


def _point_key(point: Point, tolerance_mm: float) -> tuple[int | float, int | float]:
    if tolerance_mm <= 0:
        return point.x, point.y
    return round(point.x / tolerance_mm), round(point.y / tolerance_mm)


def _segment_key(
    start: Point, end: Point, tolerance_mm: float
) -> tuple[tuple[int | float, int | float], tuple[int | float, int | float]]:
    endpoints = (_point_key(start, tolerance_mm), _point_key(end, tolerance_mm))
    return tuple(sorted(endpoints))


def _flush_run(output: PlotDocument, run: list[Point], source: Polyline) -> None:
    if len(run) >= 2:
        output.add_polyline(Polyline(run[:], source.pen, source.source_color))
    run.clear()


def remove_duplicate_segments(
    document: PlotDocument, tolerance_mm: float = 0.01
) -> tuple[PlotDocument, int]:
    """Remove repeated physical line segments, independent of drawing direction.

    Segments are compared per pen, because drawing the same geometry with another
    pen can be intentional. Duplicate segments split a polyline instead of joining
    non-adjacent points with a new line.
    """
    seen_by_pen: dict[int, set[tuple]] = {}
    output = PlotDocument(metadata=dict(document.metadata))
    removed = 0

    for polyline in document.polylines:
        seen = seen_by_pen.setdefault(polyline.pen, set())
        run: list[Point] = []

        for start, end in pairwise(polyline.points):
            if start == end:
                continue
            key = _segment_key(start, end, tolerance_mm)
            if key in seen:
                removed += 1
                _flush_run(output, run, polyline)
                continue

            seen.add(key)
            if not run:
                run.extend((start, end))
            elif run[-1] == start:
                run.append(end)
            else:
                _flush_run(output, run, polyline)
                run.extend((start, end))

        _flush_run(output, run, polyline)

    output.metadata["duplicate_segments_removed"] = removed
    return output, removed


class _EndpointIndex:
    def __init__(self, polylines: list[Polyline], allow_reverse: bool) -> None:
        endpoints = [polyline.points[0] for polyline in polylines]
        if allow_reverse:
            endpoints.extend(polyline.points[-1] for polyline in polylines)
        xs = [point.x for point in endpoints]
        ys = [point.y for point in endpoints]
        span = max(max(xs) - min(xs), max(ys) - min(ys))
        self.cell_size = span / sqrt(max(len(polylines), 1)) if span > 0 else 1.0
        self.buckets: dict[tuple[int, int], list[tuple[int, bool, Point]]] = {}

        for index, polyline in enumerate(polylines):
            self._add(index, False, polyline.points[0])
            if allow_reverse:
                self._add(index, True, polyline.points[-1])

        cells = self.buckets
        self.min_x = min(cell[0] for cell in cells)
        self.max_x = max(cell[0] for cell in cells)
        self.min_y = min(cell[1] for cell in cells)
        self.max_y = max(cell[1] for cell in cells)

    def _cell(self, point: Point) -> tuple[int, int]:
        return floor(point.x / self.cell_size), floor(point.y / self.cell_size)

    def _add(self, index: int, reverse: bool, point: Point) -> None:
        self.buckets.setdefault(self._cell(point), []).append((index, reverse, point))

    @staticmethod
    def _ring_cells(center_x: int, center_y: int, radius: int):
        if radius == 0:
            yield center_x, center_y
            return
        left = center_x - radius
        right = center_x + radius
        bottom = center_y - radius
        top = center_y + radius
        for x in range(left, right + 1):
            yield x, bottom
            yield x, top
        for y in range(bottom + 1, top):
            yield left, y
            yield right, y

    def nearest(self, point: Point, active: set[int]) -> tuple[int, bool]:
        center_x, center_y = self._cell(point)
        max_radius = max(
            center_x - self.min_x,
            self.max_x - center_x,
            center_y - self.min_y,
            self.max_y - center_y,
        )
        best: tuple[float, int, bool] | None = None

        for radius in range(max_radius + 1):
            for cell in self._ring_cells(center_x, center_y, radius):
                for index, reverse, endpoint in self.buckets.get(cell, ()):
                    if index not in active:
                        continue
                    candidate = (dist(point, endpoint), index, reverse)
                    if best is None or candidate < best:
                        best = candidate

            if best is not None:
                left = (center_x - radius) * self.cell_size
                right = (center_x + radius + 1) * self.cell_size
                bottom = (center_y - radius) * self.cell_size
                top = (center_y + radius + 1) * self.cell_size
                distance_to_unsearched = min(
                    point.x - left,
                    right - point.x,
                    point.y - bottom,
                    top - point.y,
                )
                if best[0] <= distance_to_unsearched:
                    return best[1], best[2]

        if best is None:
            raise RuntimeError("endpoint index contains no active paths")
        return best[1], best[2]


def optimize_nearest(
    document: PlotDocument,
    allow_reverse: bool = True,
    deduplicate: bool = True,
    duplicate_tolerance_mm: float = 0.01,
    progress: Callable[[int, int], None] | None = None,
) -> PlotDocument:
    if deduplicate:
        document, _ = remove_duplicate_segments(document, duplicate_tolerance_mm)
    groups = {}
    for p in document.polylines:
        groups.setdefault(p.pen, []).append(p)
    out = []
    total = len(document.polylines)
    completed = 0
    progress_interval = max(1, total // 100)
    for pen in sorted(groups):
        polylines = groups[pen]
        index = _EndpointIndex(polylines, allow_reverse)
        active = set(range(len(polylines)))
        current = None
        while active:
            if current is None:
                selected, reverse = min(active), False
            else:
                selected, reverse = index.nearest(current, active)
            active.remove(selected)
            polyline = polylines[selected]
            if reverse:
                polyline = polyline.reversed_copy()
            out.append(polyline)
            current = polyline.points[-1]
            completed += 1
            if progress and (completed == total or completed % progress_interval == 0):
                progress(completed, total)
    return PlotDocument(out, dict(document.metadata))
