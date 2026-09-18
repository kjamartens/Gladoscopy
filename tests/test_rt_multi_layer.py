"""`napariOverlay` wiring: what a node's `visualise()` actually receives.

The load-bearing guarantee is that a node declaring its layers the legacy
`(name, type)` way keeps receiving the bare napari layer, so none of the shipped
nodes change behaviour. Only a node that opts in by returning a list sees the group.
"""

import sys
import types

import numpy as np
import pytest


class FakeExtent:
    def __init__(self, world):
        self.world = np.asarray(world, dtype=float)


class FakeLayer:
    def __init__(self, name, shape=(100, 100), scale=(1.0, 1.0)):
        self.name = name
        self.shape = shape
        self.scale = np.asarray(scale, dtype=float)
        self.translate = np.asarray([0.0, 0.0])
        self.data = None

    @property
    def extent(self):
        mins = self.translate
        maxs = self.translate + self.scale * np.asarray(self.shape, dtype=float)
        return FakeExtent([mins, maxs])


class FakeLayerList(list):
    def __contains__(self, name):
        return any(layer.name == name for layer in list.__iter__(self))

    def __getitem__(self, key):
        if isinstance(key, str):
            for layer in list.__iter__(self):
                if layer.name == key:
                    return layer
            raise KeyError(key)
        return list.__getitem__(self, key)

    def remove(self, key):
        name = key if isinstance(key, str) else key.name
        for layer in list.__iter__(self):
            if layer.name == name:
                list.remove(self, layer)
                return
        raise ValueError(name)


class FakeViewer:
    def __init__(self, existing=()):
        self.layers = FakeLayerList(existing)

    def _add(self, *args, **kwargs):
        layer = FakeLayer(kwargs['name'], scale=kwargs.get('scale', (1.0, 1.0)))
        self.layers.append(layer)
        return layer

    add_image = add_points = add_shapes = add_labels = _add
    add_surface = add_tracks = add_vectors = _add


class LegacyNode:
    """A node written against the historical contract."""

    def __init__(self):
        self.seen = None

    def visualise_init(self):
        return ('Legacy layer', 'points')

    def visualise(self, image, metadata, core, napariLayer, **kwargs):
        self.seen = napariLayer
        return napariLayer


class MultiLayerNode:
    """A node that opted into the group API."""

    def __init__(self):
        self.seen = None

    def visualise_init(self):
        return [
            {'name': 'Demo: analysed frame', 'type': 'image'},
            {'name': 'Demo: peaks', 'type': 'points'},
            {'name': 'Demo: SR', 'type': 'image', 'placement': 'right'},
        ]

    def visualise(self, image, metadata, core, napariLayer, **kwargs):
        self.seen = napariLayer
        napariLayer['Demo: analysed frame'].data = image
        return napariLayer


@pytest.fixture
def overlay_cls():
    """Import napariOverlay without dragging in Qt/napari at module import time."""
    pytest.importorskip('numpy')
    from glados_pycromanager.GUI.AnalysisClass import napariOverlay
    return napariOverlay


# --------------------------------------------------------------------------
# Legacy nodes are untouched
# --------------------------------------------------------------------------

def test_legacy_node_gets_one_layer_and_is_flagged_legacy(overlay_cls):
    viewer = FakeViewer()
    overlay = overlay_cls(viewer, RT_analysisObject=LegacyNode())
    assert overlay.is_legacy is True
    assert overlay.group.names == ['Legacy layer']
    assert overlay.layer is overlay.group.primary
    assert overlay.layer_name == 'Legacy layer'
    assert overlay.layerType == 'points'


def test_legacy_node_receives_the_bare_layer_not_a_group(overlay_cls):
    """The whole back-compat promise, asserted directly."""
    from glados_pycromanager.GUI.layer_group import NapariLayerGroup
    viewer = FakeViewer()
    overlay = overlay_cls(viewer, RT_analysisObject=LegacyNode())
    target = overlay.layer if overlay.is_legacy else overlay.group
    assert isinstance(target, FakeLayer)
    assert not isinstance(target, NapariLayerGroup)


def test_overlay_without_an_rt_object_still_builds_its_named_layer(overlay_cls):
    viewer = FakeViewer()
    overlay = overlay_cls(viewer, layer_name='Manual', layerType='shapes')
    assert overlay.is_legacy is True
    assert overlay.layer.name == 'Manual'


