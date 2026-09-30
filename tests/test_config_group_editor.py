"""Coverage for config_group_editor's GUI-free data model
(collect_config_groups, group_property_set, device_type_bucket) and the
Group/Preset editor dialogs' accept flows.

Mirrors Micro-Manager's own Group Editor / Preset editor methodology: a group
is defined once by a fixed set of device/property pairs; every preset in the
group supplies values for that same set. The dialog tests exercise this by
driving the real Qt widgets under the offscreen platform (see
conftest.py / pytest-qt setup used elsewhere in this suite for GUI tests).
"""
import os
from unittest.mock import MagicMock

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt5.QtWidgets import QApplication

import glados_pycromanager.GUI.config_group_editor as config_group_editor
from glados_pycromanager.GUI.config_group_editor import (
    DEVICE_TYPE_FILTER_BUCKETS,
    ConfigGroupEditorDialog,
    GroupEditorDialog,
    PresetEditorDialog,
    collect_config_groups,
    device_type_bucket,
    group_property_set,
)


@pytest.fixture(scope="module", autouse=True)
def qapp():
    app = QApplication.instance() or QApplication([])
    yield app


class _NoOpMessageBox:
    """Stand-in for QMessageBox.warning/question: a real modal exec_() is
    flaky under the offscreen QPA platform (see test_recipe_io.py's
    _StubMessageBox for the same convention). Tests using this only assert
    that a CRUD call was refused, not that a dialog actually appeared."""

    @staticmethod
    def warning(*args, **kwargs):
        return None

    @staticmethod
    def question(*args, **kwargs):
        return None


def _mil_with(groups):
    """Build a mocked MIL.

    `groups` maps group -> {"current": preset_name_or_None,
    "presets": {preset_name: [{"device","property","value"}, ...]}}.
    """
    mil = MagicMock()
    mil.get_available_config_groups.return_value = list(groups.keys())

    def get_current_config(group):
        return groups[group]["current"]

    def get_available_configs(group):
        return list(groups[group]["presets"].keys())

    def get_config_data(group, preset):
        return (group, preset)

    def get_config_settings(config_data):
        group, preset = config_data
        return groups[group]["presets"][preset]

    mil.get_current_config.side_effect = get_current_config
    mil.get_available_configs.side_effect = get_available_configs
    mil.get_config_data.side_effect = get_config_data
    mil.get_config_settings.side_effect = get_config_settings
    return mil


def test_collects_groups_presets_and_settings():
    mil = _mil_with({
        "Objective": {
            "current": "10x",
            "presets": {
                "10x": [{"device": "Obj", "property": "Label", "value": "10x"}],
                "20x": [{"device": "Obj", "property": "Label", "value": "20x"}],
            },
        },
    })

    result = collect_config_groups(mil)

    assert len(result) == 1
    group = result[0]
    assert group["group"] == "Objective"
    assert len(group["presets"]) == 2

    by_name = {p["preset"]: p for p in group["presets"]}
    assert by_name["10x"]["is_current"] is True
    assert by_name["20x"]["is_current"] is False
    assert by_name["10x"]["settings"] == [{"device": "Obj", "property": "Label", "value": "10x"}]


def test_multi_setting_preset_keeps_every_setting():
    """A "Channel" preset commonly sets more than one device -- regression
    target for the old MMConfigUI.get_device_properties bug, which only
    ever surfaced the first device+property of a config."""
    mil = _mil_with({
        "Channel": {
            "current": None,
            "presets": {
                "DAPI": [
                    {"device": "Wheel", "property": "Label", "value": "DAPI"},
                    {"device": "Shutter", "property": "State", "value": "1"},
                ],
            },
        },
    })

    result = collect_config_groups(mil)

    settings = result[0]["presets"][0]["settings"]
    assert len(settings) == 2
    assert {s["device"] for s in settings} == {"Wheel", "Shutter"}


def test_group_with_no_presets_yields_empty_preset_list():
    mil = _mil_with({"EmptyGroup": {"current": None, "presets": {}}})
    result = collect_config_groups(mil)
    assert result == [{"group": "EmptyGroup", "presets": []}]


def test_preset_read_error_is_skipped_not_raised():
    mil = _mil_with({
        "Objective": {"current": None, "presets": {"10x": []}},
    })
    mil.get_config_data.side_effect = RuntimeError("bridge timeout")

    result = collect_config_groups(mil)

    assert result == [{
        "group": "Objective",
        "presets": [{"preset": "10x", "is_current": False, "settings": []}],
    }]


