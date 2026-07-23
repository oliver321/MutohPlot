from dataclasses import dataclass, field
from .point import Point

@dataclass
class Polyline:
    points: list[Point] = field(default_factory=list)
    pen: int = 1
