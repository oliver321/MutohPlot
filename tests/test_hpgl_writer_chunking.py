from mutohplot.devices.mutoh_xp500 import MutohXP500
from mutohplot.document import PlotDocument
from mutohplot.geometry.point import Point
from mutohplot.geometry.polyline import Polyline
from mutohplot.hpgl.writer import HPGLWriter


def test_chunking():
    hpgl = HPGLWriter(MutohXP500(unit_mm=0.01), max_command_chars=64).write(
        PlotDocument([Polyline([Point(i, i) for i in range(50)])])
    )
    assert hpgl.count("PD") > 1
    assert all(len(c) <= 64 for c in hpgl.split(";") if c.startswith("PD"))