class TestGroupPropertySet:
    def test_union_across_presets_preserves_first_seen_order(self):
        mil = MagicMock()
        mil.get_available_configs.return_value = ["A", "B"]
        settings_by_preset = {
            "A": [{"device": "Cam", "property": "Exposure", "value": "10"}],
            "B": [
                {"device": "Cam", "property": "Exposure", "value": "20"},
                {"device": "Cam", "property": "Mode", "value": "Live"},
            ],
        }
        mil.get_config_data.side_effect = lambda group, preset: preset
        mil.get_config_settings.side_effect = lambda preset: settings_by_preset[preset]

        result = group_property_set(mil, "MyGroup")

        assert result == [("Cam", "Exposure"), ("Cam", "Mode")]

    def test_no_presets_yields_empty_set(self):
        mil = MagicMock()
        mil.get_available_configs.return_value = []
        assert group_property_set(mil, "EmptyGroup") == []


class TestDeviceTypeBucket:
    def test_camera_device_type(self):
        mil = MagicMock()
        mil.get_device_type.return_value = 2
        assert device_type_bucket(mil, "Cam") == "cameras"

    def test_state_device_is_wheels_turrets_bucket(self):
        mil = MagicMock()
        mil.get_device_type.return_value = 4
        assert device_type_bucket(mil, "Wheel") == "wheels, turrets, etc."

    def test_xy_stage_is_stages_bucket(self):
        mil = MagicMock()
        mil.get_device_type.return_value = 6
        assert device_type_bucket(mil, "XYStage") == "stages"

    def test_unrecognised_type_is_other_devices(self):
        mil = MagicMock()
        mil.get_device_type.return_value = 999
        assert device_type_bucket(mil, "Odd") == "other devices"

    def test_read_error_is_other_devices(self):
        mil = MagicMock()
        mil.get_device_type.side_effect = RuntimeError("bridge timeout")
        assert device_type_bucket(mil, "Cam") == "other devices"

    def test_every_bucket_is_a_declared_filter(self):
        assert set(DEVICE_TYPE_FILTER_BUCKETS) == {
            "cameras", "shutters", "stages", "wheels, turrets, etc.", "other devices",
        }


def _mil_for_dialogs(devices_properties, device_type=2):
    """A MagicMock MIL with one or more devices, each exposing the given
    property->value map, none read-only, none with limits, no allowed values
    (plain QLineEdit widgets -- keeps the dialog tests focused on the
    group/preset CRUD calls rather than widget-kind selection, which is
    covered by test_device_property_browser.py)."""
    mil = MagicMock()
    mil.get_loaded_devices.return_value = list(devices_properties.keys())
    mil.get_device_property_names.side_effect = lambda device: list(devices_properties[device].keys())
    mil.get_property.side_effect = lambda device, prop: devices_properties[device][prop]
    mil.is_property_read_only.return_value = False
    mil.has_property_limits.return_value = False
    mil.get_allowed_property_values.return_value = []
    mil.get_device_type.return_value = device_type
    return mil


class TestGroupEditorDialogAccept:
    def test_new_group_defines_group_and_checked_properties(self):
        mil = _mil_for_dialogs({"Cam": {"Exposure": "10"}})
        mil.get_available_config_groups.return_value = []
        mil.get_available_configs.return_value = []

        dialog = GroupEditorDialog(mil)
        dialog.name_edit.setText("MyGroup")
        dialog._row_checks[("Cam", "Exposure")].setChecked(True)
        dialog._onAccept()

        mil.define_config_group.assert_called_once_with("MyGroup")
        mil.define_config.assert_called_once_with("MyGroup", "NewPreset", "Cam", "Exposure", "10")

    def test_editing_group_adds_and_removes_across_every_preset(self):
        mil = _mil_for_dialogs({"Cam": {"Exposure": "10", "Mode": "Live"}})
        mil.get_available_configs.return_value = ["NewPreset"]
        mil.get_config_data.side_effect = lambda group, preset: preset
        mil.get_config_settings.side_effect = lambda preset: [
            {"device": "Cam", "property": "Exposure", "value": "10"}
        ]

        dialog = GroupEditorDialog(mil, group_name="MyGroup")
        assert dialog._existing_pairs == {("Cam", "Exposure")}
        dialog._row_checks[("Cam", "Mode")].setChecked(True)
        dialog._row_checks[("Cam", "Exposure")].setChecked(False)
        dialog._onAccept()

        mil.define_config.assert_called_once_with("MyGroup", "NewPreset", "Cam", "Mode", "Live")
        mil.delete_config.assert_called_once_with("MyGroup", "NewPreset", "Cam", "Exposure")

    def test_renaming_group_calls_rename_before_diffing_presets(self):
        mil = _mil_for_dialogs({"Cam": {"Exposure": "10"}})
        mil.get_available_configs.return_value = ["NewPreset"]
        mil.get_config_data.side_effect = lambda group, preset: preset
        mil.get_config_settings.side_effect = lambda preset: [
            {"device": "Cam", "property": "Exposure", "value": "10"}
        ]

        dialog = GroupEditorDialog(mil, group_name="OldName")
        dialog.name_edit.setText("NewName")
        dialog._onAccept()

        mil.rename_config_group.assert_called_once_with("OldName", "NewName")
        mil.get_available_configs.assert_any_call("NewName")

    def test_no_properties_checked_refuses_to_accept(self, monkeypatch):
        # QMessageBox.warning's real modal exec_() is flaky under the
        # offscreen QPA platform (see test_recipe_io.py for the same
        # stub-instead-of-invoke convention); we only care that the CRUD
        # call was refused, not that a real dialog popped up.
        monkeypatch.setattr(config_group_editor, "QMessageBox", _NoOpMessageBox)
        mil = _mil_for_dialogs({"Cam": {"Exposure": "10"}})
        mil.get_available_config_groups.return_value = []
        mil.get_available_configs.return_value = []

        dialog = GroupEditorDialog(mil)
        dialog.name_edit.setText("MyGroup")
        dialog._onAccept()

        mil.define_config_group.assert_not_called()


