from mutohplot.hpgl.parser import HPGLParser

def test_relative_hpgl():
    doc = HPGLParser(1.0).parse_text("IN;PA10,20;PD;PR5,-2,5,2;PU;")
    assert [(p.x,p.y) for p in doc.polylines[0].points] == [
        (10,20),(15,18),(20,20)
    ]
