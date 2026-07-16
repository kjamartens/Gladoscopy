"""Tests for the Performance Mode subprocess-profiling control channel added
to AnalysisClass._subprocess_analysis_worker (control_in_queue/control_out_queue).

Exercises the real multiprocessing.Process machinery (spawn start method)
against picklable fake init/run/end functions -- no GUI, no hardware, no
diplib required, matching the existing test_analysis_process.py style.
AnalysisProcess_customFunction itself (start_profiling/stop_profiling) needs
a running Qt event loop and is not covered here, matching the existing
"no GUI integration test" policy.
"""
from __future__ import annotations

import multiprocessing as mp
import queue as std_queue

import numpy as np
import pytest

from glados_pycromanager.GUI.AnalysisClass import _subprocess_analysis_worker
from tests.fakes.fake_rt_analysis import fake_end_fn, fake_init_fn, fake_run_fn


@pytest.fixture
def mp_ctx():
    return mp.get_context("spawn")


def _make_channels(mp_ctx):
    in_queue = mp_ctx.Queue(maxsize=2)
    out_queue = mp_ctx.Queue(maxsize=2)
    stop_event = mp_ctx.Event()
    return in_queue, out_queue, stop_event


def test_worker_without_control_queues_still_works(mp_ctx):
    """Regression guard: existing callers that don't pass control_in_queue/
    control_out_queue (default None) must be unaffected."""
    in_queue, out_queue, stop_event = _make_channels(mp_ctx)
    proc = mp_ctx.Process(
        target=_subprocess_analysis_worker,
        args=({"initial_value": 10}, in_queue, out_queue, stop_event),
        kwargs={"init_fn": fake_init_fn, "run_fn": fake_run_fn, "end_fn": fake_end_fn},
        daemon=True,
    )
    proc.start()
    try:
        image = np.ones((4, 4), dtype=np.int64)
        in_queue.put((image, {"frame": 1}))
        result, metadata, _snapshot = out_queue.get(timeout=10)
        assert result == 10 + 16
        assert metadata == {"frame": 1}
    finally:
        stop_event.set()
        in_queue.put(None)
        proc.join(timeout=15)
        assert not proc.is_alive()


def test_profiling_start_stop_round_trip_does_not_disturb_frames(mp_ctx):
    in_queue, out_queue, stop_event = _make_channels(mp_ctx)
    control_in_queue = mp_ctx.Queue(maxsize=2)
    control_out_queue = mp_ctx.Queue(maxsize=2)
    proc = mp_ctx.Process(
        target=_subprocess_analysis_worker,
        args=({"initial_value": 0}, in_queue, out_queue, stop_event),
        kwargs={
            "init_fn": fake_init_fn, "run_fn": fake_run_fn, "end_fn": fake_end_fn,
            "control_in_queue": control_in_queue, "control_out_queue": control_out_queue,
        },
        daemon=True,
    )
    proc.start()
    try:
        control_in_queue.put_nowait("__perf_profile_start__")

        image = np.full((2, 2), 3, dtype=np.int64)
        in_queue.put((image, {"frame": 0}))
        result, metadata, _snapshot = out_queue.get(timeout=10)
        assert result == 12  # sum of the 2x2 image of 3s
        assert metadata == {"frame": 0}

        control_in_queue.put_nowait("__perf_profile_stop__")
        report = control_out_queue.get(timeout=10)
        assert report["__perf_report__"] is True
        assert isinstance(report["hotspots"], str)
        assert len(report["hotspots"]) > 0
        assert report["pid"] == proc.pid

        # Frame pipeline still works after a profiling cycle.
        in_queue.put((image, {"frame": 1}))
        result2, metadata2, _snapshot2 = out_queue.get(timeout=10)
        assert result2 == 24
        assert metadata2 == {"frame": 1}
    finally:
        stop_event.set()
        try:
            in_queue.put_nowait(None)
        except std_queue.Full:
            pass
        proc.join(timeout=15)
        assert not proc.is_alive()
