"""Parameterized backend-dispatch coverage for `MicroscopeInterfaceLayer`.

`test_microscope_interface_layer.py` already covers backend *detection*
and a handful of MMCore-Plus dispatch cases. This file extends that
coverage along two axes:

* For the **MMCore-Plus** branch we exercise a long list of read/write
  methods, asserting both the camelCase name choice and the argument
  forwarding (`set_exposure(42.0)` → `core.setExposure(42.0)`).
* For the **Java** and **Python-headless** branches we cannot use
  `MagicMock(spec=...)` because:
    - `pycromanager.Core` is a dynamic Java-bridge proxy whose
      snake_case methods are synthesised at runtime, and
    - `pymmcore.CMMCore` only defines camelCase methods on the class
      object yet the production code reaches for snake_case.
  Instead we force the backend tag by monkeypatching
  `MicroscopeInterfaceLayer.MI` to return the desired
  `MicroscopeInstance` value and then attach a plain `MagicMock` as
  the core. That isolates "is the right method called?" from the
  detection step (already covered) and the underlying library shape.
"""
from __future__ import annotations

from unittest.mock import MagicMock

import numpy as np
import pytest
from pymmcore import Metadata as PymmcoreMetadata

try:
    # PymmcorePlusCore is the only real backend class we can `spec=` against.
    from pymmcore_plus import CMMCorePlus as PymmcorePlusCore
except Exception:  # pragma: no cover — env without pymmcore-plus
    PymmcorePlusCore = None  # type: ignore[assignment]

from glados_pycromanager.Core.microscopeInterfaceLayer import (
    MicroscopeInstance,
    MicroscopeInterfaceLayer,
)


@pytest.fixture
def mil():
    return MicroscopeInterfaceLayer()


def _force_backend(mil_obj, monkeypatch, backend: MicroscopeInstance):
    """Force backend by setting _mi directly (methods read it via self._mi)."""
    monkeypatch.setattr(mil_obj, "_mi", backend)
    monkeypatch.setattr(mil_obj, "MI", lambda: backend)
    monkeypatch.setattr(mil_obj, "get_MI", lambda: backend)
    monkeypatch.setattr(mil_obj, "get_microscope_interface", lambda: backend)


# ---- MMCore-Plus: long parameterized list -----------------------------

MMCORE_PLUS_DISPATCH_CASES = [
    # (method_name, args, expected_camelcase_attr, expected_args)
    ("clear_roi", (), "clearROI", ()),
    ("get_auto_shutter", (), "getAutoShutter", ()),
    ("get_available_config_groups", (), "getAvailableConfigGroups", ()),
    ("get_available_configs", ("Channel",), "getAvailableConfigs", ("Channel",)),
    ("get_config_data", ("Channel", "DAPI"), "getConfigData", ("Channel", "DAPI")),
    ("get_config_group_state", ("Channel",), "getConfigGroupState", ("Channel",)),
    ("get_current_config", ("Channel",), "getCurrentConfig", ("Channel",)),
    ("get_device_type", ("DemoCam",), "getDeviceType", ("DemoCam",)),
    ("get_exposure", (), "getExposure", ()),
    ("get_focus_device", (), "getFocusDevice", ()),
    # NB: get_image_width / get_image_height are derived from get_roi() in
    # the production code — they don't dispatch directly; see the dedicated
    # test below.
    ("get_loaded_devices", (), "getLoadedDevices", ()),
    ("get_pixel_size_um", (), "getPixelSizeUm", ()),
    ("get_shutter_device", (), "getShutterDevice", ()),
    ("get_shutter_open", (), "getShutterOpen", ()),
    ("get_xy_stage_device", (), "getXYStageDevice", ()),
    ("set_auto_shutter", (True,), "setAutoShutter", (True,)),
    ("set_config", ("Channel", "DAPI"), "setConfig", ("Channel", "DAPI")),
    ("set_exposure", (42.0,), "setExposure", (42.0,)),
    ("set_focus_device", ("DemoStage",), "setFocusDevice", ("DemoStage",)),
    ("set_property", ("DemoCam", "Binning", "2"), "setProperty",
        ("DemoCam", "Binning", "2")),
    ("set_relative_position", ("DemoStage", 10.0), "setRelativePosition",
        ("DemoStage", 10.0)),
    ("set_shutter_device", ("DemoShutter",), "setShutterDevice", ("DemoShutter",)),
    ("set_shutter_open", (True,), "setShutterOpen", (True,)),
    ("snap_image", (), "snapImage", ()),
    ("stop_sequence_acquisition", (), "stopSequenceAcquisition", ()),
    ("wait_for_system", (), "waitForSystem", ()),
    # T-C1 continuous-sequence primitives.
    ("clear_circular_buffer", (), "clearCircularBuffer", ()),
    ("get_remaining_image_count", (), "getRemainingImageCount", ()),
    ("is_sequence_running", (), "isSequenceRunning", ()),
    ("start_continuous_sequence_acquisition", (),
        "startContinuousSequenceAcquisition", (0,)),
    ("start_continuous_sequence_acquisition", (25.0,),
        "startContinuousSequenceAcquisition", (25.0,)),
]


