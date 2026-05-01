"""
Unit tests for the MicroscopeInterfaceLayer abstraction.

These exercise pure logic only — no live Micro-Manager / hardware required.
Real backend cores are stand-ins via MagicMock(spec=...) so isinstance() checks
hit the dispatch branch we want to verify.
"""
from unittest.mock import MagicMock

import numpy as np
import pytest

from pycromanager import Core as PycroManagerCore
from pymmcore import CMMCore as PymmcoreCore
from pymmcore_plus import CMMCorePlus as PymmcorePlusCore

from glados_pycromanager.Core.microscopeInterfaceLayer import (
    MicroscopeInterfaceLayer,
    MicroscopeInstance,
)


@pytest.fixture
def mil():
    return MicroscopeInterfaceLayer()


def _mock_core(spec_class):
    """Build a MagicMock that passes `isinstance(m, spec_class)`."""
    return MagicMock(spec=spec_class)


class TestBackendDetection:
    def test_unset_core_is_unknown(self, mil):
        assert mil.get_microscope_interface() is MicroscopeInstance.UNKNOWN
        assert mil.MI() is MicroscopeInstance.UNKNOWN
        assert mil.get_MI() is MicroscopeInstance.UNKNOWN

    def test_pymmcore_plus_core_detected(self, mil):
        mil.set_core(_mock_core(PymmcorePlusCore))
        assert mil.MI() is MicroscopeInstance.MMCORE_PLUS

    def test_pycromanager_python_core_detected(self, mil):
        # Plain pymmcore (not the +Plus subclass) maps to PYCROMANAGER_PYTHON.
        # PymmcorePlusCore subclasses PymmcoreCore, so we must use a mock
        # spec'd against the bare pymmcore class.
        mil.set_core(_mock_core(PymmcoreCore))
        assert mil.MI() is MicroscopeInstance.PYCROMANAGER_PYTHON

    def test_pycromanager_java_core_detected(self, mil):
        mil.set_core(_mock_core(PycroManagerCore))
        assert mil.MI() is MicroscopeInstance.PYCROMANAGER_JAVA

    def test_unrecognised_object_is_unknown(self, mil):
        mil.set_core(object())
        assert mil.MI() is MicroscopeInstance.UNKNOWN


class TestSetGetCore:
    def test_set_and_get_core_roundtrip(self, mil):
        sentinel = object()
        mil.set_core(sentinel)
        assert mil.get_core() is sentinel


class TestJavaArrToNumpy:
    def test_none_returns_empty_array(self, mil):
        result = mil.java_arr_to_numpy(None)
        assert isinstance(result, np.ndarray)
        assert result.size == 0

    def test_iterable_of_strings(self, mil):
        result = mil.java_arr_to_numpy(["alpha", "beta", "gamma"])
        assert list(result) == ["alpha", "beta", "gamma"]

    def test_iterable_of_ints_stringified(self, mil):
        # The helper coerces every element to str() before building the array.
        result = mil.java_arr_to_numpy([1, 2, 3])
        assert list(result) == ["1", "2", "3"]

    def test_dtype_is_object(self, mil):
        result = mil.java_arr_to_numpy(["x", "y"])
        assert result.dtype == object


class TestDispatch:
    """Each MIL operation should route to the correct method on its core.

    Only the PymmcorePlusCore (MMCore+) branch is exercised here. The other
    two backends are reachable via dispatch but cannot be mocked with
    `spec=...`:
      - `pycromanager.Core` (Java) is a dynamic Java-bridge proxy that
        synthesises snake_case methods at runtime — they don't exist on the
        Python class object, so a spec'd MagicMock rejects them.
      - `pymmcore.CMMCore` (SWIG bindings) only declares camelCase methods
        on the class; the production code calls snake_case on it. That
        discrepancy is a latent issue worth investigating separately, not a
        contract a unit test should pin.
    """

    def test_clear_roi_pymmcore_plus_uses_camelcase(self, mil):
        core = _mock_core(PymmcorePlusCore)
        mil.set_core(core)
        mil.clear_roi()
        core.clearROI.assert_called_once()

    def test_set_exposure_pymmcore_plus(self, mil):
        core = _mock_core(PymmcorePlusCore)
        mil.set_core(core)
        mil.set_exposure(42.0)
        core.setExposure.assert_called_once_with(42.0)

    def test_set_relative_xy_position_unpacks_tuple(self, mil):
        core = _mock_core(PymmcorePlusCore)
        mil.set_core(core)
        mil.set_relative_xy_position((10.0, -5.0))
        core.setRelativeXYPosition.assert_called_once_with(10.0, -5.0)

    def test_set_roi_unpacks_four_args(self, mil):
        core = _mock_core(PymmcorePlusCore)
        mil.set_core(core)
        mil.set_roi((0, 0, 512, 512))
        core.setROI.assert_called_once_with(0, 0, 512, 512)

    def test_clear_roi_unknown_backend_raises(self, mil):
        # No core set → MI() returns UNKNOWN → callable should raise.
        with pytest.raises(ValueError, match="clear_roi"):
            mil.clear_roi()

    def test_get_focus_device_without_core_raises(self, mil):
        with pytest.raises(RuntimeError, match="not set"):
            mil.get_focus_device()


class TestGetPixelSizeUm:
    """get_pixel_size_um is the one backend-dispatch method that returns 1.0
    (rather than raising) when the backend is unknown — guard that contract."""

    def test_unknown_backend_returns_default_one(self, mil):
        assert mil.get_pixel_size_um() == 1.0

    def test_pymmcore_plus_uses_camelcase(self, mil):
        core = _mock_core(PymmcorePlusCore)
        core.getPixelSizeUm.return_value = 0.16
        mil.set_core(core)
        assert mil.get_pixel_size_um() == 0.16
