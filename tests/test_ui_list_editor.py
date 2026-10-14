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


def test_buttons_fill_two_columns_row_by_row(qapp):
    from glados_pycromanager.ui.layout.list_editor import ListEditor

    editor = ListEditor(_table(["Name"]))
    buttons = [editor.add_action(str(i)) for i in range(5)]
    grid = editor._buttons
    positions = [grid.getItemPosition(grid.indexOf(b))[:2] for b in buttons]
    assert positions == [(0, 0), (0, 1), (1, 0), (1, 1), (2, 0)]
    assert editor.buttons == buttons


def test_min_rows_overrides_the_theme(qapp):
    from glados_pycromanager.ui.layout.list_editor import ListEditor

    short = ListEditor(_table(["Name"]), min_rows=2)  # kept: the editor owns its table
    tall = ListEditor(_table(["Name"]), min_rows=6)
    rows = short.table.verticalHeader().defaultSectionSize()
    assert tall.table.minimumHeight() - short.table.minimumHeight() == 4 * rows


def test_min_width_counts_the_row_header_before_the_table_is_shown(qapp):
    from PyQt5.QtWidgets import QTableWidgetItem

    from glados_pycromanager.ui.layout.list_editor import ListEditor

    table = _table(["Channel Setting", "Exposure"])
    table.insertRow(0)
    table.setItem(0, 0, QTableWidgetItem("488"))
    editor = ListEditor(table)
    assert not table.isVisible()
    header = table.horizontalHeader()
    assert table.minimumWidth() >= (header.sectionSizeHint(0) + header.sectionSizeHint(1)
                                    + table.verticalHeader().sizeHint().width())
    editor.deleteLater()
