from dataclasses import dataclass

@dataclass(frozen=True, slots=True)
class Command:
    name: str
    payload: str

    @property
    def numeric_args(self) -> list[float]:
        if not self.payload.strip():
            return []
        values: list[float] = []
        for item in self.payload.split(","):
            item = item.strip()
            if item:
                values.append(float(item))
        return values
