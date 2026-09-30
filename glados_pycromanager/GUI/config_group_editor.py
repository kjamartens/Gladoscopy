"""Config group editor: create/rename/delete Micro-Manager configuration
groups and presets, edit the device/property settings within a group, and
save the result to a Micro-Manager .cfg file.

Deliberately mirrors Micro-Manager's own "Configuration settings" panel /
Group Editor / Preset editor methodology and phrasing (not a from-scratch UX):
a group is defined *once* by picking which device properties belong to it
(Group Editor); every preset in that group then just supplies values for that
same fixed set of properties (Preset editor). This matches how the .cfg file
actually stores it -- one `ConfigGroup,<group>,<preset>,<device>,<property>,
<value>` line per setting, e.g.:

    ConfigGroup,Simulation_type,Simulation_1,SMLMDemoCam,NupCount,20
    ConfigGroup,Simulation_type,Simulation_1,SMLMDemoCam,Pattern,Circle
    ConfigGroup,Simulation_type,Simulation_2,SMLMDemoCam,NupCount,164
    ConfigGroup,Simulation_type,Simulation_2,SMLMDemoCam,Pattern,NUP

Structural precedent: device_property_browser.py's DevicePropertyBrowserDialog
-- GUI-free data-collection functions plus QDialogs that render them, all
going through MicroscopeInterfaceLayer only so this works identically across
all three backends. The device/property table and its editable value widgets
(build_property_value_widget) are reused directly from that module.
"""

import logging
import os
import sys

