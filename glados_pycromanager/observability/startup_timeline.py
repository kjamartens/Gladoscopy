"""Startup timeline: where the time between the user's click and a usable window goes.

``mark(label)`` stamps a point in startup; ``report()`` turns the stamps into a table
measured from **process creation** (via psutil), so the interpreter's own start-up and
the console-script launcher are counted too, not just what happens after ``main()``.

Stdlib only at import time (psutil is imported when a report is built): this module is
imported before every heavy import in ``GUI_napari.py`` so that those imports can be
timed as well.
"""

import contextlib
import threading
import time

_lock = threading.Lock()
# (label, perf_counter) in the order they were stamped.
_marks: list[tuple[str, float]] = []
# Offset that turns a perf_counter reading into epoch seconds, fixed once at import so
# every mark shares the same clock. psutil's create_time() is in epoch seconds.
_EPOCH_MINUS_PERF = time.time() - time.perf_counter()


# Called with the label after every mark (the startup splash shows progress this way).
_listeners: list = []


def mark(label: str) -> None:
    """Stamp ``label`` at the current time. Safe to call from any thread.

    Listeners run on the calling thread, after the mark is stored. A listener that
    raises is ignored: progress display must never break startup.
    """
    now = time.perf_counter()
    with _lock:
        _marks.append((label, now))
        listeners = list(_listeners)
    for fn in listeners:
        with contextlib.suppress(Exception):
            fn(label)


def add_listener(fn) -> None:
    """Call ``fn(label)`` after every future mark."""
    with _lock:
        _listeners.append(fn)


def remove_listener(fn) -> None:
    with _lock:
        if fn in _listeners:
            _listeners.remove(fn)


def reset() -> None:
    """Forget every mark and listener (tests)."""
    with _lock:
        _marks.clear()
        _listeners.clear()


def _process_start_perf() -> float | None:
    """Process creation time on the perf_counter clock, or None if psutil can't say."""
    try:
        import psutil
        return psutil.Process().create_time() - _EPOCH_MINUS_PERF
    except Exception:
        return None


def report(t0: float | None = None) -> list[tuple[str, float, float]]:
    """``[(label, seconds since t0, seconds since previous mark)]``.

    ``t0`` defaults to the process start; if that is unavailable, to the first mark.
    """
    with _lock:
        marks = list(_marks)
    if not marks:
        return []
    if t0 is None:
        t0 = _process_start_perf()
    if t0 is None or t0 > marks[0][1]:
        t0 = marks[0][1]
    rows = []
    prev = t0
    for label, t in marks:
        rows.append((label, t - t0, t - prev))
        prev = t
    return rows


def _process_resources() -> str:
    try:
        import psutil
        proc = psutil.Process()
        cpu = proc.cpu_times()
        rss_mb = proc.memory_info().rss / 2**20
        return (f'process CPU {cpu.user + cpu.system:.2f} s '
                f'(user {cpu.user:.2f}, system {cpu.system:.2f}), RSS {rss_mb:.0f} MB')
    except Exception:
        return 'process CPU/RSS unavailable'


def format_report(rows: list[tuple[str, float, float]] | None = None) -> str:
    """The timeline as a fixed-width text table, plus process CPU and memory."""
    if rows is None:
        rows = report()
    if not rows:
        return '(no startup marks recorded)\n'
    width = max(len(label) for label, _, _ in rows)
    lines = [f"{'stage':<{width}}  {'at (s)':>8}  {'step (s)':>8}"]
    lines += [f'{label:<{width}}  {at:8.2f}  {step:8.2f}' for label, at, step in rows]
    lines.append(_process_resources())
    return '\n'.join(lines) + '\n'
