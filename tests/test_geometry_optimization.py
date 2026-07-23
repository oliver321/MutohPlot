from mutohplot.document import PlotDocument
from mutohplot.geometry.point import Point
from mutohplot.geometry.polyline import Polyline
from mutohplot.optimize.geometry import douglas_peucker,optimize_geometry,remove_duplicate_points

def test_duplicates(): assert remove_duplicate_points([Point(0,0),Point(0,0),Point(1,0)])==[Point(0,0),Point(1,0)]
def test_straight_line(): assert len(douglas_peucker([Point(x/10,0.001*((-1)**x)) for x in range(101)],0.01))==2
def test_document_reduction():
    out,stats=optimize_geometry(PlotDocument([Polyline([Point(x/100,0) for x in range(1001)])]),'normal')
    assert stats.points_after<stats.points_before and len(out.polylines[0].points)==2
