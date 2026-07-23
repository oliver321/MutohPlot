import math
import re
import xml.etree.ElementTree as ET
from ..document import PlotDocument
from ..geometry.point import Point
from ..geometry.polyline import Polyline
from .matrix import Matrix
from .path import parse_path

UNIT_TO_MM = {
    "mm": 1.0,
    "cm": 10.0,
    "in": 25.4,
    "pt": 25.4/72.0,
    "pc": 25.4/6.0,
    "px": 25.4/96.0,
    "": 1.0,
}

def length_mm(value: str | None) -> float | None:
    if value is None:
        return None
    m = re.fullmatch(r"\s*([-+]?(?:\d*\.\d+|\d+\.?)(?:[eE][-+]?\d+)?)\s*([A-Za-z]*)\s*", value)
    if not m:
        raise ValueError(f"Invalid SVG length: {value}")
    number, unit = float(m.group(1)), m.group(2).lower()
    if unit not in UNIT_TO_MM:
        raise ValueError(f"Unsupported SVG unit: {unit}")
    return number * UNIT_TO_MM[unit]

def parse_transform(text: str | None) -> Matrix:
    if not text:
        return Matrix()
    result = Matrix()
    for name, args_text in re.findall(r"([A-Za-z]+)\s*\(([^)]*)\)", text):
        args = [float(v) for v in re.findall(r"[-+]?(?:\d*\.\d+|\d+\.?)(?:[eE][-+]?\d+)?", args_text)]
        name = name.lower()
        if name == "translate":
            m = Matrix.translate(args[0], args[1] if len(args) > 1 else 0)
        elif name == "scale":
            m = Matrix.scale(args[0], args[1] if len(args) > 1 else None)
        elif name == "rotate":
            if len(args) == 1:
                m = Matrix.rotate(args[0])
            else:
                cx, cy = args[1], args[2]
                m = Matrix.translate(-cx,-cy).then(Matrix.rotate(args[0])).then(Matrix.translate(cx,cy))
        elif name == "matrix" and len(args) == 6:
            m = Matrix(*args)
        else:
            raise ValueError(f"Unsupported transform: {name}")
        result = result.then(m)
    return result

def parse_points(text: str) -> list[Point]:
    nums = [float(v) for v in re.findall(r"[-+]?(?:\d*\.\d+|\d+\.?)(?:[eE][-+]?\d+)?", text)]
    if len(nums) % 2:
        raise ValueError("Odd point count")
    return [Point(nums[i], nums[i+1]) for i in range(0, len(nums), 2)]

class SVGReader:
    def __init__(self, curve_steps: int = 24):
        self.curve_steps = curve_steps

    def read(self, path: str) -> PlotDocument:
        return self.read_text(open(path, "r", encoding="utf-8").read())

    def read_text(self, text: str) -> PlotDocument:
        root = ET.fromstring(text)
        width = length_mm(root.get("width"))
        height = length_mm(root.get("height"))
        viewbox = root.get("viewBox")
        vb = [float(v) for v in re.findall(r"[-+]?(?:\d*\.\d+|\d+\.?)(?:[eE][-+]?\d+)?", viewbox or "")]

        if (width is None or height is None) and len(vb) == 4:
            width = width if width is not None else vb[2]
            height = height if height is not None else vb[3]

        if width is None or height is None:
            raise ValueError("SVG requires width/height or viewBox")

        scale_x = width / vb[2] if len(vb) == 4 else 1.0
        scale_y = height / vb[3] if len(vb) == 4 else 1.0
        base = Matrix.scale(scale_x, scale_y)
        if len(vb) == 4:
            base = Matrix.translate(-vb[0], -vb[1]).then(base)

        doc = PlotDocument(metadata={"page_width_mm": width, "page_height_mm": height})
        self._walk(root, base, doc)
        return doc

    def _walk(self, elem, parent_matrix, doc):
        local = parse_transform(elem.get("transform"))
        matrix = parent_matrix.then(local)
        tag = elem.tag.split("}")[-1]

        polylines = []
        if tag == "line":
            polylines = [Polyline([
                Point(float(elem.get("x1","0")), float(elem.get("y1","0"))),
                Point(float(elem.get("x2","0")), float(elem.get("y2","0")))
            ])]
        elif tag in {"polyline", "polygon"}:
            pts = parse_points(elem.get("points",""))
            if tag == "polygon" and pts and pts[0] != pts[-1]:
                pts.append(pts[0])
            polylines = [Polyline(pts)] if len(pts) >= 2 else []
        elif tag == "rect":
            x,y = float(elem.get("x","0")), float(elem.get("y","0"))
            w,h = float(elem.get("width","0")), float(elem.get("height","0"))
            pts = [Point(x,y),Point(x+w,y),Point(x+w,y+h),Point(x,y+h),Point(x,y)]
            polylines = [Polyline(pts)]
        elif tag in {"circle", "ellipse"}:
            cx,cy = float(elem.get("cx","0")), float(elem.get("cy","0"))
            rx = float(elem.get("r", elem.get("rx","0")))
            ry = float(elem.get("r", elem.get("ry","0")))
            steps = max(24, self.curve_steps)
            pts = [
                Point(cx + rx*math.cos(2*math.pi*i/steps), cy + ry*math.sin(2*math.pi*i/steps))
                for i in range(steps+1)
            ]
            polylines = [Polyline(pts)]
        elif tag == "path":
            polylines = parse_path(elem.get("d",""), self.curve_steps)

        for poly in polylines:
            transformed = Polyline([matrix.apply(p) for p in poly.points], pen=1)
            doc.add_polyline(transformed)

        for child in list(elem):
            self._walk(child, matrix, doc)
