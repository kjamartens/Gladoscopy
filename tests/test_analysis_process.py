"""Tests for AnalysisClass._subprocess_analysis_worker (subprocess-isolated
RT-analysis compute, see https://github.com/kjamartens/Gladoscopy/issues/16).

These exercise the actual multiprocessing.Process machinery (spawn start
method) against picklable fake init/run/end functions, not a real analysis
node -- no GUI, no hardware, no diplib required. AnalysisProcess_customFunction
itself (the QThread wrapper) is not covered here since it needs a running Qt
event loop, matching the existing "no GUI integration test" policy for
AnalysisThread_customFunction.
"""
from __future__ import annotations

import multiprocessing as mp
import sys
import time

import numpy as np
import pytest

import queue as std_queue

from glados_pycromanager.GUI.AnalysisClass import _subprocess_analysis_worker
from tests.fakes.fake_rt_analysis import fake_end_fn, fake_init_fn, fake_run_fn, fake_run_fn_raises


@pytest.fixture
def mp_ctx():
    return mp.get_context("spawn")


def _make_channels(mp_ctx):
    in_queue = mp_ctx.Queue(maxsize=2)
    out_queue = mp_ctx.Queue(maxsize=2)
    stop_event = mp_ctx.Event()
    return in_queue, out_queue, stop_event


@pytest.mark.slow
def test_worker_processes_one_image_and_returns_result(mp_ctx):
    in_queue, out_queue, stop_event = _make_channels(mp_ctx)
    proc = mp_ctx.Process(
        target=_subprocess_analysis_worker,
        args=({"initial_value": 10}, in_queue, out_queue, stop_event),
        kwargs={"init_fn": fake_init_fn, "run_fn": fake_run_fn, "end_fn": fake_end_fn},
        daemon=True,
    )
    proc.start()
    try:
        image = np.ones((4, 4), dtype=np.int64)  # sum == 16
        in_queue.put((image, {"frame": 1}))
        result, metadata, state_snapshot = out_queue.get(timeout=10)

        assert result == 10 + 16
        assert metadata == {"frame": 1}
        # State snapshot carries the node's picklable attributes back to the
        # main process for the visualisation shadow instance.
        assert state_snapshot["total"] == 10 + 16
        assert state_snapshot["init_calls"] == 1
    finally:
        stop_event.set()
        in_queue.put(None)
        proc.join(timeout=15)
        assert not proc.is_alive()


@pytest.mark.slow
def test_worker_processes_multiple_images_in_order(mp_ctx):
    in_queue, out_queue, stop_event = _make_channels(mp_ctx)
    proc = mp_ctx.Process(
        target=_subprocess_analysis_worker,
        args=({"initial_value": 0}, in_queue, out_queue, stop_event),
        kwargs={"init_fn": fake_init_fn, "run_fn": fake_run_fn, "end_fn": fake_end_fn},
        daemon=True,
    )
    proc.start()
    try:
        for i in range(3):
            in_queue.put((np.full((2, 2), i + 1, dtype=np.int64), {"frame": i}))
        totals = []
        for _ in range(3):
            result, _metadata, _snapshot = out_queue.get(timeout=10)
            totals.append(result)
        # sums are 4, 8, 12 -> cumulative totals 4, 12, 24
        assert totals == [4, 12, 24]
    finally:
        stop_event.set()
        in_queue.put(None)
        proc.join(timeout=15)
        assert not proc.is_alive()


@pytest.mark.slow
def test_worker_exits_cleanly_on_stop_sentinel_without_pending_work(mp_ctx):
    in_queue, out_queue, stop_event = _make_channels(mp_ctx)
    proc = mp_ctx.Process(
        target=_subprocess_analysis_worker,
        args=({}, in_queue, out_queue, stop_event),
        kwargs={"init_fn": fake_init_fn, "run_fn": fake_run_fn, "end_fn": fake_end_fn},
        daemon=True,
    )
    proc.start()
    try:
        in_queue.put(None)  # sentinel, no image work queued first
        proc.join(timeout=15)  # spawn start method re-imports the whole module tree (PyQt5 et al.)
        assert not proc.is_alive()
        assert out_queue.empty()
    finally:
        stop_event.set()


def _get_or_fail_fast(out_queue, proc, timeout=60):
    """`out_queue.get(timeout=...)`, but give up as soon as the child dies.

    Without this, any crash inside the spawned worker (e.g. an rt_analysis_info
    dict that no longer matches the node's kwargs) costs the *full* timeout of
    dead waiting per call before the test reports a bare queue.Empty. Polling
    proc.is_alive() turns that into a ~1s failure with the child's exit code.
    """
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            return out_queue.get(timeout=0.5)
        except std_queue.Empty:
            if not proc.is_alive():
                raise AssertionError(
                    f"subprocess worker died (exitcode={proc.exitcode}) before "
                    "returning a result -- see its traceback on stderr above"
                ) from None
    raise AssertionError(f"no result from the subprocess worker within {timeout}s")


