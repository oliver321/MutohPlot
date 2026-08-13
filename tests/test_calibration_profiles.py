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


def test_profile_supports_measured_intermediate_paper_size(tmp_path):
    store = CalibrationProfileStore(tmp_path / "calibrations.json")

    saved = store.put(
        PROFILE
        | {
            "name": "Zwischenformat",
            "paper_width_mm": 350,
            "paper_height_mm": 500,
        }
    )

    assert saved["paper_width_mm"] == 350
    assert saved["paper_height_mm"] == 500
    assert saved["drawable_width_mm"] == 320
    assert saved["drawable_height_mm"] == 450


def test_old_profile_without_measured_paper_size_uses_nominal_dimensions(tmp_path):
    store = CalibrationProfileStore(tmp_path / "calibrations.json")

    saved = store.put(PROFILE)

    assert saved["paper_width_mm"] == 297
    assert saved["paper_height_mm"] == 420


def test_profile_can_be_deleted(tmp_path):
    store = CalibrationProfileStore(tmp_path / "calibrations.json")
    store.put(PROFILE)

    store.delete(PROFILE["name"])

    assert store.snapshot() == {}


def test_profile_activation_is_persisted_and_can_be_disabled(tmp_path):
    path = tmp_path / "calibrations.json"
    store = CalibrationProfileStore(path)
    store.put(PROFILE)

    active = store.activate(PROFILE["name"])

    assert active["name"] == PROFILE["name"]
    assert CalibrationProfileStore(path).active_name() == PROFILE["name"]
    assert CalibrationProfileStore(path).active_profile()["drawable_width_mm"] == 267

    store.activate(None)
    assert CalibrationProfileStore(path).active_profile() is None


def test_deleting_active_profile_disables_it(tmp_path):
    store = CalibrationProfileStore(tmp_path / "calibrations.json")
    store.put(PROFILE)
    store.activate(PROFILE["name"])

    store.delete(PROFILE["name"])

    assert store.active_name() is None


def test_changing_active_profile_requires_reactivation(tmp_path):
    store = CalibrationProfileStore(tmp_path / "calibrations.json")
    store.put(PROFILE)
    store.activate(PROFILE["name"])

    store.put(PROFILE | {"top_mm": 36})

    assert store.active_name() is None


def test_invalid_measurements_are_rejected(tmp_path):
    store = CalibrationProfileStore(tmp_path / "calibrations.json")

    with pytest.raises(ValueError, match="Messwert"):
        store.put(PROFILE | {"top_mm": -1})

    with pytest.raises(ValueError, match="Papiermaß"):
        store.put(PROFILE | {"paper_width_mm": 0})


def test_invalid_persisted_file_is_rejected(tmp_path):
    path = tmp_path / "calibrations.json"
    path.write_text(json.dumps({"broken": {}}), encoding="utf-8")

    with pytest.raises(ValueError, match="geladen"):
        CalibrationProfileStore(path)