@pytest.mark.skipif(
    PymmcorePlusCore is None, reason="pymmcore-plus not installed in test env"
)
@pytest.mark.parametrize(
    "method, args, expected_attr, expected_args", MMCORE_PLUS_DISPATCH_CASES
)
def test_mmcore_plus_dispatch(mil, method, args, expected_attr, expected_args):
    core = MagicMock(spec=PymmcorePlusCore)
    mil.set_core(core)
    getattr(mil, method)(*args)
    getattr(core, expected_attr).assert_called_once_with(*expected_args)


# ---- Java / Python-headless: snake_case via forced backend tag ----

SNAKE_CASE_DISPATCH_CASES = [
    # (method_name, args, expected_snake_attr, expected_args)
    ("clear_roi", (), "clear_roi", ()),
    ("get_auto_shutter", (), "get_auto_shutter", ()),
    ("get_current_config", ("Channel",), "get_current_config", ("Channel",)),
    ("get_exposure", (), "get_exposure", ()),
    ("get_focus_device", (), "get_focus_device", ()),
    ("set_auto_shutter", (True,), "set_auto_shutter", (True,)),
    ("set_config", ("Channel", "DAPI"), "set_config", ("Channel", "DAPI")),
    ("set_exposure", (42.0,), "set_exposure", (42.0,)),
    ("set_property", ("DemoCam", "Binning", "2"), "set_property",
        ("DemoCam", "Binning", "2")),
    ("snap_image", (), "snap_image", ()),
    ("stop_sequence_acquisition", (), "stop_sequence_acquisition", ()),
    ("wait_for_system", (), "wait_for_system", ()),
    # T-C1 continuous-sequence primitives. Both snake_case backends expose
    # these under the same names: `ZMQRemoteMMCoreJ` is built with
    # convert_camel_case=True, and mmpycorex's `CMMCoreSnakeCase` subclass
    # re-exports every CMMCore method in snake_case.
    ("clear_circular_buffer", (), "clear_circular_buffer", ()),
    ("get_remaining_image_count", (), "get_remaining_image_count", ()),
    ("is_sequence_running", (), "is_sequence_running", ()),
    ("start_continuous_sequence_acquisition", (),
        "start_continuous_sequence_acquisition", (0,)),
    ("start_continuous_sequence_acquisition", (25.0,),
        "start_continuous_sequence_acquisition", (25.0,)),
]


@pytest.mark.parametrize(
    "backend",
    [MicroscopeInstance.PYCROMANAGER_JAVA, MicroscopeInstance.PYCROMANAGER_PYTHON],
)
@pytest.mark.parametrize(
    "method, args, expected_attr, expected_args", SNAKE_CASE_DISPATCH_CASES
)
def test_snake_case_dispatch(monkeypatch, mil, backend, method, args, expected_attr, expected_args):
    core = MagicMock()
    mil.set_core(core)
    _force_backend(mil, monkeypatch, backend)
    getattr(mil, method)(*args)
    getattr(core, expected_attr).assert_called_once_with(*expected_args)


