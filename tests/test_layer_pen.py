from mutohplot.svg.reader import SVGReader

SVG = """<svg xmlns="http://www.w3.org/2000/svg" xmlns:inkscape="http://www.inkscape.org/namespaces/inkscape" width="100mm" height="100mm"><g inkscape:groupmode="layer" inkscape:label="Pen 4"><line x1="0" y1="0" x2="10" y2="10" stroke="red"/></g></svg>"""


def test_layer_pen_assignment():
    doc = SVGReader().read_text(SVG)
    assert doc.polylines[0].pen == 4
