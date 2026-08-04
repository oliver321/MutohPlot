import math
import re
import xml.etree.ElementTree as ET

from ..document import PlotDocument
from ..geometry.point import Point
from ..geometry.polyline import Polyline
from .matrix import Matrix
from .path import parse_path

UNIT = {"mm": 1, "cm": 10, "in": 25.4, "pt": 25.4 / 72, "pc": 25.4 / 6, "px": 25.4 / 96, "": 1}


def length_mm(v):
    if v is None:
        return None
    m = re.fullmatch(r"\s*([-+]?(?:\d*\.\d+|\d+\.?)(?:[eE][-+]?\d+)?)\s*([A-Za-z]*)\s*", v)
    return float(m.group(1)) * UNIT[m.group(2).lower()]


def style(s):
    d = {}
    for q in (s or "").split(";"):
        if ":" in q:
            k, v = q.split(":", 1)
            d[k.strip()] = v.strip()
    return d


def transform(s):
    if not s:
        return Matrix()
    out = Matrix()
    for name, arg in re.findall(r"([A-Za-z]+)\s*\(([^)]*)\)", s):
        a = [float(v) for v in re.findall(r"[-+]?(?:\d*\.\d+|\d+\.?)(?:[eE][-+]?\d+)?", arg)]
        name = name.lower()
        if name == "translate":
            m = Matrix.translate(a[0], a[1] if len(a) > 1 else 0)
        elif name == "scale":
            m = Matrix.scale(a[0], a[1] if len(a) > 1 else None)
        elif name == "rotate":
            m = (
                Matrix.rotate(a[0])
                if len(a) == 1
                else Matrix.translate(-a[1], -a[2])
                .then(Matrix.rotate(a[0]))
                .then(Matrix.translate(a[1], a[2]))
            )
        elif name == "matrix":
            m = Matrix(*a)
        else:
            raise ValueError(name)
        out = out.then(m)
    return out


def points(s):
    a = [float(v) for v in re.findall(r"[-+]?(?:\d*\.\d+|\d+\.?)(?:[eE][-+]?\d+)?", s)]
    return [Point(a[i], a[i + 1]) for i in range(0, len(a), 2)]


class SVGReader:
    def __init__(self, curve_steps=24, pen_count=8, pen_map=None, layer_pens=True):
        self.curve_steps = curve_steps
        self.pen_count = pen_count
        self.colors = {}
        self.pen_map = {str(k).lower(): int(v) for k, v in (pen_map or {}).items()}
        self.layer_pens = layer_pens

    def read(self, path):
        return self.read_text(open(path, encoding="utf-8").read())

    def read_text(self, text):
        root = ET.fromstring(text)
        w, h = length_mm(root.get("width")), length_mm(root.get("height"))
        vb = [
            float(v)
            for v in re.findall(
                r"[-+]?(?:\d*\.\d+|\d+\.?)(?:[eE][-+]?\d+)?", root.get("viewBox") or ""
            )
        ]
        if (w is None or h is None) and len(vb) == 4:
            w = w or vb[2]
            h = h or vb[3]
        if w is None or h is None:
            raise ValueError("SVG requires width/height or viewBox")
        base = Matrix.scale(w / vb[2], h / vb[3]) if len(vb) == 4 else Matrix()
        if len(vb) == 4:
            base = Matrix.translate(-vb[0], -vb[1]).then(base)
        self.colors = {}
        doc = PlotDocument(
            metadata={
                "page_width_mm": w,
                "page_height_mm": h,
                "color_to_pen": self.colors,
                "unsupported_svg_elements": [],
            }
        )
        self.walk(root, base, {}, doc)
        return doc

    def visible(self, s):
        try:
            return (
                s.get("display") != "none"
                and s.get("visibility") != "hidden"
                and s.get("stroke") != "none"
                and float(s.get("opacity", "1")) != 0
                and float(s.get("stroke-opacity", "1")) != 0
            )
        except ValueError:
            return True

    def pen(self, c, layer=None):
        c = (c or "#000000").strip().lower()
        if layer and self.layer_pens:
            m = re.search(r"(?:pen|stift)\s*[-_:]?\s*([1-8])", layer, re.IGNORECASE)
            if m:
                return int(m.group(1))
        if c in self.pen_map:
            self.colors[c] = self.pen_map[c]
            return self.pen_map[c]
        if c not in self.colors:
            self.colors[c] = len(self.colors) % self.pen_count + 1
        return self.colors[c]

    def walk(self, e, parent, inherit, doc, layer=None):
        tag = e.tag.split("}")[-1]
        if tag in {"defs", "clipPath", "mask", "metadata", "symbol"}:
            return
        m = transform(e.get("transform")).then(parent)
        s = dict(inherit)
        s.update(style(e.get("style")))
        current_layer = layer
        label = e.get("{http://www.inkscape.org/namespaces/inkscape}label") or e.get("id")
        if e.get("{http://www.inkscape.org/namespaces/inkscape}groupmode") == "layer":
            current_layer = label
        for k in ("stroke", "display", "visibility", "opacity", "stroke-opacity"):
            if e.get(k) is not None:
                s[k] = e.get(k)
        polys = []
        supported_containers = {"svg", "g", "a", "switch"}
        supported_geometry = {"line", "polyline", "polygon", "rect", "circle", "ellipse", "path"}
        if self.visible(s):
            if tag == "line":
                polys = [
                    Polyline(
                        [
                            Point(float(e.get("x1", "0")), float(e.get("y1", "0"))),
                            Point(float(e.get("x2", "0")), float(e.get("y2", "0"))),
                        ]
                    )
                ]
            elif tag in ("polyline", "polygon"):
                p = points(e.get("points", ""))
                if tag == "polygon" and p and p[0] != p[-1]:
                    p.append(p[0])
                if len(p) >= 2:
                    polys = [Polyline(p)]
            elif tag == "rect":
                x, y, w, h = map(
                    float,
                    (e.get("x", "0"), e.get("y", "0"), e.get("width", "0"), e.get("height", "0")),
                )
                polys = [
                    Polyline(
                        [
                            Point(x, y),
                            Point(x + w, y),
                            Point(x + w, y + h),
                            Point(x, y + h),
                            Point(x, y),
                        ]
                    )
                ]
            elif tag in ("circle", "ellipse"):
                cx, cy = float(e.get("cx", "0")), float(e.get("cy", "0"))
                rx = float(e.get("r", e.get("rx", "0")))
                ry = float(e.get("r", e.get("ry", "0")))
                n = max(24, self.curve_steps)
                polys = [
                    Polyline(
                        [
                            Point(
                                cx + rx * math.cos(2 * math.pi * i / n),
                                cy + ry * math.sin(2 * math.pi * i / n),
                            )
                            for i in range(n + 1)
                        ]
                    )
                ]
            elif tag == "path":
                polys = parse_path(e.get("d", ""), self.curve_steps)
            elif tag not in supported_containers and tag not in supported_geometry:
                doc.metadata["unsupported_svg_elements"].append(tag)
        if polys:
            pen = self.pen(s.get("stroke"), current_layer)
            color = s.get("stroke", "#000000")
            for p in polys:
                doc.add_polyline(Polyline([m.apply(q) for q in p.points], pen, color))
        for ch in list(e):
            self.walk(ch, m, s, doc, current_layer)