# ---- ROI / XY argument unpacking ------------------------------------

@pytest.mark.skipif(
    PymmcorePlusCore is None, reason="pymmcore-plus not installed in test env"
)
def test_set_roi_unpacks_four_args_mmcore_plus(mil):
    core = MagicMock(spec=PymmcorePlusCore)
    mil.set_core(core)
    mil.set_roi((1, 2, 3, 4))
    core.setROI.assert_called_once_with(1, 2, 3, 4)


@pytest.mark.skipif(
    PymmcorePlusCore is None, reason="pymmcore-plus not installed in test env"
)
def test_set_relative_xy_unpacks_tuple_mmcore_plus(mil):
    core = MagicMock(spec=PymmcorePlusCore)
    mil.set_core(core)
    mil.set_relative_xy_position((1.5, -2.5))
    core.setRelativeXYPosition.assert_called_once_with(1.5, -2.5)


@pytest.mark.parametrize(
    "backend",
    [MicroscopeInstance.PYCROMANAGER_JAVA, MicroscopeInstance.PYCROMANAGER_PYTHON],
)
def test_set_roi_forwards_tuple_snake_case(monkeypatch, mil, backend):
    core = MagicMock()
    mil.set_core(core)
    _force_backend(mil, monkeypatch, backend)
    mil.set_roi((0, 0, 256, 256))
    # Both snake_case backends forward the tuple as-is in production code.
    assert core.set_roi.call_count == 1


# ---- T-C1: frame-pulling primitives normalise to (2-D ndarray, dict) --
#
# These four can't join the tables above: their whole point is that three
# different backend return shapes (a `(ndarray, Metadata)` tuple, a
# `TaggedImage`, a flat SWIG buffer plus an out-parameter `Metadata`) come
# back to the caller as the same `(2-D ndarray, dict)`.


class _FakeTaggedImage:
    """Stand-in for mmpycorex's / pycromanager's TaggedImage."""

    def __init__(self, pix, tags):
        self.pix = pix
        self.tags = tags


@pytest.mark.skipif(
    PymmcorePlusCore is None, reason="pymmcore-plus not installed in test env"
)
@pytest.mark.parametrize(
    "method, core_attr",
    [
        ("pop_next_image_and_metadata", "popNextImageAndMD"),
        ("get_last_image_and_metadata", "getLastImageAndMD"),
    ],
)
def test_mmcore_plus_frame_pull_returns_array_and_dict(mil, method, core_attr):
    core = MagicMock(spec=PymmcorePlusCore)
    # pymmcore-plus already reshapes (fix=True) and its Metadata is a Mapping.
    getattr(core, core_attr).return_value = (
        np.arange(6, dtype=np.uint16).reshape(2, 3),
        {"Height": 2, "Width": 3},
    )
    mil.set_core(core)
    image, metadata = getattr(mil, method)()
    getattr(core, core_attr).assert_called_once_with()
    assert image.shape == (2, 3)
    assert metadata == {"Height": 2, "Width": 3}
    assert isinstance(metadata, dict)


@pytest.mark.parametrize(
    "backend",
    [MicroscopeInstance.PYCROMANAGER_JAVA, MicroscopeInstance.PYCROMANAGER_PYTHON],
)
def test_pop_next_image_reshapes_flat_tagged_image(monkeypatch, mil, backend):
    core = MagicMock()
    core.pop_next_tagged_image.return_value = _FakeTaggedImage(
        np.arange(6, dtype=np.uint16), {"Height": 2, "Width": 3}
    )
    mil.set_core(core)
    _force_backend(mil, monkeypatch, backend)
    image, metadata = mil.pop_next_image_and_metadata()
    core.pop_next_tagged_image.assert_called_once_with()
    assert image.shape == (2, 3)
    assert metadata == {"Height": 2, "Width": 3}


