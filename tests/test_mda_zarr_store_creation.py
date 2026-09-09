"""T-D1: the multiDstack display store is created from one site, with a dtype.

There used to be two creation sites and they disagreed. `_preinit_mda_zarr`
passed `dtype=`; the display-path fallback in `_napariUpdateLive_locked` called
`zarr.open()` without one, which on zarr 3.x yields a **float64** array. Every
uint16 camera frame was then upcast on write -- 4x the bytes through the
compressor and on disk, and napari's contrast fast path defeated. Which of the
two arrays an acquisition ended up with was a race between the sites.

These tests pin the single helper both sites now call.
"""
from __future__ import annotations

import numpy as np

from glados_pycromanager.GUI.napariGlados import _camera_dtype, _create_mda_zarr
from glados_pycromanager.GUI.sharedFunctions import Shared_data


def test_store_honours_the_requested_dtype(tmp_appdata):
    shared_data = Shared_data()

    array = _create_mda_zarr(shared_data, "MDA", [3, 2], 8, 6, np.uint16)

    assert array.dtype == np.uint16
    assert tuple(array.shape) == (3, 2, 8, 6)
    assert tuple(array.chunks) == (1, 1, 8, 6)


def test_store_is_never_float64_by_default(tmp_appdata):
    """The actual regression: a uint16 frame must not land in a float64 array."""
    shared_data = Shared_data()
    frame = np.zeros((8, 6), dtype=np.uint16)

    array = _create_mda_zarr(shared_data, "MDA", [2], *frame.shape, frame.dtype)

    assert array.dtype == frame.dtype != np.float64


def test_store_is_registered_and_its_temp_dir_owned(tmp_appdata):
    shared_data = Shared_data()

    array = _create_mda_zarr(shared_data, "MyNode", [2], 4, 4, np.uint8)

    # Registered under the layer name, and the TemporaryDirectory backing it is
    # owned by shared_data so it outlives this call (T-D7).
    assert shared_data.mdaZarrData["MyNode"] is array
    assert "MyNode" in shared_data.mdaZarrTempDirs
    assert shared_data.allMDAslicesRendered == {}


def test_camera_dtype_falls_back_to_uint16_without_a_core(tmp_appdata):
    shared_data = Shared_data()

    # No core attached in a bare Shared_data, so the probe must not raise.
    assert _camera_dtype(shared_data) == np.uint16


def test_camera_dtype_reads_bytes_per_pixel(tmp_appdata):
    class _Core:
        def __init__(self, n):
            self._n = n

        def getBytesPerPixel(self):
            return self._n

    class _MIL:
        def __init__(self, n):
            self.core = _Core(n)

    shared_data = Shared_data()

    shared_data.MILcore = _MIL(1)
    assert _camera_dtype(shared_data) == np.uint8

    shared_data.MILcore = _MIL(2)
    assert _camera_dtype(shared_data) == np.uint16
