"""Coverage for the config-group/preset write methods added to
`MicroscopeInterfaceLayer` for the config group editor feature:
`define_config_group`, `define_config`, `delete_config`, `delete_config_group`,
`rename_config`, `rename_config_group`, `is_config_defined`,
`save_system_configuration`, and the `get_config_settings` reader.

Follows test_mil_device_properties.py's pattern of forcing `_mi` directly with
a plain (non-spec'd) MagicMock core.
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


class TestDefineConfigGroup:
    def test_pycromanager_java(self):
        mil = _mil_for(MicroscopeInstance.PYCROMANAGER_JAVA)
        mil.define_config_group("Objective")
        mil.core.define_config_group.assert_called_once_with("Objective")

    def test_pycromanager_python(self):
        mil = _mil_for(MicroscopeInstance.PYCROMANAGER_PYTHON)
        mil.define_config_group("Objective")
        mil.core.define_config_group.assert_called_once_with("Objective")

    def test_mmcore_plus_uses_camelcase(self):
        mil = _mil_for(MicroscopeInstance.MMCORE_PLUS)
        mil.define_config_group("Objective")
        mil.core.defineConfigGroup.assert_called_once_with("Objective")

    def test_unknown_backend_raises(self):
        mil = MicroscopeInterfaceLayer()
        with pytest.raises(ValueError, match="define_config_group"):
            mil.define_config_group("Objective")


class TestDefineConfig:
    def test_group_and_preset_only(self):
        mil = _mil_for(MicroscopeInstance.MMCORE_PLUS)
        mil.define_config("Objective", "10x")
        mil.core.defineConfig.assert_called_once_with("Objective", "10x")

    def test_with_device_property_value_pycromanager_java(self):
        mil = _mil_for(MicroscopeInstance.PYCROMANAGER_JAVA)
        mil.define_config("Objective", "10x", "ObjectiveDevice", "Label", "10x")
        mil.core.define_config.assert_called_once_with("Objective", "10x", "ObjectiveDevice", "Label", "10x")

    def test_with_device_property_value_mmcore_plus(self):
        mil = _mil_for(MicroscopeInstance.MMCORE_PLUS)
        mil.define_config("Objective", "10x", "ObjectiveDevice", "Label", "10x")
        mil.core.defineConfig.assert_called_once_with("Objective", "10x", "ObjectiveDevice", "Label", "10x")

    def test_unknown_backend_raises(self):
        mil = MicroscopeInterfaceLayer()
        with pytest.raises(ValueError, match="define_config"):
            mil.define_config("Objective", "10x")


class TestDeleteConfig:
    def test_whole_preset(self):
        mil = _mil_for(MicroscopeInstance.MMCORE_PLUS)
        mil.delete_config("Objective", "10x")
        mil.core.deleteConfig.assert_called_once_with("Objective", "10x")

    def test_single_setting(self):
        mil = _mil_for(MicroscopeInstance.MMCORE_PLUS)
        mil.delete_config("Objective", "10x", "ObjectiveDevice", "Label")
        mil.core.deleteConfig.assert_called_once_with("Objective", "10x", "ObjectiveDevice", "Label")

    def test_pycromanager_python(self):
        mil = _mil_for(MicroscopeInstance.PYCROMANAGER_PYTHON)
        mil.delete_config("Objective", "10x")
        mil.core.delete_config.assert_called_once_with("Objective", "10x")


class TestDeleteConfigGroup:
    def test_mmcore_plus(self):
        mil = _mil_for(MicroscopeInstance.MMCORE_PLUS)
        mil.delete_config_group("Objective")
        mil.core.deleteConfigGroup.assert_called_once_with("Objective")

    def test_unknown_backend_raises(self):
        mil = MicroscopeInterfaceLayer()
        with pytest.raises(ValueError, match="delete_config_group"):
            mil.delete_config_group("Objective")


class TestRenameConfig:
    def test_mmcore_plus(self):
        mil = _mil_for(MicroscopeInstance.MMCORE_PLUS)
        mil.rename_config("Objective", "10x", "10x-air")
        mil.core.renameConfig.assert_called_once_with("Objective", "10x", "10x-air")

    def test_pycromanager_java(self):
        mil = _mil_for(MicroscopeInstance.PYCROMANAGER_JAVA)
        mil.rename_config("Objective", "10x", "10x-air")
        mil.core.rename_config.assert_called_once_with("Objective", "10x", "10x-air")


class TestRenameConfigGroup:
    def test_mmcore_plus(self):
        mil = _mil_for(MicroscopeInstance.MMCORE_PLUS)
        mil.rename_config_group("Objective", "Objectives")
        mil.core.renameConfigGroup.assert_called_once_with("Objective", "Objectives")


class TestIsConfigDefined:
    def test_mmcore_plus(self):
        mil = _mil_for(MicroscopeInstance.MMCORE_PLUS)
        mil.core.isConfigDefined.return_value = True
        assert mil.is_config_defined("Objective", "10x") is True
        mil.core.isConfigDefined.assert_called_once_with("Objective", "10x")


class TestSaveSystemConfiguration:
    def test_mmcore_plus(self):
        mil = _mil_for(MicroscopeInstance.MMCORE_PLUS)
        mil.save_system_configuration("C:/tmp/config.cfg")
        mil.core.saveSystemConfiguration.assert_called_once_with("C:/tmp/config.cfg")

    def test_pycromanager_python(self):
        mil = _mil_for(MicroscopeInstance.PYCROMANAGER_PYTHON)
        mil.save_system_configuration("C:/tmp/config.cfg")
        mil.core.save_system_configuration.assert_called_once_with("C:/tmp/config.cfg")

    def test_unknown_backend_raises(self):
        mil = MicroscopeInterfaceLayer()
        with pytest.raises(ValueError, match="save_system_configuration"):
            mil.save_system_configuration("C:/tmp/config.cfg")


def _fake_setting(device, prop, value, java_style):
    setting = MagicMock()
    if java_style:
        setting.get_device_label.return_value = device
        setting.get_property_name.return_value = prop
        setting.get_property_value.return_value = value
    else:
        setting.getDeviceLabel.return_value = device
        setting.getPropertyName.return_value = prop
        setting.getPropertyValue.return_value = value
    return setting


class TestGetConfigSettings:
    def test_mmcore_plus_multiple_settings(self):
        mil = _mil_for(MicroscopeInstance.MMCORE_PLUS)
        config_data = MagicMock()
        config_data.size.return_value = 2
        settings = [
            _fake_setting("Wheel", "Label", "DAPI", java_style=False),
            _fake_setting("Shutter", "State", "1", java_style=False),
        ]
        config_data.getSetting.side_effect = lambda i: settings[i]

        result = mil.get_config_settings(config_data)

        assert result == [
            {"device": "Wheel", "property": "Label", "value": "DAPI"},
            {"device": "Shutter", "property": "State", "value": "1"},
        ]

    def test_pycromanager_java_uses_snake_case_setting_methods(self):
        mil = _mil_for(MicroscopeInstance.PYCROMANAGER_JAVA)
        config_data = MagicMock()
        config_data.size.return_value = 1
        config_data.getSetting.return_value = _fake_setting("Wheel", "Label", "DAPI", java_style=True)

        result = mil.get_config_settings(config_data)

        assert result == [{"device": "Wheel", "property": "Label", "value": "DAPI"}]

    def test_empty_config_data_returns_empty_list(self):
        mil = _mil_for(MicroscopeInstance.MMCORE_PLUS)
        config_data = MagicMock()
        config_data.size.return_value = 0

        assert mil.get_config_settings(config_data) == []
