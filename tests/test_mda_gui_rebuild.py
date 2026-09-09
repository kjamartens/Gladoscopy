"""T-F7: rebuilding the MDA GUI must not pump the event loop or leak widgets.

`updateGUIwidgets` tore down and rebuilt seven group boxes, then **synthesised a
QEvent.Resize and sent it**, then called `QCoreApplication.processEvents()`.
Pumping the event loop from inside a widget-tree rebuild allows re-entrant
delivery of `showOptionChanged` / `currentTextChanged` straight back into
`updateGUIwidgets`, and can run `napariUpdateLive` slots mid-rebuild. It also
constructed a **new QPushButton("Acquire") on every call**, leaking the previous
one's connections.

These tests pin the replacements: a zero-delay singleShot relayout request, one
Acquire button for the life of the object, and the previous rebuild's wrapper
widgets being discarded rather than stacked in the same grid cells.
"""
from __future__ import annotations

import inspect
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
def mda_mod(qapp):
    import glados_pycromanager.Core.MDAGlados as MDAGlados

    return MDAGlados


@pytest.fixture(scope="module")
def mda_cls(mda_mod):
    return mda_mod.MDAGlados


@pytest.fixture(scope="module")
def dock_cls(qapp):
    import glados_pycromanager._dock_widget as dock_widget

    return dock_widget.GladosWidget


# ------------------------------------------------ no re-entrant event pumping


def test_no_synthetic_resize_and_no_process_events(mda_cls):
    source = inspect.getsource(mda_cls.updateGUIwidgets)
    body = "\n".join(
        line for line in source.splitlines() if not line.strip().startswith("#")
    )
    assert "processEvents()" not in body, (
        "pumping the event loop mid-rebuild allows re-entrant updateGUIwidgets"
    )
    assert "sendEvent" not in body, "the synthetic QEvent.Resize must be gone"
    assert "QEvent(QEvent.Resize)" not in body


def test_relayout_is_deferred_not_immediate(mda_cls):
    source = inspect.getsource(mda_cls.updateGUIwidgets)
    assert "QTimer.singleShot(0," in source, (
        "a deferred relayout replaces the synthetic resize"
    )
    assert "requestRelayout" in source


def test_the_gui_update_call_is_kept(mda_cls):
    """The task's Don't: keep self.gui.update()."""
    assert "self.gui.update()" in inspect.getsource(mda_cls.updateGUIwidgets)


def test_dead_qt_imports_were_dropped(mda_mod):
    """`QApplication`, `QCoreApplication` and `QEvent` had no other user here."""
    for name in ("QApplication", "QCoreApplication", "QEvent"):
        assert not hasattr(mda_mod, name), "%s is no longer used" % name


# --------------------------------------------------------- the parent's seam


def test_dock_exposes_request_relayout(dock_cls):
    assert callable(dock_cls.requestRelayout)


def test_request_relayout_forces_a_rebuild_at_an_unchanged_size(dock_cls, qapp):
    """The whole point: same geometry, changed widget tree."""
    from PyQt5.QtCore import QTimer

    obj = type("FakeDock", (), {})()
    obj.type = "MDA"
    obj.RELAYOUT_DEBOUNCE_MS = dock_cls.RELAYOUT_DEBOUNCE_MS
    obj._pendingLayout = None
    obj._appliedLayout = ("rows", 1)
    obj._relayoutTimer = QTimer()
    obj._relayoutTimer.setSingleShot(True)
    obj._layoutForCurrentSize = lambda: ("rows", 1)
    obj.set_groupBoxLayout = lambda **kw: None
    for name in ("_scheduleGroupBoxLayout", "requestRelayout"):
        setattr(obj, name, getattr(dock_cls, name).__get__(obj))

    # A plain resize at the same size is dropped ...
    obj._scheduleGroupBoxLayout(("rows", 1))
    assert not obj._relayoutTimer.isActive()

    # ... but an explicit request is not.
    obj.requestRelayout()
    assert obj._relayoutTimer.isActive()
    assert obj._pendingLayout == ("rows", 1)
    obj._relayoutTimer.stop()


def test_request_relayout_is_a_no_op_for_autonomous_microscopy(dock_cls):
    """resizeEvent excludes those two types; the explicit request must too."""
    for widget_type in (None, "AutonomousMicroscopy"):
        obj = type("FakeDock", (), {})()
        obj.type = widget_type
        obj._appliedLayout = ("rows", 1)
        obj.requestRelayout = dock_cls.requestRelayout.__get__(obj)
        obj.requestRelayout()
        assert obj._appliedLayout == ("rows", 1), "must not touch the layout"


# ------------------------------------------------------- the Acquire button


def test_acquire_button_is_built_once(mda_cls, qapp):
    """Reuse is keyed on a dedicated handle, not on GUI_acquire_button."""
    source = inspect.getsource(mda_cls.updateGUIwidgets)
    assert source.count('QPushButton("Acquire")') == 1
    assert "getattr(self, '_acquireButton', None) is None" in source


def test_gui_acquire_button_flag_is_not_used_as_the_built_test(mda_cls):
    """It holds a bool from __init__ before it ever holds the widget."""
    init_source = inspect.getsource(mda_cls.__init__)
    assert "self.GUI_acquire_button = GUI_acquire_button" in init_source, (
        "the attribute really does start out as the boolean flag"
    )


def test_reused_button_keeps_a_single_connection(qapp):
    """Rebuilding must not stack another `clicked` connection on the button."""
    from PyQt5.QtWidgets import QPushButton, QVBoxLayout, QWidget

    clicks = []
    button = QPushButton("Acquire")
    button.clicked.connect(lambda _: clicks.append(1))

    # Three rebuilds: re-parent into a fresh wrapper each time, as the code does.
    for _ in range(3):
        button.setParent(None)
        wrapper = QWidget()
        layout = QVBoxLayout()
        wrapper.setLayout(layout)
        layout.addWidget(button)

    button.click()
    assert clicks == [1], "one connection, one handler call"


# --------------------------------------------------------- wrapper lifetimes


def test_previous_wrappers_are_discarded(mda_cls):
    assert hasattr(mda_cls, "_discardPreviousGUIWrappers")
    source = inspect.getsource(mda_cls._discardPreviousGUIWrappers)
    assert "removeWidget" in source and "deleteLater()" in source

    rebuild = inspect.getsource(mda_cls.updateGUIwidgets)
    assert "self._discardPreviousGUIWrappers()" in rebuild
    assert "self._guiWrappers = [" in rebuild


def test_discard_is_safe_on_the_first_rebuild(mda_cls):
    """Nothing has been built yet, so there is nothing to remove."""
    obj = type("FakeMDA", (), {})()
    removed = []
    obj.gui = type("G", (), {"removeWidget": lambda self, w: removed.append(w)})()
    mda_cls._discardPreviousGUIWrappers(obj)
    assert removed == []
    assert obj._guiWrappers == []


def test_discard_survives_an_already_destroyed_wrapper(mda_cls):
    """Qt may have collected a wrapper before we get to it."""

    class _Dead:
        def setParent(self, _):
            raise RuntimeError("wrapped C/C++ object has been deleted")

        def deleteLater(self):
            raise AssertionError("must not be reached")

    obj = type("FakeMDA", (), {})()
    obj.gui = type("G", (), {"removeWidget": lambda self, w: None})()
    obj._guiWrappers = [_Dead()]
    mda_cls._discardPreviousGUIWrappers(obj)
    assert obj._guiWrappers == []
