"""ListEditor: table + top-aligned button column, header never clips its text.

The channel list's column 0 used to be a fixed 54 px, which clipped the
"Channel Setting" header.
"""
from __future__ import annotations

import os

import pytest

pytest.importorskip("PyQt5.QtWidgets")


@pytest.fixture(scope="module")
def qapp():
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from PyQt5.QtWidgets import QApplication

    return QApplication.instance() or QApplication([])


def _table(labels):
    from PyQt5.QtWidgets import QTableWidget

    table = QTableWidget(0, len(labels))
    table.setHorizontalHeaderLabels(labels)
    return table


def test_columns_never_narrower_than_header_text(qapp):
    from glados_pycromanager.ui.layout.list_editor import ListEditor

    labels = ["Channel Setting", "Exposure"]
    table = _table(labels)
    editor = ListEditor(table)
    editor.resize(40, 200)          # far too narrow
    editor.show()
    qapp.processEvents()
    header = table.horizontalHeader()
    metrics = header.fontMetrics()
    for col, text in enumerate(labels):
        assert header.sectionSize(col) >= metrics.horizontalAdvance(text)
    editor.hide()


def test_min_height_fits_configured_rows(qapp):
    from glados_pycromanager.ui.layout.list_editor import configure_table_header

    table = _table(["Name", "x"])
    configure_table_header(table, min_rows=5)
    assert table.minimumHeight() >= 5 * table.verticalHeader().defaultSectionSize()
    assert table.maximumHeight() > 10000        # no fixed height any more


def test_add_action_returns_wired_button_in_order(qapp):
    from glados_pycromanager.ui.layout.list_editor import ListEditor

    hits = []
    editor = ListEditor(_table(["Name"]))
    first = editor.add_action("Add", lambda: hits.append("add"))
    second = editor.add_action("Delete")
    first.click()
    assert hits == ["add"]
    assert editor.buttons == [first, second]
