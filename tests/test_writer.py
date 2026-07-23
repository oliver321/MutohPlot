from mutohplot.document import PlotDocument
from mutohplot.geometry.point import Point
from mutohplot.geometry.polyline import Polyline
from mutohplot.devices.mutoh_xp500 import MutohXP500
from mutohplot.hpgl.writer import HPGLWriter

def test_writer_resolution():
    doc = PlotDocument([Polyline([Point(0,0),Point(1,2)])])
    hpgl = HPGLWriter(MutohXP500(unit_mm=0.01)).write(doc)
    assert "PD100,200;" in hpgl
