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


def test_definition_and_clip_path_geometry_is_not_drawn():
    svg = """<svg xmlns="http://www.w3.org/2000/svg" width="100mm" height="100mm">
    <defs>
      <clipPath id="clip"><path d="M0,0 L100,0 L100,100 L0,100 Z"/></clipPath>
    </defs>
    <path d="M10,10 L20,20" clip-path="url(#clip)"/>
    </svg>"""

    document = SVGReader().read_text(svg)

    assert len(document.polylines) == 1
    assert [(point.x, point.y) for point in document.polylines[0].points] == [
        (10.0, 10.0),
        (20.0, 20.0),
    ]


def test_nested_transforms_are_applied_from_element_to_parent():
    svg = """<svg xmlns="http://www.w3.org/2000/svg" width="100mm" height="100mm">
    <g transform="translate(10,20)">
      <line x1="1" y1="2" x2="3" y2="4" transform="scale(2)"/>
    </g>
    </svg>"""

    document = SVGReader().read_text(svg)

    assert [(point.x, point.y) for point in document.polylines[0].points] == [
        (12.0, 24.0),
        (16.0, 28.0),
    ]
