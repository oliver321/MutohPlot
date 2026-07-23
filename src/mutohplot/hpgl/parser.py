from dataclasses import dataclass
from ..document import PlotDocument
from ..geometry.point import Point
from ..geometry.polyline import Polyline
from .tokenizer import HPGLTokenizer

@dataclass(slots=True)
class PlotState:
    x_units: float = 0.0
    y_units: float = 0.0
    absolute: bool = True
    pen_down: bool = False
    pen: int = 1

class HPGLParser:
    def __init__(self, source_unit_mm: float = 0.025):
        self.source_unit_mm = source_unit_mm

    def parse_text(self, text: str) -> PlotDocument:
        commands = HPGLTokenizer().tokenize(text)
        state = PlotState()
        doc = PlotDocument(metadata={"source_unit_mm": self.source_unit_mm})
        current = None

        for cmd in commands:
            name, args = cmd.name, cmd.numeric_args
            if name == "IN":
                state, current = PlotState(), None
            elif name == "DF":
                continue
            elif name == "SP":
                if args:
                    state.pen = int(args[0])
                current = None
            elif name in {"PA", "PR"}:
                state.absolute = name == "PA"
                if args:
                    current = self._coords(args, state, doc, current)
            elif name == "PU":
                state.pen_down, current = False, None
                if args:
                    current = self._coords(args, state, doc, current)
            elif name == "PD":
                if not state.pen_down:
                    state.pen_down = True
                    current = Polyline([self._point(state)], state.pen)
                    doc.polylines.append(current)
                if args:
                    current = self._coords(args, state, doc, current)
            else:
                doc.metadata.setdefault("unsupported_commands", []).append(name)

        doc.polylines = [p for p in doc.polylines if len(p.points) >= 2]
        return doc

    def _coords(self, args, state, doc, current):
        if len(args) % 2:
            raise ValueError("Odd coordinate count")
        for i in range(0, len(args), 2):
            x, y = args[i], args[i+1]
            if state.absolute:
                state.x_units, state.y_units = x, y
            else:
                state.x_units += x
                state.y_units += y
            pt = self._point(state)
            if state.pen_down:
                if current is None:
                    current = Polyline([pt], state.pen)
                    doc.polylines.append(current)
                else:
                    current.append(pt)
            else:
                current = None
        return current

    def _point(self, state):
        return Point(
            state.x_units * self.source_unit_mm,
            state.y_units * self.source_unit_mm
        )
