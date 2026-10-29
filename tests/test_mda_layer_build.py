"""Building the multiDstack MDA layer: at the Acquire click, reused when possible.

Building a napari layer took ~2 s on the first frame of a fast MDA (napari's
layer controls, dims sliders and GL texture, with the acquisition competing
for the CPU). Three changes, pinned here against a real napari ViewerModel:

* `_precreate_mda_layer` builds it when Acquire is clicked: the camera is read
  on a short-lived thread, the build is posted to the GUI thread, and the
  first frame finds a matching layer and only validates it.
* `_build_mda_layer` re-points an existing layer with the same number of
  dimensions at the new store instead of deleting and rebuilding it.
* `warm_up_napari_image_layer` pays napari's first-image-layer cost at
  startup-ready and leaves no layer behind.
"""
from __future__ import annotations

import numpy as np
import pytest
from napari.components import ViewerModel

import glados_pycromanager.GUI.napariGlados as ng
from glados_pycromanager.Core import microscopeInterfaceLayer as MIL
from glados_pycromanager.GUI.sharedFunctions import Shared_data


def _shared(tmp_appdata, times=3, zs=2):
    shared_data = Shared_data()
    shared_data._mdaModeParams = [{'axes': {'time': t, 'z': z}}
                                  for t in range(times) for z in range(zs)]
    shared_data.hw_pixel_size_um = 0.1
    return shared_data


def test_build_creates_a_layer_for_the_plan(tmp_appdata):
    shared_data = _shared(tmp_appdata)
    viewer = ViewerModel()

    ng._build_mda_layer(shared_data, viewer, 'MDA', 'gray', (8, 8), np.uint16)

    layer = viewer.layers['MDA']
    assert layer.data.shape == (3, 2, 8, 8)
    assert layer.data.dtype == np.uint16
    assert viewer.dims.axis_labels[:2] == ('time', 'z')
    assert ng._layer_shape_already_validated(shared_data, 'MDA', layer)


def test_same_ndim_reuses_the_layer_object(tmp_appdata):
    shared_data = _shared(tmp_appdata)
    viewer = ViewerModel()
    ng._build_mda_layer(shared_data, viewer, 'MDA', 'gray', (8, 8), np.uint16)
    first = viewer.layers['MDA']

    shared_data._mdaModeParams = [{'axes': {'time': t, 'z': z}}
                                  for t in range(5) for z in range(3)]
    ng._build_mda_layer(shared_data, viewer, 'MDA', 'gray', (16, 16), np.uint16)

    assert viewer.layers['MDA'] is first
    assert first.data.shape == (5, 3, 16, 16)
    assert len(viewer.layers) == 1


def test_a_different_ndim_replaces_the_layer(tmp_appdata):
    shared_data = _shared(tmp_appdata)
    viewer = ViewerModel()
    ng._build_mda_layer(shared_data, viewer, 'MDA', 'gray', (8, 8), np.uint16)
    first = viewer.layers['MDA']

    shared_data._mdaModeParams = [{'axes': {'time': t}} for t in range(4)]
    ng._build_mda_layer(shared_data, viewer, 'MDA', 'gray', (8, 8), np.uint16)

    assert viewer.layers['MDA'] is not first
    assert viewer.layers['MDA'].data.shape == (4, 8, 8)
    assert len(viewer.layers) == 1


def test_seed_is_written_before_the_layer_reads_the_store(tmp_appdata):
    shared_data = _shared(tmp_appdata)
    viewer = ViewerModel()
    frame = np.full((8, 8), 7, dtype=np.uint16)

    seeded = ng._build_mda_layer(shared_data, viewer, 'MDA', 'gray', (8, 8), np.uint16,
                                 seed_image=frame, seed_slice=(1, 1))

    assert seeded
    assert np.all(shared_data.mdaZarrData['MDA'][1, 1] == 7)


def _frame_meta(t, z):
    return {'Axes': {'time': t, 'z': z}}


def test_first_frame_keeps_a_precreated_matching_layer(tmp_appdata):
    shared_data = _shared(tmp_appdata)
    viewer = ViewerModel()
    ng._build_mda_layer(shared_data, viewer, 'MDA', 'gray', (8, 8), np.uint16)
    layer = viewer.layers['MDA']
    ng._invalidate_layer_shape_validation(shared_data, 'MDA')  # as the pre-build leaves it
    meta = _frame_meta(0, 0)

    ng._prepare_mda_layer_for_frame(shared_data, viewer, 'MDA', 'gray',
                                    np.zeros((8, 8), np.uint16), meta)

    assert viewer.layers['MDA'] is layer
    assert ng.ZARR_WRITTEN_SLICE_KEY not in meta  # the display path writes it
    assert ng._layer_shape_already_validated(shared_data, 'MDA', layer)


