"""Regression test for the getLayerIdFromName layer-lookup cache.

The live/MDA per-frame display path previously did a full linear scan over
every napari layer, every frame, just to find the index of one named layer.
getLayerIdFromName now accepts an optional shared_data to cache the last
known index per layer name, validated with an O(1) name check before being
trusted (so a removed/reordered/recreated layer still resolves correctly).
"""

from types import SimpleNamespace

from glados_pycromanager.GUI.napariHelperFunctions import getLayerIdFromName


class _FakeLayer:
    def __init__(self, name):
        self._name = name


class _FakeLayers(list):
    """Minimal stand-in for napari's LayerList - just needs len()/indexing."""


def _make_viewer(names):
    return SimpleNamespace(layers=_FakeLayers(_FakeLayer(n) for n in names))


def test_lookup_without_shared_data_scans_every_call():
    viewer = _make_viewer(["Live", "MDA"])
    assert getLayerIdFromName("MDA", viewer) == [1]
    assert getLayerIdFromName("MDA", viewer) == [1]


def test_lookup_with_shared_data_populates_and_reuses_cache():
    shared_data = SimpleNamespace()
    viewer = _make_viewer(["Live", "MDA"])

    result = getLayerIdFromName("MDA", viewer, shared_data)

    assert result == [1]
    assert shared_data._layer_id_cache == {"MDA": 1}

    # Second call should hit the cache path (same result, cache untouched).
    result2 = getLayerIdFromName("MDA", viewer, shared_data)
    assert result2 == [1]


def test_cache_self_heals_when_layer_order_changes():
    shared_data = SimpleNamespace()
    viewer = _make_viewer(["Live", "MDA"])
    getLayerIdFromName("MDA", viewer, shared_data)
    assert shared_data._layer_id_cache["MDA"] == 1

    # Simulate a layer being removed in front of 'MDA', shifting its index.
    viewer.layers.pop(0)
    assert viewer.layers[0]._name == "MDA"

    # Stale cached index (1) is now out of range/mismatched; must self-heal.
    result = getLayerIdFromName("MDA", viewer, shared_data)
    assert result == [0]
    assert shared_data._layer_id_cache["MDA"] == 0


def test_missing_layer_returns_empty_and_does_not_cache():
    shared_data = SimpleNamespace()
    viewer = _make_viewer(["Live"])

    result = getLayerIdFromName("DoesNotExist", viewer, shared_data)

    assert result == []
    assert shared_data._layer_id_cache == {}
