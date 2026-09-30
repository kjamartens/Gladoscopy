"""FastImage: same-shape 2-D updates skip napari's async slicer, everything else
falls back to stock `Image` behaviour. Pinned against real napari layers."""
import threading

import numpy as np
import pytest

from glados_pycromanager.GUI import fast_image_layer
from glados_pycromanager.GUI.fast_image_layer import FastImage, add_fast_image


@pytest.fixture
def layer(qapp):
    layer = FastImage(np.zeros((64, 64), np.uint16), name='live')
    # napari's layer metaclass runs a post-init refresh() after __init__
    # returns; zero the counters so each test counts only its own updates.
    layer.fast_updates = layer.slow_updates = 0
    return layer


def frame(value, shape=(64, 64), dtype=np.uint16):
    return np.full(shape, value, dtype=dtype)


def test_same_shape_assignment_takes_the_fast_path_and_keeps_identity(layer):
    new = frame(7)
    layer.data = new
    assert layer.fast_updates == 1 and layer.slow_updates == 0
    assert layer.data is new
    # The displayed view was re-sliced from the new array, not left stale.
    assert np.shares_memory(layer._data_view, new)
    assert layer._data_view[0, 0] == 7


def test_inplace_write_plus_refresh_takes_the_fast_path(layer):
    layer.data[:] = 9
    layer.refresh()
    assert layer.fast_updates == 1 and layer.slow_updates == 0
    assert layer._data_view[5, 5] == 9


def test_fast_path_skips_the_data_event(layer):
    """events.data makes the viewer reassign dims.range (which re-slices)."""
    seen = []
    layer.events.data.connect(lambda e: seen.append(e))
    layer.data = frame(3)
    assert seen == []


def test_fast_path_emits_set_data_so_vispy_uploads(layer):
    seen = []
    layer.events.set_data.connect(lambda e: seen.append(e))
    layer.data = frame(3)
    assert len(seen) == 1


@pytest.mark.parametrize('new', [
    frame(1, shape=(32, 32)),                 # shape change
    frame(1, dtype=np.float32),               # dtype change
])
def test_a_shape_or_dtype_change_falls_back(layer, new):
    layer.data = new
    # The stock setter ran (it may itself call refresh(), which is then served
    # synchronously -- same result, just without the async hop).
    assert layer.slow_updates >= 1
    assert layer.data is new
    assert layer._data_view.shape == new.shape and layer._data_view.dtype == new.dtype


def test_a_hidden_layer_falls_back(layer):
    layer.visible = False
    layer.data = frame(2)
    assert layer.fast_updates == 0
    assert layer.data[0, 0] == 2


def test_an_off_gui_thread_update_falls_back(layer):
    result = {}

    def worker():
        result['ok'] = fast_image_layer._on_gui_thread()

    t = threading.Thread(target=worker)
    t.start()
    t.join()
    assert result['ok'] is False
    assert fast_image_layer._on_gui_thread() is True


def test_a_3d_layer_never_takes_the_fast_path(qapp):
    stack = FastImage(np.zeros((3, 16, 16), np.uint16))
    stack.fast_updates = 0
    stack.data = np.ones((3, 16, 16), np.uint16)
    assert stack.fast_updates == 0


def test_continuous_auto_contrast_is_throttled(layer, monkeypatch):
    calls = []
    monkeypatch.setattr(layer, 'reset_contrast_limits', lambda *a, **k: calls.append(1))
    layer._keep_auto_contrast = True
    layer.contrast_every_n_frames = 3
    for i in range(9):
        layer.data = frame(i)
    assert len(calls) == 3


def test_manual_contrast_is_left_alone(layer, monkeypatch):
    calls = []
    monkeypatch.setattr(layer, 'reset_contrast_limits', lambda *a, **k: calls.append(1))
    layer._keep_auto_contrast = False
    for i in range(20):
        layer.data = frame(i)
    assert calls == []


def test_thumbnail_is_rebuilt_at_most_once_per_interval(layer, monkeypatch):
    calls = []
    monkeypatch.setattr(layer, '_update_thumbnail', lambda *a, **k: calls.append(1))
    for i in range(30):
        layer.data = frame(i)
    # The post-init refresh already built one; none is due within the interval.
    assert len(calls) <= 1


def test_thumbnail_is_rebuilt_once_the_interval_has_passed(layer, monkeypatch):
    calls = []
    monkeypatch.setattr(layer, '_update_thumbnail', lambda *a, **k: calls.append(1))
    monkeypatch.setattr(fast_image_layer, 'THUMBNAIL_INTERVAL_S', 0.0)
    for i in range(5):
        layer.data = frame(i)
    assert len(calls) == 5


def test_add_fast_image_falls_back_for_a_viewer_without_add_layer():
    class StubViewer:
        def add_image(self, data, **kwargs):
            return ('stock', kwargs)

    assert add_fast_image(StubViewer(), np.zeros((4, 4)), name='x') == ('stock', {'name': 'x'})


def test_add_fast_image_adds_a_fast_image(qapp):
    added = []

    class Viewer:
        def add_layer(self, layer):
            added.append(layer)

    layer = add_fast_image(Viewer(), np.zeros((8, 8)), name='rt', opacity=0.5)
    assert isinstance(layer, FastImage) and added == [layer]
    assert layer.name == 'rt' and layer.opacity == 0.5


def test_rt_image_layers_are_created_as_fast_images(qapp):
    from glados_pycromanager.GUI.layer_group import LayerSpec, create_layer
    added = []

    class Viewer:
        layers = []

        def add_layer(self, layer):
            added.append(layer)

    layer = create_layer(Viewer(), LayerSpec(name='FFT', type='image'))
    assert isinstance(layer, FastImage)
