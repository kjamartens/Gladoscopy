"""Tests for T-G7: the subprocess proxy no longer sleeps for as long as the
analysis took.

`msleep(max(1, sleepTimeMs, analysis_elapsed_ms))` caps the sustained rate at
1/(2T). On `AnalysisThread_customFunction` that is a deliberate GIL-fairness
trade -- the compute runs on that thread, in this process. On
`AnalysisProcess_customFunction` the compute runs in another process holding no
GIL of ours and the proxy thread is idle-blocked on `_out_queue.get()` for the
whole round trip, so the same sleep is pure lost throughput.
"""
from __future__ import annotations

import inspect

from glados_pycromanager.GUI.AnalysisClass import (
    AnalysisProcess_customFunction,
    AnalysisThread_customFunction,
)


def _loop_source(cls):
    return inspect.getsource(cls._run_loop)


def test_the_subprocess_proxy_sleeps_only_its_configured_delay():
    source = _loop_source(AnalysisProcess_customFunction)
    assert "self.msleep(max(1, self.sleepTimeMs))" in source
    assert "analysis_elapsed_ms" not in source


def test_the_in_process_thread_keeps_its_duty_cycle_cap():
    """Deliberately untouched: that thread's compute really does hold the GIL."""
    source = _loop_source(AnalysisThread_customFunction)
    assert "analysis_elapsed_ms" in source
    assert "self.msleep(max(1, self.sleepTimeMs, int(analysis_elapsed_ms)))" in source


def test_the_proxy_keeps_a_sleep_floor():
    """The floor stays: a busy-spinning proxy would starve the GUI thread."""
    source = _loop_source(AnalysisProcess_customFunction)
    assert "self.sleepTimeMs" in source
    assert "max(1," in source
