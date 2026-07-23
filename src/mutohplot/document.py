from dataclasses import dataclass, field
from .geometry.point import Point
from .geometry.polyline import Polyline

@dataclass
class PlotDocument:
    polylines: list[Polyline] = field(default_factory=list)
    metadata: dict = field(default_factory=dict)
