"""The retained RT-analysis result store and its axes keys."""

import logging

import numpy as np
import pytest

from glados_pycromanager.GUI.rt_history import (
    RTNodeHistory,
    RTReplayRegistry,
    RTReplaySession,
    axes_from_current_step,
    axes_key,
)


# --------------------------------------------------------------------------
# axes_key
# --------------------------------------------------------------------------

def test_axes_key_is_order_independent():
    assert axes_key({'time': 1, 'z': 2}) == axes_key({'z': 2, 'time': 1})


def test_axes_key_projects_onto_the_plan_dimensions():
    """A frame's Axes may carry keys the plan does not -- the same subset
    semantics the MDA backfill preserves."""
    axes = {'time': 1, 'z': 2, 'somethingElse': 9}
    assert axes_key(axes, ['time', 'z']) == (('time', 1), ('z', 2))


def test_axes_key_is_none_when_a_plan_dimension_is_missing():
    assert axes_key({'time': 1}, ['time', 'z']) is None


def test_axes_key_normalises_numpy_scalars():
    """Keys are compared against both metadata['Axes'] (plain ints) and
    unique_entries lookups (numpy scalars)."""
    plain = axes_key({'time': 3})
    numpy_ish = axes_key({'time': np.int64(3)})
    assert plain == numpy_ish
    assert isinstance(numpy_ish[0][1], int)


def test_axes_key_of_none_is_none():
    assert axes_key(None) is None


# --------------------------------------------------------------------------
# axes_from_current_step
# --------------------------------------------------------------------------

@pytest.fixture
def plan():
    dim_order = ['time', 'z']
    unique = {'time': np.array([0, 1, 2]), 'z': np.array([10, 20])}
    return dim_order, unique


def test_current_step_maps_back_to_axis_values(plan):
    dim_order, unique = plan
    assert axes_from_current_step([2, 1], dim_order, unique) == {'time': 2, 'z': 20}


def test_longer_current_step_is_fine(plan):
    """A napari layer over a k-dim plan has ndim == k + 2 (y, x)."""
    dim_order, unique = plan
    assert axes_from_current_step([1, 0, 0, 0], dim_order, unique) == {'time': 1, 'z': 10}


def test_shorter_current_step_is_rejected_rather_than_guessed(plan):
    dim_order, unique = plan
    assert axes_from_current_step([1], dim_order, unique) is None


def test_out_of_range_step_is_rejected(plan):
    dim_order, unique = plan
    assert axes_from_current_step([99, 0], dim_order, unique) is None
    assert axes_from_current_step([-1, 0], dim_order, unique) is None


def test_missing_dimension_values_are_rejected(plan):
    dim_order, _ = plan
    assert axes_from_current_step([0, 0], dim_order, {'time': np.array([0])}) is None


def test_no_plan_gives_no_axes():
    assert axes_from_current_step([0], [], {}) is None
    assert axes_from_current_step(None, ['time'], {'time': np.array([0])}) is None


def test_round_trips_with_the_display_path_searchsorted(plan):
    """The display path sets current_step to searchsorted indices; this must be its
    exact inverse, or replay renders the wrong frame's overlay."""
    dim_order, unique = plan
    for t in unique['time']:
        for z in unique['z']:
            step = [int(np.searchsorted(unique[d], v))
                    for d, v in zip(dim_order, (t, z))]
            assert axes_from_current_step(step, dim_order, unique) == {'time': int(t), 'z': int(z)}


# --------------------------------------------------------------------------
# RTNodeHistory
# --------------------------------------------------------------------------

def _history(mb=1.0):
    return RTNodeHistory(int(mb * 1024 * 1024), label='TestNode')


def test_record_and_get_round_trip():
    history = _history()
    key = axes_key({'time': 0})
    assert history.record(key, {'locs': np.zeros((3, 2))}, {'Axes': {'time': 0}}) is True
    entry = history.get(key)
    assert entry is not None
    assert entry.snapshot['locs'].shape == (3, 2)
    assert entry.metadata['Axes'] == {'time': 0}


def test_recording_copies_arrays_so_later_mutation_cannot_reach_history():
    """The in-process path hands over bare references to the node's own attributes,
    which run() may rewrite in place on the next frame."""
    history = _history()
    live = np.zeros((2, 2))
    key = axes_key({'time': 0})
    history.record(key, {'canvas': live})
    live += 5                                    # node reuses its buffer
    assert np.all(history.get(key).snapshot['canvas'] == 0)


def test_recording_copies_nested_containers():
    history = _history()
    live = {'inner': [np.zeros(2)]}
    key = axes_key({'time': 0})
    history.record(key, {'nested': live})
    live['inner'][0] += 1
    assert np.all(history.get(key).snapshot['nested']['inner'][0] == 0)


def test_empty_snapshot_is_not_recorded():
    history = _history()
    assert history.record(axes_key({'time': 0}), {}) is False
    assert len(history) == 0


def test_none_key_is_not_recorded():
    history = _history()
    assert history.record(None, {'a': 1}) is False


def test_zero_budget_disables_recording():
    history = RTNodeHistory(0)
    assert history.record(axes_key({'time': 0}), {'a': np.zeros(10)}) is False
    assert len(history) == 0


