import math
import re

from ..geometry.point import Point
from ..geometry.polyline import Polyline

TOKEN_RE = re.compile(r"[A-Za-z]|[-+]?(?:\d*\.\d+|\d+\.?)(?:[eE][-+]?\d+)?")


def cubic(p0, p1, p2, p3, n):
    return [
        Point(
            (1 - t) ** 3 * p0.x
            + 3 * (1 - t) ** 2 * t * p1.x
            + 3 * (1 - t) * t * t * p2.x
            + t**3 * p3.x,
            (1 - t) ** 3 * p0.y
            + 3 * (1 - t) ** 2 * t * p1.y
            + 3 * (1 - t) * t * t * p2.y
            + t**3 * p3.y,
        )
        for t in (i / n for i in range(1, n + 1))
    ]


def quad(p0, p1, p2, n):
    return [
        Point(
            (1 - t) ** 2 * p0.x + 2 * (1 - t) * t * p1.x + t * t * p2.x,
            (1 - t) ** 2 * p0.y + 2 * (1 - t) * t * p1.y + t * t * p2.y,
        )
        for t in (i / n for i in range(1, n + 1))
    ]


def arc(p0, rx, ry, phi, large, sweep, p1, n):
    if rx == 0 or ry == 0 or p0 == p1:
        return [p1]
    rx, ry = abs(rx), abs(ry)
    ph = math.radians(phi % 360)
    cp, sp = math.cos(ph), math.sin(ph)
    dx, dy = (p0.x - p1.x) / 2, (p0.y - p1.y) / 2
    xp = cp * dx + sp * dy
    yp = -sp * dx + cp * dy
    lam = xp * xp / (rx * rx) + yp * yp / (ry * ry)
    if lam > 1:
        s = math.sqrt(lam)
        rx *= s
        ry *= s
    sg = -1 if bool(large) == bool(sweep) else 1
    num = max(0, rx * rx * ry * ry - rx * rx * yp * yp - ry * ry * xp * xp)
    den = rx * rx * yp * yp + ry * ry * xp * xp
    k = 0 if den == 0 else sg * math.sqrt(num / den)
    cxp = k * rx * yp / ry
    cyp = -k * ry * xp / rx
    cx = cp * cxp - sp * cyp + (p0.x + p1.x) / 2
    cy = sp * cxp + cp * cyp + (p0.y + p1.y) / 2

    def ang(u, v):
        m = math.hypot(*u) * math.hypot(*v)
        z = 1 if m == 0 else max(-1, min(1, (u[0] * v[0] + u[1] * v[1]) / m))
        a = math.acos(z)
        return -a if u[0] * v[1] - u[1] * v[0] < 0 else a

    u = ((xp - cxp) / rx, (yp - cyp) / ry)
    v = ((-xp - cxp) / rx, (-yp - cyp) / ry)
    a0 = ang((1, 0), u)
    da = ang(u, v)
    if not sweep and da > 0:
        da -= 2 * math.pi
    if sweep and da < 0:
        da += 2 * math.pi
    count = max(4, int(abs(da) / (2 * math.pi) * n))
    return [
        Point(
            cx + cp * rx * math.cos(a0 + da * i / count) - sp * ry * math.sin(a0 + da * i / count),
            cy + sp * rx * math.cos(a0 + da * i / count) + cp * ry * math.sin(a0 + da * i / count),
        )
        for i in range(1, count + 1)
    ]


def parse_path(data, curve_steps=24):
    tok = TOKEN_RE.findall(data)
    i = 0
    cmd = None
    cur = Point(0, 0)
    start = cur
    pts = []
    out = []
    cc = qc = None

    def finish():
        nonlocal pts
        if len(pts) >= 2:
            out.append(Polyline(pts))
        pts = []

    def num():
        nonlocal i
        v = float(tok[i])
        i += 1
        return v

    while i < len(tok):
        if tok[i].isalpha():
            cmd = tok[i]
            i += 1
        rel = cmd.islower()
        op = cmd.upper()
        if op == "M":
            x, y = num(), num()
            x += cur.x if rel else 0
            y += cur.y if rel else 0
            finish()
            cur = start = Point(x, y)
            pts = [cur]
            cmd = "l" if rel else "L"
            cc = qc = None
        elif op == "L":
            x, y = num(), num()
            x += cur.x if rel else 0
            y += cur.y if rel else 0
            cur = Point(x, y)
            pts.append(cur)
            cc = qc = None
        elif op == "H":
            cur = Point(num() + (cur.x if rel else 0), cur.y)
            pts.append(cur)
            cc = qc = None
        elif op == "V":
            cur = Point(cur.x, num() + (cur.y if rel else 0))
            pts.append(cur)
            cc = qc = None
        elif op == "C":
            x1, y1, x2, y2, x, y = [num() for _ in range(6)]
            if rel:
                x1 += cur.x
                y1 += cur.y
                x2 += cur.x
                y2 += cur.y
                x += cur.x
                y += cur.y
            p1, p2, p3 = Point(x1, y1), Point(x2, y2), Point(x, y)
            pts += cubic(cur, p1, p2, p3, curve_steps)
            cur = p3
            cc = p2
            qc = None
        elif op == "S":
            x2, y2, x, y = [num() for _ in range(4)]
            if rel:
                x2 += cur.x
                y2 += cur.y
                x += cur.x
                y += cur.y
            p1 = cur if cc is None else Point(2 * cur.x - cc.x, 2 * cur.y - cc.y)
            p2, p3 = Point(x2, y2), Point(x, y)
            pts += cubic(cur, p1, p2, p3, curve_steps)
            cur = p3
            cc = p2
            qc = None
        elif op == "Q":
            x1, y1, x, y = [num() for _ in range(4)]
            if rel:
                x1 += cur.x
                y1 += cur.y
                x += cur.x
                y += cur.y
            p1, p2 = Point(x1, y1), Point(x, y)
            pts += quad(cur, p1, p2, curve_steps)
            cur = p2
            qc = p1
            cc = None
        elif op == "T":
            x, y = num(), num()
            x += cur.x if rel else 0
            y += cur.y if rel else 0
            p1 = cur if qc is None else Point(2 * cur.x - qc.x, 2 * cur.y - qc.y)
            p2 = Point(x, y)
            pts += quad(cur, p1, p2, curve_steps)
            cur = p2
            qc = p1
            cc = None
        elif op == "A":
            rx, ry, rot, large, sweep, x, y = [num() for _ in range(7)]
            x += cur.x if rel else 0
            y += cur.y if rel else 0
            p = Point(x, y)
            pts += arc(cur, rx, ry, rot, int(large), int(sweep), p, curve_steps)
            cur = p
            cc = qc = None
        elif op == "Z":
            if cur != start:
                pts.append(start)
            cur = start
            finish()
            cmd = None
            cc = qc = None
        else:
            raise NotImplementedError(cmd)
    finish()
    return out