@pytest.mark.slow
def test_worker_runs_the_real_fft_node_end_to_end(mp_ctx):
    """Regression test for two bugs found only via live GUI testing (not caught
    by the fake-based tests above), see
    https://github.com/kjamartens/Gladoscopy/issues/16:

    1. The child process never imported the RT-analysis plugin package, so
       `_resolve_node_obj` couldn't find FFT_im.RealTimeFFT (NameError).
    2. A hand-built minimal rt_analysis_info dict without a matching
       "LineEdit#<function>#<kwarg>" entry hits an UnboundLocalError inside
       getFunctionEvalTextFromCurrentData_RTAnalysis_init -- this is what the
       real GUI-built dict always includes (see
       GUI/utils.py's `line_edit.setObjectName(f"LineEdit#{function}#{kwarg}")`
       and FlowChart_dockWidgets.py's currentData population from that
       objectName), so the dict shape here must match production, not a
       hand-picked minimal subset.

    Uses the real utils.realTimeAnalysis_init/run/end (init_fn/run_fn/end_fn
    left at their defaults) against the real FFT_im.RealTimeFFT node.
    """
    # diplib/IPython pt_inputhooks gotcha (see CLAUDE.md): once *any* earlier test
    # in the session has pulled IPython into sys.modules -- napari does --
    # `import diplib` raises AttributeError, which importorskip does not catch, so
    # this test fails in a full-suite run while passing in isolation. Same guard
    # as subprocess_pool.py's bootstrap and FFT_im.RealTimeFFT.__init__.
    if 'IPython' in sys.modules:
        import IPython.terminal.pt_inputhooks  # noqa: F401
    pytest.importorskip("diplib")
    in_queue, out_queue, stop_event = _make_channels(mp_ctx)
    # One "LineEdit#<function>#<kwarg>" entry per kwarg in RealTimeFFT's
    # __function_metadata__ optional_kwargs -- getEvalTextFromGUIFunction indexes
    # methodKwargValues positionally, so a *missing* kwarg here is an IndexError
    # in the child, not a default-value fallback. bool-typed kwargs use the same
    # LineEdit# objectName and are stored as "True"/"False" strings (see
    # changeDataVarUponKwargChange's QCheckBox branch in GUI/utils.py).
    # Keep this dict in sync when the node gains a kwarg.
    rt_analysis_info = {
        "__selectedDropdownEntryRTAnalysis__": "Real-Time FFT",
        "__displayNameFunctionNameMap__": [("Real-Time FFT", "FFT_im.RealTimeFFT")],
        "LineEdit#FFT_im.RealTimeFFT#LogScale": "True",
        "LineEdit#FFT_im.RealTimeFFT#WindowTaper": "False",
        "LineEdit#FFT_im.RealTimeFFT#WindowTaperStrength": "0.25",
    }
    proc = mp_ctx.Process(
        target=_subprocess_analysis_worker,
        args=(rt_analysis_info, in_queue, out_queue, stop_event),
        daemon=True,
    )
    proc.start()
    try:
        image = np.random.rand(64, 64).astype(np.uint16)
        in_queue.put((image, {"frame": 0}))
        result, metadata, state_snapshot = _get_or_fail_fast(out_queue, proc, timeout=60)

        assert metadata == {"frame": 0}
        fft_display = state_snapshot["fft_display"]
        assert fft_display.shape == (64, 64)
        # GUI-sourced kwarg values always arrive as quoted strings through the
        # eval-text mechanism (LogScale="True"), not Python bools -- this is
        # pre-existing behaviour of getEvalTextFromGUIFunction, not something
        # introduced by subprocess isolation.
        assert state_snapshot["log_scale"] == "True"

        # A second frame must also work (init isn't re-run per frame).
        in_queue.put((image, {"frame": 1}))
        _result2, metadata2, _snapshot2 = _get_or_fail_fast(out_queue, proc, timeout=60)
        assert metadata2 == {"frame": 1}
    finally:
        stop_event.set()
        in_queue.put(None)
        proc.join(timeout=20)
        assert not proc.is_alive()


@pytest.mark.slow
def test_worker_survives_a_run_fn_exception_without_crashing(mp_ctx):
    in_queue, out_queue, stop_event = _make_channels(mp_ctx)
    proc = mp_ctx.Process(
        target=_subprocess_analysis_worker,
        args=({"initial_value": 5}, in_queue, out_queue, stop_event),
        kwargs={"init_fn": fake_init_fn, "run_fn": fake_run_fn_raises, "end_fn": fake_end_fn},
        daemon=True,
    )
    proc.start()
    try:
        in_queue.put((np.ones((2, 2), dtype=np.int64), {"frame": 0}))
        # A failing run_fn must be caught inside the worker loop: no result is
        # emitted, but the worker process itself must not crash/exit.
        with pytest.raises(std_queue.Empty):
            out_queue.get(timeout=2)
        assert proc.is_alive()
    finally:
        stop_event.set()
        in_queue.put(None)
        proc.join(timeout=15)
        assert not proc.is_alive()
