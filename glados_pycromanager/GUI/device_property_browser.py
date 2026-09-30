"""Device property browser: a table of every loaded device's properties.

Structural precedent: performance_report_dialog.py's PerformanceReportDialog --
a small, self-contained QDialog opened via .exec_(). collect_device_properties()
is kept GUI-free and goes through MicroscopeInterfaceLayer only, so it works
identically across all three backends and is unit-testable with a mocked MIL.

Supersedes the dead MMConfigUI.get_device_properties() prototype (formerly in
MMcontrols.py's "deprecated" region), which called raw pycromanager-Java-style
methods directly (only worked for one backend) and had a bug where the
range/limits branch never appended to property_items.
"""

import logging
import os
import sys

from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import (
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QHBoxLayout,
    QHeaderView,
    QLineEdit,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
)

if 'glados_pycromanager' not in sys.modules and 'site-packages' not in __file__:
    sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..')))

logger = logging.getLogger(__name__)

COLUMN_DEVICE = 0
COLUMN_PROPERTY = 1
COLUMN_VALUE = 2
COLUMN_READ_ONLY = 3


def collect_device_properties(mil) -> list:
    """Return one dict per (device, property) pair, backend-blind via MIL.

    Each dict has keys: device, name, value, read_only, and either
    {"kind": "range", "min": ..., "max": ...} or
    {"kind": "enum", "options": [...]} merged in.
    """
    items = []
    for device in mil.get_loaded_devices():
        try:
            property_names = mil.get_device_property_names(device)
        except (RuntimeError, OSError, ValueError) as exc:
            logger.warning("Could not read property names for device %s: %s", device, exc)
            continue
        for prop in property_names:
            try:
                value = mil.get_property(device, prop)
                read_only = mil.is_property_read_only(device, prop)
                entry = {"device": device, "name": prop, "value": value, "read_only": read_only}
                if mil.has_property_limits(device, prop):
                    entry["kind"] = "range"
                    entry["min"] = mil.get_property_lower_limit(device, prop)
                    entry["max"] = mil.get_property_upper_limit(device, prop)
                else:
                    entry["kind"] = "enum"
                    entry["options"] = list(mil.get_allowed_property_values(device, prop))
                items.append(entry)
            except (RuntimeError, OSError, ValueError) as exc:
                logger.warning("Could not read property %s.%s: %s", device, prop, exc)
    return items


def build_property_value_widget(entry, parent, on_change):
    """Build the editable widget for one property's value.

    `entry` is one item from collect_device_properties() (device/name/value/
    read_only/kind/options-or-min-max). `on_change(new_value: str)` is called
    when the user commits an edit (combo selection, or editingFinished on a
    line edit) -- it decides what happens to the new value (e.g. write it to
    hardware immediately, or just record it for a preset being built), which
    is what lets this be shared between the always-live device property
    browser and the config group editor's live/non-live tables.

    Returns a QWidget; a read-only property returns a plain (non-editable)
    QLineEdit instead of a QTableWidgetItem so callers can use it uniformly
    with QTableWidget.setCellWidget() / any other layout.
    """
    value = entry["value"]

    if entry["read_only"]:
        display = QLineEdit(str(value), parent)
        display.setReadOnly(True)
        return display

    if entry["kind"] == "enum" and entry["options"]:
        combo = QComboBox(parent)
        combo.addItems([str(opt) for opt in entry["options"]])
        index = combo.findText(str(value))
        if index >= 0:
            combo.setCurrentIndex(index)
        combo.currentTextChanged.connect(on_change)
        return combo

    edit = QLineEdit(str(value), parent)
    edit.editingFinished.connect(lambda edit=edit: on_change(edit.text()))
    return edit


class DevicePropertyBrowserDialog(QDialog):
    """Shows every loaded device's properties in an editable table.

    Open with `dialog.exec_()`. All reads/writes go through the MIL instance
    passed in, so this works unchanged for any of the three backends.
    """

    def __init__(self, mil, parent=None):
        super().__init__(parent)
        self._mil = mil
        self.setWindowTitle("Device Property Browser")
        self.setMinimumSize(700, 500)

        self.table = QTableWidget(self)
        self.table.setColumnCount(4)
        self.table.setHorizontalHeaderLabels(["Device", "Property", "Value", "Read-only"])
        self.table.horizontalHeader().setSectionResizeMode(COLUMN_PROPERTY, QHeaderView.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(COLUMN_VALUE, QHeaderView.Stretch)
        self.table.verticalHeader().setVisible(False)

        refresh_btn = QPushButton("Refresh", self)
        refresh_btn.clicked.connect(self.refresh)

        buttons = QDialogButtonBox(QDialogButtonBox.Close, parent=self)
        buttons.rejected.connect(self.reject)
        buttons.accepted.connect(self.accept)

        row = QHBoxLayout()
        row.addWidget(refresh_btn)
        row.addStretch()
        row.addWidget(buttons)

        layout = QVBoxLayout(self)
        layout.addWidget(self.table)
        layout.addLayout(row)

        self.refresh()

    def refresh(self):
        items = collect_device_properties(self._mil)
        self.table.setRowCount(len(items))
        for row_index, entry in enumerate(items):
            device_item = QTableWidgetItem(entry["device"])
            device_item.setFlags(device_item.flags() & ~Qt.ItemIsEditable)
            self.table.setItem(row_index, COLUMN_DEVICE, device_item)

            name_item = QTableWidgetItem(entry["name"])
            name_item.setFlags(name_item.flags() & ~Qt.ItemIsEditable)
            self.table.setItem(row_index, COLUMN_PROPERTY, name_item)

            read_only_item = QTableWidgetItem("Yes" if entry["read_only"] else "No")
            read_only_item.setFlags(read_only_item.flags() & ~Qt.ItemIsEditable)
            self.table.setItem(row_index, COLUMN_READ_ONLY, read_only_item)

            self._setValueWidget(row_index, entry)

    def _setValueWidget(self, row_index, entry):
        device, prop = entry["device"], entry["name"]
        widget = build_property_value_widget(
            entry, self.table, on_change=lambda value, device=device, prop=prop: self._writeProperty(device, prop, value)
        )
        self.table.setCellWidget(row_index, COLUMN_VALUE, widget)

    def _writeProperty(self, device, prop, value):
        try:
            self._mil.set_property(device, prop, value)
        except (RuntimeError, OSError, ValueError) as exc:
            logger.warning("Setting property %s.%s to %r failed: %s", device, prop, value, exc)
