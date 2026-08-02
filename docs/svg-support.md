# SVG support in v0.0.3

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
- Q/q
- Z/z

Not yet supported:
- S/s
- T/t
- A/a
- text
- clip paths
- CSS-based visibility and styling
