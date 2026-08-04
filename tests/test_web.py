import time
import threading

import pytest

from mutohplot.web import WebApplication, _conversion_args
from mutohplot.web_profiles import PenProfileStore, standard_profile


SIMPLE_HPGL = "IN;SP1;PA0,0;PD4000,2000;PU;"
SIMPLE_SVG = """<svg xmlns="http://www.w3.org/2000/svg" width="100mm" height="50mm">
<line x1="0" y1="0" x2="100" y2="50" stroke="red"/>
</svg>"""


def test_prepare_returns_a3_preview_and_plot_token():
    app = WebApplication()

    result = app.prepare("test.hpgl", SIMPLE_HPGL, {"optimize": False})

    assert result["token"]
    assert result["name"] == "test.hpgl"
    assert result["polylines"] == 1
    assert result["bytes"] > 0
    assert result["preview_url"] == f'/api/preview/{result["token"]}'
    preview = app.state.prepared[result["token"]].preview_svg
    assert "<svg" in preview
    assert 'width="297.0mm"' in preview
    assert result["token"] in app.state.prepared


def test_prepare_replaces_previous_approval():
    app = WebApplication()
    first = app.prepare("one.hpgl", SIMPLE_HPGL, {"optimize": False})
    second = app.prepare("two.hpgl", SIMPLE_HPGL, {"optimize": False})

    assert first["token"] not in app.state.prepared
    assert second["token"] in app.state.prepared


def test_prepare_svg_fits_to_a3_and_reports_pen_mapping():
    app = WebApplication()

    result = app.prepare("zeichnung.svg", SIMPLE_SVG, {"optimize": False})

    assert result["source_type"] == "SVG"
    assert result["pens"] == {"red": 1}
    assert result["polylines"] == 1
    assert result["scale"] > 1
    assert 'width="297.0mm"' in app.state.prepared[result["token"]].preview_svg
    assert app.state.prepared[result["token"]].data.startswith(b"IN;")


def test_prepare_svg_with_default_path_optimization():
    app = WebApplication()

    result = app.prepare("zeichnung.svg", SIMPLE_SVG, {})

    assert result["source_type"] == "SVG"
    assert result["polylines"] == 1


def test_prepare_svg_auto_rotation_selects_larger_fit():
    app = WebApplication()

    result = app.prepare(
        "zeichnung.svg", SIMPLE_SVG, {"rotation": "auto", "optimize": False}
    )

    assert result["rotation"] == 90


@pytest.mark.parametrize("rotation", [0, 90, 180, 270])
def test_prepare_svg_applies_manual_rotation(rotation):
    app = WebApplication()

    result = app.prepare(
        "zeichnung.svg", SIMPLE_SVG, {"rotation": str(rotation), "optimize": False}
    )

    assert result["rotation"] == rotation


def test_prepare_svg_without_fit_preserves_scale_and_warns_about_bounds():
    app = WebApplication()

    result = app.prepare(
        "zeichnung.svg", SIMPLE_SVG, {"fit": False, "rotation": "0", "optimize": False}
    )

    assert result["scale"] is None
    assert result["rotation"] == 0
    assert "Zeichnung liegt außerhalb des sicheren Bereichs" in result["warnings"]


@pytest.mark.parametrize(
    ("paper", "width", "height"),
    [
        ("a3", 297.0, 420.0),
        ("a2", 420.0, 594.0),
        ("a1", 594.0, 841.0),
        ("a0", 841.0, 1189.0),
    ],
)
def test_prepare_svg_uses_selected_paper_size(paper, width, height):
    app = WebApplication()

    result = app.prepare("zeichnung.svg", SIMPLE_SVG, {"paper": paper, "optimize": False})

    preview = app.state.prepared[result["token"]].preview_svg
    assert f'width="{width}mm"' in preview
    assert f'height="{height}mm"' in preview


def test_prepare_svg_rejects_document_without_supported_geometry():
    app = WebApplication()
    text_only = '<svg xmlns="http://www.w3.org/2000/svg" width="100" height="100"><text>Hi</text></svg>'

    with pytest.raises(ValueError, match="keine unterstützte"):
        app.prepare("text.svg", text_only, {})


def test_prepare_svg_warns_about_ignored_text_in_mixed_document():
    app = WebApplication()
    mixed = SIMPLE_SVG.replace("</svg>", "<text x=\"10\" y=\"10\">Hi</text></svg>")

    result = app.prepare("mixed.svg", mixed, {"optimize": False})

    assert result["warnings"] == ["Nicht gezeichnete SVG-Elemente: text"]


