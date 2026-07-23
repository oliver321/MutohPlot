from ..document import PlotDocument
from ..devices.base import DeviceProfile
from ..transform.coordinate import CoordinateTransform

class HPGLWriter:
    def __init__(self, device: DeviceProfile, transform=None):
        self.device = device
        self.transform = transform or CoordinateTransform.identity()

    def write(self, document: PlotDocument) -> str:
        parts = ["IN;", "DF;"]
        current_pen = None

        for polyline in document.polylines:
            if len(polyline.points) < 2:
                continue
            if current_pen != polyline.pen:
                parts.append(f"SP{polyline.pen};")
                current_pen = polyline.pen

            p0 = self.transform.apply(polyline.points[0])
            x0, y0 = self.device.mm_to_units(p0.x, p0.y)
            parts.append(f"PU{x0},{y0};")

            coords = []
            for point in polyline.points[1:]:
                mapped = self.transform.apply(point)
                x, y = self.device.mm_to_units(mapped.x, mapped.y)
                coords.append(f"{x},{y}")
            parts.append("PD" + ",".join(coords) + ";")
            parts.append("PU;")

        parts.extend(["PU0,0;", "SP0;", "IN;"])
        return "".join(parts)