def test_get_last_image_java_uses_tagged_image(monkeypatch, mil):
    core = MagicMock()
    core.get_last_tagged_image.return_value = _FakeTaggedImage(
        np.arange(6, dtype=np.uint16), {"Height": 3, "Width": 2}
    )
    mil.set_core(core)
    _force_backend(mil, monkeypatch, MicroscopeInstance.PYCROMANAGER_JAVA)
    image, metadata = mil.get_last_image_and_metadata()
    core.get_last_tagged_image.assert_called_once_with()
    assert image.shape == (3, 2)
    assert metadata == {"Height": 3, "Width": 2}


def test_get_last_image_python_passes_metadata_out_param(monkeypatch, mil):
    core = MagicMock()
    core.get_last_image_md.return_value = np.arange(6, dtype=np.uint16)
    mil.set_core(core)
    _force_backend(mil, monkeypatch, MicroscopeInstance.PYCROMANAGER_PYTHON)
    # No usable Height/Width tags come back from the SWIG out-parameter here,
    # so the reshape must fall back on the ROI-derived shape cache.
    core.get_roi.return_value = (0, 0, 3, 2)
    image, metadata = mil.get_last_image_and_metadata()
    assert core.get_last_image_md.call_count == 1
    args = core.get_last_image_md.call_args[0]
    assert args[0] == 0 and args[1] == 0  # channel, slice
    assert isinstance(args[2], PymmcoreMetadata)  # out-parameter, not a dict
    assert image.shape == (2, 3)  # ROI is (x, y, w, h) -> (h, w)
    assert metadata == {}


# ---- T-C1: image-shape cache ----------------------------------------

def test_image_shape_cache_reads_roi_once(monkeypatch, mil):
    core = MagicMock()
    core.get_roi.return_value = (0, 0, 3, 2)
    mil.set_core(core)
    _force_backend(mil, monkeypatch, MicroscopeInstance.PYCROMANAGER_JAVA)
    assert mil._get_image_shape() == (2, 3)
    assert mil._get_image_shape() == (2, 3)
    core.get_roi.assert_called_once()


def test_set_roi_invalidates_image_shape_cache(monkeypatch, mil):
    core = MagicMock()
    core.get_roi.return_value = (0, 0, 3, 2)
    mil.set_core(core)
    _force_backend(mil, monkeypatch, MicroscopeInstance.PYCROMANAGER_JAVA)
    assert mil._get_image_shape() == (2, 3)
    core.get_roi.return_value = (0, 0, 8, 4)
    mil.set_roi((0, 0, 8, 4))
    assert mil._get_image_shape() == (4, 8)


def test_clear_roi_invalidates_image_shape_cache(monkeypatch, mil):
    core = MagicMock()
    core.get_roi.return_value = (0, 0, 3, 2)
    mil.set_core(core)
    _force_backend(mil, monkeypatch, MicroscopeInstance.PYCROMANAGER_JAVA)
    mil._get_image_shape()
    mil.clear_roi()
    assert mil._image_shape_cache is None


@pytest.mark.skipif(
    PymmcorePlusCore is None, reason="pymmcore-plus not installed in test env"
)
def test_set_core_resets_image_shape_cache(mil):
    core = MagicMock(spec=PymmcorePlusCore)
    core.getROI.return_value = (0, 0, 3, 2)
    mil.set_core(core)
    mil._get_image_shape()
    mil.set_core(core)
    assert mil._image_shape_cache is None


# ---- T-C1: get_image no longer uses the removed `newshape=` kwarg ----

