"""Coverage for device_property_browser.collect_device_properties().

Regression target: the deprecated MMConfigUI.get_device_properties() prototype
this replaces only ever appended to property_items inside its "enum" branch,
so a range-limited (has_property_limits) property was silently dropped. This
must not reproduce.
"""
from unittest.mock import MagicMock

from glados_pycromanager.GUI.device_property_browser import collect_device_properties


def _mil_with(devices):
    """Build a mocked MIL. `devices` maps device -> {prop: entry_kwargs}."""
    mil = MagicMock()
    mil.get_loaded_devices.return_value = list(devices.keys())

    def get_device_property_names(device):
        return list(devices[device].keys())

    def get_property(device, prop):
        return devices[device][prop]["value"]

    def is_property_read_only(device, prop):
        return devices[device][prop].get("read_only", False)

    def has_property_limits(device, prop):
        return devices[device][prop].get("kind") == "range"

    def get_property_lower_limit(device, prop):
        return devices[device][prop].get("min")

    def get_property_upper_limit(device, prop):
        return devices[device][prop].get("max")

    def get_allowed_property_values(device, prop):
        return devices[device][prop].get("options", [])

    mil.get_device_property_names.side_effect = get_device_property_names
    mil.get_property.side_effect = get_property
    mil.is_property_read_only.side_effect = is_property_read_only
    mil.has_property_limits.side_effect = has_property_limits
    mil.get_property_lower_limit.side_effect = get_property_lower_limit
    mil.get_property_upper_limit.side_effect = get_property_upper_limit
    mil.get_allowed_property_values.side_effect = get_allowed_property_values
    return mil


def test_collects_enum_range_and_read_only_properties():
    mil = _mil_with({
        "Shutter": {
            "State": {"value": "On", "kind": "enum", "options": ["On", "Off"]},
        },
        "Camera": {
            "Exposure": {"value": 10.0, "kind": "range", "min": 1.0, "max": 1000.0},
            "CameraName": {"value": "DemoCam", "read_only": True, "kind": "range", "min": 0, "max": 0},
        },
    })

    items = collect_device_properties(mil)

    by_key = {(i["device"], i["name"]): i for i in items}
    assert len(items) == 3

    enum_item = by_key[("Shutter", "State")]
    assert enum_item["kind"] == "enum"
    assert enum_item["options"] == ["On", "Off"]
    assert enum_item["value"] == "On"
    assert enum_item["read_only"] is False

    range_item = by_key[("Camera", "Exposure")]
    assert range_item["kind"] == "range"
    assert range_item["min"] == 1.0
    assert range_item["max"] == 1000.0
    assert range_item["value"] == 10.0

    read_only_item = by_key[("Camera", "CameraName")]
    assert read_only_item["read_only"] is True


def test_device_with_no_properties_yields_no_items():
    mil = _mil_with({"EmptyDevice": {}})
    assert collect_device_properties(mil) == []


def test_property_read_error_is_skipped_not_raised():
    mil = _mil_with({"Camera": {"Exposure": {"value": 10.0, "kind": "range", "min": 0, "max": 100}}})
    mil.get_property.side_effect = RuntimeError("bridge timeout")

    items = collect_device_properties(mil)

    assert items == []