from PyQt5.QtCore import Qt, QTimer
from PyQt5.QtWidgets import (
    QAbstractItemView,
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

if 'glados_pycromanager' not in sys.modules and 'site-packages' not in __file__:
    sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..')))

import glados_pycromanager.GUI.device_property_browser as device_property_browser
from glados_pycromanager.io.appdata import storeSharedData_GlobalData

logger = logging.getLogger(__name__)

# How long the Save button reads "Saved!" before reverting, so a click that
# writes a file with no other visible effect still gets user feedback.
SAVED_FEEDBACK_MS = 1500

# Mirrors MMcontrols.py's getDevicesOfDeviceType() deviceTypeArray -- see
# https://javadoc.scijava.org/Micro-Manager-Core/mmcorej/DeviceType.html
DEVICE_TYPE_NAMES = {
    1: 'GenericDevice', 2: 'CameraDevice', 3: 'ShutterDevice', 4: 'StateDevice',
    5: 'StageDevice', 6: 'XYStageDevice', 7: 'GenericDevice', 8: 'GenericDevice',
    9: 'AutoFocusDevice', 10: 'CoreDevice', 11: 'GenericDevice', 12: 'GenericDevice',
    13: 'GenericDevice', 14: 'GenericDevice', 15: 'HubDevice',
}

DEVICE_TYPE_FILTER_BUCKETS = ("cameras", "shutters", "stages", "wheels, turrets, etc.", "other devices")

_BUCKET_TYPE_NAMES = {
    "cameras": {"CameraDevice"},
    "shutters": {"ShutterDevice"},
    "stages": {"StageDevice", "XYStageDevice"},
    "wheels, turrets, etc.": {"StateDevice"},
}


def device_type_bucket(mil, device) -> str:
    """Classify a device into one of DEVICE_TYPE_FILTER_BUCKETS."""
    try:
        type_name = DEVICE_TYPE_NAMES.get(mil.get_device_type(device), 'GenericDevice')
    except (RuntimeError, OSError, ValueError):
        return "other devices"
    for bucket, names in _BUCKET_TYPE_NAMES.items():
        if type_name in names:
            return bucket
    return "other devices"


def collect_config_groups(mil) -> list:
    """Return one dict per configuration group, backend-blind via MIL.

    Each dict: {"group": str, "presets": [{"preset": str, "is_current": bool,
    "settings": [{"device", "property", "value"}, ...]}, ...]}.
    """
    groups = []
    for group in mil.get_available_config_groups():
        try:
            current_preset = mil.get_current_config(group)
        except (RuntimeError, OSError, ValueError):
            current_preset = None

        presets = []
        for preset in mil.get_available_configs(group):
            try:
                config_data = mil.get_config_data(group, preset)
                settings = mil.get_config_settings(config_data)
            except (RuntimeError, OSError, ValueError) as exc:
                logger.warning("Could not read preset %s.%s: %s", group, preset, exc)
                settings = []
            presets.append({"preset": preset, "is_current": preset == current_preset, "settings": settings})
        groups.append({"group": group, "presets": presets})
    return groups


def group_property_set(mil, group_name) -> list:
    """Return the (device, property) pairs shared by every preset in a group.

    A Micro-Manager config group's "shape" -- which properties belong to it
    -- is fixed once at group-creation time; every preset in the group just
    supplies values for that same set. There is no core-level record of this
    set independent of the presets, so it is derived as the union of settings
    across all of the group's existing presets.
    """
    pairs = []
    seen = set()
    for preset in mil.get_available_configs(group_name):
        config_data = mil.get_config_data(group_name, preset)
        for setting in mil.get_config_settings(config_data):
            key = (setting["device"], setting["property"])
            if key not in seen:
                seen.add(key)
                pairs.append(key)
    return pairs


class GroupEditorDialog(QDialog):
    """Micro-Manager's "Group Editor": pick which device properties make up
    a configuration group, and (for a new group) their starting values.

    Interacting with a property's "Current Property Value" writes it to the
    live device immediately, exactly like the device property browser --
    this is how you put the hardware into the state you want the group's
    first preset ("NewPreset") to capture. Editing an *existing* group's
    property selection instead adds/removes that setting across every one of
    the group's existing presets (added properties take the live value shown
    here; MMCore has no notion of a property being "unset" within a preset
    that already defines others).
    """

    def __init__(self, mil, group_name=None, parent=None):
        super().__init__(parent)
        self._mil = mil
        self._original_group_name = group_name
        self._is_new = group_name is None
        self._existing_pairs = set(group_property_set(mil, group_name)) if group_name else set()
        self._live_values = {}
        self._row_checks = {}
        self._entries = []

        self.setWindowTitle("Group Editor")
        self.setMinimumSize(700, 550)

        header_box = QGroupBox("Specify properties in this configuration group:")
        header_layout = QHBoxLayout(header_box)
        header_layout.addWidget(QLabel("Group name:"))
        self.name_edit = QLineEdit(group_name or "", self)
        header_layout.addWidget(self.name_edit)

        filter_column = self._buildFilterColumn()

        self.table = QTableWidget(self)
        self.table.setColumnCount(3)
        self.table.setHorizontalHeaderLabels(["Property Name", "Use in Group", "Current Property Value"])
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(2, QHeaderView.Stretch)
        self.table.verticalHeader().setVisible(False)

        body_row = QHBoxLayout()
        filter_widget = QWidget(self)
        filter_widget.setLayout(filter_column)
        body_row.addWidget(filter_widget)
        body_row.addWidget(self.table, 1)

        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel, parent=self)
        buttons.accepted.connect(self._onAccept)
        buttons.rejected.connect(self.reject)

        layout = QVBoxLayout(self)
        layout.addWidget(header_box)
        layout.addLayout(body_row)
        layout.addWidget(buttons)

        self._loadProperties()

    def _buildFilterColumn(self):
        self.filter_checks = {}
        column = QVBoxLayout()
        column.addWidget(QLabel("Device type:"))

        all_none_row = QHBoxLayout()
        all_button = QPushButton("All", self)
        all_button.clicked.connect(lambda: self._setAllFilters(True))
        none_button = QPushButton("None", self)
        none_button.clicked.connect(lambda: self._setAllFilters(False))
        all_none_row.addWidget(all_button)
        all_none_row.addWidget(none_button)
        column.addLayout(all_none_row)

        for bucket in DEVICE_TYPE_FILTER_BUCKETS:
            checkbox = QCheckBox(bucket, self)
            checkbox.setChecked(True)
            checkbox.stateChanged.connect(self._applyFilters)
            self.filter_checks[bucket] = checkbox
            column.addWidget(checkbox)

        column.addWidget(QLabel("Device or property name:"))
        search_row = QHBoxLayout()
        self.search_edit = QLineEdit(self)
        self.search_edit.textChanged.connect(self._applyFilters)
        clear_button = QPushButton("Clear", self)
        clear_button.clicked.connect(lambda: self.search_edit.setText(""))
        search_row.addWidget(self.search_edit)
        search_row.addWidget(clear_button)
        column.addLayout(search_row)

        column.addWidget(QLabel("Property type:"))
        self.show_read_only_check = QCheckBox("Show read-only", self)
        self.show_read_only_check.setChecked(True)
        self.show_read_only_check.stateChanged.connect(self._applyFilters)
        column.addWidget(self.show_read_only_check)

        column.addStretch()
        return column

    def _setAllFilters(self, checked):
        for checkbox in self.filter_checks.values():
            checkbox.setChecked(checked)

    def _loadProperties(self):
        self._entries = device_property_browser.collect_device_properties(self._mil)
        self.table.setRowCount(len(self._entries))
        for row, entry in enumerate(self._entries):
            key = (entry["device"], entry["name"])

            name_item = QTableWidgetItem(f"{entry['device']}-{entry['name']}")
            name_item.setFlags(name_item.flags() & ~Qt.ItemIsEditable)
            self.table.setItem(row, 0, name_item)

            checkbox = QCheckBox(self.table)
            checkbox.setChecked(key in self._existing_pairs)
            self._row_checks[key] = checkbox
            self.table.setCellWidget(row, 1, checkbox)

            self._live_values[key] = entry["value"]
            widget = device_property_browser.build_property_value_widget(
                entry, self.table, on_change=lambda value, key=key, entry=entry: self._onValueChanged(key, entry, value)
            )
            self.table.setCellWidget(row, 2, widget)
        self._applyFilters()

    def _onValueChanged(self, key, entry, value):
        self._live_values[key] = value
        if entry["read_only"]:
            return
        try:
            self._mil.set_property(entry["device"], entry["name"], value)
        except (RuntimeError, OSError, ValueError) as exc:
            logger.warning("Setting property %s.%s failed: %s", entry["device"], entry["name"], exc)

    def _applyFilters(self):
        search = self.search_edit.text().strip().lower()
        show_read_only = self.show_read_only_check.isChecked()
        active_buckets = {bucket for bucket, checkbox in self.filter_checks.items() if checkbox.isChecked()}
        for row, entry in enumerate(self._entries):
            bucket = device_type_bucket(self._mil, entry["device"])
            visible = bucket in active_buckets
            if visible and not show_read_only and entry["read_only"]:
                visible = False
            if visible and search:
                haystack = f"{entry['device']} {entry['name']}".lower()
                visible = search in haystack
            self.table.setRowHidden(row, not visible)

    def _onAccept(self):
        name = self.name_edit.text().strip()
        if not name:
            QMessageBox.warning(self, "Group Editor", "Enter a group name.")
            return
        checked_pairs = {key for key, checkbox in self._row_checks.items() if checkbox.isChecked()}
        if not checked_pairs:
            QMessageBox.warning(self, "Group Editor", "Select at least one property.")
            return

        try:
            if self._is_new:
                self._mil.define_config_group(name)
                for device, prop in checked_pairs:
                    self._mil.define_config(name, "NewPreset", device, prop, str(self._live_values[(device, prop)]))
            else:
                group_name = self._original_group_name
                if name != group_name:
                    self._mil.rename_config_group(group_name, name)
                    group_name = name
                added = checked_pairs - self._existing_pairs
                removed = self._existing_pairs - checked_pairs
                for preset in list(self._mil.get_available_configs(group_name)):
                    for device, prop in added:
                        self._mil.define_config(group_name, preset, device, prop, str(self._live_values[(device, prop)]))
                    for device, prop in removed:
                        self._mil.delete_config(group_name, preset, device, prop)
        except (RuntimeError, OSError, ValueError) as exc:
            QMessageBox.warning(self, "Group Editor", f"Could not save group '{name}': {exc}")
            return
        self.accept()


