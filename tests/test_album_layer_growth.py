"""T-E4: album mode grows a buffer in place instead of np.append + recreate.

`addToExistingOrNewLayer` used to `np.append` the new frame onto the whole
stack -- copying every frame already in it, so O(N^2) bytes over a session --
and then **destroy the napari layer and rebuild it** with `add_image`, copying
a dozen display properties across and forcing a full texture re-upload, on
every snap. The two-frame case also allocated with a bare `np.zeros(...)`,
which is float64, silently upcasting a uint16 camera stack to 4x its size.

It now appends into a geometrically grown buffer and hands napari a view of the
filled part. What these tests pin: the frames come out correct and in order,
the dtype is the camera's, the layer object survives, and the copying is
amortized rather than quadratic.
"""
from __future__ import annotations

from types import SimpleNamespace

import numpy as np
import pytest

from glados_pycromanager.GUI import napariHelperFunctions as nhf
from glados_pycromanager.GUI.napariHelperFunctions import (
    ALBUM_GROWTH_FACTOR,
    ALBUM_INITIAL_CAPACITY,
    addToExistingOrNewLayer,
)


class _FakeLayer:
    def __init__(self, name, data):
        self._name = name
        self.name = name
        self.data = data
        self.metadata = {}
        self.scale = [1, 1]
        self._keep_auto_contrast = True


class _FakeLayers(list):
    def remove(self, layer):  # pragma: no cover - must never be reached now
        raise AssertionError('album append must not destroy the layer')


class _FakeDims:
    def __init__(self):
        self.steps = []

    def set_current_step(self, axis, value):
        self.steps.append((axis, value))


class _FakeViewer:
    def __init__(self):
        self.layers = _FakeLayers()
        self.dims = _FakeDims()
        self.added = []

    def add_image(self, data, name=None, **kwargs):
        layer = _FakeLayer(name, data)
        self.layers.append(layer)
        self.added.append(layer)
        return layer

    def reset_view(self):
        pass


@pytest.fixture
def viewer(monkeypatch):
    # The real one selects layers through napari's LayerList API; irrelevant here.
    monkeypatch.setattr(nhf, 'moveLayerToTop', lambda *a, **k: None)
    return _FakeViewer()


@pytest.fixture
def shared_data():
    return SimpleNamespace(MILcore=SimpleNamespace(get_pixel_size_um=lambda: 0.1))


def _snap(viewer, shared_data, value, dtype=np.uint16, shape=(4, 6)):
    image = np.full(shape, value, dtype=dtype)
    addToExistingOrNewLayer(viewer, 'Album', image, shared_data_throughput=shared_data)
    return image


def test_first_snap_creates_a_two_dimensional_layer(viewer, shared_data):
    _snap(viewer, shared_data, 7)
    assert len(viewer.layers) == 1
    assert viewer.layers[0].data.shape == (4, 6)


def test_twenty_snaps_are_all_present_and_in_order(viewer, shared_data):
    for value in range(20):
        _snap(viewer, shared_data, value)

    data = viewer.layers[0].data
    assert data.shape == (20, 4, 6)
    for value in range(20):
        assert np.array_equal(data[value], np.full((4, 6), value, dtype=np.uint16))


def test_stack_keeps_the_cameras_dtype(viewer, shared_data):
    # The two-frame step is where the old float64 upcast happened.
    _snap(viewer, shared_data, 1)
    _snap(viewer, shared_data, 2)
    assert viewer.layers[0].data.dtype == np.uint16

    for value in range(3, 10):
        _snap(viewer, shared_data, value)
    assert viewer.layers[0].data.dtype == np.uint16


def test_uint8_camera_stays_uint8(viewer, shared_data):
    for value in range(5):
        _snap(viewer, shared_data, value, dtype=np.uint8)
    assert viewer.layers[0].data.dtype == np.uint8


