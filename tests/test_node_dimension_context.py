"""Tests for T-G8: nodes read a cached acquisition dimension map.

`pSMLM` and `RT_counter` called `utils.getDimensionsFromAcqData` uncached inside
`run()`, walking every event of the plan -- all 999 of a live-mode one -- in pure
Python on every frame, holding the GIL. Reading `_mdaModeParams` at all also
triggers its lazy useq -> pycromanager conversion.
"""
from __future__ import annotations

from types import SimpleNamespace

import pandas as pd
import pytest

import glados_pycromanager.GUI.utils as utils
from glados_pycromanager.AutonomousMicroscopy.Real_Time_Analysis.pSMLM import (
    SMLM_FRAME_COMPACTION_THRESHOLD,
    pSMLM,
)


class _CountingSharedData:
    """Stands in for Shared_data: counts how often the plan is actually read."""

    def __init__(self, events):
        self._events = events
        self._mdaModeParamsGeneration = 0
        self.reads = 0

    @property
    def _mdaModeParams(self):
        self.reads += 1
        return self._events


def _events(n_time=5, n_z=3):
    return [{'axes': {'time': t, 'z': z}} for t in range(n_time) for z in range(n_z)]


def test_the_plan_is_walked_once_per_acquisition():
    shared_data = _CountingSharedData(_events())
    first = utils.getAcquisitionDimensions(shared_data)
    for _ in range(200):
        utils.getAcquisitionDimensions(shared_data)
    assert shared_data.reads == 1
    dimOrder, n_entries, unique = first
    assert dimOrder == ['time', 'z']
    assert n_entries == [5, 3]
    assert list(unique['z']) == [0, 1, 2]


def test_a_new_acquisition_invalidates_the_map():
    shared_data = _CountingSharedData(_events())
    utils.getAcquisitionDimensions(shared_data)
    shared_data._events = _events(n_time=2, n_z=4)
    shared_data._mdaModeParamsGeneration += 1
    dimOrder, n_entries, _unique = utils.getAcquisitionDimensions(shared_data)
    assert n_entries == [2, 4]
    assert shared_data.reads == 2


def test_a_cached_none_is_not_mistaken_for_a_cold_cache():
    """getDimensionsFromAcqData legitimately returns None for an empty plan."""
    shared_data = _CountingSharedData([])
    assert utils.getAcquisitionDimensions(shared_data) is None
    assert utils.getAcquisitionDimensions(shared_data) is None
    assert shared_data.reads == 1


def test_no_shared_data_is_tolerated():
    """A subprocess-isolated node is handed shared_data=None inside run()."""
    assert utils.getAcquisitionDimensions(None) is None


def test_a_plain_object_without_a_generation_still_works_uncached():
    shared_data = SimpleNamespace(_mdaModeParams=_events(n_time=2, n_z=2))
    dimOrder, n_entries, _unique = utils.getAcquisitionDimensions(shared_data)
    assert dimOrder == ['time', 'z']
    assert n_entries == [2, 2]


def test_napari_glados_delegates_to_the_shared_helper():
    from glados_pycromanager.GUI import napariGlados

    shared_data = _CountingSharedData(_events())
    # Same cached tuple object, not merely an equal one (its members are
    # numpy arrays, which do not compare cleanly with ==).
    assert napariGlados._get_cached_dimensions(shared_data) is utils.getAcquisitionDimensions(shared_data)
    assert shared_data.reads == 1


# --- pSMLM accumulation is bounded in object count, not in data ------------

class _FakeCore:
    def get_pixel_size_um(self):
        return 1.0


def test_psmlm_frames_are_compacted_without_losing_localizations():
    node = pSMLM(core=_FakeCore(), ROIradius=3, stdmult=2)
    total = SMLM_FRAME_COMPACTION_THRESHOLD + 5
    for i in range(total):
        node._append_smlm_frame(pd.DataFrame({"x_pos": [float(i)], "y_pos": [float(i)]}))

    # The list is bounded ...
    assert len(node._smlm_frames) <= 6
    # ... but not one localization was dropped.
    full = node.fullSMLMlocs
    assert len(full) == total
    assert list(full["x_pos"])[:3] == [0.0, 1.0, 2.0]
    assert list(full["x_pos"])[-1] == float(total - 1)


def test_psmlm_below_the_threshold_is_untouched():
    node = pSMLM(core=_FakeCore(), ROIradius=3, stdmult=2)
    frames = [pd.DataFrame({"x_pos": [float(i)], "y_pos": [float(i)]}) for i in range(10)]
    for frame in frames:
        node._append_smlm_frame(frame)
    # Same objects, no copying, exactly as before compaction was introduced.
    for original, stored in zip(frames, node._smlm_frames):
        assert stored is original
