from pathlib import Path

from mutohplot.devices.mutoh_xp500 import MutohXP500
from mutohplot.hpgl.parser import HPGLParser
from mutohplot.hpgl.writer import HPGLWriter


def test_relative_hpgl():
    doc = HPGLParser(1.0).parse_text("IN;PA10,20;PD;PR5,-2,5,2;PU;")
    assert [(p.x,p.y) for p in doc.polylines[0].points] == [
        (10,20),(15,18),(20,20)
    ]


def test_arc_and_circle_are_written_as_mutoh_polylines():
    doc = HPGLParser(1.0).parse_text(
        "IN;SP2;PU10,0;PD;AA0,0,90,45;PU20,20;CI5,90;"
    )

    hpgl = HPGLWriter(MutohXP500(unit_mm=1.0)).write(doc)

    assert "SP2;PU10,0;PD7,7,0,10;PU;" in hpgl
    assert "PU25,20;PD20,25,15,20,20,15,25,20;PU;" in hpgl


def test_libtest_fixture_parses_with_arcs_and_circles():
    input_path = Path(__file__).parent.parent / "examples" / "libtest.hpgl"

    document = HPGLParser().parse_text(input_path.read_text(errors="replace"))

    assert len(document.polylines) == 25
    assert sum(len(line.points) for line in document.polylines) == 731
