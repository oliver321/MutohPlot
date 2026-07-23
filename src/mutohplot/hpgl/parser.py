from dataclasses import dataclass
from ..document import PlotDocument
from ..geometry.point import Point
from ..geometry.polyline import Polyline
from .tokenizer import HPGLTokenizer
from .tokens import Command

@dataclass(slots=True)
class PlotState:
    x_units: float = 0.0
    y_units: float = 0.0
    absolute: bool = True
    pen_down: bool = False
    pen: int = 1

class HPGLParser:
    def __init__(self, source_unit_mm: float = 0.025):
        if source_unit_mm <= 0:
            raise ValueError("source_unit_mm must be positive")
        self.source_unit_mm = source_unit_mm

    def parse_text(self, text: str) -> PlotDocument:
        return self.parse_commands(HPGLTokenizer().tokenize(text))

    def parse_commands(self, commands: list[Command]) -> PlotDocument:
        state = PlotState()
        document = PlotDocument(metadata={"source_unit_mm": self.source_unit_mm})
        current: Polyline | None = None

        for command in commands:
            name = command.name
            args = command.numeric_args

            if name == "IN":
                state = PlotState()
                current = None
            elif name == "DF":
                continue
            elif name == "SP":
                if args:
                    state.pen = int(args[0])
                current = None
            elif name in {"PA", "PR"}:
                state.absolute = name == "PA"
                if args:
                    current = self._coordinates(args, state, document, current)
            elif name == "PU":
                state.pen_down = False
                current = None
                if args:
                    current = self._coordinates(args, state, document, current)
            elif name == "PD":
                if not state.pen_down:
                    state.pen_down = True
                    current = Polyline([self._point_mm(state)], state.pen)
                    document.polylines.append(current)
                if args:
                    current = self._coordinates(args, state, document, current)
            else:
                unsupported = document.metadata.setdefault("unsupported_commands", [])
                if isinstance(unsupported, list):
                    unsupported.append(name)

        document.polylines = [p for p in document.polylines if len(p.points) >= 2]
        return document

    def _coordinates(self, args, state, document, current):
        if len(args) % 2:
            raise ValueError(f"Odd coordinate count: {args}")
        for i in range(0, len(args), 2):
            x_arg, y_arg = args[i], args[i + 1]
            if state.absolute:
                state.x_units, state.y_units = x_arg, y_arg
            else:
                state.x_units += x_arg
                state.y_units += y_arg
            point = self._point_mm(state)
            if state.pen_down:
                if current is None:
                    current = Polyline([point], state.pen)
                    document.polylines.append(current)
                else:
                    current.append(point)
            else:
                current = None
        return current

    def _point_mm(self, state: PlotState) -> Point:
        return Point(
            state.x_units * self.source_unit_mm,
            state.y_units * self.source_unit_mm,
        )
