"""Coverage for the Configurations panel fixes:

1. ConfigInfo.isDropDown/isSlider/isInputField must be mutually exclusive.
   Previously a group with exactly one *named* preset (anything but the
   'NewPreset' sentinel) whose property had limits satisfied both
   isDropDown() and isSlider() -- and addLabel() used independent `if`
   statements (not elif), so both a 1-item preset-name dropdown AND a
   slider got added to the same row, squeezing out the label. Per the
   Micro-Manager methodology this UI otherwise mirrors, a group managing a
   single property should always be edited via that property's own widget,
   never through a synthetic preset-name dropdown.
2. addLabel()'s widget selection is elif, not independent ifs (source
   inspection, matching the convention in test_mode_setter_no_sleep.py for
   MMcontrols.py methods that are impractical to unit-test by instantiating
   the whole MMConfigUI widget tree).
3. The "Refresh configs from MM" button, updateAllMMinfo(), and
   openConfigGroupEditor() all route through the new rebuildConfigLayout()
   (which re-fetches groups/presets from MIL and recreates every row),
   instead of the old updateConfigsFromMM() which only pushed values into
   already-existing widgets and could never show a group/preset added after
   construction.
4. The Device Property Browser / Config Group Editor buttons live in the
   Configurations panel itself, not the unrelated debug button row.
"""
import inspect
from unittest.mock import MagicMock

import glados_pycromanager.GUI.MMcontrols as MMcontrols
from glados_pycromanager.GUI.MMcontrols import ConfigInfo


def _fake_shared_data(nr_configs, has_limits):
    """Build a MagicMock shared_data.MILcore satisfying ConfigInfo's calls
    for a group with `nr_configs` presets, whose single underlying
    device/property (used only when nr_configs<=1) does/doesn't have
    limits, per `has_limits`."""
    mil = MagicMock()
    mil.get_available_config_groups.return_value = ["MyGroup"]
    mil.get_available_configs.return_value = [f"Preset{i}" for i in range(nr_configs)]
    if nr_configs <= 1:
        # deviceNameProperty_fromVerbose() parses "<html>Device:Property=Value<br>"
        mil.get_config_group_state.return_value = "state"
        mil.verbose_info_from_config_group_state.return_value = "<html>Cam:Exposure=10<br>"
        mil.has_property_limits.return_value = has_limits
    shared_data = MagicMock()
    shared_data.MILcore = mil
    return shared_data


def _config_info(nr_configs, has_limits):
    shared_data = _fake_shared_data(nr_configs, has_limits)
    MMcontrols.shared_data = shared_data
    core = MagicMock()
    return ConfigInfo(core, shared_data, 0)


class TestConfigInfoWidgetSelectionMutualExclusivity:
    def test_multiple_named_presets_is_dropdown_only(self):
        info = _config_info(nr_configs=2, has_limits=False)
        assert info.isDropDown() is True
        assert info.isSlider() is False
        assert info.isInputField() is False

    def test_single_preset_with_limits_is_slider_only(self):
        info = _config_info(nr_configs=1, has_limits=True)
        assert info.isDropDown() is False
        assert info.isSlider() is True
        assert info.isInputField() is False

    def test_single_preset_without_limits_is_input_field_only(self):
        info = _config_info(nr_configs=1, has_limits=False)
        assert info.isDropDown() is False
        assert info.isSlider() is False
        assert info.isInputField() is True

    def test_single_named_preset_is_no_longer_shown_as_a_dropdown(self):
        """Regression: a group with exactly one preset used to be treated
        as a preset-name dropdown whenever that preset wasn't literally
        named 'NewPreset' -- even though it manages exactly one property
        and should be edited directly (slider/input field), matching how
        Micro-Manager's own single-property groups behave."""
        info = _config_info(nr_configs=1, has_limits=True)
        assert info.isDropDown() is False

    def test_empty_group_shows_no_widget(self):
        info = _config_info(nr_configs=0, has_limits=False)
        assert info.isDropDown() is False
        assert info.isSlider() is False
        assert info.isInputField() is False


class TestAddLabelUsesElifChain:
    def test_widget_selection_is_elif_not_independent_ifs(self):
        source = inspect.getsource(MMcontrols.MMConfigUI.addLabel)
        assert "elif" in source, (
            "addLabel() must pick one of dropdown/slider/input-field via elif -- "
            "independent ifs let more than one value widget land in the same row."
        )

    def test_read_only_display_is_checked_before_dropdown_slider_input(self):
        """isReadOnly() must be the first branch: a group backed entirely by
        read-only properties should render as a static label, never an
        editable dropdown/slider/input field the user can't actually use."""
        source = inspect.getsource(MMcontrols.MMConfigUI.addLabel)
        assert source.index("isReadOnly()") < source.index("isDropDown()")


