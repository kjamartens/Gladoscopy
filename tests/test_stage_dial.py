"""StageDial: which ring/direction a point hits, and what a click emits."""
import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PyQt5.QtCore import QPointF, Qt
from PyQt5.QtWidgets import QApplication

from glados_pycromanager.ui.widgets.stage_dial import DIRECTIONS, RINGS, StageDial


@pytest.fixture(scope="module")
def dial():
    app = QApplication.instance() or QApplication([])  # noqa: F841 -- keep referenced
    d = StageDial()
    d.resize(d.sizeHint())
    yield d
    del app


def test_every_segment_centre_maps_back_to_itself(dial):
    for direction in range(len(DIRECTIONS)):
        for ring in range(1, RINGS + 1):
            assert dial.segment_at(dial.segment_center(direction, ring)) == (direction, ring)


def test_hub_and_outside_hit_nothing(dial):
    c = QPointF(dial.width() / 2, dial.height() / 2)
    assert dial.segment_at(c) is None
    assert dial.segment_at(QPointF(0, 0)) is None  # corner, outside the outer ring


def test_click_emits_direction_and_ring(dial):
    from PyQt5.QtTest import QTest

    got = []
    dial.stepRequested.connect(lambda dx, dy, size: got.append((dx, dy, size)))
    up, left = 1, 2
    for direction, ring in ((up, 1), (left, 3)):
        QTest.mouseClick(dial, Qt.LeftButton, pos=dial.segment_center(direction, ring).toPoint())
    assert got == [(0, 1, 1), (-1, 0, 3)]


def test_readout_is_settable_like_a_label(dial):
    dial.setText("1.0\n2.0")
    assert dial.text() == "1.0\n2.0"
