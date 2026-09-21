"""ResponsiveGrid: sections are placed per shape bucket and never recreated.

The MDA and Controls docks register their sections once; resizing between the
four `classify_shape` buckets, or hiding a section, only moves existing widgets.
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


@pytest.fixture
def grid(qapp):
    from PyQt5.QtWidgets import QLabel

    from glados_pycromanager.ui.layout.responsive import TALL, WIDE, Placement, ResponsiveGrid

    g = ResponsiveGrid()
    for key in ("top", "a", "b", "c"):
        g.register(key, QLabel(key))
    g.set_placements(
        {
            WIDE: [Placement("top", 0, 0, 1, 3), Placement("a", 1, 0), Placement("b", 1, 1), Placement("c", 1, 2)],
            TALL: [Placement("top", 0, 0), Placement("a", 1, 0), Placement("b", 2, 0), Placement("c", 3, 0)],
        },
        column_stretch={WIDE: {"b": 2}},
    )
    return g


def test_classify_shape_buckets():
    from glados_pycromanager.ui.layout.responsive import classify_shape

    assert classify_shape(400, 100) == ('rows', 1)
    assert classify_shape(100, 400) == ('columns', 1)
    assert classify_shape(110, 100) == ('rows', 2)
    assert classify_shape(100, 110) == ('columns', 2)


def test_apply_places_per_bucket(grid):
    from glados_pycromanager.ui.layout.responsive import TALL, WIDE

    grid.apply(WIDE)
    assert grid.position_of("top") == (0, 0, 1, 3)
    assert grid.position_of("c") == (1, 2, 1, 1)
    grid.apply(TALL)
    assert grid.position_of("c") == (3, 0, 1, 1)
    assert grid.bucket == TALL


def test_unknown_bucket_falls_back_to_default(grid):
    from glados_pycromanager.ui.layout.responsive import LANDSCAPE

    grid.apply(LANDSCAPE)
    assert grid.position_of("c") == (1, 2, 1, 1)


def test_apply_creates_no_widgets_and_is_idempotent(grid):
    from PyQt5.QtWidgets import QWidget

    from glados_pycromanager.ui.layout.responsive import TALL, WIDE

    grid.apply(WIDE)
    before = set(map(id, grid.findChildren(QWidget)))
    for bucket in (TALL, WIDE) * 20:
        grid.apply(bucket)
    assert set(map(id, grid.findChildren(QWidget))) == before
    assert grid.apply(WIDE) is False


def test_hidden_sections_close_ranks(grid):
    from glados_pycromanager.ui.layout.responsive import TALL, WIDE

    grid.apply(WIDE)
    grid.set_hidden({"b"})
    assert grid.position_of("b") is None
    assert grid.position_of("c") == (1, 1, 1, 1)       # moved left into b's column
    assert grid.position_of("top") == (0, 0, 1, 2)     # span shrinks with it
    assert grid.widget_for("b").isHidden()
    grid.apply(TALL)
    assert grid.position_of("c") == (2, 0, 1, 1)       # moved up into b's row
    grid.set_hidden(())
    assert not grid.widget_for("b").isHidden()
    assert grid.position_of("c") == (3, 0, 1, 1)


def test_column_stretch_follows_the_section(grid):
    from glados_pycromanager.ui.layout.responsive import WIDE

    grid.apply(WIDE)
    assert grid._grid.columnStretch(1) == 2
    grid.set_hidden({"a"})
    assert grid._grid.columnStretch(0) == 2           # b is now column 0
