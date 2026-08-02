from itertools import pairwise
from math import hypot

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


def optimize_nearest(
    document: PlotDocument,
    allow_reverse: bool = True,
    deduplicate: bool = True,
    duplicate_tolerance_mm: float = 0.01,
) -> PlotDocument:
    if deduplicate:
        document, _ = remove_duplicate_segments(document, duplicate_tolerance_mm)
    groups = {}
    for p in document.polylines:
        groups.setdefault(p.pen, []).append(p)
    out = []
    for pen in sorted(groups):
        rem = groups[pen][:]
        cur = None
        while rem:
            best = (float("inf"), 0, False)
            for i, p in enumerate(rem):
                ds = 0 if cur is None else dist(cur, p.points[0])
                de = 0 if cur is None else dist(cur, p.points[-1])
                if ds < best[0]:
                    best = (ds, i, False)
                if allow_reverse and de < best[0]:
                    best = (de, i, True)
            _, i, rev = best
            p = rem.pop(i)
            if rev:
                p = p.reversed_copy()
            out.append(p)
            cur = p.points[-1]
    return PlotDocument(out, dict(document.metadata))
