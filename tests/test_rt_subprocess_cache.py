"""Tests for the RT-analysis warm-restart subprocess cache (see
AnalysisClass.py's _rt_config_key/_park_subprocess_worker and CLAUDE.md's
RT-analysis subprocess-isolation section). Pure logic -- no GUI, no Qt event
loop, no real multiprocessing.Process required.
"""
from __future__ import annotations

from glados_pycromanager.GUI.AnalysisClass import (
    _RT_SUBPROCESS_CACHE_MAX_ENTRIES,
    _park_subprocess_worker,
    _rt_config_key,
)


class _FakeSharedData:
    def __init__(self):
        self._rt_subprocess_cache = {}


class _FakeProcess:
    def __init__(self):
        self.terminated = False

    def terminate(self):
        self.terminated = True


def _fake_worker():
    return {
        'process': _FakeProcess(),
        'in_queue': None,
        'out_queue': None,
        'stop_event': None,
        'control_in_queue': None,
        'control_out_queue': None,
        'RT_analysis_object': None,
    }


def test_rt_config_key_is_stable_regardless_of_dict_key_order():
    a = {'__selectedDropdownEntryRTAnalysis__': 'Real-Time FFT', 'LineEdit#a#b': '1'}
    b = {'LineEdit#a#b': '1', '__selectedDropdownEntryRTAnalysis__': 'Real-Time FFT'}
    assert _rt_config_key(a) == _rt_config_key(b)


def test_rt_config_key_differs_for_different_kwargs():
    a = {'__selectedDropdownEntryRTAnalysis__': 'Real-Time FFT', 'LineEdit#a#b': '1'}
    b = {'__selectedDropdownEntryRTAnalysis__': 'Real-Time FFT', 'LineEdit#a#b': '2'}
    assert _rt_config_key(a) != _rt_config_key(b)


def test_rt_config_key_none_for_non_dict_analysis_info():
    # e.g. the plain-string sentinels used elsewhere ('LiveModeVisualisation')
    assert _rt_config_key('LiveModeVisualisation') is None
    assert _rt_config_key(None) is None


def test_park_then_reclaim_round_trip():
    shared_data = _FakeSharedData()
    key = _rt_config_key({'__selectedDropdownEntryRTAnalysis__': 'Real-Time FFT'})
    worker = _fake_worker()

    _park_subprocess_worker(shared_data, key, worker)

    assert key in shared_data._rt_subprocess_cache
    reclaimed = shared_data._rt_subprocess_cache.pop(key)
    assert reclaimed is worker
    assert reclaimed['process'].terminated is False


def test_park_evicts_least_recently_used_over_cap():
    # _park_subprocess_worker stamps last_used = time.time() on every call, so
    # parking these in order (oldest first) is what makes the first one the
    # least-recently-used entry -- ties are broken by dict insertion order,
    # which still points at the first-parked entry.
    shared_data = _FakeSharedData()
    workers = []
    for i in range(_RT_SUBPROCESS_CACHE_MAX_ENTRIES + 1):
        key = _rt_config_key({'__selectedDropdownEntryRTAnalysis__': f'Node {i}'})
        worker = _fake_worker()
        workers.append((key, worker))
        _park_subprocess_worker(shared_data, key, worker)

    assert len(shared_data._rt_subprocess_cache) == _RT_SUBPROCESS_CACHE_MAX_ENTRIES
    # The oldest (lowest last_used) entry should have been evicted + terminated.
    oldest_key, oldest_worker = workers[0]
    assert oldest_key not in shared_data._rt_subprocess_cache
    assert oldest_worker['process'].terminated is True
    # The most recent one must still be present and untouched.
    newest_key, newest_worker = workers[-1]
    assert newest_key in shared_data._rt_subprocess_cache
    assert newest_worker['process'].terminated is False
