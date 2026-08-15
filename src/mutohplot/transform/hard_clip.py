from dataclasses import dataclass

from ..hard_clip import HardClipProfile


@dataclass(frozen=True, slots=True)
class HardClipOffset:
    first_mm: float
    second_mm: float


def hard_clip_center_correction(profile: HardClipProfile) -> HardClipOffset:
    """Return the correction needed to map paper-centred coordinates to the
    hard-clip-centred coordinate system.

    Mutoh first coordinate is vertical/down.
    Mutoh second coordinate is horizontal/right.

    A larger top margin than bottom margin means the hard-clip centre is lower
    on the paper. Therefore paper-centred coordinates must be shifted by the
    negative of that displacement.
    """
    first = -(profile.top_mm - profile.bottom_mm) / 2.0
    second = -(profile.left_mm - profile.right_mm) / 2.0
    return HardClipOffset(first_mm=first, second_mm=second)
