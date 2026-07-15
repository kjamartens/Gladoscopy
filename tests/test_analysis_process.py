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
