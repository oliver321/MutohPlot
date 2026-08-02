from .geometry import (
    QUALITY_PROFILES,
    OptimizationStats,
    QualityProfile,
    optimize_geometry,
    point_count,
)
from .paths import optimize_nearest, remove_duplicate_segments

__all__ = [
    "QUALITY_PROFILES",
    "OptimizationStats",
    "QualityProfile",
    "optimize_geometry",
    "optimize_nearest",
    "point_count",
    "remove_duplicate_segments",
]