class TestPresetEditorDialogAccept:
    def test_new_preset_defines_every_property_in_the_group(self):
        mil = _mil_for_dialogs({"Cam": {"Exposure": "10", "Mode": "Live"}})
        mil.get_available_configs.return_value = ["NewPreset"]
        mil.get_config_data.side_effect = lambda group, preset: preset
        mil.get_config_settings.side_effect = lambda preset: [
            {"device": "Cam", "property": "Exposure", "value": "10"},
            {"device": "Cam", "property": "Mode", "value": "Live"},
        ]

        dialog = PresetEditorDialog(mil, "MyGroup")
        dialog.name_edit.setText("Preset1")
        dialog._onAccept()

        calls = {(c.args[2], c.args[3]): c.args[4] for c in mil.define_config.call_args_list}
        assert calls == {("Cam", "Exposure"): "10", ("Cam", "Mode"): "Live"}
        for c in mil.define_config.call_args_list:
            assert c.args[0] == "MyGroup" and c.args[1] == "Preset1"

    def test_editing_preset_renames_when_name_changed(self):
        mil = _mil_for_dialogs({"Cam": {"Exposure": "10"}})
        mil.get_available_configs.return_value = ["OldPreset"]
        mil.get_config_data.side_effect = lambda group, preset: preset
        mil.get_config_settings.side_effect = lambda preset: [
            {"device": "Cam", "property": "Exposure", "value": "10"}
        ]

        dialog = PresetEditorDialog(mil, "MyGroup", preset_name="OldPreset")
        dialog.name_edit.setText("NewPreset")
        dialog._onAccept()

        mil.rename_config.assert_called_once_with("MyGroup", "OldPreset", "NewPreset")

    def test_empty_name_refuses_to_accept(self, monkeypatch):
        monkeypatch.setattr(config_group_editor, "QMessageBox", _NoOpMessageBox)
        mil = _mil_for_dialogs({"Cam": {"Exposure": "10"}})
        mil.get_available_configs.return_value = ["NewPreset"]
        mil.get_config_data.side_effect = lambda group, preset: preset
        mil.get_config_settings.side_effect = lambda preset: [
            {"device": "Cam", "property": "Exposure", "value": "10"}
        ]

        dialog = PresetEditorDialog(mil, "MyGroup")
        dialog.name_edit.setText("")
        dialog._onAccept()

        mil.define_config.assert_not_called()


class TestSaveConfigurationFeedback:
    """The Save button must relabel to "Saved!" (and disable itself) right
    after a successful save, so a click that otherwise has no visible
    effect still gives the user feedback -- then revert once
    SAVED_FEEDBACK_MS elapses, via _restoreSaveButton()."""

    def _dialog(self, monkeypatch):
        monkeypatch.setattr(config_group_editor, "storeSharedData_GlobalData", lambda shared_data: None)
        mil = MagicMock()
        mil.get_available_config_groups.return_value = []
        shared_data = MagicMock()
        shared_data.config.micromanager_config.config_path = "C:/tmp/x.cfg"
        return ConfigGroupEditorDialog(mil, shared_data), mil

    def test_successful_save_flashes_saved_and_disables_button(self, monkeypatch):
        dialog, mil = self._dialog(monkeypatch)

        dialog.saveConfiguration()

        mil.save_system_configuration.assert_called_once_with("C:/tmp/x.cfg")
        assert dialog.save_button.text() == "Saved!"
        assert dialog.save_button.isEnabled() is False

    def test_restore_save_button_reverts_label_and_reenables(self, monkeypatch):
        dialog, _mil = self._dialog(monkeypatch)

        dialog.saveConfiguration()
        dialog._restoreSaveButton()

        assert dialog.save_button.text() == "Save"
        assert dialog.save_button.isEnabled() is True

    def test_failed_save_does_not_flash_saved(self, monkeypatch):
        dialog, mil = self._dialog(monkeypatch)
        monkeypatch.setattr(config_group_editor, "QMessageBox", _NoOpMessageBox)
        mil.save_system_configuration.side_effect = RuntimeError("disk full")

        dialog.saveConfiguration()

        assert dialog.save_button.text() == "Save"
        assert dialog.save_button.isEnabled() is True