def _config_info_with_properties(pairs, read_only_by_pair):
    """Build a ConfigInfo whose group is backed by the given (device, property)
    pairs, one preset per pair collapsed into a single preset's settings, with
    is_property_read_only() answering per read_only_by_pair."""
    mil = MagicMock()
    mil.get_available_config_groups.return_value = ["MyGroup"]
    mil.get_available_configs.return_value = ["NewPreset"]
    mil.get_config_data.return_value = "configdata"
    mil.get_config_settings.return_value = [
        {"device": device, "property": prop, "value": "0"} for device, prop in pairs
    ]
    mil.is_property_read_only.side_effect = lambda device, prop: read_only_by_pair[(device, prop)]
    mil.get_current_config.return_value = "NewPreset"
    shared_data = MagicMock()
    shared_data.MILcore = mil
    MMcontrols.shared_data = shared_data
    core = MagicMock()
    return ConfigInfo(core, shared_data, 0)


class TestConfigInfoReadOnly:
    def test_all_properties_read_only(self):
        info = _config_info_with_properties(
            [("Cam", "ActualFrameIntervalMs")],
            {("Cam", "ActualFrameIntervalMs"): True},
        )
        assert info.isReadOnly() is True

    def test_mixed_read_only_and_writable_is_not_read_only(self):
        info = _config_info_with_properties(
            [("Cam", "ActualFrameIntervalMs"), ("Cam", "Exposure")],
            {("Cam", "ActualFrameIntervalMs"): True, ("Cam", "Exposure"): False},
        )
        assert info.isReadOnly() is False

    def test_empty_group_is_not_read_only(self):
        info = _config_info_with_properties([], {})
        assert info.isReadOnly() is False


class TestConfigPanelRefreshRoutesThroughRebuild:
    def test_refresh_button_is_wired_to_rebuild_config_layout(self):
        source = inspect.getsource(MMcontrols.MMConfigUI.__init__)
        assert "self.refreshButton.clicked.connect(lambda index: self.rebuildConfigLayout())" in source

    def test_update_all_mm_info_calls_rebuild_config_layout(self):
        source = inspect.getsource(MMcontrols.MMConfigUI.updateAllMMinfo)
        assert "self.rebuildConfigLayout()" in source

    def test_open_config_group_editor_triggers_a_refresh(self):
        source = inspect.getsource(MMcontrols.MMConfigUI.openConfigGroupEditor)
        assert "self.updateAllMMinfo()" in source or "self.rebuildConfigLayout()" in source


class TestConfigPanelButtonPlacement:
    def test_device_and_config_buttons_live_in_the_configs_block_not_debug_row(self):
        init_source = inspect.getsource(MMcontrols.MMConfigUI.__init__)
        configs_block = init_source.split("if showConfigs:")[1].split("if showStages:")[0]
        assert "devicePropertyBrowserButton" in configs_block
        assert "configGroupEditorButton" in configs_block

        debug_row_start = init_source.find("debugHbox = QHBoxLayout()")
        debug_row_end = init_source.find("liveModeLayout.addLayout(debugHbox")
        debug_row = init_source[debug_row_start:debug_row_end]
        assert "devicePropertyBrowserButton" not in debug_row
        assert "configGroupEditorButton" not in debug_row


class TestRebuildConfigLayout:
    def test_rebuild_recreates_rows_from_current_mil_state(self):
        """A minimal, real (not source-inspected) exercise of
        rebuildConfigLayout()'s bookkeeping: it must reset every per-row
        dict and end up with one ConfigInfo per group MIL currently
        reports -- the actual bug (frozen row/dropdown state) was that
        these were only ever populated once, at construction."""
        panel = MMcontrols.MMConfigUI.__new__(MMcontrols.MMConfigUI)
        panel.showConfigs = True
        panel.core = MagicMock()
        shared_data = MagicMock()
        shared_data.MILcore.get_available_config_groups.return_value = ["A", "B", "C"]
        panel.shared_data = shared_data
        MMcontrols.shared_data = shared_data

        panel.configLayout = MagicMock()
        panel.configLayout.count.return_value = 0
        panel._clearConfigLayout = MagicMock()
        panel.addRow = MagicMock(side_effect=lambda config_id: MagicMock())

        panel.rebuildConfigLayout()

        panel._clearConfigLayout.assert_called_once()
        assert len(panel.config_groups) == 3
        assert all(isinstance(v, ConfigInfo) for v in panel.config_groups.values())
        assert panel.addRow.call_count == 3
        assert panel.dropDownBoxes == {}
        assert panel.sliders == {}
        assert panel.editFields == {}

    def test_rebuild_is_a_noop_when_configs_panel_not_shown(self):
        panel = MMcontrols.MMConfigUI.__new__(MMcontrols.MMConfigUI)
        panel.showConfigs = False
        panel._clearConfigLayout = MagicMock()

        panel.rebuildConfigLayout()

        panel._clearConfigLayout.assert_not_called()
