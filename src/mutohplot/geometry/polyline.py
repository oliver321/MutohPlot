from dataclasses import dataclass, field
from .point import Point

@dataclass(slots=True)
class Polyline:
    points: list[Point] = field(default_factory=list)
    pen: int = 1

    def append(self, point: Point) -> None:
        self.points.append(point)
