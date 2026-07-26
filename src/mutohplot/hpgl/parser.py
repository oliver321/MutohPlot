from dataclasses import dataclass
from math import ceil, cos, hypot, radians, sin

from ..document import PlotDocument
from ..geometry.point import Point
from ..geometry.polyline import Polyline
from .stroke_font import glyph_rows
from .tokenizer import HPGLTokenizer


@dataclass(slots=True)
class PlotState:
    x_units: float = 0.0
    y_units: float = 0.0
    absolute: bool = True
    pen_down: bool = False
    pen: int = 1
    char_width_mm: float = 2.85
    char_height_mm: float = 3.75
    label_direction_x: float = 1.0
    label_direction_y: float = 0.0

class HPGLParser:
    def __init__(self, source_unit_mm: float = 0.025):
        self.source_unit_mm = source_unit_mm

    def parse_text(self, text: str) -> PlotDocument:
        commands = HPGLTokenizer().tokenize(text)
        state = PlotState()
        doc = PlotDocument(
            metadata={
                "source_unit_mm": self.source_unit_mm,
                "hpgl_commands": [command.name for command in commands],
            }
        )
        current = None

        for cmd in commands:
            name = cmd.name
            if name == "IN":
                state, current = PlotState(), None
            elif name == "DF":
                continue
            elif name == "SP":
                args = cmd.numeric_args
                if args:
                    state.pen = int(args[0])
                current = None
            elif name in {"PA", "PR"}:
                args = cmd.numeric_args
                state.absolute = name == "PA"
                if args:
                    current = self._coords(args, state, doc, current)
            elif name == "PU":
                args = cmd.numeric_args
                state.pen_down, current = False, None
                if args:
                    current = self._coords(args, state, doc, current)
            elif name == "PD":
                args = cmd.numeric_args
                if not state.pen_down:
                    state.pen_down = True
                    current = Polyline([self._point(state)], state.pen)
                    doc.polylines.append(current)
                if args:
                    current = self._coords(args, state, doc, current)
            elif name in {"AA", "AR"}:
                current = self._arc(name, cmd.numeric_args, state, doc, current)
            elif name == "CI":
                current = self._circle(cmd.numeric_args, state, doc)
            elif name == "SI":
                args = cmd.numeric_args
                if not args:
                    state.char_width_mm, state.char_height_mm = 2.85, 3.75
                elif len(args) == 2:
                    state.char_width_mm = abs(args[0]) * 10.0
                    state.char_height_mm = abs(args[1]) * 10.0
                else:
                    raise ValueError("SI requires width and height")
            elif name in {"DI", "DR"}:
                args = cmd.numeric_args
                if not args:
                    state.label_direction_x, state.label_direction_y = 1.0, 0.0
                elif len(args) == 2:
                    length = hypot(args[0], args[1])
                    if length == 0:
                        raise ValueError(f"{name} direction vector must not be zero")
                    state.label_direction_x = args[0] / length
                    state.label_direction_y = args[1] / length
                else:
                    raise ValueError(f"{name} requires run and rise")
            elif name == "LB":
                current = self._label(cmd.payload, state, doc)
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

    def _arc(self, name, args, state, doc, current):
        if len(args) not in {3, 4}:
            raise ValueError(f"{name} requires center, sweep angle, and optional chord angle")

        start_x, start_y = state.x_units, state.y_units
        if name == "AA":
            center_x, center_y = args[0], args[1]
        else:
            center_x = start_x + args[0]
            center_y = start_y + args[1]

        sweep_degrees = args[2]
        chord_degrees = self._chord_angle(args[3] if len(args) == 4 else 5.0)
        radius_x = start_x - center_x
        radius_y = start_y - center_y
        steps = max(1, ceil(abs(sweep_degrees) / chord_degrees))

        if state.pen_down and current is None:
            current = Polyline([self._point(state)], state.pen)
            doc.polylines.append(current)

        for step in range(1, steps + 1):
            angle = radians(sweep_degrees * step / steps)
            x_units = center_x + cos(angle) * radius_x - sin(angle) * radius_y
            y_units = center_y + sin(angle) * radius_x + cos(angle) * radius_y
            if state.pen_down:
                current.append(self._point_from_units(x_units, y_units))

        end_angle = radians(sweep_degrees)
        state.x_units = center_x + cos(end_angle) * radius_x - sin(end_angle) * radius_y
        state.y_units = center_y + sin(end_angle) * radius_x + cos(end_angle) * radius_y
        return current

    def _circle(self, args, state, doc):
        if len(args) not in {1, 2}:
            raise ValueError("CI requires radius and optional chord angle")

        signed_radius = args[0]
        radius = abs(signed_radius)
        chord_degrees = self._chord_angle(args[1] if len(args) == 2 else 5.0)
        steps = max(2, ceil(360.0 / chord_degrees))
        start_degrees = 0.0 if signed_radius >= 0 else 180.0

        points = []
        for step in range(steps + 1):
            angle = radians(start_degrees + 360.0 * step / steps)
            points.append(
                self._point_from_units(
                    state.x_units + radius * cos(angle),
                    state.y_units + radius * sin(angle),
                )
            )
        doc.polylines.append(Polyline(points, state.pen))

        if state.pen_down:
            current = Polyline([self._point(state)], state.pen)
            doc.polylines.append(current)
            return current
        return None

    def _point_from_units(self, x_units, y_units):
        return Point(
            x_units * self.source_unit_mm,
            y_units * self.source_unit_mm,
        )

    def _label(self, text, state, doc):
        # Approximate the HP-GL default label cell. Labels are converted to
        # ordinary polylines so all later fit/axis transforms remain valid.
        cell_width_mm = state.char_width_mm
        cell_height_mm = state.char_height_mm
        column_mm = cell_width_mm / 5.0
        row_mm = cell_height_mm / 7.0
        origin_x_mm = state.x_units * self.source_unit_mm
        baseline_y_mm = state.y_units * self.source_unit_mm
        direction_x = state.label_direction_x
        direction_y = state.label_direction_y
        perpendicular_x = -direction_y
        perpendicular_y = direction_x

        missing = doc.metadata.setdefault("unsupported_label_characters", [])
        cursor_mm = 0.0
        line_offset_mm = 0.0
        for character in text:
            if character == "\n":
                cursor_mm = 0.0
                line_offset_mm -= cell_height_mm * 1.4
                continue
            rows, supported = glyph_rows(character)
            if not supported:
                missing.append(character)
            for row, bits in enumerate(rows):
                column = 0
                while column < 5:
                    if bits[column] == "0":
                        column += 1
                        continue
                    start = column
                    while column + 1 < 5 and bits[column + 1] == "1":
                        column += 1
                    start_along_mm = cursor_mm + start * column_mm
                    end_along_mm = cursor_mm + (column + 1) * column_mm
                    across_mm = line_offset_mm + (6 - row) * row_mm
                    doc.polylines.append(
                        Polyline(
                            [
                                Point(
                                    origin_x_mm
                                    + direction_x * start_along_mm
                                    + perpendicular_x * across_mm,
                                    baseline_y_mm
                                    + direction_y * start_along_mm
                                    + perpendicular_y * across_mm,
                                ),
                                Point(
                                    origin_x_mm
                                    + direction_x * end_along_mm
                                    + perpendicular_x * across_mm,
                                    baseline_y_mm
                                    + direction_y * end_along_mm
                                    + perpendicular_y * across_mm,
                                ),
                            ],
                            state.pen,
                        )
                    )
                    column += 1
            cursor_mm += cell_width_mm * 1.2

        state.x_units = (
            origin_x_mm + direction_x * cursor_mm + perpendicular_x * line_offset_mm
        ) / self.source_unit_mm
        state.y_units = (
            baseline_y_mm + direction_y * cursor_mm + perpendicular_y * line_offset_mm
        ) / self.source_unit_mm
        return None

    @staticmethod
    def _chord_angle(value):
        return min(180.0, max(0.5, value))