def test_overlay_with_no_layer_name_creates_nothing_and_does_not_deref(overlay_cls):
    """napariOverlay(layer_name=None) legitimately has no `.layer`; the teardown
    paths must go through `.group` for exactly this reason."""
    viewer = FakeViewer()
    overlay = overlay_cls(viewer, layer_name=None)
    assert overlay.group.names == []
    assert len(viewer.layers) == 0
    assert not hasattr(overlay, 'layer')
    assert overlay.group.primary is None


def test_none_layer_type_still_falls_back_to_shapes(overlay_cls):
    viewer = FakeViewer()
    overlay = overlay_cls(viewer, layer_name='Fallback', layerType=None)
    assert overlay.layerType == 'shapes'


# --------------------------------------------------------------------------
# Opted-in nodes
# --------------------------------------------------------------------------

def test_multi_layer_node_gets_every_declared_layer(overlay_cls):
    viewer = FakeViewer()
    overlay = overlay_cls(viewer, RT_analysisObject=MultiLayerNode())
    assert overlay.is_legacy is False
    assert overlay.group.names == ['Demo: analysed frame', 'Demo: peaks', 'Demo: SR']
    assert len(viewer.layers) == 3


def test_multi_layer_node_can_address_its_layers_by_name(overlay_cls):
    viewer = FakeViewer()
    node = MultiLayerNode()
    overlay = overlay_cls(viewer, RT_analysisObject=node)
    image = np.arange(4).reshape(2, 2)
    node.visualise(image, {}, None, overlay.group)
    assert np.array_equal(overlay.group['Demo: analysed frame'].data, image)


def test_side_by_side_layer_is_offset(overlay_cls):
    viewer = FakeViewer()
    overlay = overlay_cls(viewer, RT_analysisObject=MultiLayerNode())
    assert overlay.group['Demo: SR'].translate[-1] > 0
    assert overlay.group['Demo: peaks'].translate[-1] == pytest.approx(0.0)


def test_placement_uses_the_acquisition_layer_when_there_is_one(overlay_cls):
    """An SR panel should sit beside the image the node analysed, not beside its
    own 32x32 placeholder."""
    acquisition = FakeLayer('MDA', shape=(512, 512))
    viewer = FakeViewer(existing=[acquisition])

    class SharedData:
        newestLayerName = 'MDA'

    overlay = overlay_cls(viewer, RT_analysisObject=MultiLayerNode(),
                          shared_data=SharedData())
    assert overlay.group['Demo: SR'].translate[-1] > 512.0


def test_refresh_placement_is_a_no_op_when_nothing_moved(overlay_cls):
    viewer = FakeViewer()
    overlay = overlay_cls(viewer, RT_analysisObject=MultiLayerNode())
    assert overlay.refreshPlacement() is False


def test_refresh_placement_follows_a_changed_frame_size(overlay_cls):
    viewer = FakeViewer()
    overlay = overlay_cls(viewer, RT_analysisObject=MultiLayerNode())
    before = float(overlay.group['Demo: SR'].translate[-1])
    overlay.group['Demo: analysed frame'].shape = (100, 400)
    assert overlay.refreshPlacement() is True
    assert float(overlay.group['Demo: SR'].translate[-1]) > before


def test_overlay_with_no_layers_refreshes_placement_harmlessly(overlay_cls):
    overlay = overlay_cls(FakeViewer(), layer_name=None)
    assert overlay.refreshPlacement() is False


# --------------------------------------------------------------------------
# Teardown
# --------------------------------------------------------------------------

def test_removing_the_group_removes_every_layer(overlay_cls):
    viewer = FakeViewer()
    overlay = overlay_cls(viewer, RT_analysisObject=MultiLayerNode())
    overlay.group.remove_all(viewer)
    assert len(viewer.layers) == 0


def test_group_membership_is_how_teardown_matches_a_removed_layer(overlay_cls):
    """`layer_removed_event_callback` matches on group membership, so closing any
    one of a node's layers must identify that node."""
    viewer = FakeViewer()
    overlay = overlay_cls(viewer, RT_analysisObject=MultiLayerNode())
    for name in ('Demo: analysed frame', 'Demo: peaks', 'Demo: SR'):
        assert name in overlay.group.names
    assert 'Some other layer' not in overlay.group.names
