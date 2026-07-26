from __future__ import annotations

import tomllib
from dataclasses import dataclass
from importlib.resources import files
from pathlib import Path

from .document import PlotDocument

SUPPORTED_PEN_WIDTHS_MM = (0.3, 0.5, 0.7, 1.0, 1.5)
SUPPORTED_PEN_TYPES = (
    "technical-pen",
    "fiber",
    "pencil",
    "ballpoint",
    "other",
)
DEFAULT_CONFIG_NAME = "Standard.toml"


class PenConfigError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class Pen:
    number: int
    width_mm: float
    color: str
    pen_type: str
    group: str
    speed_mm_s: float | None = None


@dataclass(frozen=True, slots=True)
class PenProfile:
    name: str
    source: str
    fill_spacing_factor: float
    pens: dict[int, Pen]

    def pen(self, number: int) -> Pen:
        try:
            return self.pens[number]
        except KeyError as error:
            raise PenConfigError(f"pen number must be between 1 and 8: {number}") from error


def _required_table(data: dict, key: str) -> dict:
    value = data.get(key)
    if not isinstance(value, dict):
        raise PenConfigError(f"missing or invalid [{key}] table")
    return value


def _required_text(table: dict, key: str, location: str) -> str:
    value = table.get(key)
    if not isinstance(value, str) or not value.strip():
        raise PenConfigError(f"{location}.{key} must be a non-empty string")
    return value.strip()


def _width(value, location: str) -> float:
    if not isinstance(value, (int, float)) or isinstance(value, bool):
        raise PenConfigError(f"{location} must be a number")
    width = float(value)
    if width not in SUPPORTED_PEN_WIDTHS_MM:
        choices = ", ".join(f"{item:g}" for item in SUPPORTED_PEN_WIDTHS_MM)
        raise PenConfigError(f"{location} must be one of: {choices} mm")
    return width


def _speed(value, location: str) -> float | None:
    if value is None:
        return None
    if not isinstance(value, (int, float)) or isinstance(value, bool):
        raise PenConfigError(f"{location} must be a number")
    speed = float(value)
    if speed <= 0:
        raise PenConfigError(f"{location} must be greater than zero")
    return speed


def _pen_type(value, location: str) -> str:
    if not isinstance(value, str) or value not in SUPPORTED_PEN_TYPES:
        choices = ", ".join(SUPPORTED_PEN_TYPES)
        raise PenConfigError(f"{location} must be one of: {choices}")
    return value


def _parse_profile(data: dict, source: str) -> PenProfile:
    profile = _required_table(data, "profile")
    fill = _required_table(data, "fill")
    defaults = _required_table(data, "pens")
    groups = _required_table(data, "pen-groups")

    name = _required_text(profile, "name", "profile")
    spacing_value = fill.get("spacing-factor")
    if not isinstance(spacing_value, (int, float)) or isinstance(spacing_value, bool):
        raise PenConfigError("fill.spacing-factor must be a number")
    spacing_factor = float(spacing_value)
    if not 0 < spacing_factor <= 1:
        raise PenConfigError("fill.spacing-factor must be greater than 0 and at most 1")

    default_width = _width(defaults.get("default-width-mm"), "pens.default-width-mm")
    default_color = _required_text(defaults, "default-color", "pens")
    default_type = _pen_type(defaults.get("default-type"), "pens.default-type")
    default_speed = _speed(defaults.get("default-speed-mm-s"), "pens.default-speed-mm-s")

    pens = {
        number: Pen(
            number=number,
            width_mm=default_width,
            color=default_color,
            pen_type=default_type,
            group="default",
            speed_mm_s=default_speed,
        )
        for number in range(1, 9)
    }
    assigned: set[int] = set()

    for group_name, group in groups.items():
        location = f"pen-groups.{group_name}"
        if not isinstance(group, dict):
            raise PenConfigError(f"{location} must be a table")
        numbers = group.get("pens")
        if not isinstance(numbers, list) or not numbers:
            raise PenConfigError(f"{location}.pens must be a non-empty array")
        width = _width(group.get("width-mm"), f"{location}.width-mm")
        color = _required_text(group, "color", location)
        pen_type = _pen_type(group.get("type"), f"{location}.type")
        speed = _speed(group.get("speed-mm-s"), f"{location}.speed-mm-s")
        for number in numbers:
            if not isinstance(number, int) or isinstance(number, bool) or not 1 <= number <= 8:
                raise PenConfigError(f"{location}.pens entries must be integers from 1 to 8")
            if number in assigned:
                raise PenConfigError(f"pen {number} is assigned to more than one group")
            assigned.add(number)
            pens[number] = Pen(
                number=number,
                width_mm=width,
                color=color,
                pen_type=pen_type,
                group=group_name,
                speed_mm_s=speed,
            )

    return PenProfile(
        name=name,
        source=source,
        fill_spacing_factor=spacing_factor,
        pens=pens,
    )


def load_pen_profile(config_path: str | Path | None = None) -> PenProfile:
    if config_path is None:
        resource = files("mutohplot").joinpath("config", DEFAULT_CONFIG_NAME)
        source = f"installed:{DEFAULT_CONFIG_NAME}"
        if not resource.is_file():
            raise PenConfigError(
                f"required installed configuration is missing: {DEFAULT_CONFIG_NAME}"
            )
        raw = resource.read_bytes()
    else:
        path = Path(config_path).expanduser()
        source = str(path)
        if not path.is_file():
            raise PenConfigError(f"configuration file not found: {path}")
        raw = path.read_bytes()

    try:
        data = tomllib.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, tomllib.TOMLDecodeError) as error:
        raise PenConfigError(f"invalid TOML in {source}: {error}") from error
    if not isinstance(data, dict):
        raise PenConfigError(f"invalid configuration in {source}")
    return _parse_profile(data, source)


def apply_pen_colors(document: PlotDocument, profile: PenProfile) -> None:
    for polyline in document.polylines:
        if polyline.source_color is None:
            polyline.source_color = profile.pen(polyline.pen).color
    document.metadata["pen_profile"] = profile.name
    document.metadata["pen_config_source"] = profile.source
