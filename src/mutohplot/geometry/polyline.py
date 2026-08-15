from dataclasses import dataclass, field
from .point import Point

@dataclass(slots=True)
class Polyline:
    points: list[Point] = field(default_factory=list)
    pen: int = 1
    source_color: str | None = None

    def append(self, point: Point) -> None:
        self.points.append(point)

    def reversed_copy(self):
        return Polyline(list(reversed(self.points)), self.pen, self.source_color)
