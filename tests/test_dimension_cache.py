"""T-D5: `_get_cached_dimensions` must key on acquisition identity, not `id()`.

The cache used to be keyed on `id(shared_data._mdaModeParams)`. A memory
address is not an identity: CPython reuses the addresses of freed objects, so
once one acquisition's event list was released, the next acquisition's list
could be allocated at the very same address and the cache would hand back the
*previous* acquisition's dimension map. Every `sliceTuple`, the zarr store's
shape and the napari dims stepping derive from that map, so the second of two
back-to-back differently-shaped MDAs would render into the first one's grid.

These tests pin the replacement: a generation counter bumped by the
`_mdaModeParams` setter.
"""
from __future__ import annotations

import useq

from glados_pycromanager.GUI.napariGlados import _get_cached_dimensions
from glados_pycromanager.GUI.sharedFunctions import Shared_data


def _events(dim, n):
    return [{"axes": {dim: i}} for i in range(n)]


def test_reassignment_recomputes_the_dimensions(tmp_appdata):
    shared_data = Shared_data()

    shared_data._mdaModeParams = _events("time", 3)
    dim_order, n_entries, _ = _get_cached_dimensions(shared_data)
    assert dim_order == ["time"]
    assert n_entries == [3]

    shared_data._mdaModeParams = _events("z", 7)
    dim_order, n_entries, _ = _get_cached_dimensions(shared_data)
    assert dim_order == ["z"]
    assert n_entries == [7]


def test_a_recycled_address_does_not_return_the_previous_map(tmp_appdata):
    """The actual `id()` failure mode, made deterministic.

    Rather than gambling on the allocator, drive the exact state the old code
    could reach: a second params list reported at the first one's address.
    """
    shared_data = Shared_data()

    first = _events("time", 3)
    shared_data._mdaModeParams = first
    assert _get_cached_dimensions(shared_data)[1] == [3]

    second = _events("time", 9)
    shared_data._mdaModeParams = second
    # Simulate the collision: had the key still been id(), this would be a hit.
    shared_data._dims_cache = (id(second), ([], [3], {}))

    assert _get_cached_dimensions(shared_data)[1] == [9]


def test_repeated_reads_of_one_acquisition_hit_the_cache(tmp_appdata):
    shared_data = Shared_data()
    shared_data._mdaModeParams = _events("time", 4)

    first = _get_cached_dimensions(shared_data)
    second = _get_cached_dimensions(shared_data)
    assert second is first  # same tuple object -- not recomputed


def test_a_cached_none_is_not_mistaken_for_an_empty_cache(tmp_appdata):
    """getDimensionsFromAcqData returns None for an empty event list."""
    shared_data = Shared_data()
    shared_data._mdaModeParams = []

    assert _get_cached_dimensions(shared_data) is None
    generation = shared_data._mdaModeParamsGeneration
    assert _get_cached_dimensions(shared_data) is None
    # Still the same generation entry, i.e. it was served from the cache rather
    # than recomputed because None read as "nothing cached yet".
    assert shared_data._dims_cache == (generation, None)


def test_the_lazy_useq_conversion_does_not_bump_the_generation(tmp_appdata):
    """Materialising a sequence is the same acquisition, just converted."""
    shared_data = Shared_data()
    shared_data._mdaModeParams = useq.MDASequence(
        time_plan={"interval": 0.0, "loops": 5}
    )

    generation = shared_data._mdaModeParamsGeneration
    dim_order, n_entries, _ = _get_cached_dimensions(shared_data)
    assert n_entries == [5]
    assert shared_data._mdaModeParamsGeneration == generation

    # ...and the now-materialised list still serves from the same cache entry.
    assert _get_cached_dimensions(shared_data)[1] == [5]
    assert shared_data._dims_cache[0] == generation


def test_the_generation_advances_on_every_assignment(tmp_appdata):
    shared_data = Shared_data()
    start = shared_data._mdaModeParamsGeneration
    shared_data._mdaModeParams = _events("time", 1)
    shared_data._mdaModeParams = _events("time", 1)
    assert shared_data._mdaModeParamsGeneration == start + 2