def test_byte_accounting_tracks_arrays():
    history = _history()
    history.record(axes_key({'time': 0}), {'a': np.zeros(1000, dtype=np.float64)})
    assert history.nbytes >= 8000


def test_oldest_entries_are_dropped_at_the_budget():
    #Room for ~2 of these.
    history = RTNodeHistory(3 * 8000, label='TestNode')
    for t in range(5):
        history.record(axes_key({'time': t}), {'a': np.zeros(1000, dtype=np.float64)})
    assert history.get(axes_key({'time': 0})) is None      # evicted
    assert history.get(axes_key({'time': 4})) is not None   # newest kept
    assert history.dropped > 0
    assert history.nbytes <= history.budget_bytes


def test_eviction_warns_once_not_per_frame(caplog):
    history = RTNodeHistory(3 * 8000, label='TestNode')
    with caplog.at_level(logging.WARNING):
        for t in range(20):
            history.record(axes_key({'time': t}), {'a': np.zeros(1000, dtype=np.float64)})
    assert caplog.text.count('exceeded their') == 1


def test_re_recording_the_same_frame_replaces_rather_than_accumulates():
    history = _history()
    key = axes_key({'time': 0})
    history.record(key, {'a': np.zeros(1000, dtype=np.float64)})
    first = history.nbytes
    history.record(key, {'a': np.ones(1000, dtype=np.float64)})
    assert len(history) == 1
    assert history.nbytes == first
    assert np.all(history.get(key).snapshot['a'] == 1)


def test_generation_mismatch_reads_as_a_miss():
    """History from a previous acquisition describes a different plan, so replaying
    it would place the wrong overlay on the frame."""
    history = _history()
    key = axes_key({'time': 0})
    history.record(key, {'a': 1}, generation=7)
    assert history.get(key, generation=7) is not None
    assert history.get(key, generation=8) is None
    assert history.get(key) is not None          # unspecified generation = don't care


def test_set_budget_evicts_immediately():
    history = _history()
    for t in range(5):
        history.record(axes_key({'time': t}), {'a': np.zeros(1000, dtype=np.float64)})
    history.set_budget(8000)
    assert history.nbytes <= 8000


def test_clear_resets_size_and_the_warning():
    history = _history()
    history.record(axes_key({'time': 0}), {'a': np.zeros(10)})
    history.clear()
    assert len(history) == 0
    assert history.nbytes == 0


# --------------------------------------------------------------------------
# RTReplaySession / RTReplayRegistry
# --------------------------------------------------------------------------

class FakeGroup:
    def __init__(self, names):
        self.names = names
        self.primary = f'<primary {names[0]}>' if names else None


def _session(key='n1', names=('Layer A',), is_legacy=False, **kw):
    return RTReplaySession(key=key, node=object(), analysis_info={},
                           group=FakeGroup(list(names)), is_legacy=is_legacy,
                           history=_history(), label=key, **kw)


def test_visualisation_target_respects_the_legacy_contract():
    assert _session(is_legacy=True).visualisation_target == '<primary Layer A>'
    assert isinstance(_session(is_legacy=False).visualisation_target, FakeGroup)


def test_session_without_a_group_has_no_target():
    session = _session()
    session.group = None
    assert session.visualisation_target is None


def test_empty_snapshot_disables_replay_once_and_says_why(caplog):
    session = _session()
    with caplog.at_level(logging.INFO):
        assert session.note_snapshot({}) is False
        assert session.note_snapshot({}) is False
    assert session.enabled is False
    assert caplog.text.count('__snapshot_attrs__') == 1


def test_non_empty_snapshot_keeps_replay_enabled():
    session = _session()
    assert session.note_snapshot({'a': 1}) is True
    assert session.enabled is True


def test_registry_registers_and_finds_by_layer_name():
    registry = RTReplayRegistry()
    session = registry.register(_session(names=('raw', 'SR')))
    assert registry.session_for_layer('SR') is session
    assert registry.session_for_layer('unrelated') is None


def test_registry_unregister_clears_the_history():
    registry = RTReplayRegistry()
    session = registry.register(_session())
    session.history.record(axes_key({'time': 0}), {'a': 1})
    registry.unregister(session.key)
    assert len(registry) == 0
    assert len(session.history) == 0


def test_registry_splits_the_budget_across_sessions():
    registry = RTReplayRegistry(budget_bytes=1000)
    a = registry.register(_session(key='a'))
    assert a.history.budget_bytes == 1000
    b = registry.register(_session(key='b'))
    assert a.history.budget_bytes == 500
    assert b.history.budget_bytes == 500


def test_registry_rebalances_when_a_session_goes_away():
    registry = RTReplayRegistry(budget_bytes=1000)
    a = registry.register(_session(key='a'))
    registry.register(_session(key='b'))
    registry.unregister('b')
    assert a.history.budget_bytes == 1000


def test_registry_set_budget_propagates():
    registry = RTReplayRegistry(budget_bytes=1000)
    a = registry.register(_session(key='a'))
    registry.set_budget(4000)
    assert a.history.budget_bytes == 4000


def test_registry_clear_drops_everything():
    registry = RTReplayRegistry()
    registry.register(_session(key='a'))
    registry.clear()
    assert len(registry) == 0
