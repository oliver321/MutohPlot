"""Persistent serial hardware settings for the local web interface."""

from __future__ import annotations

import json
import os
import tempfile
import threading
from copy import deepcopy
from pathlib import Path

SUPPORTED_BAUDRATES = {9600, 19200, 38400}
SUPPORTED_FLOW_CONTROL = {"xonxoff", "none"}
SUPPORTED_BUFFER_PROFILES = {"small", "large"}


def default_hardware_settings() -> dict:
    return {
        "port": "/dev/ttyUSB0",
        "baudrate": 19200,
        "frame": "8N1",
        "flow_control": "xonxoff",
        "buffer_profile": "small",
    }


def validate_hardware_settings(settings: dict) -> dict:
    if not isinstance(settings, dict):
        raise TypeError("Ungültige Hardwareeinstellungen")
    port = str(settings.get("port", "")).strip()
    if not port or len(port) > 255:
        raise ValueError("Bitte eine serielle Schnittstelle auswählen")
    try:
        baudrate = int(settings.get("baudrate"))
    except (TypeError, ValueError) as error:
        raise ValueError("Ungültige Übertragungsgeschwindigkeit") from error
    if baudrate not in SUPPORTED_BAUDRATES:
        raise ValueError("Unterstützt werden 9600, 19200 und 38400 Baud")
    frame = str(settings.get("frame", ""))
    if frame != "8N1":
        raise ValueError("Der XP-500 wird derzeit nur mit 8N1 unterstützt")
    flow_control = str(settings.get("flow_control", "")).lower()
    if flow_control not in SUPPORTED_FLOW_CONTROL:
        raise ValueError("Unbekannte Flusssteuerung")
    buffer_profile = str(settings.get("buffer_profile", "")).lower()
    if buffer_profile not in SUPPORTED_BUFFER_PROFILES:
        raise ValueError("Unbekanntes Pufferprofil")
    return {
        "port": port,
        "baudrate": baudrate,
        "frame": frame,
        "flow_control": flow_control,
        "buffer_profile": buffer_profile,
    }


class HardwareSettingsStore:
    def __init__(self, path: str | Path | None = None) -> None:
        configured = os.environ.get("MUTOHPLOT_HARDWARE_SETTINGS")
        self.path = Path(
            path or configured or Path.home() / ".config" / "mutohplot" / "hardware.json"
        )
        self.lock = threading.Lock()
        self._settings = self._load()
        if not self.path.is_file():
            self._save()

    def _load(self) -> dict:
        if not self.path.is_file():
            return default_hardware_settings()
        try:
            return validate_hardware_settings(json.loads(self.path.read_text(encoding="utf-8")))
        except (OSError, json.JSONDecodeError, TypeError, ValueError) as error:
            raise ValueError(
                f"Hardwareeinstellungen konnten nicht geladen werden: {error}"
            ) from error

    def _save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        handle, temporary = tempfile.mkstemp(
            prefix="hardware-", suffix=".json", dir=self.path.parent
        )
        try:
            with os.fdopen(handle, "w", encoding="utf-8") as stream:
                json.dump(self._settings, stream, ensure_ascii=False, indent=2)
                stream.write("\n")
            os.replace(temporary, self.path)
        finally:
            if os.path.exists(temporary):
                os.unlink(temporary)

    def get(self) -> dict:
        with self.lock:
            return deepcopy(self._settings)

    def put(self, settings: dict) -> dict:
        validated = validate_hardware_settings(settings)
        with self.lock:
            self._settings = validated
            self._save()
            return deepcopy(validated)
