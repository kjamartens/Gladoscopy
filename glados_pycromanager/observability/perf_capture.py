"""Performance Mode capture engine.

Shared cProfile + psutil lifecycle used by both the GUI "Performance Mode"
toggle (`glados_pycromanager/GUI/performance_mode_widget.py`) and the
dev-only `--profile-runtime` CLI flag (`GUI_napari.py`). Pure logic, no Qt/
napari imports, so it's unit-testable in isolation (see
`tests/test_perf_capture.py`).

Design notes:
  * `psutil` calls are wrapped defensively -- AccessDenied/NotImplementedError/
    NoSuchProcess must never crash a capture; they degrade to an entry in
    `PerformanceReport.warnings` instead.
  * Per-thread CPU attribution uses `psutil.Process().threads()` (native OS
    thread ids, user+system time) diffed across the capture window, matched
    against a caller-supplied `native_id -> label` registry (see
    `Shared_data.perfThreadLabels`) so the report can say *which* component
    (GUI thread, acquisition worker, a specific RT-analysis node's QThread)
    consumed the CPU -- the key novice-actionable number for diagnosing
    GIL-starvation-style slowdowns.
  * `frames_rendered` is derived from `cProfile.getstats()` by counting calls
    to a function literally named `napariUpdateLive` -- the same technique
    already used (informally) by the pre-existing `--profile-runtime` flag.
  * Not every busy thread is one we register a label for (native library
    threads -- Qt's internal thread pool, vispy's OpenGL thread, the
    pycromanager/Java bridge -- never call register_perf_thread_label). For
    those, `stop()` takes a one-shot `sys._current_frames()` snapshot and
    attaches a short "what was this thread doing right now" stack hint to
    every thread delta, labeled or not, so an unexplained "thread 28708 at
    50% CPU" entry is still diagnosable instead of a dead end. Python thread
    idents (`sys._current_frames()` keys) equal native OS thread ids on
    Windows -- this app's only supported platform -- so the native_id from
    psutil.Process().threads() can be used directly as the lookup key.
"""
from __future__ import annotations

import cProfile
import io
import os
import pstats
import sys
import time
import traceback
from dataclasses import dataclass, field
from typing import Callable

try:
    import psutil
except ImportError:  # pragma: no cover - psutil is a hard dependency, but
    # degrade rather than crash an import chain if it's ever missing.
    psutil = None  # type: ignore[assignment]


@dataclass
class ThreadCpuSample:
    native_id: int
    label: str
    user_time: float
    system_time: float


@dataclass
class ThreadCpuDelta:
    native_id: int
    label: str
    cpu_seconds: float
    pct_of_window: float
    stack_hint: str | None = None


@dataclass
class SubprocessReport:
    node_label: str
    pid: int | None = None
    cpu_percent: float | None = None
    rss_mb: float | None = None
    thread_count: int | None = None
    hotspots: str | None = None
    error: str | None = None


@dataclass
class PerformanceReport:
    duration_s: float = 0.0
    frames_rendered: int = 0
    effective_fps: float = 0.0
    main_cpu_percent_start: float | None = None
    main_cpu_percent_end: float | None = None
    main_rss_mb_start: float | None = None
    main_rss_mb_end: float | None = None
    thread_deltas: list[ThreadCpuDelta] = field(default_factory=list)
    hotspots_text: str = ""
    subprocess_reports: list[SubprocessReport] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


def compute_thread_deltas(
    before: list[ThreadCpuSample],
    after: list[ThreadCpuSample],
    window_seconds: float,
) -> list[ThreadCpuDelta]:
    """Diff per-thread CPU time across a capture window.

    Threads present only in `after` (spawned mid-window) are diffed against
    a zero baseline. Threads present only in `before` (exited mid-window)
    are dropped -- there is no "after" sample to report a current state for.
    """
    before_by_id = {s.native_id: s for s in before}
    deltas = []
    for sample in after:
        base = before_by_id.get(sample.native_id)
        base_total = (base.user_time + base.system_time) if base is not None else 0.0
        cpu_seconds = max(0.0, (sample.user_time + sample.system_time) - base_total)
        pct = (100.0 * cpu_seconds / window_seconds) if window_seconds > 0 else 0.0
        deltas.append(ThreadCpuDelta(
            native_id=sample.native_id,
            label=sample.label,
            cpu_seconds=cpu_seconds,
            pct_of_window=pct,
        ))
    deltas.sort(key=lambda d: d.cpu_seconds, reverse=True)
    return deltas


def _safe(fn: Callable, default, warnings: list[str], what: str):
    try:
        return fn()
    except Exception as exc:  # noqa: BLE001 - profiling must never crash the app
        warnings.append(f"{what} unavailable: {exc!r}")
        return default


def _stack_hint(frame, max_frames: int = 3) -> str | None:
    """One-line "what is this thread doing right now" summary from a single
    stack-frame snapshot (see module docstring for why this works on
    Windows). Innermost frame first."""
    if frame is None:
        return None
    try:
        entries = traceback.extract_stack(frame, limit=max_frames)
    except Exception:  # noqa: BLE001 - a snapshot-formatting failure must not crash the capture
        return None
    return " <- ".join(
        f"{os.path.basename(e.filename)}:{e.lineno} in {e.name}()"
        for e in reversed(entries)
    )


def annotate_stack_hints(deltas: list[ThreadCpuDelta], frames_by_native_id: dict) -> None:
    """Mutates `deltas` in place, attaching a stack_hint from a
    sys._current_frames()-shaped mapping wherever the native_id matches."""
    for d in deltas:
        d.stack_hint = _stack_hint(frames_by_native_id.get(d.native_id))


