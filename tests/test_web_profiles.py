import json

import pytest

from mutohplot.web_profiles import PenProfileStore, standard_profile


def test_new_store_has_standard_default(tmp_path):
    store = PenProfileStore(tmp_path / "pens.json")

    data = store.snapshot()

    assert data["default"] == "Standard"
    assert data["profiles"]["Standard"]["pens"]["1"]["type"] == "pencil"
    assert (tmp_path / "pens.json").is_file()


def test_profile_create_rename_default_and_reload(tmp_path):
    path = tmp_path / "pens.json"
    store = PenProfileStore(path)
    profile = standard_profile()
    profile["name"] = "Fineliner"
    profile["pens"]["1"].update(label="Rot 0,3", type="fiber", width_mm=0.3, color="#ff0000")

    store.put(profile)
    store.set_default("Fineliner")
    profile["name"] = "Fineliner fein"
    store.put(profile, previous_name="Fineliner")

    reloaded = PenProfileStore(path).snapshot()
    assert reloaded["default"] == "Fineliner fein"
    assert reloaded["profiles"]["Fineliner fein"]["pens"]["1"]["color"] == "#ff0000"


def test_default_profile_cannot_be_deleted(tmp_path):
    store = PenProfileStore(tmp_path / "pens.json")

    with pytest.raises(ValueError, match="Standardprofil"):
        store.delete("Standard")


def test_invalid_persisted_profile_is_rejected(tmp_path):
    path = tmp_path / "pens.json"
    path.write_text(json.dumps({"default": "Broken", "profiles": {}}), encoding="utf-8")

    with pytest.raises(ValueError, match="geladen"):
        PenProfileStore(path)


def test_legacy_graphite_color_is_normalized_for_browser_preview(tmp_path):
    store = PenProfileStore(tmp_path / "pens.json")

    assert store.get("Standard")["pens"]["1"]["color"] == "#41424c"