class PresetEditorDialog(QDialog):
    """Micro-Manager's "Preset editor for the '<group>' configuration group":
    supply values for the group's fixed set of properties, under a preset
    name. Does not touch live hardware -- unlike the Group Editor's table,
    these are just the values recorded into the preset."""

    def __init__(self, mil, group_name, preset_name=None, parent=None):
        super().__init__(parent)
        self._mil = mil
        self._group_name = group_name
        self._original_preset_name = preset_name
        self._is_new = preset_name is None
        self._values = {}

        self.setWindowTitle(f'Preset editor for the "{group_name}" configuration group')
        self.setMinimumSize(450, 400)

        header_box = QGroupBox("Specify property values for this preset:")
        header_layout = QHBoxLayout(header_box)
        header_layout.addWidget(QLabel("Preset name:"))
        self.name_edit = QLineEdit(preset_name or "", self)
        header_layout.addWidget(self.name_edit)

        self.table = QTableWidget(self)
        self.table.setColumnCount(2)
        self.table.setHorizontalHeaderLabels(["Property Name", "Preset Value"])
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        self.table.verticalHeader().setVisible(False)

        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel, parent=self)
        buttons.accepted.connect(self._onAccept)
        buttons.rejected.connect(self.reject)

        layout = QVBoxLayout(self)
        layout.addWidget(header_box)
        layout.addWidget(self.table)
        layout.addWidget(buttons)

        self._loadRows()

    def _loadRows(self):
        pairs = group_property_set(self._mil, self._group_name)
        all_props = {(e["device"], e["name"]): e for e in device_property_browser.collect_device_properties(self._mil)}

        existing_values = {}
        if not self._is_new:
            for group_entry in collect_config_groups(self._mil):
                if group_entry["group"] != self._group_name:
                    continue
                for preset_entry in group_entry["presets"]:
                    if preset_entry["preset"] == self._original_preset_name:
                        for setting in preset_entry["settings"]:
                            existing_values[(setting["device"], setting["property"])] = setting["value"]

        self.table.setRowCount(len(pairs))
        for row, key in enumerate(pairs):
            device, prop = key
            entry = dict(all_props.get(key, {
                "device": device, "name": prop, "value": "", "read_only": False, "kind": "enum", "options": [],
            }))
            if key in existing_values:
                entry["value"] = existing_values[key]
            elif self._is_new:
                try:
                    entry["value"] = self._mil.get_property(device, prop)
                except (RuntimeError, OSError, ValueError):
                    pass
            self._values[key] = entry["value"]

            label_item = QTableWidgetItem(f"{device}-{prop}")
            label_item.setFlags(label_item.flags() & ~Qt.ItemIsEditable)
            self.table.setItem(row, 0, label_item)

            widget = device_property_browser.build_property_value_widget(
                entry, self.table, on_change=lambda value, key=key: self._values.__setitem__(key, value)
            )
            self.table.setCellWidget(row, 1, widget)

    def _onAccept(self):
        name = self.name_edit.text().strip()
        if not name:
            QMessageBox.warning(self, "Preset Editor", "Enter a preset name.")
            return
        try:
            if not self._is_new and name != self._original_preset_name:
                self._mil.rename_config(self._group_name, self._original_preset_name, name)
            for (device, prop), value in self._values.items():
                self._mil.define_config(self._group_name, name, device, prop, str(value))
        except (RuntimeError, OSError, ValueError) as exc:
            QMessageBox.warning(self, "Preset Editor", f"Could not save preset '{name}': {exc}")
            return
        self.accept()


