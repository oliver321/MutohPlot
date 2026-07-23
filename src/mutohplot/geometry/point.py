from dataclasses import dataclass

@dataclass(slots=True)
class Point:
    x: float
    y: float
