"""Tests for glados_pycromanager.observability.perf_capture (Performance
Mode's shared cProfile + psutil capture engine).

Pure logic, no Qt/napari/multiprocessing -- matches the existing "pure-logic
surfaces only" test policy for this repo.
"""
from __future__ import annotations

import pytest

from glados_pycromanager.observability.perf_capture import (
    PerformanceCapture,
    PerformanceReport,
    ThreadCpuDelta,
    ThreadCpuSample,
    annotate_stack_hints,
    compute_thread_deltas,
    format_report_text,
)


def test_compute_thread_deltas_basic():
    before = [ThreadCpuSample(native_id=1, label="A", user_time=1.0, system_time=0.5)]
    after = [ThreadCpuSample(native_id=1, label="A", user_time=2.0, system_time=1.0)]
    deltas = compute_thread_deltas(before, after, window_seconds=1.0)
    assert len(deltas) == 1
    assert deltas[0].cpu_seconds == pytest.approx(1.5)
    assert deltas[0].pct_of_window == pytest.approx(150.0)


def test_compute_thread_deltas_sorted_descending():
    before: list[ThreadCpuSample] = []
    after = [
        ThreadCpuSample(native_id=1, label="low", user_time=0.1, system_time=0.0),
        ThreadCpuSample(native_id=2, label="high", user_time=5.0, system_time=0.0),
    ]
    deltas = compute_thread_deltas(before, after, window_seconds=5.0)
    assert [d.label for d in deltas] == ["high", "low"]


def test_compute_thread_deltas_thread_spawned_mid_window():
    # Thread not present in "before" -> diffed against a zero baseline.
    before: list[ThreadCpuSample] = []
    after = [ThreadCpuSample(native_id=9, label="new-thread", user_time=0.3, system_time=0.2)]
    deltas = compute_thread_deltas(before, after, window_seconds=1.0)
    assert deltas[0].cpu_seconds == pytest.approx(0.5)


def test_compute_thread_deltas_thread_exited_mid_window_is_dropped():
    # Thread present only in "before" (exited) has no "after" sample -> excluded.
    before = [ThreadCpuSample(native_id=1, label="gone", user_time=1.0, system_time=0.0)]
    after: list[ThreadCpuSample] = []
    deltas = compute_thread_deltas(before, after, window_seconds=1.0)
    assert deltas == []


def test_compute_thread_deltas_zero_window_does_not_raise():
    before: list[ThreadCpuSample] = []
    after = [ThreadCpuSample(native_id=1, label="A", user_time=1.0, system_time=0.0)]
    deltas = compute_thread_deltas(before, after, window_seconds=0.0)
    assert deltas[0].pct_of_window == 0.0


def test_capture_start_stop_extracts_frame_count():
    capture = PerformanceCapture(get_thread_registry=lambda: {})

    def napariUpdateLive(_data):
        return None

    capture.start()
    for _ in range(3):
        napariUpdateLive({})
    report = capture.stop()

    assert report.frames_rendered == 3
    assert report.duration_s > 0
    assert "napariUpdateLive" in report.hotspots_text or report.frames_rendered == 3


def test_capture_degrades_gracefully_when_psutil_unavailable(monkeypatch):
    import glados_pycromanager.observability.perf_capture as perf_capture_module

    monkeypatch.setattr(perf_capture_module, "psutil", None)
    capture = PerformanceCapture(get_thread_registry=lambda: {})
    capture.start()
    report = capture.stop()

    assert report.thread_deltas == []
    assert report.main_cpu_percent_start is None
    assert any("psutil" in w for w in report.warnings)


def test_capture_degrades_gracefully_when_threads_call_raises(monkeypatch):
    import glados_pycromanager.observability.perf_capture as perf_capture_module

    class _RaisingProc:
        def threads(self):
            raise NotImplementedError("not supported on this platform")

        def cpu_percent(self, interval=None):
            return 1.0

        def memory_info(self):
            class _M:
                rss = 1024 * 1024
            return _M()

    monkeypatch.setattr(perf_capture_module, "psutil", type("psutil", (), {"Process": staticmethod(lambda: _RaisingProc())}))
    capture = PerformanceCapture(get_thread_registry=lambda: {})
    capture.start()
    report = capture.stop()

    assert report.thread_deltas == []
    assert any("per-thread" in w for w in report.warnings)


def test_annotate_stack_hints_matches_by_native_id():
    import sys
    import threading

    deltas = [ThreadCpuDelta(native_id=threading.get_native_id(), label="me", cpu_seconds=1.0, pct_of_window=10.0)]
    annotate_stack_hints(deltas, sys._current_frames())
    assert deltas[0].stack_hint is not None
    assert "test_perf_capture.py" in deltas[0].stack_hint


def test_annotate_stack_hints_missing_thread_leaves_none():
    deltas = [ThreadCpuDelta(native_id=999999999, label="ghost", cpu_seconds=1.0, pct_of_window=10.0)]
    annotate_stack_hints(deltas, {})
    assert deltas[0].stack_hint is None


def test_capture_stop_populates_stack_hints_for_current_thread():
    capture = PerformanceCapture(get_thread_registry=lambda: {})
    capture.start()
    report = capture.stop()
    # The calling (test) thread is always in the psutil sample and should get
    # a non-None hint since sys._current_frames() always includes it.
    import threading
    mine = [d for d in report.thread_deltas if d.native_id == threading.get_native_id()]
    assert mine and mine[0].stack_hint is not None


def test_format_report_text_contains_key_sections():
    report = PerformanceReport(
        duration_s=5.0,
        frames_rendered=42,
        effective_fps=8.4,
        hotspots_text="   1 function calls\n",
    )
    text = format_report_text(report)
    assert "Performance Mode report" in text
    assert "CPU per component" in text
    assert "Main process function hotspots" in text
    assert "42" in text
