import re
from ..geometry.point import Point
from ..geometry.polyline import Polyline

TOKEN_RE = re.compile(r"[A-Za-z]|[-+]?(?:\d*\.\d+|\d+\.?)(?:[eE][-+]?\d+)?")

def _cubic(p0, p1, p2, p3, steps):
    pts = []
    for i in range(1, steps + 1):
        t = i / steps
        u = 1 - t
        pts.append(Point(
            u**3*p0.x + 3*u*u*t*p1.x + 3*u*t*t*p2.x + t**3*p3.x,
            u**3*p0.y + 3*u*u*t*p1.y + 3*u*t*t*p2.y + t**3*p3.y,
        ))
    return pts

def _quad(p0, p1, p2, steps):
    pts = []
    for i in range(1, steps + 1):
        t = i / steps
        u = 1 - t
        pts.append(Point(
            u*u*p0.x + 2*u*t*p1.x + t*t*p2.x,
            u*u*p0.y + 2*u*t*p1.y + t*t*p2.y,
        ))
    return pts

def parse_path(data: str, curve_steps: int = 24) -> list[Polyline]:
    tokens = TOKEN_RE.findall(data)
    i = 0
    cmd = None
    cur = Point(0, 0)
    start = Point(0, 0)
    current = []
    result = []

    def finish():
        nonlocal current
        if len(current) >= 2:
            result.append(Polyline(current))
        current = []

    def num():
        nonlocal i
        v = float(tokens[i]); i += 1
        return v

    while i < len(tokens):
        if tokens[i].isalpha():
            cmd = tokens[i]; i += 1
        if cmd is None:
            raise ValueError("Path data missing command")

        rel = cmd.islower()
        op = cmd.upper()

        if op == "M":
            x, y = num(), num()
            if rel:
                x += cur.x; y += cur.y
            finish()
            cur = start = Point(x, y)
            current = [cur]
            cmd = "l" if rel else "L"

        elif op == "L":
            x, y = num(), num()
            if rel:
                x += cur.x; y += cur.y
            cur = Point(x, y)
            current.append(cur)

        elif op == "H":
            x = num() + (cur.x if rel else 0)
            cur = Point(x, cur.y)
            current.append(cur)

        elif op == "V":
            y = num() + (cur.y if rel else 0)
            cur = Point(cur.x, y)
            current.append(cur)

        elif op == "C":
            x1,y1,x2,y2,x,y = num(),num(),num(),num(),num(),num()
            if rel:
                x1+=cur.x; y1+=cur.y; x2+=cur.x; y2+=cur.y; x+=cur.x; y+=cur.y
            p1,p2,p3 = Point(x1,y1),Point(x2,y2),Point(x,y)
            current.extend(_cubic(cur,p1,p2,p3,curve_steps))
            cur = p3

        elif op == "Q":
            x1,y1,x,y = num(),num(),num(),num()
            if rel:
                x1+=cur.x; y1+=cur.y; x+=cur.x; y+=cur.y
            p1,p2 = Point(x1,y1),Point(x,y)
            current.extend(_quad(cur,p1,p2,curve_steps))
            cur = p2

        elif op == "Z":
            if cur != start:
                current.append(start)
            cur = start
            finish()
            cmd = None

        else:
            raise NotImplementedError(f"Unsupported SVG path command: {cmd}")

    finish()
    return result
