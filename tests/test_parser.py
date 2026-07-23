from mutohplot.hpgl.parser import HPGLParser

def test_absolute_pen_down_path():
    doc = HPGLParser(0.025).parse_text("IN;SP2;PU100,200;PD300,400,500,600;PU;")
    assert len(doc.polylines) == 1
    poly = doc.polylines[0]
    assert poly.pen == 2
    assert [(p.x, p.y) for p in poly.points] == [
        (2.5, 5.0), (7.5, 10.0), (12.5, 15.0)
    ]

def test_relative_mode():
    doc = HPGLParser(1.0).parse_text("IN;PA10,20;PD;PR5,-2,5,2;PU;")
    assert [(p.x, p.y) for p in doc.polylines[0].points] == [
        (10.0, 20.0), (15.0, 18.0), (20.0, 20.0)
    ]
