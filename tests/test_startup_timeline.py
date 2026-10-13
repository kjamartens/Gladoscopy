"""Startup timeline (observability/startup_timeline.py) and its consumers.

Covers the mark/report/format round trip, the aggregation in
scripts/profile_startup_full.py (which parses format_report's own output back),
and napariGlados' once-only startup-ready hook.
"""

import pytest

from glados_pycromanager.observability import startup_timeline
from scripts import profile_startup_full


@pytest.fixture(autouse=True)
def _fresh_timeline():
    startup_timeline.reset()
    yield
    startup_timeline.reset()


def _fake_marks(monkeypatch, marks):
    """Install (label, perf_counter) marks without depending on the real clock."""
    monkeypatch.setattr(startup_timeline, '_marks', list(marks))


def test_report_measures_from_given_t0_with_per_step_deltas(monkeypatch):
    _fake_marks(monkeypatch, [('a', 10.5), ('b', 11.0), ('c', 13.0)])
    rows = startup_timeline.report(t0=10.0)
    assert [r[0] for r in rows] == ['a', 'b', 'c']
    assert [round(r[1], 6) for r in rows] == [0.5, 1.0, 3.0]
    assert [round(r[2], 6) for r in rows] == [0.5, 0.5, 2.0]


def test_report_defaults_to_process_start(monkeypatch):
    _fake_marks(monkeypatch, [('a', 10.5)])
    monkeypatch.setattr(startup_timeline, '_process_start_perf', lambda: 9.5)
    assert round(startup_timeline.report()[0][1], 6) == 1.0


def test_report_falls_back_to_first_mark_without_a_usable_process_start(monkeypatch):
    _fake_marks(monkeypatch, [('a', 10.5), ('b', 12.0)])
    monkeypatch.setattr(startup_timeline, '_process_start_perf', lambda: None)
    assert [round(r[1], 6) for r in startup_timeline.report()] == [0.0, 1.5]
    # A process start *after* the first mark is a clock mismatch, not a real t0.
    monkeypatch.setattr(startup_timeline, '_process_start_perf', lambda: 11.0)
    assert round(startup_timeline.report()[0][1], 6) == 0.0


def test_empty_timeline_formats_without_error():
    assert startup_timeline.report() == []
    assert 'no startup marks' in startup_timeline.format_report()


def test_mark_records_in_order():
    startup_timeline.mark('first')
    startup_timeline.mark('second')
    assert [r[0] for r in startup_timeline.report()] == ['first', 'second']


def test_aggregator_parses_format_report_output(monkeypatch):
    _fake_marks(monkeypatch, [('GUI_napari import started', 1.0),
                              ('dock built: Controls', 3.25),
                              ('ready (event loop idle after layout)', 4.0)])
    text = startup_timeline.format_report(startup_timeline.report(t0=0.0))
    rows = profile_startup_full.parse_timeline(text)
    assert rows == [('GUI_napari import started', 1.0),
                    ('dock built: Controls', 3.25),
                    ('ready (event loop idle after layout)', 4.0)]


def test_median_timeline_uses_median_of_each_runs_own_step():
    runs = [[('a', 1.0), ('b', 2.0)],
            [('a', 3.0), ('b', 4.0)],
            [('a', 2.0), ('b', 6.0)]]
    summary = profile_startup_full.median_timeline(runs)
    assert summary == [('a', 2.0, 2.0, 3), ('b', 4.0, 1.0, 3)]


def test_median_timeline_keeps_stages_missing_from_some_runs():
    runs = [[('a', 1.0), ('dialog', 2.0), ('b', 3.0)],
            [('a', 1.0), ('b', 2.0)]]
    summary = profile_startup_full.median_timeline(runs)
    assert [s[0] for s in summary] == ['a', 'dialog', 'b']
    assert summary[1][3] == 1


def test_startup_ready_hook_fires_once_and_runs_late_registrations_immediately(monkeypatch):
    from glados_pycromanager.GUI import napariGlados

    monkeypatch.setattr(napariGlados, '_startup_ready_fired', False)
    monkeypatch.setattr(napariGlados, '_startup_ready_callbacks', [])
    calls = []
    napariGlados.call_when_startup_ready(lambda: calls.append('early'))
    assert calls == []
    napariGlados._startupReady()
    napariGlados._startupReady()
    assert calls == ['early']
    napariGlados.call_when_startup_ready(lambda: calls.append('late'))
    assert calls == ['early', 'late']
    assert [r[0] for r in startup_timeline.report()] == ['ready (event loop idle after layout)']


def test_startup_ready_hook_survives_a_failing_callback(monkeypatch):
    from glados_pycromanager.GUI import napariGlados

    monkeypatch.setattr(napariGlados, '_startup_ready_fired', False)
    monkeypatch.setattr(napariGlados, '_startup_ready_callbacks', [])
    calls = []
    napariGlados.call_when_startup_ready(lambda: 1 / 0)
    napariGlados.call_when_startup_ready(lambda: calls.append('after'))
    napariGlados._startupReady()
    assert calls == ['after']
