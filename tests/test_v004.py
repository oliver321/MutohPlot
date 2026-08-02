from mutohplot.document import PlotDocument
from mutohplot.geometry.point import Point
from mutohplot.geometry.polyline import Polyline
from mutohplot.optimize.paths import optimize_nearest, remove_duplicate_segments
from mutohplot.svg.path import parse_path
from mutohplot.svg.reader import SVGReader


def test_extended_paths():
    assert len(parse_path("M0,0 C0,10 10,10 10,0 S20,-10 20,0", 8)[0].points) == 17
    assert len(parse_path("M0,0 Q5,10 10,0 T20,0", 8)[0].points) == 17
    assert parse_path("M0,0 A10,10 0 0 1 20,0", 24)[0].points[-1].x == 20


def test_visibility_and_pens():
    s = '<svg xmlns="http://www.w3.org/2000/svg" width="100mm" height="50mm"><line x2="10" stroke="red"/><line y1="10" x2="10" y2="10" stroke="blue"/><line y1="20" x2="10" y2="20" stroke="none"/></svg>'
    d = SVGReader().read_text(s)
    assert len(d.polylines) == 2
    assert [p.pen for p in d.polylines] == [1, 2]


def test_optimizer():
    d = PlotDocument(
        [
            Polyline([Point(0, 0), Point(1, 0)]),
            Polyline([Point(100, 0), Point(101, 0)]),
            Polyline([Point(2, 0), Point(3, 0)]),
        ]
    )
    assert optimize_nearest(d).pen_up_distance_mm() < d.pen_up_distance_mm()


def test_duplicate_segments_are_removed_in_both_directions():
    document = PlotDocument(
        [
            Polyline([Point(0, 0), Point(10, 0)], pen=1),
            Polyline([Point(10, 0), Point(0, 0)], pen=1),
        ]
    )

    output, removed = remove_duplicate_segments(document)

    assert removed == 1
    assert len(output.polylines) == 1
    assert output.polylines[0].points == [Point(0, 0), Point(10, 0)]


def test_repeated_frame_is_only_drawn_once():
    frame = [Point(0, 0), Point(20, 0), Point(20, 10), Point(0, 10), Point(0, 0)]
    document = PlotDocument([Polyline(frame, pen=1), Polyline(frame, pen=1)])

    output = optimize_nearest(document)

    assert output.metadata["duplicate_segments_removed"] == 4
    assert len(output.polylines) == 1
    assert output.polylines[0].points == frame


def test_same_segment_with_different_pens_is_preserved():
    document = PlotDocument(
        [
            Polyline([Point(0, 0), Point(10, 0)], pen=1),
            Polyline([Point(10, 0), Point(0, 0)], pen=2),
        ]
    )

    output, removed = remove_duplicate_segments(document)

    assert removed == 0
    assert len(output.polylines) == 2


def test_duplicate_segment_splits_path_without_adding_connection():
    document = PlotDocument(
        [
            Polyline([Point(0, 0), Point(1, 0)], pen=1),
            Polyline([Point(0, 0), Point(1, 0), Point(1, 1)], pen=1),
        ]
    )

    output, removed = remove_duplicate_segments(document)

    assert removed == 1
    assert len(output.polylines) == 2
    assert output.polylines[1].points == [Point(1, 0), Point(1, 1)]
