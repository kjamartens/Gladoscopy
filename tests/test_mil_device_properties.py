"""Coverage for the device-property introspection methods added to
`MicroscopeInterfaceLayer` for the device property browser feature:
`get_device_property_names`, `get_allowed_property_values`,
`is_property_read_only`.

Follows test_mil_hardware_lock.py's pattern of forcing `_mi` directly with a
plain (non-spec'd) MagicMock core, since the Java-bridge and pymmcore
snake_case methods these branches call are synthesised at runtime and cannot
be represented by a `spec=...` mock (see test_microscope_interface_layer.py's
TestDispatch docstring for why).
"""
from unittest.mock import MagicMock

import pytest

from glados_pycromanager.Core.microscopeInterfaceLayer import (
    MicroscopeInstance,
    MicroscopeInterfaceLayer,
)


def _mil_for(backend):
    m = MicroscopeInterfaceLayer()
    m.core = MagicMock()
    m._mi = backend
    return m


class TestGetDevicePropertyNames:
    def test_pycromanager_java_converts_via_java_arr_to_numpy(self):
        mil = _mil_for(MicroscopeInstance.PYCROMANAGER_JAVA)
        mil.core.get_device_property_names.return_value = ["Exposure", "Binning"]
        result = mil.get_device_property_names("Camera")
        mil.core.get_device_property_names.assert_called_once_with("Camera")
        assert list(result) == ["Exposure", "Binning"]

    def test_pycromanager_python_returns_directly(self):
        mil = _mil_for(MicroscopeInstance.PYCROMANAGER_PYTHON)
        mil.core.get_device_property_names.return_value = ["Exposure"]
        result = mil.get_device_property_names("Camera")
        mil.core.get_device_property_names.assert_called_once_with("Camera")
        assert result == ["Exposure"]

    def test_mmcore_plus_uses_camelcase(self):
        mil = _mil_for(MicroscopeInstance.MMCORE_PLUS)
        mil.core.getDevicePropertyNames.return_value = ["Exposure"]
        result = mil.get_device_property_names("Camera")
        mil.core.getDevicePropertyNames.assert_called_once_with("Camera")
        assert result == ["Exposure"]

    def test_unknown_backend_raises(self):
        mil = MicroscopeInterfaceLayer()
        with pytest.raises(ValueError, match="get_device_property_names"):
            mil.get_device_property_names("Camera")


class TestGetAllowedPropertyValues:
    def test_pycromanager_java_converts_via_java_arr_to_numpy(self):
        mil = _mil_for(MicroscopeInstance.PYCROMANAGER_JAVA)
        mil.core.get_allowed_property_values.return_value = ["On", "Off"]
        result = mil.get_allowed_property_values("Shutter", "State")
        mil.core.get_allowed_property_values.assert_called_once_with("Shutter", "State")
        assert list(result) == ["On", "Off"]

    def test_pycromanager_python_returns_directly(self):
        mil = _mil_for(MicroscopeInstance.PYCROMANAGER_PYTHON)
        mil.core.get_allowed_property_values.return_value = ["On", "Off"]
        result = mil.get_allowed_property_values("Shutter", "State")
        assert result == ["On", "Off"]

    def test_mmcore_plus_uses_camelcase(self):
        mil = _mil_for(MicroscopeInstance.MMCORE_PLUS)
        mil.core.getAllowedPropertyValues.return_value = ["On", "Off"]
        result = mil.get_allowed_property_values("Shutter", "State")
        mil.core.getAllowedPropertyValues.assert_called_once_with("Shutter", "State")
        assert result == ["On", "Off"]

    def test_unknown_backend_raises(self):
        mil = MicroscopeInterfaceLayer()
        with pytest.raises(ValueError, match="get_allowed_property_values"):
            mil.get_allowed_property_values("Shutter", "State")


class TestIsPropertyReadOnly:
    def test_pycromanager_java(self):
        mil = _mil_for(MicroscopeInstance.PYCROMANAGER_JAVA)
        mil.core.is_property_read_only.return_value = True
        assert mil.is_property_read_only("Camera", "CameraName") is True
        mil.core.is_property_read_only.assert_called_once_with("Camera", "CameraName")

    def test_pycromanager_python(self):
        mil = _mil_for(MicroscopeInstance.PYCROMANAGER_PYTHON)
        mil.core.is_property_read_only.return_value = False
        assert mil.is_property_read_only("Camera", "Exposure") is False

    def test_mmcore_plus_uses_camelcase(self):
        mil = _mil_for(MicroscopeInstance.MMCORE_PLUS)
        mil.core.isPropertyReadOnly.return_value = True
        assert mil.is_property_read_only("Camera", "CameraName") is True
        mil.core.isPropertyReadOnly.assert_called_once_with("Camera", "CameraName")

    def test_unknown_backend_raises(self):
        mil = MicroscopeInterfaceLayer()
        with pytest.raises(ValueError, match="is_property_read_only"):
            mil.is_property_read_only("Camera", "CameraName")
