"""T-D4: the end-of-MDA slice backfill.

The finalisation pass used to be O(N_events x M_rendered) dict-subset
comparisons with a ``time.sleep(0.001)`` **and** a random NDTiff
``read_image()`` per missing frame, all on the GUI thread. Because the
visualisation queue is fps-throttled, "missing" is most of a fast acquisition,
so a large MDA froze the UI for seconds at the end of every run.

It could not simply be deleted: T-D3's every-frame writer only runs on the
``MMCORE_PLUS`` frame-ring path. Both pycromanager callbacks
(``image_process_fn`` / ``image_saved_fn``) do no acquisition-side zarr write at
all, so on those backends the display path is the store's only writer and the
backfill is what makes the finished stack complete.

These tests pin the two halves of what T-D4 actually changed: membership is a
set lookup with subset semantics preserved, and the whole pass is skipped on a
backend with no NDTiff dataset to read from.
"""
from __future__ import annotations

import numpy as np
import pytest

from glados_pycromanager.GUI.napariGlados import (
    _axes_key,
    _backfill_missing_slices,
    _create_mda_zarr,
    _record_rendered_axes,
    _rendered_axes_lookup,
)
from glados_pycromanager.GUI.sharedFunctions import Shared_data


class _FakeDataset:
    """Stands in for the NDTiff `Dataset` the pycromanager backends expose."""

    def __init__(self, shape=(4, 4), dtype=np.uint16):
        self.shape = shape
        self.dtype = dtype
        self.reads = []

    def read_image(self, **axes):
        self.reads.append({k: v for k, v in axes.items() if v is not None})
        return np.full(self.shape, len(self.reads), dtype=self.dtype)


class _FakeAcq:
    def __init__(self, dataset):
        self._dataset = dataset


def _events(channels=('DAPI', 'FITC'), times=(0, 1)):
    return [{'axes': {'channel': c, 'time': t}} for t in times for c in channels]


def _prepare(shared_data, events, h=4, w=4):
    shared_data._mdaModeParams = events
    # Shape must match what getDimensionsFromAcqData derives from the events.
    n_channels = len({e['axes']['channel'] for e in events})
    n_times = len({e['axes']['time'] for e in events})
    return _create_mda_zarr(shared_data, 'MDA', [n_channels, n_times], h, w, np.uint16)


# --- membership ------------------------------------------------------------

def test_axes_key_is_order_independent():
    assert _axes_key({'channel': 'DAPI', 'time': 0}) == _axes_key({'time': 0, 'channel': 'DAPI'})


def test_record_rendered_axes_dedupes_and_initialises(tmp_appdata):
    shared_data = Shared_data()

    _record_rendered_axes(shared_data, {'channel': 'DAPI', 'time': 0})
    _record_rendered_axes(shared_data, {'channel': 'DAPI', 'time': 0})
    _record_rendered_axes(shared_data, {'channel': 'FITC', 'time': 0})

    # A set, not the old running-integer dict: the same slice rendered twice is
    # one entry, and the finalisation lookup is O(1) rather than O(M).
    assert isinstance(shared_data.allMDAslicesRendered, set)
    assert len(shared_data.allMDAslicesRendered) == 2


def test_lookup_preserves_subset_semantics():
    """A rendered frame carries more axes than the event that asked for it.

    `metadata['Axes']` can hold keys the pycromanager event's `axes` does not,
    which is why the original test was `expected.items() <= rendered.items()`.
    Projecting onto the expected key names must keep that behaviour.
    """
    rendered = {_axes_key({'channel': 'DAPI', 'time': 0, 'z': 3})}

    lookup = _rendered_axes_lookup(rendered, ('channel', 'time'))

    assert ('DAPI', 0) in lookup
    assert ('FITC', 0) not in lookup


def test_lookup_ignores_frames_missing_an_expected_axis():
    rendered = {_axes_key({'channel': 'DAPI'})}

    assert _rendered_axes_lookup(rendered, ('channel', 'time')) == set()


