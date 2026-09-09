"""Tests for T-G6: the metadata picklability probe runs once, not per frame.

`AnalysisProcess_customFunction` validates that a frame's metadata can cross the
process boundary before handing it to `multiprocessing.Queue.put()` -- which
pickles on a background feeder thread and fails *silently* there, looking exactly
like "the worker never responded". That check was a full `pickle.dumps` on every
frame whose result was thrown away; the verdict is invariant for a given backend.
"""
from __future__ import annotations

import pickle
from types import SimpleNamespace

import pytest

import glados_pycromanager.GUI.AnalysisClass as AnalysisClass
from glados_pycromanager.GUI.AnalysisClass import AnalysisProcess_customFunction


class _Unpicklable:
    """Stands in for metadata holding a live handle no pickler can take."""

    def __reduce__(self):
        raise TypeError("cannot pickle a live bridge handle")


class _Prober(SimpleNamespace):
    """Carries just the probe state, so the real method can be exercised without
    constructing a QThread (let alone spawning a worker process)."""
    _picklable_metadata = AnalysisProcess_customFunction._picklable_metadata


@pytest.fixture
def prober():
    return _Prober(_metadata_probe_type=None, _metadata_picklable=True)


@pytest.fixture
def counting_pickle(monkeypatch):
    calls = {"n": 0}

    class _CountingPickle:
        @staticmethod
        def dumps(obj, *args, **kwargs):
            calls["n"] += 1
            return pickle.dumps(obj, *args, **kwargs)

    monkeypatch.setattr(AnalysisClass, "pickle", _CountingPickle)
    return calls


def test_a_picklable_metadata_type_is_probed_once(prober, counting_pickle):
    for frame in range(100):
        assert prober._picklable_metadata({"Axes": {"time": frame}}) == {"Axes": {"time": frame}}
    assert counting_pickle["n"] == 1


def test_an_unpicklable_metadata_is_dropped_and_not_re_probed(prober, counting_pickle, caplog):
    with caplog.at_level("WARNING"):
        for _ in range(10):
            assert prober._picklable_metadata(_Unpicklable()) == {}
    assert counting_pickle["n"] == 1
    assert "not picklable" in caplog.text


def test_a_different_metadata_type_is_re_probed(prober, counting_pickle):
    prober._picklable_metadata({"a": 1})
    prober._picklable_metadata({"a": 2})
    assert counting_pickle["n"] == 1
    # A different shape can legitimately have a different verdict.
    assert prober._picklable_metadata(_Unpicklable()) == {}
    assert counting_pickle["n"] == 2
    # ...and switching back re-probes once more rather than reusing the verdict.
    assert prober._picklable_metadata({"a": 3}) == {"a": 3}
    assert counting_pickle["n"] == 3


def test_the_frame_still_goes_through_when_metadata_is_dropped(prober):
    """The documented degradation: lose the metadata, keep the frame."""
    assert prober._picklable_metadata(_Unpicklable()) == {}
    assert prober._metadata_picklable is False
