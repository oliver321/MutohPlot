from dataclasses import dataclass

from .paper import Paper


@dataclass(frozen=True, slots=True)
class HardClipProfile:
    """Hardware clip margins measured from the physical media edges.

    A: leading/top edge in the media-feed direction
    B: trailing/bottom edge
    C: left edge
    D: right edge
    """

    name: str
    top_mm: float
    bottom_mm: float
    left_mm: float
    right_mm: float
    tolerance_mm: float = 1.0


@dataclass(frozen=True, slots=True)
class DrawableArea:
    x_min_mm: float
    y_min_mm: float
    x_max_mm: float
    y_max_mm: float

    @property
    def width_mm(self) -> float:
        return self.x_max_mm - self.x_min_mm

    @property
    def height_mm(self) -> float:
        return self.y_max_mm - self.y_min_mm

    @property
    def center_x_mm(self) -> float:
        return (self.x_min_mm + self.x_max_mm) / 2.0

    @property
    def center_y_mm(self) -> float:
        return (self.y_min_mm + self.y_max_mm) / 2.0


HARD_CLIP_PROFILES = {
    "none": HardClipProfile("None", 0.0, 0.0, 0.0, 0.0, 0.0),
    "norm": HardClipProfile("Norm", 35.0, 15.0, 15.0, 15.0),
    "exp": HardClipProfile("Exp", 25.0, 5.0, 5.0, 5.0),
    "type1": HardClipProfile("Type 1", 25.0, 5.0, 11.0, 11.0),
    "type3": HardClipProfile("Type 3", 25.0, 10.0, 10.0, 10.0),
}


def get_hard_clip(name: str) -> HardClipProfile:
    normalized = name.lower().replace(" ", "").replace("-", "")
    aliases = {
        "normal": "norm",
        "normalmode": "norm",
        "expanded": "exp",
        "type01": "type1",
        "type03": "type3",
        "off": "none",
    }
    normalized = aliases.get(normalized, normalized)
    try:
        return HARD_CLIP_PROFILES[normalized]
    except KeyError as exc:
        choices = ", ".join(HARD_CLIP_PROFILES)
        raise ValueError(f"Unknown hard-clip profile: {name}. Choose one of: {choices}") from exc


def drawable_area(
    paper: Paper,
    profile: HardClipProfile,
    extra_margin_mm: float = 0.0,
) -> DrawableArea:
    if extra_margin_mm < 0:
        raise ValueError("Additional margin must not be negative")

    area = DrawableArea(
        x_min_mm=profile.left_mm + extra_margin_mm,
        y_min_mm=profile.top_mm + extra_margin_mm,
        x_max_mm=paper.width_mm - profile.right_mm - extra_margin_mm,
        y_max_mm=paper.height_mm - profile.bottom_mm - extra_margin_mm,
    )
    if area.width_mm <= 0 or area.height_mm <= 0:
        raise ValueError(
            f"Hard-clip margins and additional margin leave no drawable area on {paper.name}"
        )
    return area


def origin_offset_from_page_center(profile: HardClipProfile) -> tuple[float, float]:
    """Return the hard-clip centre offset in page coordinates.

    The first return value is vertical/downward, the second horizontal/rightward.
    For Norm, Exp and Type 1 this is (10, 0) mm; Type 3 is (7.5, 0) mm.
    """

    vertical = (profile.top_mm - profile.bottom_mm) / 2.0
    horizontal = (profile.left_mm - profile.right_mm) / 2.0
    return vertical, horizontal