def test_get_image_java_reshapes_flat_buffer(monkeypatch, mil):
    core = MagicMock()
    core.get_tagged_image.return_value = _FakeTaggedImage(
        np.arange(6, dtype=np.uint16), {"Height": 2, "Width": 3}
    )
    core.get_roi.return_value = (0, 0, 3, 2)
    mil.set_core(core)
    _force_backend(mil, monkeypatch, MicroscopeInstance.PYCROMANAGER_JAVA)
    # NumPy 2.1 removed np.reshape(newshape=...); the old code raised here.
    assert mil.get_image().shape == (2, 3)
    # One bridge fetch for the pixels, not three (.pix + two .tags lookups).
    core.get_tagged_image.assert_called_once()


# ---- Unknown backend behaviour --------------------------------------

UNKNOWN_BACKEND_CASES = [
    ("clear_roi", (), ValueError),
    ("get_auto_shutter", (), ValueError),
    ("get_available_config_groups", (), ValueError),
    ("get_exposure", (), ValueError),
    ("set_exposure", (1.0,), ValueError),
    ("snap_image", (), ValueError),
    ("wait_for_system", (), ValueError),
    ("clear_circular_buffer", (), ValueError),
    ("get_last_image_and_metadata", (), ValueError),
    ("get_remaining_image_count", (), ValueError),
    ("is_sequence_running", (), ValueError),
    ("pop_next_image_and_metadata", (), ValueError),
    ("start_continuous_sequence_acquisition", (), ValueError),
]


@pytest.mark.parametrize("method, args, exc", UNKNOWN_BACKEND_CASES)
def test_unknown_backend_raises(mil, method, args, exc):
    # No core set → MI() = UNKNOWN → every dispatch helper raises.
    with pytest.raises(exc):
        getattr(mil, method)(*args)


def test_get_pixel_size_um_unknown_returns_one(mil):
    # Special-case method that defaults to 1.0 rather than raising.
    assert mil.get_pixel_size_um() == 1.0


@pytest.mark.skipif(
    PymmcorePlusCore is None, reason="pymmcore-plus not installed in test env"
)
def test_get_pixel_size_um_caches_after_first_call(mil):
    core = MagicMock(spec=PymmcorePlusCore)
    core.getPixelSizeUm.return_value = 0.65
    mil.set_core(core)
    assert mil.get_pixel_size_um() == 0.65
    assert mil.get_pixel_size_um() == 0.65
    core.getPixelSizeUm.assert_called_once()  # only one hardware hit


@pytest.mark.skipif(
    PymmcorePlusCore is None, reason="pymmcore-plus not installed in test env"
)
def test_invalidate_pixel_size_cache_forces_rehit(mil):
    core = MagicMock(spec=PymmcorePlusCore)
    core.getPixelSizeUm.return_value = 0.65
    mil.set_core(core)
    mil.get_pixel_size_um()
    mil.invalidate_pixel_size_cache()
    mil.get_pixel_size_um()
    assert core.getPixelSizeUm.call_count == 2


@pytest.mark.skipif(
    PymmcorePlusCore is None, reason="pymmcore-plus not installed in test env"
)
def test_set_core_resets_pixel_size_cache(mil):
    core = MagicMock(spec=PymmcorePlusCore)
    core.getPixelSizeUm.return_value = 0.65
    mil.set_core(core)
    mil.get_pixel_size_um()  # populates cache
    core2 = MagicMock(spec=PymmcorePlusCore)
    core2.getPixelSizeUm.return_value = 1.0
    mil.set_core(core2)
    assert mil.get_pixel_size_um() == 1.0
    core2.getPixelSizeUm.assert_called_once()  # cache was cleared by set_core


@pytest.mark.skipif(
    PymmcorePlusCore is None, reason="pymmcore-plus not installed in test env"
)
def test_get_exposure_caches_after_first_call(mil):
    core = MagicMock(spec=PymmcorePlusCore)
    core.getExposure.return_value = 42.0
    mil.set_core(core)
    assert mil.get_exposure() == 42.0
    assert mil.get_exposure() == 42.0
    core.getExposure.assert_called_once()  # only one hardware hit