class ConfigGroupEditorDialog(QDialog):
    """Micro-Manager's "Configuration settings" panel: one row per group,
    a preset dropdown per row (selecting a preset activates it immediately),
    and Group/Preset +/-/Edit buttons that open GroupEditorDialog /
    PresetEditorDialog.

    Open with `dialog.exec_()`. All reads/writes go through the MIL instance
    passed in, so this works unchanged for any of the three backends.
    """

    def __init__(self, mil, shared_data, parent=None):
        super().__init__(parent)
        self._mil = mil
        self._shared_data = shared_data
        self._groups_cache = []
        self.setWindowTitle("Configuration settings")
        self.setMinimumSize(500, 450)

        self.table = QTableWidget(self)
        self.table.setColumnCount(2)
        self.table.setHorizontalHeaderLabels(["Group", "Preset"])
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        self.table.verticalHeader().setVisible(False)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SingleSelection)

        top_row = QHBoxLayout()
        top_row.addWidget(QLabel("Configuration settings"))
        top_row.addStretch()
        self.save_button = QPushButton("Save", self)
        self.save_button.clicked.connect(self.saveConfiguration)
        top_row.addWidget(self.save_button)

        group_preset_row = QHBoxLayout()
        group_preset_row.addWidget(QLabel("Group:"))
        for text, handler in (("+", self.newGroup), ("−", self.deleteGroup), ("Edit", self.editGroup)):
            button = QPushButton(text, self)
            button.clicked.connect(handler)
            group_preset_row.addWidget(button)
        group_preset_row.addSpacing(20)
        group_preset_row.addWidget(QLabel("Preset:"))
        for text, handler in (("+", self.newPreset), ("−", self.deletePreset), ("Edit", self.editPreset)):
            button = QPushButton(text, self)
            button.clicked.connect(handler)
            group_preset_row.addWidget(button)
        group_preset_row.addStretch()

        close_buttons = QDialogButtonBox(QDialogButtonBox.Close, parent=self)
        close_buttons.rejected.connect(self.reject)
        close_buttons.accepted.connect(self.accept)

        layout = QVBoxLayout(self)
        layout.addLayout(top_row)
        layout.addWidget(self.table)
        layout.addLayout(group_preset_row)
        layout.addWidget(close_buttons)

        self.refresh()

    def refresh(self):
        self._groups_cache = collect_config_groups(self._mil)
        self.table.setRowCount(len(self._groups_cache))
        for row, group_entry in enumerate(self._groups_cache):
            name_item = QTableWidgetItem(group_entry["group"])
            name_item.setFlags(name_item.flags() & ~Qt.ItemIsEditable)
            self.table.setItem(row, 0, name_item)

            combo = QComboBox(self.table)
            combo.addItems([p["preset"] for p in group_entry["presets"]])
            current = next((p["preset"] for p in group_entry["presets"] if p["is_current"]), None)
            if current is not None:
                index = combo.findText(current)
                if index >= 0:
                    combo.setCurrentIndex(index)
            combo.currentTextChanged.connect(
                lambda preset, group=group_entry["group"]: self._activatePreset(group, preset)
            )
            self.table.setCellWidget(row, 1, combo)

    def _activatePreset(self, group, preset):
        if not preset:
            return
        try:
            self._mil.set_config(group, preset)
        except (RuntimeError, OSError, ValueError) as exc:
            logger.warning("Could not activate preset %s.%s: %s", group, preset, exc)

    def _selectedGroup(self):
        row = self.table.currentRow()
        if row < 0 or row >= len(self._groups_cache):
            return None
        return self._groups_cache[row]["group"]

    def _selectedPreset(self):
        row = self.table.currentRow()
        if row < 0:
            return None
        combo = self.table.cellWidget(row, 1)
        return combo.currentText() if combo is not None else None

    def newGroup(self):
        dialog = GroupEditorDialog(self._mil, parent=self)
        if dialog.exec_() == QDialog.Accepted:
            self.refresh()

    def editGroup(self):
        group = self._selectedGroup()
        if group is None:
            self._warn("Select a group to edit.")
            return
        dialog = GroupEditorDialog(self._mil, group_name=group, parent=self)
        if dialog.exec_() == QDialog.Accepted:
            self.refresh()

    def deleteGroup(self):
        group = self._selectedGroup()
        if group is None:
            self._warn("Select a group to delete.")
            return
        if not self._confirm(f"Delete group '{group}' and all of its presets?"):
            return
        try:
            self._mil.delete_config_group(group)
        except (RuntimeError, OSError, ValueError) as exc:
            self._warn(f"Could not delete group '{group}': {exc}")
        self.refresh()

    def newPreset(self):
        group = self._selectedGroup()
        if group is None:
            self._warn("Select a group to add a preset to.")
            return
        dialog = PresetEditorDialog(self._mil, group, parent=self)
        if dialog.exec_() == QDialog.Accepted:
            self.refresh()

    def editPreset(self):
        group = self._selectedGroup()
        preset = self._selectedPreset()
        if group is None or not preset:
            self._warn("Select a preset to edit.")
            return
        dialog = PresetEditorDialog(self._mil, group, preset_name=preset, parent=self)
        if dialog.exec_() == QDialog.Accepted:
            self.refresh()

    def deletePreset(self):
        group = self._selectedGroup()
        preset = self._selectedPreset()
        if group is None or not preset:
            self._warn("Select a preset to delete.")
            return
        if not self._confirm(f"Delete preset '{group}/{preset}'?"):
            return
        try:
            self._mil.delete_config(group, preset)
        except (RuntimeError, OSError, ValueError) as exc:
            self._warn(f"Could not delete preset '{preset}': {exc}")
        self.refresh()

    def saveConfiguration(self):
        path = self._shared_data.config.micromanager_config.config_path
        try:
            self._mil.save_system_configuration(path)
            logger.info("Saved Micro-Manager configuration to %s", path)
        except (RuntimeError, OSError, ValueError) as exc:
            self._warn(f"Could not save configuration to {path}: {exc}")
            return
        storeSharedData_GlobalData(self._shared_data)
        self._flashSavedFeedback()

    def _flashSavedFeedback(self):
        """Briefly relabel the Save button to "Saved!" so the user gets
        feedback that the click actually did something, then restore it."""
        self.save_button.setText("Saved!")
        self.save_button.setEnabled(False)
        QTimer.singleShot(SAVED_FEEDBACK_MS, self._restoreSaveButton)

    def _restoreSaveButton(self):
        self.save_button.setText("Save")
        self.save_button.setEnabled(True)

    def _warn(self, message):
        logger.warning(message)
        QMessageBox.warning(self, "Configuration settings", message)

    def _confirm(self, message) -> bool:
        return QMessageBox.question(self, "Configuration settings", message, QMessageBox.Yes | QMessageBox.No) == QMessageBox.Yes