class PerformanceCapture:
    """One start()/stop() cycle = one capture window."""

    def __init__(self, get_thread_registry: Callable[[], dict[int, str]] | None = None, hotspot_top_n: int = 25):
        self._get_thread_registry = get_thread_registry or (lambda: {})
        self._hotspot_top_n = hotspot_top_n
        self._profiler = cProfile.Profile()
        self._t0 = 0.0
        self._warnings: list[str] = []
        self._proc = psutil.Process() if psutil is not None else None
        self._cpu_before: float | None = None
        self._rss_before: float | None = None
        self._threads_before: list[ThreadCpuSample] = []

    def _thread_samples(self) -> list[ThreadCpuSample]:
        if self._proc is None:
            self._warnings.append("psutil is not available; per-thread CPU breakdown skipped")
            return []
        registry = self._get_thread_registry()
        raw = _safe(self._proc.threads, [], self._warnings, "per-thread CPU times")
        return [
            ThreadCpuSample(
                native_id=t.id,
                label=registry.get(t.id, f"thread {t.id}"),
                user_time=t.user_time,
                system_time=t.system_time,
            )
            for t in raw
        ]

    def start(self) -> None:
        self._warnings = []
        self._t0 = time.time()
        if self._proc is None:
            self._warnings.append("psutil is not available; CPU%/RSS/thread stats skipped")
        else:
            self._cpu_before = _safe(lambda: self._proc.cpu_percent(interval=None), None, self._warnings, "main process CPU%")
            self._rss_before = _safe(lambda: self._proc.memory_info().rss / (1024 * 1024), None, self._warnings, "main process RSS")
        self._threads_before = self._thread_samples()
        self._profiler.enable()

    def stop(self, subprocess_reports: list[SubprocessReport] | None = None) -> PerformanceReport:
        self._profiler.disable()
        elapsed = max(1e-9, time.time() - self._t0)

        frames_rendered = 0
        for entry in self._profiler.getstats():
            code = getattr(entry, "code", None)
            if code is not None and getattr(code, "co_name", "") == "napariUpdateLive":
                frames_rendered = entry.callcount
                break

        cpu_after = None
        rss_after = None
        if self._proc is not None:
            cpu_after = _safe(lambda: self._proc.cpu_percent(interval=None), None, self._warnings, "main process CPU%")
            rss_after = _safe(lambda: self._proc.memory_info().rss / (1024 * 1024), None, self._warnings, "main process RSS")
        threads_after = self._thread_samples()
        thread_deltas = compute_thread_deltas(self._threads_before, threads_after, elapsed)
        annotate_stack_hints(thread_deltas, _safe(sys._current_frames, {}, self._warnings, "thread stack snapshot"))

        buf = io.StringIO()
        pstats.Stats(self._profiler, stream=buf).sort_stats("cumulative").print_stats(self._hotspot_top_n)

        return PerformanceReport(
            duration_s=elapsed,
            frames_rendered=frames_rendered,
            effective_fps=frames_rendered / elapsed,
            main_cpu_percent_start=self._cpu_before,
            main_cpu_percent_end=cpu_after,
            main_rss_mb_start=self._rss_before,
            main_rss_mb_end=rss_after,
            thread_deltas=thread_deltas,
            hotspots_text=buf.getvalue(),
            subprocess_reports=list(subprocess_reports or []),
            warnings=list(self._warnings),
        )


def format_report_text(report: PerformanceReport) -> str:
    lines: list[str] = []
    lines.append("=== Performance Mode report ===")
    lines.append(
        f"Capture window: {report.duration_s:.2f}s | "
        f"frames rendered: {report.frames_rendered} | "
        f"effective FPS: {report.effective_fps:.1f}"
    )
    lines.append("")

    lines.append("-- CPU per component (main process threads) --")
    if report.thread_deltas:
        lines.append(f"{'label':<45}{'cpu (s)':>10}{'% of window':>14}")
        for d in report.thread_deltas:
            lines.append(f"{d.label:<45}{d.cpu_seconds:>10.3f}{d.pct_of_window:>13.1f}%")
            if d.stack_hint:
                # Snapshot taken the instant the capture stopped -- "what was
                # this thread doing right now", not a trace of the whole
                # window. Most useful for unlabeled/library threads (Qt,
                # vispy, pycromanager/Java bridge) that never register a
                # perf_thread_label.
                lines.append(f"    at capture-stop: {d.stack_hint}")
    else:
        lines.append("(no per-thread data available)")
    lines.append("")

    lines.append("-- Main process --")
    lines.append(f"CPU%: {report.main_cpu_percent_start} -> {report.main_cpu_percent_end}")
    lines.append(f"RSS (MB): {report.main_rss_mb_start} -> {report.main_rss_mb_end}")
    lines.append("")

    if report.subprocess_reports:
        lines.append("-- RT-analysis subprocess-isolated nodes --")
        for sub in report.subprocess_reports:
            lines.append(f"* {sub.node_label} (pid={sub.pid})")
            if sub.error:
                lines.append(f"    error: {sub.error}")
                continue
            lines.append(f"    CPU%: {sub.cpu_percent}  RSS (MB): {sub.rss_mb}  threads: {sub.thread_count}")
            if sub.hotspots:
                lines.append("    hotspots:")
                for hline in sub.hotspots.splitlines():
                    lines.append(f"    {hline}")
        lines.append("")

    lines.append("-- Main process function hotspots (top by cumulative time) --")
    lines.append(report.hotspots_text.rstrip())

    if report.warnings:
        lines.append("")
        lines.append("-- Warnings --")
        for w in report.warnings:
            lines.append(f"* {w}")

    return "\n".join(lines) + "\n"
