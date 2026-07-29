from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class Command:
    name: str
    payload: str

    @property
    def numeric_args(self) -> list[float]:
        if not self.payload.strip():
            return []
        return [float(v.strip()) for v in self.payload.split(",") if v.strip()]
