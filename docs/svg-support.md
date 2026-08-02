# SVG support

Supported elements:
- line
- polyline
- polygon
- rect
- circle
- ellipse
- path

Nested element and group transforms are composed in SVG order. Geometry inside
non-rendering definition containers such as `defs`, `clipPath`, `mask`, and
`symbol` is not plotted directly.

Supported path commands:
- M/m
- L/l
- H/h
- V/v
- C/c
- S/s
- Q/q
- T/t
- A/a
- Z/z

Not yet supported:
- text
- applying clip-path geometry (definitions themselves are correctly ignored)
- CSS-based visibility and styling
