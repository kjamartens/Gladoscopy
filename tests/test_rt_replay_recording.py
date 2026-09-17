"""Recording retained RT-analysis results, and the `__replayable__` resolution."""

import numpy as np
import pytest

import glados_pycromanager.GUI.utils as utils
from glados_pycromanager.GUI import rt_history


# --------------------------------------------------------------------------
# utils.realTimeAnalysis_replayable
# --------------------------------------------------------------------------

@pytest.fixture
def fake_entry(monkeypatch):
    """Drive realTimeAnalysis_replayable off a supplied metadata entry."""
    holder = {}

    def _entry(_name):
        return holder.get('entry')

    monkeypatch.setattr(utils, '_nodeFunctionEntry', _entry)
    monkeypatch.setattr(utils, '_rtAnalysisClassName', lambda _info: 'Fake.Node')

    def _set(entry, node_obj=None):
        holder['entry'] = entry
        monkeypatch.setattr(utils, '_resolve_node_obj', lambda _n: node_obj)

    return _set


def test_explicit_replayable_flag_wins(fake_entry):
    fake_entry({'__replayable__': False, '__snapshot_attrs__': ['a']})
    assert utils.realTimeAnalysis_replayable({}) is False
    fake_entry({'__replayable__': True})
    assert utils.realTimeAnalysis_replayable({}) is True


def test_declaring_snapshot_attrs_implies_replayable(fake_entry):
    fake_entry({'__snapshot_attrs__': ['SMLMlocs']})
    assert utils.realTimeAnalysis_replayable({}) is True


def test_a_snapshot_method_implies_replayable(fake_entry):
    class WithSnapshot:
        def snapshot(self):
            return {}

    fake_entry({}, node_obj=WithSnapshot)
    assert utils.realTimeAnalysis_replayable({}) is True


def test_declaring_nothing_is_not_replayable(fake_entry):
    """Conservative by construction: no contract means no replay, rather than a
    silently wrong overlay."""
    class Bare:
        pass

    fake_entry({}, node_obj=Bare)
    assert utils.realTimeAnalysis_replayable({}) is False


def test_unresolvable_node_is_not_replayable(monkeypatch):
    monkeypatch.setattr(utils, '_rtAnalysisClassName',
                        lambda _info: (_ for _ in ()).throw(KeyError('nope')))
    assert utils.realTimeAnalysis_replayable({}) is False


# --------------------------------------------------------------------------
# Recording
# --------------------------------------------------------------------------

class FakeGroup:
    names = ['Layer']
    primary = 'layer'


class FakeSharedData:
    _mdaModeParamsGeneration = 3
    newestLayerName = 'MDA'


def _session(**kw):
    defaults = dict(
        key='node', node=object(), analysis_info={}, group=FakeGroup(),
        is_legacy=False,
        history=rt_history.RTNodeHistory(1024 * 1024, label='TestNode'),
        label='TestNode')
    defaults.update(kw)
    return rt_history.RTReplaySession(**defaults)


@pytest.fixture
def record():
    from glados_pycromanager.GUI.AnalysisClass import _recordReplayFrame
    return _recordReplayFrame


def test_a_frame_is_recorded_under_its_axes(record):
    session = _session()
    metadata = {'Axes': {'time': 4}}
    assert record(session, FakeSharedData(), metadata, {'locs': np.zeros((2, 2))}) is True
    entry = session.history.get(rt_history.axes_key({'time': 4}))
    assert entry is not None
    assert entry.generation == 3


def test_recording_is_skipped_for_a_disabled_session(record):
    session = _session(enabled=False)
    assert record(session, FakeSharedData(), {'Axes': {'time': 0}}, {'a': 1}) is False


def test_an_empty_snapshot_disables_the_session(record):
    """Otherwise replay would re-render the last analysed frame at every scrub
    position and look like it was working."""
    session = _session()
    assert record(session, FakeSharedData(), {'Axes': {'time': 0}}, {}) is False
    assert session.enabled is False


def test_a_frame_without_axes_is_not_recorded(record):
    session = _session()
    assert record(session, FakeSharedData(), {'ImageNumber': 1}, {'a': 1}) is False


def test_no_session_is_harmless(record):
    assert record(None, FakeSharedData(), {'Axes': {'time': 0}}, {'a': 1}) is False


def test_a_failure_disables_retention_rather_than_breaking_the_analysis(record):
    """Retention is a convenience; it must never take an acquisition down."""
    class Exploding:
        label = 'TestNode'
        enabled = True

        def note_snapshot(self, _s):
            raise RuntimeError('boom')

    session = Exploding()
    assert record(session, FakeSharedData(), {'Axes': {'time': 0}}, {'a': 1}) is False
    assert session.enabled is False


def test_recorded_snapshots_survive_the_node_reusing_its_buffer(record):
    """The in-process producer hands over live references."""
    session = _session()
    buffer = np.zeros((4, 4))
    record(session, FakeSharedData(), {'Axes': {'time': 0}}, {'canvas': buffer})
    buffer += 7
    entry = session.history.get(rt_history.axes_key({'time': 0}))
    assert np.all(entry.snapshot['canvas'] == 0)


def test_generation_separates_two_acquisitions(record):
    session = _session()
    shared = FakeSharedData()
    record(session, shared, {'Axes': {'time': 0}}, {'a': 1})
    key = rt_history.axes_key({'time': 0})
    assert session.history.get(key, generation=3) is not None
    #A new plan bumps the generation; the old result must not be replayed onto it.
    assert session.history.get(key, generation=4) is None


# --------------------------------------------------------------------------
# Registry on Shared_data
# --------------------------------------------------------------------------

def test_shared_data_exposes_a_lazily_built_registry():
    from glados_pycromanager.GUI.sharedFunctions import Shared_data
    shared = Shared_data()
    assert shared._rt_replay is None
    registry = shared.rt_replay
    assert isinstance(registry, rt_history.RTReplayRegistry)
    assert shared.rt_replay is registry          # cached


def test_registry_budget_follows_the_configured_setting():
    from glados_pycromanager.GUI.sharedFunctions import Shared_data
    shared = Shared_data()
    shared.config.rt_analysis_config.replay_history_budget_mb = 8
    assert shared.rt_replay.budget_bytes == 8 * 1024 * 1024


def test_a_nonsense_budget_setting_falls_back_to_the_default():
    from glados_pycromanager.GUI.sharedFunctions import Shared_data
    shared = Shared_data()
    shared.config.rt_analysis_config.replay_history_budget_mb = 'not a number'
    assert shared.rt_replay.budget_bytes == rt_history.DEFAULT_HISTORY_BUDGET_MB * 1024 * 1024
