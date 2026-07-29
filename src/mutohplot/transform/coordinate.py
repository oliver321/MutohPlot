from dataclasses import dataclass

from ..geometry.point import Point


@dataclass(frozen=True, slots=True)
class CoordinateTransform:
    a: float = 1.0
    b: float = 0.0
    c: float = 0.0
    d: float = 1.0
    tx: float = 0.0
    ty: float = 0.0

    def apply(self, point: Point) -> Point:
        return Point(
            self.a * point.x + self.b * point.y + self.tx,
            self.c * point.x + self.d * point.y + self.ty,
        )

    @classmethod
    def identity(cls):
        return cls()

    @classmethod
    def svg_to_mutoh(cls, page_width_mm: float, page_height_mm: float):
        return cls(
            a=0.0,
            b=1.0,
            c=1.0,
            d=0.0,
            tx=-page_height_mm / 2.0,
            ty=-page_width_mm / 2.0,
        )
