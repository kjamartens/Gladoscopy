"""Tests for T-G9: stopping an RT-analysis node actually stops its threads.

`AnalysisThread_customFunction.run()` blocked on `self._new_image.wait()` with no
timeout, and `stop()` cleared `is_running` without ever setting that event -- so
the loop never woke to re-check the flag and the QThread blocked forever.
`destroy()`'s `quit()` only exits a Qt event loop, not an overridden `run()`, so
every start/stop cycle of an in-process node leaked one or two blocked threads
plus their frame deques. The visualisation thread had the same shape.
"""
from __future__ import annotations

import inspect
import threading
import time
from collections import deque
from threading import Event
from types import SimpleNamespace

import pytest

from glados_pycromanager.GUI.AnalysisClass import (
    RT_THREAD_WAIT_TIMEOUT_S,
    AnalysisProcess_customFunction,
    AnalysisThread_customFunction,
    AnalysisThread_customFunction_Visualisation,
)


class _Loop(SimpleNamespace):
    """Runs the real `_run_loop` without constructing a QThread."""
    _run_loop = AnalysisThread_customFunction._run_loop

    def msleep(self, ms):
        time.sleep(ms / 1000.0)

    def runAnalysis(self, data):
        return None


def _start_loop(**overrides):
    state = _Loop(is_running=True, image_queue_analysis=deque(),
                  _new_image=Event(), sleepTimeMs=1, **overrides)
    thread = threading.Thread(target=state._run_loop, daemon=True)
    thread.start()
    time.sleep(0.05)
    assert thread.is_alive()
    return state, thread


def test_clearing_the_flag_and_waking_the_event_returns_from_run():
    state, thread = _start_loop()
    state.is_running = False
    state._new_image.set()
    thread.join(timeout=2)
    assert not thread.is_alive()


def test_the_timed_wait_is_a_deadman_even_without_the_wake():
    """Belt and braces: a stop that somehow never sets the event still lands
    within one wait timeout instead of hanging forever."""
    state, thread = _start_loop()
    state.is_running = False  # deliberately no _new_image.set()
    thread.join(timeout=RT_THREAD_WAIT_TIMEOUT_S * 3)
    assert not thread.is_alive()


class _Stopper(SimpleNamespace):
    stop = AnalysisThread_customFunction.stop

    def endAnalysis(self, analysisInfo, core=None):
        self.ends += 1


def _stopper():
    return _Stopper(_teardown_done=False, is_running=True, running=True,
                    _activity_event=Event(), _new_image=Event(),
                    analysisInfo={}, shared_data=SimpleNamespace(core=None),
                    ends=0, skipAnalysisThreadDeletion=False)


def test_stop_wakes_the_run_loop():
    node = _stopper()
    node.stop()
    assert node.is_running is False
    assert node._new_image.is_set()
    assert node._activity_event.is_set()


def test_stop_runs_the_node_teardown_exactly_once():
    """destroy() calls stop(), and both used to run endAnalysis - so a node's
    end() ran twice per teardown."""
    node = _stopper()
    node.stop()
    node.stop()
    assert node.ends == 1


def test_destroy_no_longer_calls_end_analysis_itself():
    source = inspect.getsource(AnalysisThread_customFunction.destroy)
    assert "self.endAnalysis(" not in source
    assert "self.stop()" in source
    assert "self.wait(" in source


def test_the_visualisation_thread_has_a_stop_that_wakes_it():
    vis = SimpleNamespace(running=True, is_running=True, _new_image=Event())
    AnalysisThread_customFunction_Visualisation.stop(vis)
    assert vis.running is False
    assert vis._new_image.is_set()


@pytest.mark.parametrize("cls", [
    AnalysisThread_customFunction,
    AnalysisProcess_customFunction,
    AnalysisThread_customFunction_Visualisation,
])
def test_no_loop_waits_without_a_timeout(cls):
    source = inspect.getsource(cls.run if cls is AnalysisThread_customFunction_Visualisation else cls._run_loop)
    assert "_new_image.wait()" not in source, f"{cls.__name__} can block forever on stop"
    assert "_new_image.wait(" in source


@pytest.mark.parametrize("cls", [AnalysisThread_customFunction, AnalysisProcess_customFunction])
def test_destroy_joins_and_reports_a_thread_that_will_not_exit(cls):
    source = inspect.getsource(cls.destroy)
    assert "RT_THREAD_JOIN_TIMEOUT_MS" in source
    assert "logging.warning" in source
    assert "visualisationObject" in source