def test_the_layer_object_is_never_replaced(viewer, shared_data):
    _snap(viewer, shared_data, 0)
    layer = viewer.layers[0]
    for value in range(1, 12):
        _snap(viewer, shared_data, value)
    # One add_image call in total: the create branch. Everything after it
    # mutates the same layer, so display properties survive for free and there
    # is no texture rebuild.
    assert viewer.layers[0] is layer
    assert len(viewer.added) == 1


def test_display_properties_survive_appends(viewer, shared_data):
    _snap(viewer, shared_data, 0)
    layer = viewer.layers[0]
    layer.contrast_limits = [10, 200]
    layer.gamma = 0.5
    for value in range(1, 6):
        _snap(viewer, shared_data, value)
    assert layer.contrast_limits == [10, 200]
    assert layer.gamma == 0.5


def test_dims_step_points_at_the_newest_frame(viewer, shared_data):
    for value in range(5):
        _snap(viewer, shared_data, value)
    axis, step = viewer.dims.steps[-1]
    assert axis == 0
    # Frames 0..4 are present, so the newest is index 4 -- not 5, which the old
    # code passed and relied on napari clamping.
    assert step == 4
    assert np.array_equal(viewer.layers[0].data[step],
                          np.full((4, 6), 4, dtype=np.uint16))


def test_buffer_grows_geometrically_not_per_frame(viewer, shared_data):
    for value in range(ALBUM_INITIAL_CAPACITY + 1):
        _snap(viewer, shared_data, value)

    buffer = viewer.layers[0].metadata[nhf.ALBUM_BUFFER_KEY]
    # One doubling, not one reallocation per frame.
    assert buffer.shape[0] == ALBUM_INITIAL_CAPACITY * ALBUM_GROWTH_FACTOR
    assert viewer.layers[0].metadata[nhf.ALBUM_COUNT_KEY] == ALBUM_INITIAL_CAPACITY + 1


def test_appends_do_not_reallocate_while_capacity_remains(viewer, shared_data):
    _snap(viewer, shared_data, 0)
    _snap(viewer, shared_data, 1)
    buffer = viewer.layers[0].metadata[nhf.ALBUM_BUFFER_KEY]

    _snap(viewer, shared_data, 2)
    # Same buffer object: the frame was written into spare capacity, and the
    # layer got a longer view of it. No copy of the existing frames at all.
    assert viewer.layers[0].metadata[nhf.ALBUM_BUFFER_KEY] is buffer


def test_layer_data_is_a_view_of_the_buffer(viewer, shared_data):
    for value in range(3):
        _snap(viewer, shared_data, value)
    layer = viewer.layers[0]
    buffer = layer.metadata[nhf.ALBUM_BUFFER_KEY]
    assert layer.data.base is buffer
    assert layer.data.shape[0] == layer.metadata[nhf.ALBUM_COUNT_KEY]


def test_bookkeeping_rebuilds_when_the_frame_shape_changes(viewer, shared_data):
    for value in range(3):
        _snap(viewer, shared_data, value, shape=(4, 6))
    # A ROI change mid-album: the old frames cannot be stacked with the new one
    # at all, so a fresh stack starts around the new shape. `np.append` raised
    # ValueError here before.
    _snap(viewer, shared_data, 9, shape=(8, 8))
    data = viewer.layers[0].data
    assert data.shape == (1, 8, 8)
    assert np.array_equal(data[-1], np.full((8, 8), 9, dtype=np.uint16))

    # And the new stack grows normally from there.
    _snap(viewer, shared_data, 10, shape=(8, 8))
    assert viewer.layers[0].data.shape == (2, 8, 8)


def test_external_data_assignment_is_recovered_from(viewer, shared_data):
    for value in range(3):
        _snap(viewer, shared_data, value)
    layer = viewer.layers[0]
    # Something outside this function replaced the stack; the stale count must
    # not be trusted to index the new data.
    layer.data = np.zeros((7, 4, 6), dtype=np.uint16)

    _snap(viewer, shared_data, 5)

    assert layer.data.shape == (8, 4, 6)
    assert np.array_equal(layer.data[-1], np.full((4, 6), 5, dtype=np.uint16))
