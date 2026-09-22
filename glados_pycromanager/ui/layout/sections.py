"""Section boxes, aligned form rows and a wrapping row: the toolkit's building blocks.

- `Section` is a titled box with a stable `key` (e.g. ``"mda.z"``). The key is
  how a `ResponsiveGrid` places it and how a future "hidden sections" setting
  names it.
- `FormGrid` is a three-column grid: label | field (stretches) | trailing widget
  (a unit dropdown, a "Set" or "..." button). Every form-style section uses it,
  so rows line up the same way everywhere.
- `FlowRow` wraps its children onto more lines when narrow, e.g. a strip of
  checkboxes that needs one line in a wide dock and two in a narrow one.
"""
from __future__ import annotations

from PyQt5.QtCore import QPoint, QRect, QSize, Qt
from PyQt5.QtWidgets import (
    QGridLayout,
    QGroupBox,
    QLabel,
    QLayout,
    QSizePolicy,
    QSpacerItem,
    QWidget,
)

from glados_pycromanager.ui.layout.theme import ROLE_SECTION, current_theme, set_role


def apply_section_spacing(layout: QLayout, margins: bool = True, title_px: int = 0) -> None:
    """Give `layout` the theme's inner spacing (and margins, unless `margins=False`).

    `title_px` is extra room above the body for a group-box title: the theme's
    stylesheet zeroes QGroupBox padding, so nothing else reserves it.
    """
    t = current_theme()
    layout.setSpacing(t.section_spacing_px)
    m = t.section_margin_px if margins else 0
    layout.setContentsMargins(m, m + title_px, m, m)


class Section(QGroupBox):
    """A titled box of related controls.

    `set_active(False)` greys the whole section out; it is `setEnabled`, so code
    that reads `isEnabled()` to decide whether a dimension takes part keeps
    working. Hiding a section is not done here but by the `ResponsiveGrid` that
    places it, so the remaining sections close ranks.
    """

    def __init__(self, title: str, key: str, layout: QLayout | None = None, parent: QWidget | None = None):
        super().__init__(title, parent)
        self.key = key
        set_role(self, ROLE_SECTION)
        if layout is None:
            layout = FormGrid()
        apply_section_spacing(layout, title_px=current_theme().font_px + 2 if title else 0)
        self.setLayout(layout)

    @property
    def body(self) -> QLayout:
        return self.layout()

    def set_active(self, active: bool) -> None:
        self.setEnabled(bool(active))


class FormGrid(QGridLayout):
    """label | field | trailing, one row per setting; the field column stretches."""

    LABEL, FIELD, TRAILING = 0, 1, 2

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self.setColumnStretch(self.FIELD, 1)
        self._next_row = 0

    @property
    def row_count(self) -> int:
        return self._next_row

    def add_row(self, label, field=None, trailing=None) -> int:
        """Add one row and return its index.

        `label` is a string (a `QLabel` is made for it), a widget, or None.
        `field` and `trailing` are widgets or layouts. With no trailing item the
        field spans into the trailing column, so a lone field is as wide as a
        field plus button in the rows around it.
        """
        row = self._next_row
        if label is not None:
            if isinstance(label, str):
                label = QLabel(label)
            self.addWidget(label, row, self.LABEL)
        if field is not None:
            span = 1 if trailing is not None else 2
            self._add(field, row, self.FIELD, 1, span)
        if trailing is not None:
            self._add(trailing, row, self.TRAILING, 1, 1)
        self._next_row += 1
        return row

    def add_full_row(self, item) -> int:
        """A widget or layout across all three columns."""
        row = self._next_row
        self._add(item, row, 0, 1, 3)
        self._next_row += 1
        return row

    def add_stretch(self) -> None:
        """Absorb spare height below the last row, so the rows stay at the top."""
        self.addItem(QSpacerItem(0, 0, QSizePolicy.Minimum, QSizePolicy.Expanding), self._next_row, 0, 1, 3)
        self.setRowStretch(self._next_row, 1)
        self._next_row += 1

    def _add(self, item, row, col, rowspan, colspan):
        if isinstance(item, QLayout):
            self.addLayout(item, row, col, rowspan, colspan)
        else:
            self.addWidget(item, row, col, rowspan, colspan)


class FlowLayout(QLayout):
    """Lays its items out left to right, wrapping onto a new line when out of width."""

    def __init__(self, parent: QWidget | None = None, spacing: int | None = None):
        super().__init__(parent)
        self._items = []
        self.setContentsMargins(0, 0, 0, 0)
        self.setSpacing(current_theme().section_spacing_px if spacing is None else spacing)

    def addItem(self, item):  # noqa: N802 -- Qt override
        self._items.append(item)

    def count(self):
        return len(self._items)

    def itemAt(self, index):  # noqa: N802
        return self._items[index] if 0 <= index < len(self._items) else None

    def takeAt(self, index):  # noqa: N802
        return self._items.pop(index) if 0 <= index < len(self._items) else None

    def expandingDirections(self):  # noqa: N802
        return Qt.Orientations(0)

    def hasHeightForWidth(self):  # noqa: N802
        return True

    def heightForWidth(self, width):  # noqa: N802
        return self._do_layout(QRect(0, 0, width, 0), test_only=True)

    def setGeometry(self, rect):  # noqa: N802
        super().setGeometry(rect)
        self._do_layout(rect, test_only=False)

    def sizeHint(self):  # noqa: N802
        # One line: as wide as everything side by side.
        width = sum(i.sizeHint().width() for i in self._items) + self.spacing() * max(len(self._items) - 1, 0)
        height = max((i.sizeHint().height() for i in self._items), default=0)
        m = self.contentsMargins()
        return QSize(width + m.left() + m.right(), height + m.top() + m.bottom())

    def minimumSize(self):  # noqa: N802
        size = QSize()
        for item in self._items:
            size = size.expandedTo(item.minimumSize())
        m = self.contentsMargins()
        return size + QSize(m.left() + m.right(), m.top() + m.bottom())

    def _do_layout(self, rect, test_only):
        m = self.contentsMargins()
        area = rect.adjusted(m.left(), m.top(), -m.right(), -m.bottom())
        x, y, line_height = area.x(), area.y(), 0
        spacing = self.spacing()
        for item in self._items:
            hint = item.sizeHint()
            next_x = x + hint.width() + spacing
            if next_x - spacing > area.right() + 1 and line_height > 0:
                x = area.x()
                y = y + line_height + spacing
                next_x = x + hint.width() + spacing
                line_height = 0
            if not test_only:
                item.setGeometry(QRect(QPoint(x, y), hint))
            x = next_x
            line_height = max(line_height, hint.height())
        return y + line_height - rect.y() + m.bottom()


class FlowRow(QWidget):
    """A widget whose children wrap onto more lines when it is narrow."""

    def __init__(self, widgets=(), parent: QWidget | None = None):
        super().__init__(parent)
        self.flow = FlowLayout(self)
        for widget in widgets:
            self.flow.addWidget(widget)
        policy = QSizePolicy(QSizePolicy.Preferred, QSizePolicy.Preferred)
        policy.setHeightForWidth(True)
        self.setSizePolicy(policy)

    def add(self, widget: QWidget) -> None:
        self.flow.addWidget(widget)
