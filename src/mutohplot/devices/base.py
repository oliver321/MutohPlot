from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class DeviceProfile:
    name: str
    unit_mm: float
    pen_count: int
    origin: str
    first_axis_direction: str
    second_axis_direction: str

    def mm_to_units(self, first_mm: float, second_mm: float) -> tuple[int, int]:
        if self.unit_mm <= 0:
            raise ValueError("Device unit must be positive")
        return round(first_mm / self.unit_mm), round(second_mm / self.unit_mm)
