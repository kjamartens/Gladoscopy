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

import pytest

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


# ---- Unknown backend behaviour --------------------------------------

UNKNOWN_BACKEND_CASES = [
    ("clear_roi", (), ValueError),
    ("get_auto_shutter", (), ValueError),
    ("get_available_config_groups", (), ValueError),
    ("get_exposure", (), ValueError),
    ("set_exposure", (1.0,), ValueError),
    ("snap_image", (), ValueError),
    ("wait_for_system", (), ValueError),
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
