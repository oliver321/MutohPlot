"""Persistent measured hard-clip profiles for the calibration assistant."""

from __future__ import annotations

import json
import os
import tempfile
import threading
from copy import deepcopy
from pathlib import Path

from .paper import get_paper


def validate_calibration_profile(profile: dict) -> dict:
    if not isinstance(profile, dict):
        raise TypeError("Ungültiges Kalibrierungsprofil")
    name = str(profile.get("name", "")).strip()
    if not name or len(name) > 60:
        raise ValueError("Der Profilname muss 1 bis 60 Zeichen lang sein")
    paper = str(profile.get("paper", "")).lower()
    if paper not in {"a3", "a2", "a1", "a0"}:
        raise ValueError("Unbekanntes Papierformat")
    window = str(profile.get("window", "")).lower()
    if window not in {"norm", "exp", "type1", "type3"}:
        raise ValueError("Unbekannter Hard-Clip-Modus")
    values = {}
    for field in ("top_mm", "bottom_mm", "left_mm", "right_mm"):
        try:
            value = float(profile.get(field))
        except (TypeError, ValueError) as error:
            raise ValueError(f"Messwert {field} ist ungültig") from error
        if not 0 <= value <= 200:
            raise ValueError(f"Messwert {field} muss zwischen 0 und 200 mm liegen")
        values[field] = value
    dimensions = get_paper(paper)
    drawable_width = dimensions.width_mm - values["left_mm"] - values["right_mm"]
    drawable_height = dimensions.height_mm - values["top_mm"] - values["bottom_mm"]
    if drawable_width <= 0 or drawable_height <= 0:
        raise ValueError("Die Messwerte ergeben keine gültige Zeichenfläche")
    return {
        "name": name,
        "paper": paper,
        "window": window,
        **values,
        "drawable_width_mm": round(drawable_width, 2),
        "drawable_height_mm": round(drawable_height, 2),
        "offset_first_mm": round(-(values["top_mm"] - values["bottom_mm"]) / 2, 3),
        "offset_second_mm": round(-(values["left_mm"] - values["right_mm"]) / 2, 3),
    }


class CalibrationProfileStore:
    def __init__(self, path: str | Path | None = None) -> None:
        configured = os.environ.get("MUTOHPLOT_CALIBRATION_PROFILES")
        self.path = Path(
            path
            or configured
            or Path.home() / ".config" / "mutohplot" / "calibration-profiles.json"
        )
        self.lock = threading.Lock()
        self._profiles = self._load()

    def _load(self) -> dict[str, dict]:
        if not self.path.is_file():
            return {}
        try:
            raw = json.loads(self.path.read_text(encoding="utf-8"))
            return {name: validate_calibration_profile(profile) for name, profile in raw.items()}
        except (OSError, json.JSONDecodeError, TypeError, ValueError) as error:
            raise ValueError(
                f"Kalibrierungsprofile konnten nicht geladen werden: {error}"
            ) from error

    def _save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        handle, temporary = tempfile.mkstemp(
            prefix="calibration-", suffix=".json", dir=self.path.parent
        )
        try:
            with os.fdopen(handle, "w", encoding="utf-8") as stream:
                json.dump(self._profiles, stream, ensure_ascii=False, indent=2)
                stream.write("\n")
            os.replace(temporary, self.path)
        finally:
            if os.path.exists(temporary):
                os.unlink(temporary)

    def snapshot(self) -> dict[str, dict]:
        with self.lock:
            return deepcopy(self._profiles)

    def put(self, profile: dict) -> dict:
        validated = validate_calibration_profile(profile)
        with self.lock:
            self._profiles[validated["name"]] = validated
            self._save()
            return deepcopy(validated)

    def delete(self, name: str) -> None:
        with self.lock:
            if name not in self._profiles:
                raise ValueError(f"Unbekanntes Kalibrierungsprofil: {name}")
            del self._profiles[name]
            self._save()
