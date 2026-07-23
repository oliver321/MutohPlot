from dataclasses import dataclass, field
from .geometry.polyline import Polyline

@dataclass(slots=True)
class PlotDocument:
    polylines: list[Polyline] = field(default_factory=list)
    metadata: dict[str, object] = field(default_factory=dict)

    def add_polyline(self, polyline: Polyline) -> None:
        if len(polyline.points) >= 2:
            self.polylines.append(polyline)
