from ..transform.coordinate import CoordinateTransform

class HPGLWriter:
    def __init__(self, device, transform=None):
        self.device = device
        self.transform = transform or CoordinateTransform.identity()

    def write(self, document):
        out = ["IN;", "DF;"]
        current_pen = None
        for poly in document.polylines:
            if len(poly.points) < 2:
                continue
            if current_pen != poly.pen:
                out.append(f"SP{poly.pen};")
                current_pen = poly.pen
            p0 = self.transform.apply(poly.points[0])
            x0, y0 = self.device.mm_to_units(p0.x, p0.y)
            out.append(f"PU{x0},{y0};")
            coords = []
            for p in poly.points[1:]:
                p = self.transform.apply(p)
                x, y = self.device.mm_to_units(p.x, p.y)
                coords.append(f"{x},{y}")
            out.append("PD" + ",".join(coords) + ";")
            out.append("PU;")
        out.extend(["PU0,0;", "SP0;", "IN;"])
        return "".join(out)