def test_first_frame_rebuilds_on_a_dtype_mismatch_and_seeds_itself(tmp_appdata):
    shared_data = _shared(tmp_appdata)
    viewer = ViewerModel()
    ng._build_mda_layer(shared_data, viewer, 'MDA', 'gray', (8, 8), np.uint16)
    ng._invalidate_layer_shape_validation(shared_data, 'MDA')
    meta = _frame_meta(2, 1)
    frame = np.full((8, 8), 3, dtype=np.uint8)

    ng._prepare_mda_layer_for_frame(shared_data, viewer, 'MDA', 'gray', frame, meta)

    assert viewer.layers['MDA'].data.dtype == np.uint8
    assert meta[ng.ZARR_WRITTEN_SLICE_KEY] == (2, 1)
    assert np.all(shared_data.mdaZarrData['MDA'][2, 1] == 3)


class _Bridge:
    def __init__(self, viewer):
        self.viewer = viewer

    def submit(self, fn, *a, wait=False, **k):
        return fn(self.viewer, *a, **k)


class _Mil:
    def __init__(self, mi, h=8, w=8):
        self._mi, self.h, self.w = mi, h, w

    def MI(self):
        return self._mi

    def get_image_height(self):
        return self.h

    def get_image_width(self):
        return self.w


def _precreate(shared_data, viewer, monkeypatch, mi):
    import glados_pycromanager.GUI.napari_bridge as nb

    monkeypatch.setattr(nb, 'get_bridge', lambda sd: _Bridge(viewer))
    monkeypatch.setattr(ng, '_camera_dtype', lambda sd: np.uint16)
    shared_data._MILcore = _Mil(mi)
    shared_data.config.mda_config.vis_method = 'multiDstack'
    shared_data._mdaMode = True
    thread = ng._precreate_mda_layer(shared_data, 'MDA')
    if thread is not None:
        thread.join(timeout=30)
    return thread


def test_acquire_click_builds_the_layer_off_the_first_frame(tmp_appdata, monkeypatch):
    shared_data = _shared(tmp_appdata)
    viewer = ViewerModel()

    _precreate(shared_data, viewer, monkeypatch, MIL.MicroscopeInstance.PYCROMANAGER_PYTHON)

    assert viewer.layers['MDA'].data.shape == (3, 2, 8, 8)
    # Left for the first real frame to confirm (binning is not in the ROI).
    assert not ng._layer_shape_already_validated(shared_data, 'MDA', viewer.layers['MDA'])


def test_acquire_click_does_nothing_on_mmcore_plus(tmp_appdata, monkeypatch):
    shared_data = _shared(tmp_appdata)
    viewer = ViewerModel()

    thread = _precreate(shared_data, viewer, monkeypatch, MIL.MicroscopeInstance.MMCORE_PLUS)

    assert thread is None
    assert len(viewer.layers) == 0


def test_a_stopped_acquisition_is_not_built_for(tmp_appdata, monkeypatch):
    shared_data = _shared(tmp_appdata)
    viewer = ViewerModel()
    import glados_pycromanager.GUI.napari_bridge as nb

    def stop_then_build(fn, *a, **k):
        shared_data._mdaMode = False
        return fn(viewer)
    monkeypatch.setattr(nb, 'get_bridge',
                        lambda sd: type('B', (), {'submit': staticmethod(stop_then_build)})())
    monkeypatch.setattr(ng, '_camera_dtype', lambda sd: np.uint16)
    shared_data._MILcore = _Mil(MIL.MicroscopeInstance.PYCROMANAGER_PYTHON)
    shared_data.config.mda_config.vis_method = 'multiDstack'
    shared_data._mdaMode = True

    ng._precreate_mda_layer(shared_data, 'MDA').join(timeout=30)

    assert len(viewer.layers) == 0


def test_warm_up_leaves_no_layer(tmp_appdata):
    viewer = ViewerModel()
    ng.warm_up_napari_image_layer(viewer)
    assert len(viewer.layers) == 0
