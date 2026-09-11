"""T-H1: MDA plan rebuilds from GUI edits are debounced.

`get_MDA_events_from_GUI` was wired straight to 17 widget signals, 9 of them
`textChanged`, which fires per character. Every call built a `useq.MDASequence`,
materialised it with `to_pycromanager()` (one validated dict per frame), made a
hardware `set_focus_device()` call and rewrote the whole `glados_state.json`.
Typing "100000" time points did all of that six times over.

These tests pin: one rebuild per burst of edits, an immediate rebuild when a
line edit loses focus or an acquisition starts, synchronous rebuilds during
construction (unchanged), and a state write decoupled from the rebuild.
"""
from __future__ import annotations

import inspect
import os
import re

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


def _settle(timer, timeout_ms=3000):
    from PyQt5.QtCore import QCoreApplication, QElapsedTimer, QEventLoop

    clock = QElapsedTimer()
    clock.start()
    while timer is not None and timer.isActive() and clock.elapsed() < timeout_ms:
        QCoreApplication.processEvents(QEventLoop.AllEvents, 20)
    QCoreApplication.processEvents(QEventLoop.AllEvents, 20)


@pytest.fixture
def host(mda_cls, qapp):
    """A QObject carrying the real debounce methods over recording stand-ins."""
    from PyQt5.QtCore import QObject

    def _make(fully_started=True, autoSaveLoad=True):
        obj = type("FakeMDA", (QObject,), {})()
        obj.MDA_EVENTS_DEBOUNCE_MS = mda_cls.MDA_EVENTS_DEBOUNCE_MS
        obj.MDA_STATE_SAVE_DEBOUNCE_MS = mda_cls.MDA_STATE_SAVE_DEBOUNCE_MS
        obj.fully_started = fully_started
        obj.autoSaveLoad = autoSaveLoad
        obj.rebuilds = 0
        obj.saves = 0

        def rebuild():
            # Mirrors the real method's contract: a rebuild supersedes a
            # pending debounce, then schedules the state write.
            pending = getattr(obj, "_mdaEventsUpdateTimer", None)
            if pending is not None:
                pending.stop()
            obj.rebuilds += 1
            if obj.fully_started and obj.autoSaveLoad:
                obj._scheduleMDAStateSave()

        def save():
            obj.saves += 1

        obj.get_MDA_events_from_GUI = rebuild
        obj._saveMDAStateNow = save
        for name in (
            "scheduleMDAEventsUpdate",
            "flushMDAEventsUpdate",
            "_scheduleMDAStateSave",
            "flushMDAStateSave",
        ):
            setattr(obj, name, getattr(mda_cls, name).__get__(obj))
        return obj

    return _make


# ------------------------------------------------------------ the debounce


def test_a_burst_of_keystrokes_rebuilds_once(host):
    obj = host()
    for _ in range(6):  # "100000"
        obj.scheduleMDAEventsUpdate()
    assert obj.rebuilds == 0, "no plan rebuild while the user is still typing"

    _settle(obj._mdaEventsUpdateTimer)
    assert obj.rebuilds == 1


def test_flush_runs_a_pending_rebuild_immediately(host):
    obj = host()
    obj.scheduleMDAEventsUpdate()
    obj.flushMDAEventsUpdate()
    assert obj.rebuilds == 1
    assert not obj._mdaEventsUpdateTimer.isActive()

    _settle(obj._mdaEventsUpdateTimer)
    assert obj.rebuilds == 1, "a flushed rebuild must not fire a second time"


def test_flush_with_nothing_pending_is_a_no_op(host):
    obj = host()
    obj.flushMDAEventsUpdate()
    assert obj.rebuilds == 0
    obj.scheduleMDAEventsUpdate()
    _settle(obj._mdaEventsUpdateTimer)
    obj.flushMDAEventsUpdate()
    assert obj.rebuilds == 1


def test_rebuilds_are_synchronous_during_construction(host):
    obj = host(fully_started=False)
    obj.scheduleMDAEventsUpdate()
    assert obj.rebuilds == 1, "a freshly built panel must have its plan in place"
    assert getattr(obj, "_mdaEventsUpdateTimer", None) is None


def test_the_real_rebuild_cancels_a_pending_debounce(mda_cls):
    source = inspect.getsource(mda_cls.get_MDA_events_from_GUI)
    start = source.index("logging.debug('starting get_MDA_events_from_GUI')")
    assert source.index("_mdaEventsUpdateTimer", start) < source.index("self.exposureGroupBox")
    assert "pendingUpdate.stop()" in source


# ------------------------------------------------------------ the state write


def test_the_state_write_is_debounced_separately(host):
    obj = host()
    for _ in range(5):
        obj.scheduleMDAEventsUpdate()
        obj.flushMDAEventsUpdate()
    assert obj.rebuilds == 5
    assert obj.saves == 0, "the JSON write is not coupled to each rebuild"

    _settle(obj._mdaStateSaveTimer)
    assert obj.saves == 1


def test_flushing_the_state_write(host):
    obj = host()
    obj.flushMDAStateSave()
    assert obj.saves == 0
    obj._scheduleMDAStateSave()
    obj.flushMDAStateSave()
    assert obj.saves == 1
    assert not obj._mdaStateSaveTimer.isActive()


def test_no_state_write_without_autosave(host):
    obj = host(autoSaveLoad=False)
    obj.scheduleMDAEventsUpdate()
    obj.flushMDAEventsUpdate()
    assert getattr(obj, "_mdaStateSaveTimer", None) is None


def test_the_rebuild_no_longer_writes_the_file_inline(mda_cls):
    source = inspect.getsource(mda_cls.get_MDA_events_from_GUI)
    assert "save_state_MDA" not in source
    assert "self._scheduleMDAStateSave()" in source


def test_the_timers_are_not_persisted(qapp):
    from glados_pycromanager.GUI import utils

    exclusions = utils.CustomMainWindow().storingExceptions
    assert "_mdaEventsUpdateTimer" in exclusions
    assert "_mdaStateSaveTimer" in exclusions


# ------------------------------------------------------------ the wiring


def test_no_signal_calls_the_rebuild_directly(mda_mod):
    source = inspect.getsource(mda_mod)
    assert not re.search(r"\.connect\(lambda: self(\.parent)?\.get_MDA_events_from_GUI\(\)\)", source)
    assert len(re.findall(r"\.connect\(lambda: self(\.parent)?\.scheduleMDAEventsUpdate\(\)\)", source)) == 18


def test_every_debounced_line_edit_flushes_on_editing_finished(mda_mod):
    source = inspect.getsource(mda_mod)
    edited = set(re.findall(r"self\.(\w+)\.textChanged\.connect\(lambda: self\.scheduleMDAEventsUpdate\(\)\)", source))
    flushed = set(re.findall(r"self\.(\w+)\.editingFinished\.connect\(self\.flushMDAEventsUpdate\)", source))
    assert len(edited) == 9
    assert edited == flushed


@pytest.mark.parametrize("method", ["MDA_acq_from_GUI", "MDA_acq_from_Node"])
def test_acquisition_applies_pending_edits_before_reading_the_plan(mda_cls, method):
    source = inspect.getsource(getattr(mda_cls, method))
    assert source.index("self.flushMDAEventsUpdate()") < source.index("_mdaModeParams = self.mda")


def test_get_events_applies_pending_edits(mda_cls):
    source = inspect.getsource(mda_cls.getEvents)
    assert source.index("self.flushMDAEventsUpdate()") < source.index("return self.mda")
