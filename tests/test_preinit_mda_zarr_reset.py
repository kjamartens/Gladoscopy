"""_preinit_mda_zarr must discard a stale multiDstack store, not reuse it.

Two real-hardware bugs both traced back to the same root cause: a
`shared_data.mdaZarrData[layerName]` array left over from a *previous*
acquisition (same layer name, e.g. the default "MDA") was reused as-is for a
new acquisition without checking whether its shape still matched:

* `_preinit_mda_zarr` only ever checked `is not None` and returned early,
  so a store pre-created for an acquisition with a different number of
  non-image dimensions (e.g. a previous z-stack under the same layer name)
  was written into as though it still had that shape -- every
  `ZarrFrameWriter` write then raised "too many indices"/"could not
  broadcast" and every frame of the acquisition was lost.
* The equivalent reuse in the display-path fallback additionally never
  compared the trailing image-plane (h, w) at all, so a ROI/binning change
  between two acquisitions that happened to have the same leading dim
  counts (e.g. both "5 time points") went undetected there too.

These tests pin `_preinit_mda_zarr`'s fix: reusing a store only when its
full shape (leading dims *and* h/w) and dtype already match, discarding and
recreating it otherwise.
"""
from __future__ import annotations

import numpy as np

import glados_pycromanager.GUI.napariGlados as napariGlados
from glados_pycromanager.GUI.sharedFunctions import Shared_data
from tests.fakes.fake_mil import FakeMicroscopeInterfaceLayer


def _handler_for(shared_data):
    handler = object.__new__(napariGlados.napariHandler)
    handler.shared_data = shared_data
    return handler


def _pycromanager_events(**axes_values):
    """Build the pycromanager-style event list `_get_cached_dimensions` reads.

    One event per combination of the given per-axis values, each carrying an
    `'axes'` dict -- the same shape `useq.pycromanager.to_pycromanager()`
    produces and what `getDimensionsFromAcqData` walks.
    """
    import itertools

    names = list(axes_values)
    events = []
    for combo in itertools.product(*axes_values.values()):
        events.append({"axes": dict(zip(names, combo))})
    return events


def _seed_mil(shared_data, h, w):
    mil = FakeMicroscopeInterfaceLayer()
    mil.set_image(np.zeros((h, w), dtype=np.uint16))
    # Bypass the MILcore setter: it probes for set_hardware_mirror (T-B2),
    # which is not part of what this test exercises and the fake raises
    # NotImplementedError for anything not explicitly stubbed.
    shared_data._MILcore = mil


def test_a_fresh_store_is_created_when_none_exists(tmp_appdata):
    shared_data = Shared_data()
    shared_data.newestLayerName = "MDA"
    _seed_mil(shared_data, 8, 6)
    shared_data._mdaModeParams = _pycromanager_events(time=range(3))

    handler = _handler_for(shared_data)
    assert handler._preinit_mda_zarr(shared_data) is True
    assert tuple(shared_data.mdaZarrData["MDA"].shape) == (3, 8, 6)


def test_a_matching_store_is_reused_not_recreated(tmp_appdata):
    shared_data = Shared_data()
    shared_data.newestLayerName = "MDA"
    _seed_mil(shared_data, 8, 6)
    shared_data._mdaModeParams = _pycromanager_events(time=range(3))

    handler = _handler_for(shared_data)
    handler._preinit_mda_zarr(shared_data)
    array_first = shared_data.mdaZarrData["MDA"]

    # Same acquisition shape again (e.g. a second call in the same run) --
    # must not be discarded.
    assert handler._preinit_mda_zarr(shared_data) is False
    assert shared_data.mdaZarrData["MDA"] is array_first


def test_a_store_with_a_different_leading_dim_count_is_replaced(tmp_appdata):
    """Regression: a previous z-stack's store reused for a t-only acquisition."""
    shared_data = Shared_data()
    shared_data.newestLayerName = "MDA"
    _seed_mil(shared_data, 8, 6)

    # Previous acquisition: a (t=2, z=3) stack.
    shared_data._mdaModeParams = _pycromanager_events(time=range(2), z=range(3))
    handler = _handler_for(shared_data)
    handler._preinit_mda_zarr(shared_data)
    stale_array = shared_data.mdaZarrData["MDA"]
    assert tuple(stale_array.shape) == (2, 3, 8, 6)

    # New acquisition under the same layer name: t-only, 5 points.
    shared_data._mdaModeParams = _pycromanager_events(time=range(5))
    assert handler._preinit_mda_zarr(shared_data) is True
    new_array = shared_data.mdaZarrData["MDA"]
    assert new_array is not stale_array
    assert tuple(new_array.shape) == (5, 8, 6)


def test_a_store_with_a_different_frame_size_is_replaced(tmp_appdata):
    """Regression: a ROI/binning change between two acquisitions with the same
    leading dim counts (both "5 time points") left the frame size stale."""
    shared_data = Shared_data()
    shared_data.newestLayerName = "MDA"
    shared_data._mdaModeParams = _pycromanager_events(time=range(5))

    _seed_mil(shared_data, 3200, 3200)
    handler = _handler_for(shared_data)
    handler._preinit_mda_zarr(shared_data)
    stale_array = shared_data.mdaZarrData["MDA"]
    assert tuple(stale_array.shape) == (5, 3200, 3200)

    # Binning changed: same 5 time points, smaller frames.
    _seed_mil(shared_data, 1600, 1600)
    assert handler._preinit_mda_zarr(shared_data) is True
    new_array = shared_data.mdaZarrData["MDA"]
    assert new_array is not stale_array
    assert tuple(new_array.shape) == (5, 1600, 1600)
