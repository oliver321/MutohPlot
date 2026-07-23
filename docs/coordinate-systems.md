# Coordinate systems

Internal geometry uses millimetres.

SVG:
- origin top-left
- x right
- y down

Mutoh XP-500:
- origin centre
- first HPGL coordinate vertical/down
- second HPGL coordinate horizontal/right

For page width W and height H:

    first  = svg_y - H/2
    second = svg_x - W/2
