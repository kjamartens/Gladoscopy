"""A table with a block of action buttons beside it, top-aligned with the table.

Used for the XY position list and the channel list. The table keeps its own
class (and every method callers use on it); `ListEditor` only owns the
arrangement and the header sizing:

- text columns stretch, numeric columns size to their contents;
- no column can shrink below its header text (the channel list's column 0
  was a fixed 54 px, which clipped "Channel Setting" to "annel Setti");
- the table is at least `Theme.table_min_rows` rows tall instead of a fixed
  240 px, and grows with the section;
- the buttons fill `button_columns` columns (default 2), row by row, so a
  long list of actions does not set the section's height.
"""
from __future__ import annotations

from PyQt5.QtCore import QTimer
from PyQt5.QtWidgets import (
    QGridLayout,
    QHBoxLayout,
    QHeaderView,
    QPushButton,
    QSizePolicy,
    QTableWidget,
    QVBoxLayout,
    QWidget,
)

from glados_pycromanager.ui.layout.theme import compact_spacing, current_theme


def configure_table_header(table: QTableWidget, stretch_columns=None, min_rows: int | None = None) -> None:
    """Size `table`'s columns from their header text and give it a row-count minimum height.

    `stretch_columns` are the columns that take spare width (default: column 0).
    Call again after the column count or labels change.
    """
    t = current_theme()
    if stretch_columns is None:
        stretch_columns = (0,)
    if min_rows is None:
        min_rows = t.table_min_rows
    header = table.horizontalHeader()
    header.setStretchLastSection(False)
    header.setMinimumSectionSize(header.fontMetrics().averageCharWidth() * 3)
    min_width = 0
    for col in range(table.columnCount()):
        stretch = col in stretch_columns
        header.setSectionResizeMode(col, QHeaderView.Stretch if stretch else QHeaderView.ResizeToContents)
        # A content-sized column is as wide as its widest cell (cell widgets
        # included), which can exceed its header; the stretch column gets the rest.
        width = header.sectionSizeHint(col)
        if not stretch:
            width = max(width, table.sizeHintForColumn(col))
        min_width += width
    vertical = table.verticalHeader()
    frame = 2 * table.frameWidth()
    # isHidden, not isVisible: the table is usually not shown yet when this runs.
    vheader_width = vertical.sizeHint().width() if not vertical.isHidden() else 0
    table.setMinimumWidth(min_width + vheader_width + frame)
    table.setMinimumHeight(header.sizeHint().height() + min_rows * vertical.defaultSectionSize() + frame)
    table.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)


#: Button columns beside the table; two keeps the XY list's seven actions to four rows.
DEFAULT_BUTTON_COLUMNS = 2


class ListEditor(QWidget):
    """`table` on the left, a block of buttons on its right (`button_columns` wide)."""

    def __init__(self, table: QTableWidget, stretch_columns=None, parent: QWidget | None = None,
                 button_columns: int = DEFAULT_BUTTON_COLUMNS, min_rows: int | None = None):
        super().__init__(parent)
        self.table = table
        self._stretch_columns = stretch_columns
        self._button_columns = max(1, int(button_columns))
        self._min_rows = min_rows  # None: the theme's table_min_rows
        self._button_list: list[QPushButton] = []
        spacing = compact_spacing()
        row = QHBoxLayout(self)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(spacing)
        row.addWidget(table, 1)
        column = QVBoxLayout()
        column.setContentsMargins(0, 0, 0, 0)
        self._buttons = QGridLayout()
        self._buttons.setContentsMargins(0, 0, 0, 0)
        self._buttons.setSpacing(spacing)
        column.addLayout(self._buttons)
        column.addStretch(1)
        row.addLayout(column)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.refresh_header()
        # Rows bring cell widgets that can widen a content-sized column; recompute
        # once they are in (cell widgets are set after the row is inserted).
        model = table.model()
        model.rowsInserted.connect(self._scheduleRefresh)
        model.rowsRemoved.connect(self._scheduleRefresh)

    def _scheduleRefresh(self, *_args) -> None:
        QTimer.singleShot(0, self.refresh_header)

    def refresh_header(self) -> None:
        configure_table_header(self.table, self._stretch_columns, self._min_rows)

    def add_action(self, text: str, slot=None) -> QPushButton:
        """Append a button to the block (row by row) and return it."""
        button = QPushButton(text)
        if slot is not None:
            button.clicked.connect(slot)
        row, col = divmod(len(self._button_list), self._button_columns)
        self._buttons.addWidget(button, row, col)
        self._button_list.append(button)
        return button

    @property
    def buttons(self) -> list[QPushButton]:
        return list(self._button_list)
