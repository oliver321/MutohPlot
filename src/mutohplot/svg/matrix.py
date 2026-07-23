from dataclasses import dataclass
from math import cos, sin, radians
from ..geometry.point import Point

@dataclass(frozen=True, slots=True)
class Matrix:
    a: float = 1.0
    b: float = 0.0
    c: float = 0.0
    d: float = 1.0
    e: float = 0.0
    f: float = 0.0

    def apply(self, p: Point) -> Point:
        return Point(
            self.a*p.x + self.c*p.y + self.e,
            self.b*p.x + self.d*p.y + self.f
        )

    def then(self, other):
        return Matrix(
            other.a*self.a + other.c*self.b,
            other.b*self.a + other.d*self.b,
            other.a*self.c + other.c*self.d,
            other.b*self.c + other.d*self.d,
            other.a*self.e + other.c*self.f + other.e,
            other.b*self.e + other.d*self.f + other.f,
        )

    @classmethod
    def translate(cls, x, y=0.0):
        return cls(e=x, f=y)

    @classmethod
    def scale(cls, x, y=None):
        return cls(a=x, d=x if y is None else y)

    @classmethod
    def rotate(cls, angle_deg):
        r = radians(angle_deg)
        return cls(a=cos(r), b=sin(r), c=-sin(r), d=cos(r))
