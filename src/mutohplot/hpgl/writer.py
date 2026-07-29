from ..transform.coordinate import CoordinateTransform


class HPGLWriter:
    def __init__(self, device, transform=None, max_command_chars=16384):
        self.device = device
        self.transform = transform or CoordinateTransform.identity()
        self.max_command_chars = max(64, int(max_command_chars))

    def write(self, document):
        out = ["IN;", "DF;", "PA;"]
        current_pen = None
        for poly in document.polylines:
            if len(poly.points) < 2:
                continue
            if current_pen != poly.pen:
                out.append(f"SP{poly.pen};")
                current_pen = poly.pen
            transformed = [self.transform.apply(point) for point in poly.points]
            units = [self.device.mm_to_units(point.x, point.y) for point in transformed]
            out.append(f"PU{units[0][0]},{units[0][1]};")
            self._append(out, "PD", units[1:])
            out.append("PU;")
        out.extend(["PU0,0;", "SP0;", "IN;"])
        return "".join(out)

    def _append(self, out, prefix, coords):
        cmd = prefix
        first = True
        for x, y in coords:
            token = f"{x},{y}"
            candidate = cmd + ("" if first else ",") + token
            if len(candidate) + 1 > self.max_command_chars and not first:
                out.append(cmd + ";")
                cmd = prefix + token
            else:
                cmd = candidate
            first = False
        if not first:
            out.append(cmd + ";")
