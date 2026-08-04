"""Persistent pen-magazine profiles for the local web interface."""

from __future__ import annotations

import json
import os
import re
import tempfile
import threading
from copy import deepcopy
from pathlib import Path

from .pen_config import SUPPORTED_PEN_TYPES, SUPPORTED_PEN_WIDTHS_MM, load_pen_profile

TYPE_LABELS = {
    "technical-pen": "Tusche-/Zeichenstift",
    "fiber": "Faserstift",
    "pencil": "Bleistift",
    "ballpoint": "Kugelschreiber",
    "other": "Sonstiger Stift",
}
COLOR_ALIASES = {"graphite": "#41424c"}


def standard_profile() -> dict:
    installed = load_pen_profile()
    return {
        "name": "Standard",
        "pens": {
            str(number): {
                "label": f"Stift {number}",
                "type": pen.pen_type,
                "width_mm": pen.width_mm,
                "color": COLOR_ALIASES.get(pen.color.lower(), pen.color),
            }
            for number, pen in installed.pens.items()
        },
    }


def validate_profile(profile: dict) -> dict:
    if not isinstance(profile, dict):
        raise TypeError("Ungültiges Stiftprofil")
    name = str(profile.get("name", "")).strip()
    if not name or len(name) > 60:
        raise ValueError("Der Profilname muss 1 bis 60 Zeichen lang sein")
    raw_pens = profile.get("pens")
    if not isinstance(raw_pens, dict):
        raise TypeError("Das Profil muss die Stifte 1 bis 8 enthalten")
    pens = {}
    for number in range(1, 9):
        raw = raw_pens.get(str(number))
        if not isinstance(raw, dict):
            raise TypeError(f"Stift {number} fehlt")
        label = str(raw.get("label", "")).strip()
        if not label or len(label) > 60:
            raise ValueError(f"Bezeichnung für Stift {number} ist ungültig")
        pen_type = str(raw.get("type", ""))
        if pen_type not in SUPPORTED_PEN_TYPES:
            raise ValueError(f"Art für Stift {number} ist ungültig")
        try:
            width = float(raw.get("width_mm"))
        except (TypeError, ValueError) as error:
            raise ValueError(f"Breite für Stift {number} ist ungültig") from error
        if width not in SUPPORTED_PEN_WIDTHS_MM:
            raise ValueError(f"Breite für Stift {number} wird nicht unterstützt")
        color = str(raw.get("color", "")).strip()
        color = COLOR_ALIASES.get(color.lower(), color)
        if not re.fullmatch(r"(?:#[0-9A-Fa-f]{6}|[A-Za-z]{1,30})", color):
            raise ValueError(f"Farbe für Stift {number} ist ungültig")
        pens[str(number)] = {
            "label": label,
            "type": pen_type,
            "width_mm": width,
            "color": color,
        }
    return {"name": name, "pens": pens}


class PenProfileStore:
    def __init__(self, path: str | Path | None = None) -> None:
        self.path = Path(path or Path.home() / ".config" / "mutohplot" / "web-pens.json")
        self.lock = threading.Lock()
        was_missing = not self.path.is_file()
        self._data = self._load()
        if was_missing:
            self._save()

    def _load(self) -> dict:
        if not self.path.is_file():
            profile = standard_profile()
            return {"default": "Standard", "profiles": {"Standard": profile}}
        try:
            raw = json.loads(self.path.read_text(encoding="utf-8"))
            profiles = {
                name: validate_profile(profile) for name, profile in raw.get("profiles", {}).items()
            }
            default = str(raw.get("default", ""))
            if not profiles or default not in profiles:
                raise ValueError("Standardprofil fehlt")
            return {"default": default, "profiles": profiles}
        except (OSError, json.JSONDecodeError, TypeError, ValueError) as error:
            raise ValueError(f"Stiftprofile konnten nicht geladen werden: {error}") from error

    def _save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        handle, temporary = tempfile.mkstemp(
            prefix="web-pens-", suffix=".json", dir=self.path.parent
        )
        try:
            with os.fdopen(handle, "w", encoding="utf-8") as stream:
                json.dump(self._data, stream, ensure_ascii=False, indent=2)
                stream.write("\n")
            os.replace(temporary, self.path)
        finally:
            if os.path.exists(temporary):
                os.unlink(temporary)

    def snapshot(self) -> dict:
        with self.lock:
            return deepcopy(self._data)

    def get(self, name: str | None = None) -> dict:
        with self.lock:
            selected = name or self._data["default"]
            try:
                return deepcopy(self._data["profiles"][selected])
            except KeyError as error:
                raise ValueError(f"Unbekanntes Stiftprofil: {selected}") from error

    def put(self, profile: dict, previous_name: str | None = None) -> dict:
        validated = validate_profile(profile)
        with self.lock:
            old_name = previous_name or validated["name"]
            if previous_name and previous_name not in self._data["profiles"]:
                raise ValueError(f"Unbekanntes Stiftprofil: {previous_name}")
            if validated["name"] != old_name and validated["name"] in self._data["profiles"]:
                raise ValueError("Ein Profil mit diesem Namen existiert bereits")
            if previous_name:
                del self._data["profiles"][previous_name]
            self._data["profiles"][validated["name"]] = validated
            if self._data["default"] == previous_name:
                self._data["default"] = validated["name"]
            self._save()
            return deepcopy(validated)

    def set_default(self, name: str) -> None:
        with self.lock:
            if name not in self._data["profiles"]:
                raise ValueError(f"Unbekanntes Stiftprofil: {name}")
            self._data["default"] = name
            self._save()

    def delete(self, name: str) -> None:
        with self.lock:
            if name == self._data["default"]:
                raise ValueError("Das Standardprofil kann nicht gelöscht werden")
            if name not in self._data["profiles"]:
                raise ValueError(f"Unbekanntes Stiftprofil: {name}")
            del self._data["profiles"][name]
            self._save()
