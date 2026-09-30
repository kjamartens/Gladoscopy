"""A table with a column of action buttons beside it, top-aligned with the table.

Used for the XY position list and the channel list. The table keeps its own
class (and every method callers use on it); `ListEditor` only owns the
arrangement and the header sizing:

- text columns stretch, numeric columns size to their contents;
- no column can shrink below its header text (the channel list's column 0
  was a fixed 54 px, which clipped "Channel Setting" to "annel Setti");
- the table is at least `Theme.table_min_rows` rows tall instead of a fixed
  240 px, and grows with the section.
"""
from __future__ import annotations

from PyQt5.QtWidgets import (
    QHBoxLayout,
    QHeaderView,
    QPushButton,
    QSizePolicy,
    QTableWidget,
    QVBoxLayout,
    QWidget,
)

from glados_pycromanager.ui.layout.theme import current_theme


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
        mode = QHeaderView.Stretch if col in stretch_columns else QHeaderView.ResizeToContents
        header.setSectionResizeMode(col, mode)
        min_width += header.sectionSizeHint(col)
    vertical = table.verticalHeader()
    frame = 2 * table.frameWidth()
    vheader_width = vertical.sizeHint().width() if vertical.isVisible() else 0
    table.setMinimumWidth(min_width + vheader_width + frame)
    table.setMinimumHeight(header.sizeHint().height() + min_rows * vertical.defaultSectionSize() + frame)
    table.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)


class ListEditor(QWidget):
    """`table` on the left, a vertical column of buttons on its right."""

    def __init__(self, table: QTableWidget, stretch_columns=None, parent: QWidget | None = None):
        super().__init__(parent)
        self.table = table
        self._stretch_columns = stretch_columns
        spacing = current_theme().section_spacing_px
        row = QHBoxLayout(self)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(spacing)
        row.addWidget(table, 1)
        self._buttons = QVBoxLayout()
        self._buttons.setContentsMargins(0, 0, 0, 0)
        self._buttons.setSpacing(spacing)
        self._buttons.addStretch(1)
        row.addLayout(self._buttons)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.refresh_header()

    def refresh_header(self) -> None:
        configure_table_header(self.table, self._stretch_columns)

    def add_action(self, text: str, slot=None) -> QPushButton:
        """Append a button to the column (above the trailing stretch) and return it."""
        button = QPushButton(text)
        if slot is not None:
            button.clicked.connect(slot)
        self._buttons.insertWidget(self._buttons.count() - 1, button)
        return button

    @property
    def buttons(self) -> list[QPushButton]:
        return [self._buttons.itemAt(i).widget() for i in range(self._buttons.count())
                if self._buttons.itemAt(i).widget() is not None]
