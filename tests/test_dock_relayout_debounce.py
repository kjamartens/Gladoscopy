"""T-F6: the dock relayout must not run per pixel, and must not leak scroll areas.

`GladosWidget.resizeEvent` called `set_groupBoxLayout`, which removes every widget
from the layout, `setParent(None)`s them, builds a **brand-new QScrollArea plus
container plus QGridLayout**, re-adds everything and forces a full layout pass via
`minimumSizeHint()`. That ran on every QResizeEvent -- i.e. every pixel of a
splitter drag -- and the previous QScrollArea was orphaned and never destroyed, so
each resize leaked one.

These tests pin the coalescing contract (one rebuild per settled drag, none at all
when the orientation bucket is unchanged) and the release of the replaced scroll
area. They drive the scheduling methods directly rather than a real napari dock.
"""
from __future__ import annotations

import os

import pytest

pytest.importorskip("PyQt5.QtWidgets")


@pytest.fixture(scope="module")
def qapp():
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from PyQt5.QtCore import QCoreApplication, Qt
    from PyQt5.QtWidgets import QApplication

    QCoreApplication.setAttribute(Qt.AA_ShareOpenGLContexts, True)
    return QApplication.instance() or QApplication([])


@pytest.fixture(scope="module")
def dock_mod(qapp):
    import glados_pycromanager._dock_widget as dock_widget

    return dock_widget


@pytest.fixture(scope="module")
def glados_widget_cls(dock_mod):
    return dock_mod.GladosWidget


@pytest.fixture
def scheduler(glados_widget_cls, qapp):
    """A bare object carrying the real scheduling methods, recording rebuilds."""
    from PyQt5.QtCore import QTimer

    def _make():
        obj = type("FakeDock", (), {})()
        obj.RELAYOUT_DEBOUNCE_MS = glados_widget_cls.RELAYOUT_DEBOUNCE_MS
        obj.rebuilds = []
        obj.set_groupBoxLayout = lambda rowsOrColumns='rows', n_items=1: (
            obj.rebuilds.append((rowsOrColumns, n_items))
        )
        obj._pendingLayout = None
        obj._appliedLayout = None
        obj._relayoutTimer = QTimer()
        obj._relayoutTimer.setSingleShot(True)
        for name in ("_scheduleGroupBoxLayout", "_applyPendingLayout"):
            setattr(obj, name, getattr(glados_widget_cls, name).__get__(obj))
        obj._relayoutTimer.timeout.connect(obj._applyPendingLayout)
        return obj

    return _make


def _settle(qapp, widget, timeout_ms=1500):
    """Spin the event loop until the debounce timer has fired."""
    from PyQt5.QtCore import QCoreApplication, QEventLoop, QElapsedTimer

    clock = QElapsedTimer()
    clock.start()
    while widget._relayoutTimer.isActive() and clock.elapsed() < timeout_ms:
        QCoreApplication.processEvents(QEventLoop.AllEvents, 20)
    QCoreApplication.processEvents(QEventLoop.AllEvents, 20)


# ------------------------------------------------------------- the debounce


def test_a_drag_produces_one_rebuild(scheduler, qapp):
    w = scheduler()
    # 200 resize events alternating between two orientation buckets, as a
    # splitter drag across the square aspect ratio would deliver.
    for i in range(200):
        w._scheduleGroupBoxLayout(("rows", 2) if i % 2 else ("columns", 2))
    assert w.rebuilds == [], "nothing rebuilds while the drag is in flight"

    _settle(qapp, w)
    assert len(w.rebuilds) == 1, "a settled drag costs exactly one rebuild"


def test_the_last_orientation_wins(scheduler, qapp):
    w = scheduler()
    w._scheduleGroupBoxLayout(("rows", 1))
    w._scheduleGroupBoxLayout(("columns", 2))
    w._scheduleGroupBoxLayout(("rows", 2))
    _settle(qapp, w)
    assert w.rebuilds == [("rows", 2)]


def test_an_unchanged_orientation_costs_nothing(scheduler, qapp):
    """Most resize events during a drag stay in the same bucket."""
    w = scheduler()
    w._scheduleGroupBoxLayout(("rows", 1))
    _settle(qapp, w)
    assert w.rebuilds == [("rows", 1)]

    for _ in range(500):
        w._scheduleGroupBoxLayout(("rows", 1))
    assert not w._relayoutTimer.isActive(), "no timer armed for a no-op layout"
    _settle(qapp, w)
    assert len(w.rebuilds) == 1, "identical layout must not rebuild anything"


def test_a_later_genuine_change_still_rebuilds(scheduler, qapp):
    w = scheduler()
    w._scheduleGroupBoxLayout(("rows", 1))
    _settle(qapp, w)
    w._scheduleGroupBoxLayout(("columns", 1))
    _settle(qapp, w)
    assert w.rebuilds == [("rows", 1), ("columns", 1)]


def test_applied_layout_tracks_what_was_built(scheduler, qapp):
    w = scheduler()
    w._scheduleGroupBoxLayout(("columns", 2))
    _settle(qapp, w)
    assert w._appliedLayout == ("columns", 2)
    assert w._pendingLayout is None


def test_draining_with_nothing_pending_is_a_no_op(scheduler):
    w = scheduler()
    w._applyPendingLayout()
    assert w.rebuilds == []


def test_a_resize_before_init_falls_back_to_a_direct_rebuild(scheduler):
    """A QResizeEvent can arrive before __init__ has built the timer."""
    w = scheduler()
    w._relayoutTimer = None
    w._scheduleGroupBoxLayout(("rows", 1))
    assert w.rebuilds == [("rows", 1)]


def test_resize_event_classifies_sizes_the_same_way(glados_widget_cls, qapp):
    """The four aspect-ratio buckets must be unchanged by the refactor."""
    import inspect

    source = inspect.getsource(glados_widget_cls.resizeEvent)
    assert "width > height * 1.25" in source and "('rows', 1)" in source
    assert "height > width * 1.25" in source and "('columns', 1)" in source
    assert "('rows', 2)" in source and "('columns', 2)" in source
    assert "_scheduleGroupBoxLayout" in source


# ---------------------------------------------------------- the scroll area


def test_replaced_scroll_area_is_released(glados_widget_cls):
    import inspect

    source = inspect.getsource(glados_widget_cls.set_groupBoxLayout)
    assert "deleteLater()" in source, "the orphaned QScrollArea must be destroyed"
    assert "isinstance(widget, QScrollArea)" in source, (
        "only the scroll area is ours to destroy; a live control must not be"
    )


def test_scroll_area_deletion_actually_destroys_it(qapp, dock_mod):
    """Qt must really collect a deleteLater()'d, orphaned scroll area."""
    import sip
    from PyQt5.QtCore import QCoreApplication, QEvent
    from PyQt5.QtWidgets import QScrollArea, QWidget

    area = QScrollArea()
    area.setWidget(QWidget())
    area.setParent(None)
    area.deleteLater()

    # DeferredDelete events are only dispatched at the event-loop level they
    # were posted from, so ask for them by type rather than pumping generally.
    QCoreApplication.sendPostedEvents(None, QEvent.DeferredDelete)

    assert sip.isdeleted(area), "deleteLater must reclaim the orphaned scroll area"
