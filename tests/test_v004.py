from mutohplot.svg.path import parse_path
from mutohplot.svg.reader import SVGReader
from mutohplot.document import PlotDocument
from mutohplot.geometry.point import Point
from mutohplot.geometry.polyline import Polyline
from mutohplot.optimize.paths import optimize_nearest

def test_extended_paths():
 assert len(parse_path('M0,0 C0,10 10,10 10,0 S20,-10 20,0',8)[0].points)==17
 assert len(parse_path('M0,0 Q5,10 10,0 T20,0',8)[0].points)==17
 assert parse_path('M0,0 A10,10 0 0 1 20,0',24)[0].points[-1].x==20

def test_visibility_and_pens():
 s='<svg xmlns="http://www.w3.org/2000/svg" width="100mm" height="50mm"><line x2="10" stroke="red"/><line y1="10" x2="10" y2="10" stroke="blue"/><line y1="20" x2="10" y2="20" stroke="none"/></svg>'
 d=SVGReader().read_text(s);assert len(d.polylines)==2;assert [p.pen for p in d.polylines]==[1,2]

def test_optimizer():
 d=PlotDocument([Polyline([Point(0,0),Point(1,0)]),Polyline([Point(100,0),Point(101,0)]),Polyline([Point(2,0),Point(3,0)])])
 assert optimize_nearest(d).pen_up_distance_mm()<d.pen_up_distance_mm()
