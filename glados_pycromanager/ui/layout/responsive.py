"""Place sections according to the dock's shape, without ever recreating them.

A panel registers its sections once under stable keys and declares, per shape
bucket, where each goes (`Placement`). `ResponsiveGrid.apply(bucket)` moves the
existing widgets into that arrangement; nothing is constructed or destroyed, so
signal connections and widget state survive any number of relayouts.

The buckets are the four `classify_shape` returns. Both hosts use it: the
standalone dock (`MDAGlados.handleSizeChange`) and the napari-plugin
`GladosWidget`.

`set_hidden(keys)` removes sections from the arrangement; rows and columns left
empty close up. It is the hook for a future "hidden sections" layout setting.
"""
from __future__ import annotations

from typing import NamedTuple

from PyQt5.QtWidgets import QGridLayout, QWidget

from glados_pycromanager.ui.layout.theme import current_theme

WIDE = ('rows', 1)
LANDSCAPE = ('rows', 2)
PORTRAIT = ('columns', 2)
TALL = ('columns', 1)
ALL_BUCKETS = (WIDE, LANDSCAPE, PORTRAIT, TALL)


def classify_shape(width, height):
    """Which arrangement suits a `width` x `height` area."""
    if width > height * 1.25:
        return ('rows', 1)      # Wide
    elif height > width * 1.25:
        return ('columns', 1)   # Tall
    elif width > height:
        return ('rows', 2)      # Landscape
    else:
        return ('columns', 2)   # Portrait


class Placement(NamedTuple):
    key: str
    row: int
    col: int
    rowspan: int = 1
    colspan: int = 1


class ResponsiveGrid(QWidget):
    """A grid of registered widgets, arranged per shape bucket."""

    def __init__(self, parent: QWidget | None = None, default_bucket=WIDE):
        super().__init__(parent)
        self._grid = QGridLayout(self)
        self._grid.setContentsMargins(0, 0, 0, 0)
        self._grid.setSpacing(current_theme().grid_spacing_px)
        self._widgets: dict[str, QWidget] = {}
        self._placements: dict = {}
        self._column_stretch: dict = {}
        self._hidden: frozenset = frozenset()
        self._applied = None
        self._default_bucket = default_bucket
        self._stretched_rows: set[int] = set()
        self._stretched_cols: set[int] = set()

    # -- declaration -------------------------------------------------------
    def register(self, key: str, widget: QWidget) -> QWidget:
        self._widgets[key] = widget
        widget.setParent(self)
        widget.hide()   # shown once placed
        self._applied = None
        return widget

    def set_placements(self, placements: dict, column_stretch: dict | None = None) -> None:
        """`placements`: {bucket: [Placement, ...]}; `column_stretch`: {bucket: {key: stretch}}.

        Stretch is given per *section key*, not per column index, so it follows
        the section when hidden sections make columns close up.
        """
        self._placements = dict(placements)
        self._column_stretch = dict(column_stretch or {})
        self._applied = None

    def set_hidden(self, keys) -> None:
        self._hidden = frozenset(k for k in keys if k)
        if self._applied is not None:
            bucket = self._applied[0]
            self._applied = None
            self.apply(bucket)

    # -- queries -----------------------------------------------------------
    @property
    def bucket(self):
        return self._applied[0] if self._applied is not None else None

    @property
    def hidden(self) -> frozenset:
        return self._hidden

    def widget_for(self, key: str) -> QWidget:
        return self._widgets[key]

    def position_of(self, key: str):
        """(row, col, rowspan, colspan) of a placed widget, or None."""
        widget = self._widgets.get(key)
        index = self._grid.indexOf(widget) if widget is not None else -1
        return None if index < 0 else self._grid.getItemPosition(index)

    # -- arranging ---------------------------------------------------------
    def apply(self, bucket=None) -> bool:
        """Arrange for `bucket` (default: the current one, else the default). True if anything moved."""
        if bucket is None:
            bucket = self.bucket or self._default_bucket
        state = (bucket, self._hidden)
        if state == self._applied:
            return False
        placements = self._placements.get(bucket) or self._placements.get(self._default_bucket) or []
        visible = [p for p in placements if p.key in self._widgets and p.key not in self._hidden]

        for widget in self._widgets.values():
            self._grid.removeWidget(widget)
        for r in self._stretched_rows:
            self._grid.setRowStretch(r, 0)
        for c in self._stretched_cols:
            self._grid.setColumnStretch(c, 0)
        self._stretched_rows, self._stretched_cols = set(), set()

        rows = _Axis([(p.row, p.rowspan) for p in visible])
        cols = _Axis([(p.col, p.colspan) for p in visible])
        stretch = self._column_stretch.get(bucket, {})
        placed = set()
        for p in visible:
            row, rowspan = rows.map(p.row, p.rowspan)
            col, colspan = cols.map(p.col, p.colspan)
            widget = self._widgets[p.key]
            self._grid.addWidget(widget, row, col, rowspan, colspan)
            placed.add(p.key)
            if p.key in stretch and colspan == 1:
                self._grid.setColumnStretch(col, stretch[p.key])
                self._stretched_cols.add(col)
        for key, widget in self._widgets.items():
            widget.setVisible(key in placed)

        # Spare space goes below and to the right of the arrangement unless a
        # section asked for it, so sections keep their natural size.
        self._grid.setRowStretch(rows.count, 1)
        self._stretched_rows.add(rows.count)
        if not self._stretched_cols:
            self._grid.setColumnStretch(cols.count, 1)
            self._stretched_cols.add(cols.count)

        self._applied = state
        return True


class _Axis:
    """Closes up the rows (or columns) that no visible placement uses.

    Single-cell placements decide which indices are in use. A spanning placement
    (e.g. a full-width bar) then covers whichever used indices fall inside its
    span, so it shrinks with them rather than holding a hidden section's column
    open; one that covers no used index keeps a single cell of its own.
    """

    def __init__(self, spans):
        used = {start for start, span in spans if span == 1}
        for start, span in spans:
            if span > 1 and not any(start <= i < start + span for i in used):
                used.add(start)
        self._used = sorted(used)
        self._index = {old: new for new, old in enumerate(self._used)}

    @property
    def count(self) -> int:
        return len(self._used)

    def map(self, start, span):
        inside = [self._index[i] for i in self._used if start <= i < start + span]
        return inside[0], inside[-1] - inside[0] + 1
