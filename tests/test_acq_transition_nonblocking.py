"""T-F10: the Live/MDA toggle must not freeze the GUI thread.

`acqModeChanged`'s start path waits up to `ACQ_STOP_TIMEOUT_S` (10 s) on
`_worker_stopped_event` before letting a new acquisition worker start -- the guard
that stops two workers driving the same native MMCore/Java engine concurrently.
That wait ran on whatever thread called it, which for a button click is the GUI
thread, so a single click could freeze the UI for ten seconds.

These tests pin that the *waiting* moved off the GUI thread while the
serialization itself did not: the guard, the lock and the timeout are all still
there, and the transition resumes on the GUI thread once the previous worker has
gone.

The two `time.sleep(0.1)` calls in the mode setters are deliberately untouched --
they were excluded at the user's request (claude_decisions.md, item H2) and
removing them needs a separate decision.
"""
from __future__ import annotations

import inspect
import os
import threading
import time

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
def napari_glados(qapp):
    import glados_pycromanager.GUI.napariGlados as napariGlados

    return napariGlados


def _pump(predicate, timeout_s=5):
    """Run the GUI event loop until `predicate()` or the timeout."""
    from PyQt5.QtCore import QCoreApplication, QElapsedTimer, QEventLoop

    clock = QElapsedTimer()
    clock.start()
    while not predicate() and clock.elapsed() < timeout_s * 1000:
        QCoreApplication.processEvents(QEventLoop.AllEvents, 10)
    return predicate()


class _FakeViewer:
    pass


@pytest.fixture
def handler(napari_glados, qapp):
    """A bare object carrying the real deferral machinery."""

    def _make(liveOrMda="live", timeout=1.0):
        from threading import Event

        obj = type("FakeHandler", (), {})()
        obj.liveOrMda = liveOrMda
        obj.ACQ_STOP_TIMEOUT_S = timeout
        obj._worker_stopped_event = Event()
        obj._transition_deferred = False
        obj.transition_signals = napari_glados._AcqTransitionSignals()

        shared = type("S", (), {})()
        shared.napariViewer = _FakeViewer()
        shared.liveMode = True
        shared.mdaMode = True
        obj.shared_data = shared

        obj.resumed = []
        obj.acqModeChanged = lambda: obj.resumed.append(
            threading.current_thread().name
        )
        obj._defer_transition_until_worker_stops = (
            napari_glados.napariHandler._defer_transition_until_worker_stops.__get__(obj)
        )
        return obj

    return _make


# ------------------------------------------------------ the wait moves off GUI


def test_the_gui_thread_returns_immediately(handler):
    """The whole point: a click must not block for ACQ_STOP_TIMEOUT_S."""
    h = handler(timeout=5.0)  # a long timeout the caller must not sit through

    started = time.monotonic()
    assert h._defer_transition_until_worker_stops() is True
    elapsed = time.monotonic() - started

    assert elapsed < 0.5, "the caller waited %.2fs; it must not wait at all" % elapsed
    h._worker_stopped_event.set()  # let the waiter finish


def test_the_transition_resumes_on_the_gui_thread(handler, qapp):
    h = handler(timeout=5.0)
    h._defer_transition_until_worker_stops()

    h._worker_stopped_event.set()
    assert _pump(lambda: bool(h.resumed))
    assert h.resumed == ["MainThread"], (
        "the continuation must run where napari and the core expect it"
    )
    assert h._transition_deferred is False


def test_started_and_finished_are_emitted(handler, qapp):
    h = handler(timeout=5.0)
    events = []
    h.transition_signals.started.connect(lambda: events.append("started"))
    h.transition_signals.finished.connect(lambda ok: events.append(("finished", ok)))

    h._defer_transition_until_worker_stops()
    assert events == ["started"], "the button is disabled before the wait begins"

    h._worker_stopped_event.set()
    assert _pump(lambda: len(events) == 2)
    assert events == ["started", ("finished", True)]


def test_a_timeout_reverts_the_mode_and_reports_failure(handler, qapp):
    h = handler(timeout=0.2)  # never set the event
    results = []
    h.transition_signals.finished.connect(lambda ok: results.append(ok))

    h._defer_transition_until_worker_stops()
    assert _pump(lambda: bool(results), timeout_s=5)

    assert results == [False]
    assert h.shared_data.liveMode is False, "a failed start must not leave the flag on"
    assert h.resumed == [], "no acquisition may start after the guard times out"


