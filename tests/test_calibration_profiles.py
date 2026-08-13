import json

import pytest

from mutohplot.calibration_profiles import CalibrationProfileStore

PROFILE = {
    "name": "A3 Norm gemessen",
    "paper": "a3",
    "window": "norm",
    "top_mm": 35,
    "bottom_mm": 15,
    "left_mm": 15,
    "right_mm": 15,
}


def test_profile_is_calculated_saved_and_reloaded(tmp_path):
    path = tmp_path / "calibrations.json"
    store = CalibrationProfileStore(path)

    saved = store.put(PROFILE)

    assert saved["drawable_width_mm"] == 267
    assert saved["drawable_height_mm"] == 370
    assert saved["offset_first_mm"] == -10
    assert saved["offset_second_mm"] == 0
    assert CalibrationProfileStore(path).snapshot()[saved["name"]] == saved


def test_profile_can_be_deleted(tmp_path):
    store = CalibrationProfileStore(tmp_path / "calibrations.json")
    store.put(PROFILE)

    store.delete(PROFILE["name"])

    assert store.snapshot() == {}


def test_invalid_measurements_are_rejected(tmp_path):
    store = CalibrationProfileStore(tmp_path / "calibrations.json")

    with pytest.raises(ValueError, match="Messwert"):
        store.put(PROFILE | {"top_mm": -1})


def test_invalid_persisted_file_is_rejected(tmp_path):
    path = tmp_path / "calibrations.json"
    path.write_text(json.dumps({"broken": {}}), encoding="utf-8")

    with pytest.raises(ValueError, match="geladen"):
        CalibrationProfileStore(path)