def test_prepare_svg_applies_manual_color_to_pen_mapping():
    app = WebApplication()

    result = app.prepare(
        "zeichnung.svg", SIMPLE_SVG, {"optimize": False, "pen_map": {"red": 7}}
    )

    assert result["pens"] == {"red": 7}
    assert app.state.prepared[result["token"]].data.find(b"SP7;") >= 0


def test_prepare_svg_uses_selected_persistent_pen_profile(tmp_path):
    store = PenProfileStore(tmp_path / "pens.json")
    profile = standard_profile()
    profile["name"] = "Farbstifte"
    profile["pens"]["1"]["color"] = "#123456"
    store.put(profile)
    app = WebApplication(profile_store=store)

    result = app.prepare(
        "zeichnung.svg", SIMPLE_SVG, {"profile": "Farbstifte", "optimize": False}
    )

    preview = app.state.prepared[result["token"]].preview_svg
    assert result["profile_name"] == "Farbstifte"
    assert 'stroke="#123456"' in preview


def test_prepare_hpgl_can_remap_source_pen_to_physical_slot(tmp_path):
    store = PenProfileStore(tmp_path / "pens.json")
    app = WebApplication(profile_store=store)

    result = app.prepare(
        "zeichnung.hpgl",
        SIMPLE_HPGL,
        {"optimize": False, "hpgl_pen_map": {"1": 4}},
    )

    prepared = app.state.prepared[result["token"]]
    assert result["mapping_type"] == "hpgl-pen"
    assert result["pens"] == {"1": 4}
    assert b"SP4;" in prepared.data
    assert 'stroke="#41424c"' in prepared.preview_svg


def test_prepare_hpgl_applies_manual_rotation():
    app = WebApplication()

    result = app.prepare(
        "zeichnung.hpgl", SIMPLE_HPGL, {"rotation": "270", "optimize": False}
    )

    assert result["rotation"] == 270


def test_prepare_rejects_unknown_file_type():
    app = WebApplication()
    with pytest.raises(ValueError, match="Unterstützt"):
        app.prepare("zeichnung.txt", SIMPLE_HPGL, {})


def test_start_sends_prepared_data_with_safe_serial_defaults():
    calls = []

    def sender(data, settings, profile, progress):
        calls.append((data, settings, profile))
        progress(len(data), len(data))

    app = WebApplication(sender=sender)
    prepared = app.prepare("test.hpgl", SIMPLE_HPGL, {"optimize": False})
    app.start(prepared["token"], "/dev/ttyUSB0", "small")

    for _ in range(100):
        if app.state.snapshot()["status"] == "complete":
            break
        time.sleep(0.01)

    assert app.state.snapshot()["status"] == "complete"
    assert calls[0][1].baudrate == 19200
    assert calls[0][1].xonxoff is True
    assert calls[0][2].name == "small"


def test_start_rejects_unknown_or_stale_preview():
    app = WebApplication()
    with pytest.raises(ValueError, match="Vorschau"):
        app.start("unknown", "/dev/ttyUSB0", "small")


def test_shutdown_waits_for_active_transmission():
    release = threading.Event()

    def sender(data, settings, profile, progress):
        release.wait(2)
        progress(len(data), len(data))

    app = WebApplication(sender=sender)
    prepared = app.prepare("test.hpgl", SIMPLE_HPGL, {"optimize": False})
    app.start(prepared["token"], "/dev/ttyUSB0", "small")

    done = app.request_shutdown()
    assert done.is_set() is False
    assert app.state.snapshot()["shutdown_requested"] is True
    assert "wartet" in app.state.snapshot()["message"]

    release.set()
    assert done.wait(2)
    assert app.state.snapshot()["status"] == "complete"


def test_conversion_options_preserve_a3_and_calibration_defaults():
    args = _conversion_args({})
    assert args.paper == "a3"
    assert args.window == "norm"
    assert args.offset_first == 0.0
    assert args.offset_second == 0.0
    assert args.no_hardclip_correction is False


def test_conversion_options_accept_a0_and_reject_unknown_paper():
    assert _conversion_args({"paper": "a0"}).paper == "a0"
    with pytest.raises(ValueError, match="Papierformat"):
        _conversion_args({"paper": "letter"})


def test_conversion_options_validate_rotation_mode():
    assert _conversion_args({"rotation": "auto"}).auto_rotate is True
    assert _conversion_args({"rotation": "90"}).rotate == 90
    with pytest.raises(ValueError, match="Drehung"):
        _conversion_args({"rotation": "45"})


def test_conversion_options_allow_no_fit_only_without_rotation():
    args = _conversion_args({"fit": False, "rotation": "0"})
    assert args.fit is False
    assert args.auto_rotate is False
    with pytest.raises(ValueError, match="Einpassen"):
        _conversion_args({"fit": False, "rotation": "90"})