def test_a_timed_out_mda_reverts_mdaMode(handler, qapp):
    h = handler(liveOrMda="mda", timeout=0.2)
    results = []
    h.transition_signals.finished.connect(lambda ok: results.append(ok))
    h._defer_transition_until_worker_stops()
    assert _pump(lambda: bool(results), timeout_s=5)
    assert h.shared_data.mdaMode is False
    assert h.shared_data.liveMode is True, "the other mode must be untouched"


def test_a_second_request_does_not_start_a_second_waiter(handler, qapp):
    h = handler(timeout=5.0)
    assert h._defer_transition_until_worker_stops() is True
    assert h._defer_transition_until_worker_stops() is True, (
        "an in-flight transition absorbs further requests"
    )

    h._worker_stopped_event.set()
    assert _pump(lambda: bool(h.resumed))
    assert len(h.resumed) == 1, "exactly one continuation, not one per click"


def test_a_worker_thread_still_blocks_inline(handler):
    """A worker's own thread may wait; that is what it is for."""
    h = handler(timeout=5.0)
    box = {}

    def _target():
        box["deferred"] = h._defer_transition_until_worker_stops()

    worker = threading.Thread(target=_target)
    worker.start()
    worker.join(5)
    assert box["deferred"] is False, "off the GUI thread, the caller waits itself"


# ------------------------------------------------- the serialization survives


def test_the_blocking_wait_and_the_lock_are_still_there(napari_glados):
    source = inspect.getsource(napari_glados.napariHandler.acqModeChanged)
    assert "with self._acq_transition_lock:" in source, (
        "stop-before-start serialization exists because concurrent workers "
        "caused a JVM fatal crash"
    )
    assert source.count(
        "self._worker_stopped_event.wait(timeout=self.ACQ_STOP_TIMEOUT_S)"
    ) == 2, "the blocking wait remains as the off-GUI-thread path"
    assert source.count("self._defer_transition_until_worker_stops()") == 2, (
        "both the live and the mda branch must defer"
    )


def test_the_fast_path_skips_the_deferral_entirely(napari_glados):
    """No previous worker: no wait, no thread, no signal."""
    source = inspect.getsource(napari_glados.napariHandler.acqModeChanged)
    assert "if not self._worker_stopped_event.is_set():" in source


def test_headless_callers_still_block(handler, monkeypatch):
    """With no QApplication there is no GUI thread to protect."""
    import PyQt5.QtWidgets as QtWidgets

    h = handler()
    monkeypatch.setattr(QtWidgets.QApplication, "instance", staticmethod(lambda: None))
    assert h._defer_transition_until_worker_stops() is False


def test_the_mode_setter_sleeps_are_untouched(qapp):
    """Excluded at the user's request; removing them is a separate decision."""
    from glados_pycromanager.GUI import sharedFunctions

    for name in ("on_liveMode_value_change", "on_mdaMode_value_change"):
        source = inspect.getsource(getattr(sharedFunctions.Shared_data, name))
        assert "time.sleep(0.1)" in source


# ------------------------------------------------------------- the button


def test_the_live_button_is_wired_to_the_transition_signals(qapp):
    from glados_pycromanager.GUI.MMcontrols import MMConfigUI

    source = inspect.getsource(MMConfigUI._connectLiveModeTransitionSignals)
    assert "signals.started.connect" in source
    assert "signals.finished.connect" in source
    assert "_setLiveModeButtonBusy" in source


def test_a_click_while_disabled_is_ignored(qapp):
    from glados_pycromanager.GUI.MMcontrols import MMConfigUI

    source = inspect.getsource(MMConfigUI.changeLiveMode)
    assert "if not self.LiveModeButton.isEnabled():" in source


def test_button_busy_state_survives_a_destroyed_widget(qapp):
    from glados_pycromanager.GUI.MMcontrols import MMConfigUI

    class _Dead:
        def setEnabled(self, _):
            raise RuntimeError("wrapped C/C++ object has been deleted")

    obj = type("FakeUI", (), {})()
    obj.LiveModeButton = _Dead()
    MMConfigUI._setLiveModeButtonBusy(obj, True)  # must not raise


def test_missing_handler_does_not_break_construction(qapp):
    """The signals may not exist yet when the widget is built."""
    from glados_pycromanager.GUI.MMcontrols import MMConfigUI

    obj = type("FakeUI", (), {})()
    obj.shared_data = type("S", (), {})()
    MMConfigUI._connectLiveModeTransitionSignals(obj)  # must not raise