# --- the pass itself -------------------------------------------------------

def test_backfill_is_skipped_without_an_ndtiff_dataset(tmp_appdata):
    """MMCORE_PLUS: T-D3 already wrote every frame and there is nothing to read."""
    shared_data = Shared_data()
    _prepare(shared_data, _events())
    shared_data.allMDAslicesRendered = set()

    # _mdaModeAcqData is only ever assigned in the pycromanager Acquisition
    # branches, so on this backend it is absent entirely.
    assert _backfill_missing_slices(shared_data, 'MDA') == 0


def test_backfill_only_reads_the_slices_that_are_missing(tmp_appdata):
    shared_data = Shared_data()
    array = _prepare(shared_data, _events())
    shared_data.allMDAslicesRendered = set()
    # Two of the four expected frames made it through the fps-throttled display.
    _record_rendered_axes(shared_data, {'channel': 'DAPI', 'time': 0})
    _record_rendered_axes(shared_data, {'channel': 'FITC', 'time': 1})

    dataset = _FakeDataset()
    shared_data._mdaModeAcqData = _FakeAcq(dataset)

    filled = _backfill_missing_slices(shared_data, 'MDA')

    assert filled == 2
    assert dataset.reads == [
        {'channel': 'FITC', 'time': 0},
        {'channel': 'DAPI', 'time': 1},
    ]
    # ... and they landed in the store, at the indices the dimension map gives.
    assert array[1, 0, 0, 0] == 1
    assert array[0, 1, 0, 0] == 2
    # The two already-rendered slices were left untouched (still zeros here,
    # since this test never ran the display path that would have written them).
    assert array[0, 0, 0, 0] == 0
    assert array[1, 1, 0, 0] == 0


def test_backfill_fills_everything_when_nothing_was_rendered(tmp_appdata):
    shared_data = Shared_data()
    _prepare(shared_data, _events())
    shared_data.allMDAslicesRendered = set()
    shared_data._mdaModeAcqData = _FakeAcq(_FakeDataset())

    assert _backfill_missing_slices(shared_data, 'MDA') == 4


def test_backfill_survives_a_slice_the_dataset_never_acquired(tmp_appdata):
    """A cancelled MDA: the events exist, the frames do not."""
    class _Empty(_FakeDataset):
        def read_image(self, **axes):
            raise IndexError('not acquired')

    shared_data = Shared_data()
    _prepare(shared_data, _events())
    shared_data.allMDAslicesRendered = set()
    shared_data._mdaModeAcqData = _FakeAcq(_Empty())

    assert _backfill_missing_slices(shared_data, 'MDA') == 0


def test_backfill_does_not_sleep_per_missing_frame(tmp_appdata, monkeypatch):
    """The freeze this task exists to remove: 1 ms of sleep per missing slice."""
    import glados_pycromanager.GUI.napariGlados as ng

    calls = []
    monkeypatch.setattr(ng.time, 'sleep', lambda s: calls.append(s))

    shared_data = Shared_data()
    _prepare(shared_data, _events(times=range(50)))
    shared_data.allMDAslicesRendered = set()
    shared_data._mdaModeAcqData = _FakeAcq(_FakeDataset())

    _backfill_missing_slices(shared_data, 'MDA')

    assert calls == []


@pytest.mark.parametrize('rendered_count', [0, 5, 25])
def test_backfill_cost_does_not_scale_with_rendered_count(tmp_appdata, rendered_count):
    """The O(N x M) half: lookups must not grow with how much was rendered."""
    shared_data = Shared_data()
    events = _events(times=range(50))
    _prepare(shared_data, events)
    shared_data.allMDAslicesRendered = set()
    for event in events[:rendered_count]:
        _record_rendered_axes(shared_data, dict(event['axes']))
    shared_data._mdaModeAcqData = _FakeAcq(_FakeDataset())

    assert _backfill_missing_slices(shared_data, 'MDA') == len(events) - rendered_count
