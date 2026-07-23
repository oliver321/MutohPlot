from mutohplot.svg.reader import SVGReader

SVG = """<svg xmlns="http://www.w3.org/2000/svg" width="100mm" height="50mm">
<line x1="0" y1="0" x2="100" y2="50"/>
<rect x="10" y="10" width="20" height="10"/>
<path d="M 0 25 L 100 25"/>
</svg>"""

def test_svg_primitives():
    doc = SVGReader().read_text(SVG)
    assert doc.metadata["page_width_mm"] == 100.0
    assert doc.metadata["page_height_mm"] == 50.0
    assert len(doc.polylines) == 3
