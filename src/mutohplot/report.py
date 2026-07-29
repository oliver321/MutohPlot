from dataclasses import dataclass

from .hard_clip import DrawableArea, HardClipProfile, origin_offset_from_page_center
from .paper import Paper
from .transform.hard_clip import hard_clip_center_correction


@dataclass(frozen=True, slots=True)
class BoundsCheck:
    inside: bool
    left_over_mm: float = 0.0
    top_over_mm: float = 0.0
    right_over_mm: float = 0.0
    bottom_over_mm: float = 0.0


def check_bounds(document, area: DrawableArea) -> BoundsCheck:
    bounds = document.bounds()
    if bounds is None:
        return BoundsCheck(True)
    x0, y0, x1, y1 = bounds
    left = max(0.0, area.x_min_mm - x0)
    top = max(0.0, area.y_min_mm - y0)
    right = max(0.0, x1 - area.x_max_mm)
    bottom = max(0.0, y1 - area.y_max_mm)
    return BoundsCheck(
        inside=not any((left, top, right, bottom)),
        left_over_mm=left,
        top_over_mm=top,
        right_over_mm=right,
        bottom_over_mm=bottom,
    )


def transformation_report(
    document,
    paper: Paper,
    profile: HardClipProfile,
    area: DrawableArea,
    margin_mm: float,
    scale: float | None = None,
) -> str:
    bounds = document.bounds()
    vertical, horizontal = origin_offset_from_page_center(profile)
    correction = hard_clip_center_correction(profile)

    lines = [
        f"Paper: {paper.name} {paper.width_mm:.1f} x {paper.height_mm:.1f} mm",
        f"Hard clip: {profile.name}",
        (
            "Hard-clip margins: "
            f"top={profile.top_mm:.1f}, bottom={profile.bottom_mm:.1f}, "
            f"left={profile.left_mm:.1f}, right={profile.right_mm:.1f} mm"
        ),
        (
            f"Hard-clip area: "
            f"{paper.width_mm - profile.left_mm - profile.right_mm:.1f} x "
            f"{paper.height_mm - profile.top_mm - profile.bottom_mm:.1f} mm"
        ),
        f"Additional margin: {margin_mm:.1f} mm",
        f"Available area: {area.width_mm:.1f} x {area.height_mm:.1f} mm",
        (
            "Hard-clip centre relative to paper centre: "
            f"vertical={vertical:+.1f} mm, horizontal={horizontal:+.1f} mm"
        ),
        (
            "Automatic Mutoh correction: "
            f"first={correction.first_mm:+.1f} mm, "
            f"second={correction.second_mm:+.1f} mm"
        ),
    ]

    if bounds:
        x0, y0, x1, y1 = bounds
        lines.append(f"Drawing bounds: x={x0:.2f}..{x1:.2f} mm, y={y0:.2f}..{y1:.2f} mm")
        lines.append(f"Drawing size: {x1 - x0:.2f} x {y1 - y0:.2f} mm")
    if scale is not None:
        lines.append(f"Fit scale: {scale:.6f}")

    check = check_bounds(document, area)
    if check.inside:
        lines.append("Bounds check: inside drawable area")
    else:
        lines.append(
            "Bounds check: OUTSIDE "
            f"(left={check.left_over_mm:.2f}, top={check.top_over_mm:.2f}, "
            f"right={check.right_over_mm:.2f}, bottom={check.bottom_over_mm:.2f} mm)"
        )
    return "\n".join(lines)
