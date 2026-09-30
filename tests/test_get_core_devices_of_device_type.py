"""getCoreDevicesOfDeviceType must handle both a raw Java-proxy `core` (whose
get_device_type() returns an object with .to_string()) and MIL, whose
get_device_type() already normalizes every backend to a plain int.

Regression for: FlowChart_dockWidgets._collectCoreVariables calls this with
shared_data.MILcore (int-returning), which raised
"'int' object has no attribute 'to_string'" for every loaded device, on every
backend, in the standalone (non-plugin) app.
"""
from __future__ import annotations

from glados_pycromanager.GUI import utils


class _FakeMILCore:
    """Stand-in for MicroscopeInterfaceLayer.get_device_type(): plain ints."""

    def __init__(self, devices_and_types):
        self._devices_and_types = devices_and_types

    def get_loaded_devices(self):
        return list(self._devices_and_types)

    def get_device_type(self, device):
        return self._devices_and_types[device]


class _JavaDeviceType:
    """Stand-in for a pyjavaz-wrapped DeviceType, which exposes .to_string()."""

    def __init__(self, name):
        self._name = name

    def to_string(self):
        return self._name


class _FakeJavaCore:
    """Stand-in for a raw pycromanager Java Core()."""

    def __init__(self, devices_and_types):
        self._devices_and_types = devices_and_types

    def get_loaded_devices(self):
        return list(self._devices_and_types)

    def get_device_type(self, device):
        return _JavaDeviceType(self._devices_and_types[device])


def test_int_returning_core_is_mapped_through_the_name_table():
    core = _FakeMILCore({"PIZStage": 5, "Camera": 2, "XYStage": 6})

    assert utils.getCoreDevicesOfDeviceType(core, "StageDevice") == ["PIZStage"]
    assert utils.getCoreDevicesOfDeviceType(core, "XYStageDevice") == ["XYStage"]
    assert utils.getCoreDevicesOfDeviceType(core, "CameraDevice") == ["Camera"]


def test_java_proxy_core_still_uses_to_string():
    core = _FakeJavaCore({"PIZStage": "StageDevice", "Camera": "CameraDevice"})

    assert utils.getCoreDevicesOfDeviceType(core, "StageDevice") == ["PIZStage"]


def test_no_matching_devices_returns_empty_list():
    core = _FakeMILCore({"Camera": 2})

    assert utils.getCoreDevicesOfDeviceType(core, "StageDevice") == []
