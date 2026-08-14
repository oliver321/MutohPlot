import json

import pytest

from mutohplot.hardware_settings import (
    HardwareSettingsStore,
    default_hardware_settings,
    validate_hardware_settings,
)


def test_default_hardware_settings_match_xp500_connection():
    assert default_hardware_settings() == {
        "port": "/dev/ttyUSB0",
        "baudrate": 19200,
        "frame": "8N1",
        "flow_control": "xonxoff",
        "buffer_profile": "small",
    }


def test_hardware_settings_are_persistent(tmp_path):
    path = tmp_path / "hardware.json"
    store = HardwareSettingsStore(path)
    saved = store.put(
        {
            "port": "/dev/ttyUSB1",
            "baudrate": 38400,
            "frame": "8N1",
            "flow_control": "none",
            "buffer_profile": "large",
        }
    )

    assert HardwareSettingsStore(path).get() == saved
    assert json.loads(path.read_text(encoding="utf-8")) == saved


@pytest.mark.parametrize(
    ("field", "value", "message"),
    [
        ("port", "", "Schnittstelle"),
        ("baudrate", 115200, "9600"),
        ("frame", "7E1", "8N1"),
        ("flow_control", "rtscts", "Flusssteuerung"),
        ("buffer_profile", "medium", "Pufferprofil"),
    ],
)
def test_hardware_settings_reject_unsupported_values(field, value, message):
    settings = default_hardware_settings()
    settings[field] = value

    with pytest.raises((TypeError, ValueError), match=message):
        validate_hardware_settings(settings)
