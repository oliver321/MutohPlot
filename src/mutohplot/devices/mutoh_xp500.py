from dataclasses import dataclass
from .base import DeviceProfile

@dataclass(frozen=True, slots=True)
class MutohXP500(DeviceProfile):
    name: str = "Mutoh XP-500"
    unit_mm: float = 0.01
    pen_count: int = 8
    origin: str = "center"
    first_axis_direction: str = "down"
    second_axis_direction: str = "right"