@pytest.mark.skipif(
    PymmcorePlusCore is None, reason="pymmcore-plus not installed in test env"
)
def test_invalidate_exposure_cache_forces_rehit(mil):
    core = MagicMock(spec=PymmcorePlusCore)
    core.getExposure.return_value = 42.0
    mil.set_core(core)
    mil.get_exposure()
    mil.invalidate_exposure_cache()
    mil.get_exposure()
    assert core.getExposure.call_count == 2


@pytest.mark.skipif(
    PymmcorePlusCore is None, reason="pymmcore-plus not installed in test env"
)
def test_set_exposure_invalidates_cache(mil):
    core = MagicMock(spec=PymmcorePlusCore)
    core.getExposure.return_value = 42.0
    mil.set_core(core)
    mil.get_exposure()  # populates cache
    mil.set_exposure(100.0)
    core.getExposure.return_value = 100.0
    assert mil.get_exposure() == 100.0
    assert core.getExposure.call_count == 2  # cache was cleared by set_exposure


@pytest.mark.skipif(
    PymmcorePlusCore is None, reason="pymmcore-plus not installed in test env"
)
def test_set_core_resets_exposure_cache(mil):
    core = MagicMock(spec=PymmcorePlusCore)
    core.getExposure.return_value = 42.0
    mil.set_core(core)
    mil.get_exposure()  # populates cache
    core2 = MagicMock(spec=PymmcorePlusCore)
    core2.getExposure.return_value = 10.0
    mil.set_core(core2)
    assert mil.get_exposure() == 10.0
    core2.getExposure.assert_called_once()  # cache was cleared by set_core


@pytest.mark.skipif(
    PymmcorePlusCore is None, reason="pymmcore-plus not installed in test env"
)
def test_image_width_and_height_derive_from_roi(mil):
    core = MagicMock(spec=PymmcorePlusCore)
    core.getROI.return_value = (0, 0, 123, 456)
    mil.set_core(core)
    assert mil.get_image_width() == 123
    assert mil.get_image_height() == 456


# ---- T-C1: the fake MIL mirrors the new primitives -------------------


def test_fake_mil_exposes_every_continuous_sequence_primitive(fake_mil):
    # The fake raises NotImplementedError from __getattr__ for anything it
    # does not implement, so a plain getattr is the assertion.
    for name in (
        "clear_circular_buffer",
        "get_last_image_and_metadata",
        "get_remaining_image_count",
        "is_sequence_running",
        "pop_next_image_and_metadata",
        "start_continuous_sequence_acquisition",
    ):
        assert callable(getattr(fake_mil, name))


def test_fake_mil_circular_buffer_pop_is_fifo_and_peek_is_lifo(fake_mil):
    fake_mil.push_frame(np.zeros((2, 2), dtype=np.uint16), {"n": 0})
    fake_mil.push_frame(np.ones((2, 2), dtype=np.uint16), {"n": 1})
    assert fake_mil.get_remaining_image_count() == 2

    # `latest` peeks the newest frame and consumes nothing.
    _, newest = fake_mil.get_last_image_and_metadata()
    assert newest == {"n": 1}
    assert fake_mil.get_remaining_image_count() == 2

    # `sequential` pops the oldest frame.
    _, oldest = fake_mil.pop_next_image_and_metadata()
    assert oldest == {"n": 0}
    assert fake_mil.get_remaining_image_count() == 1


def test_fake_mil_sequence_running_tracks_start_and_stop(fake_mil):
    assert fake_mil.is_sequence_running() is False
    fake_mil.start_continuous_sequence_acquisition()
    assert fake_mil.is_sequence_running() is True
    assert fake_mil._continuous_starts == [0.0]
    fake_mil.stop_sequence_acquisition()
    assert fake_mil.is_sequence_running() is False


def test_fake_mil_clear_circular_buffer_empties_it(fake_mil):
    fake_mil.push_frame(np.zeros((2, 2), dtype=np.uint16))
    fake_mil.clear_circular_buffer()
    assert fake_mil.get_remaining_image_count() == 0
    with pytest.raises(IndexError):
        fake_mil.pop_next_image_and_metadata()
