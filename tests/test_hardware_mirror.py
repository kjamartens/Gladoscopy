"""Coverage for the mirrored hardware constants (T-B2).

`napariUpdateLive`'s rate-limit gate used to call `MILcore.get_exposure()` on
the GUI thread for every candidate frame, and each layer creation made three
`get_pixel_size_um()` calls. On PYCROMANAGER_JAVA a bridge round trip was
measured at ~257 ms, so the display path must never reach for MIL at all.

`Shared_data` therefore mirrors the values into plain attributes
(`hw_exposure_ms`, `hw_pixel_size_um`, `hw_roi`, `hw_image_shape`), refreshed
only where the hardware value can change: MIL calls back into the mirror from
`set_core`, `set_exposure`, `set_roi` and `clear_roi`, and the acquisition
worker refreshes once at acquisition start.
"""
from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from glados_pycromanager.Core.microscopeInterfaceLayer import (
    MicroscopeInstance,
    MicroscopeInterfaceLayer,
)
from glados_pycromanager.GUI import napariGlados
from glados_pycromanager.GUI.sharedFunctions import Shared_data


@pytest.fixture
def mil():
    m = MicroscopeInterfaceLayer()
    m.core = MagicMock()
    m._mi = MicroscopeInstance.MMCORE_PLUS
    m.core.getExposure.return_value = 20.0
    m.core.getPixelSizeUm.return_value = 0.11
    m.core.getROI.return_value = (0, 0, 512, 256)
    return m


@pytest.fixture
def shared(qtbot_unused=None):
    return Shared_data()


def test_binding_a_bound_mil_populates_the_mirror(shared, mil):
    shared.MILcore = mil

    assert shared.hw_exposure_ms == 20.0
    assert shared.hw_pixel_size_um == 0.11
    assert shared.hw_roi == (0, 0, 512, 256)
    assert shared.hw_image_shape == (256, 512)  # (height, width)


def test_set_exposure_refreshes_the_mirror(shared, mil):
    shared.MILcore = mil
    mil.core.getExposure.return_value = 5.0

    mil.set_exposure(5.0)

    assert shared.hw_exposure_ms == 5.0


def test_set_roi_and_clear_roi_refresh_the_geometry_mirror(shared, mil):
    shared.MILcore = mil

    mil.core.getROI.return_value = (10, 20, 64, 32)
    mil.set_roi((10, 20, 64, 32))
    assert shared.hw_roi == (10, 20, 64, 32)
    assert shared.hw_image_shape == (32, 64)

    mil.core.getROI.return_value = (0, 0, 512, 256)
    mil.clear_roi()
    assert shared.hw_image_shape == (256, 512)


def test_set_core_notifies_the_mirror(mil):
    """A rebind (backend switch) must invalidate the previous core's values.

    Asserted on the notification rather than on the mirrored values: `set_core`
    classifies a MagicMock as UNKNOWN, and the callback runs *inside* set_core,
    i.e. before a test could force the backend branch back.
    """
    seen = []
    mil.set_hardware_mirror(seen.append)

    mil.set_core(MagicMock())

    assert seen == ["core"]


def test_display_path_reads_the_mirror_without_calling_mil(shared, mil):
    """The whole point: no MIL call once the mirror is warm."""
    shared.MILcore = mil
    mil.core.reset_mock()

    assert napariGlados._mirrored_exposure_ms(shared) == 20.0
    assert napariGlados._mirrored_pixel_size_um(shared) == 0.11

    mil.core.getExposure.assert_not_called()
    mil.core.getPixelSizeUm.assert_not_called()


def test_display_path_falls_back_to_mil_when_the_mirror_is_cold(shared, mil):
    """A shared_data whose mirror was never refreshed still gets a value."""
    shared._MILcore = mil  # bypass the setter, so no refresh happened
    assert shared.hw_exposure_ms is None

    assert napariGlados._mirrored_exposure_ms(shared) == 20.0
    assert shared.hw_exposure_ms == 20.0  # and the fallback warms the mirror


def test_refresh_is_a_noop_without_a_bound_core(shared):
    unbound = MicroscopeInterfaceLayer()
    shared.MILcore = unbound  # core is None -- must not raise
    assert shared.hw_exposure_ms is None
    shared.refresh_hardware_mirror()
    assert shared.hw_exposure_ms is None


def test_mirror_callback_failure_never_escapes_into_mil(mil):
    """A broken observer must not break a hardware write."""
    def boom(reason):
        raise RuntimeError("mirror exploded")

    mil.set_hardware_mirror(boom)
    mil.set_exposure(7.0)  # must not raise
    mil.core.setExposure.assert_called_once_with(7.0)


def test_apply_pixel_scale_falls_back_to_one_when_unset(shared, mil):
    shared.MILcore = mil
    shared.hw_pixel_size_um = 0.0
    layer = MagicMock()

    napariGlados._apply_pixel_scale(layer, shared)

    assert layer.scale == [1, 1]
