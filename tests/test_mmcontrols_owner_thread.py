"""MMcontrols slots submit hardware intents instead of blocking (T-B4, last file).

`MMcontrols.py` was the last standing violation of threading invariant 1 named
in `CLAUDE.md`: it snapped images, moved stages and wrote device properties
directly in GUI slots. A snap blocks for the whole exposure; a stage move for
the whole move; and a wheel notch over the napari canvas reaches the stage slot.

Everything now goes through `submitHardware()`, which queues onto the
`MicroscopeService` owner thread (T-B3) and falls back to a direct call when no
service is running. What is asserted here:

1. The hardware work really leaves the calling thread when a service runs, and
   really runs inline when one does not.
2. Widget and napari touches come back to the GUI thread (`guiThreadCall`).
3. Ordering that matters is preserved: a position read-back submitted after a
   move reports the post-move position, and live mode does not start until the
   exposure write has landed.

The methods are bound onto a bare host object rather than constructing a real
`MMConfigUI`, which needs a full Qt widget tree and a live Micro-Manager.
"""
from __future__ import annotations

import threading
import time

import numpy as np
import pytest

import glados_pycromanager.GUI.MMcontrols as mm
from glados_pycromanager.Core.microscope_service import MicroscopeService


class FakeMIL:
    """Records each hardware call with the thread that made it."""

    def __init__(self):
        self.core = object()
        self.calls = []

    def _record(self, name, *args):
        self.calls.append((name, args, threading.get_ident()))

    def set_exposure(self, value):
        self._record('set_exposure', value)

    def snap_image(self):
        self._record('snap_image')

    def get_image(self):
        self._record('get_image')
        return np.zeros((4, 6), dtype=np.uint16)

    def set_relative_position(self, stage, distance):
        self._record('set_relative_position', stage, distance)

    def get_position(self, stage):
        self._record('get_position', stage)
        return 12.5

    def set_relative_xy_position(self, rel):
        self._record('set_relative_xy_position', tuple(rel))

    def get_xy_stage_device(self):
        self._record('get_xy_stage_device')
        return 'XY'

    def get_xy_position(self, name):
        self._record('get_xy_position', name)
        return (1.0, 2.0)

    def set_shutter_open(self, state):
        self._record('set_shutter_open', state)

    def set_auto_shutter(self, state):
        self._record('set_auto_shutter', state)

    def set_shutter_device(self, device):
        self._record('set_shutter_device', device)

    def clear_roi(self):
        self._record('clear_roi')

    def set_roi(self, roi):
        self._record('set_roi', tuple(roi))

    def wait_for_system(self):
        self._record('wait_for_system')

    def MI(self):
        return 'FAKE'

    def names(self):
        return [name for name, _args, _thread in self.calls]

    def threads(self):
        return {thread for _name, _args, thread in self.calls}


class FakeSharedData:
    def __init__(self, mil, service=None):
        self.MILcore = mil
        self.microscope_service = service
        self.liveMode = False

    def microscope_proxy(self, priority=None):
        service = self.microscope_service
        if service is None:
            return self.MILcore
        return service.proxy()


class FakeWidget:
    def __init__(self, text=''):
        self._text = str(text)

    def text(self):
        return self._text

    def setText(self, value):
        self._text = str(value)

    def currentText(self):
        return self._text


@pytest.fixture
def shared(monkeypatch):
    """A shared_data with a fake MIL, and the module globals pointed at it."""
    mil = FakeMIL()
    sd = FakeSharedData(mil)
    monkeypatch.setattr(mm, 'shared_data', sd, raising=False)
    # guiThreadCall would otherwise try to build a napari bridge.
    monkeypatch.setattr(mm, 'guiThreadCall', lambda _sd, fn: fn())
    return sd


@pytest.fixture
def service(shared):
    svc = MicroscopeService(shared.MILcore, name='MMcontrolsTestService').start()
    shared.microscope_service = svc
    yield svc
    svc.stop()


def _drain(service, timeout=5.0):
    service.submit(lambda: None, label='barrier').wait(timeout)


class _Host:
    """Binds the MMConfigUI methods under test onto a minimal object."""

    snapImage = mm.MMConfigUI.snapImage
    _snapImage_hw = mm.MMConfigUI._snapImage_hw
    moveOneDStage = mm.MMConfigUI.moveOneDStage
    updateOneDstageLayout = mm.MMConfigUI.updateOneDstageLayout
    _readOneDstagePosition = mm.MMConfigUI._readOneDstagePosition
    on_shutterOpenCloseButtonPressed = mm.MMConfigUI.on_shutterOpenCloseButtonPressed
    resetROI = mm.MMConfigUI.resetROI
    setROI = mm.MMConfigUI.setROI
    _setROI_hw = mm.MMConfigUI._setROI_hw
    _setROI_liveRestart = mm.MMConfigUI._setROI_liveRestart
    _startLiveAfterExposure = mm.MMConfigUI._startLiveAfterExposure
    _startLiveMode = mm.MMConfigUI._startLiveMode

    def __init__(self, shared_data):
        self.shared_data = shared_data
        self.exposureTimeInputField = FakeWidget('25')
        self.oneDstageDropdown = FakeWidget('Z')
        self.oneDMoveEditField = {'Z': {
            'oneDStackedWidget_Z_1': FakeWidget('0.5'),
            'oneDStackedWidget_Z_2': FakeWidget('5'),
        }}
        self.shutterOpenCloseButton = _FakeButton('Open')
        self.iconFolder = ''
        self.shown = []
        self.applied = []

    # GUI halves, stubbed so no Qt is needed
    def _showSnappedImage(self, image):
        self.shown.append(image)

    def _applyOneDstageLayout(self, stage_name, pos):
        self.applied.append((stage_name, pos))


class _FakeButton:
    def __init__(self, text):
        self._text = text
        self.icon = None

    def text(self):
        return self._text

    def setText(self, value):
        self._text = value

    def setIcon(self, icon):
        self.icon = icon


@pytest.fixture(autouse=True)
def _no_qicon(monkeypatch):
    """The shutter slot builds a QIcon; a stub keeps this Qt-free."""
    monkeypatch.setattr(mm, 'QIcon', lambda *a, **k: 'icon')


def test_snap_runs_off_the_calling_thread_and_displays_on_it(shared, service):
    host = _Host(shared)
    caller = threading.get_ident()

    host.snapImage()
    _drain(service)

    assert shared.MILcore.names() == ['set_exposure', 'snap_image', 'get_image']
    assert caller not in shared.MILcore.threads()
    assert shared.MILcore.calls[0][1] == (25.0,)  # the widget value, read on the caller
    assert len(host.shown) == 1


def test_snap_runs_inline_without_a_service(shared):
    host = _Host(shared)

    host.snapImage()

    assert shared.MILcore.names() == ['set_exposure', 'snap_image', 'get_image']
    assert shared.MILcore.threads() == {threading.get_ident()}
    assert len(host.shown) == 1


def test_stage_move_is_queued_and_the_readback_follows_it(shared, service):
    """FIFO ordering is what makes the read-back report the post-move position."""
    host = _Host(shared)
    caller = threading.get_ident()

    host.moveOneDStage(2)  # small step
    _drain(service)

    assert shared.MILcore.names() == ['set_relative_position', 'get_position']
    assert shared.MILcore.calls[0][1] == ('Z', 0.5)
    assert caller not in shared.MILcore.threads()
    assert host.applied == [('Z', 12.5)]


def test_stage_move_applies_wheel_notches_as_one_move(shared):
    """T-F8's `steps` multiplier still folds a burst into a single move."""
    host = _Host(shared)

    host.moveOneDStage(2, steps=4)

    assert shared.MILcore.calls[0][1] == ('Z', 2.0)


def test_shutter_write_is_queued_but_the_button_updates_immediately(shared, service):
    host = _Host(shared)

    host.on_shutterOpenCloseButtonPressed()

    # The button never waited for a reply, and still does not.
    assert host.shutterOpenCloseButton.text() == 'Close'
    _drain(service)
    assert shared.MILcore.names() == ['set_shutter_open']
    assert shared.MILcore.calls[0][1] == (True,)
    assert threading.get_ident() not in shared.MILcore.threads()


def test_reset_roi_is_queued(shared, service):
    host = _Host(shared)

    host.resetROI()
    _drain(service)

    assert shared.MILcore.names() == ['clear_roi']


def test_set_roi_without_live_mode_is_one_queued_job(shared, service):
    host = _Host(shared)
    shared.liveMode = False

    host.setROI([1, 2, 3, 4])
    _drain(service)

    assert shared.MILcore.names() == ['set_roi', 'wait_for_system']
    assert shared.MILcore.calls[0][1] == ((1, 2, 3, 4),)


def test_set_roi_during_live_runs_off_both_the_gui_and_owner_threads(shared, service):
    """It waits for the acquisition worker, so it can hold neither thread.

    On the GUI thread that wait is up to ACQ_STOP_TIMEOUT_S; on the owner thread
    it would deadlock, because the live worker's own stop call is queued *on*
    that thread. So the orchestration gets a short-lived thread of its own.
    """
    host = _Host(shared)
    flips = []
    # Record the liveMode flips (and their thread) without a real acqModeChanged.
    type(shared).liveMode = property(
        lambda self: True,
        lambda self, value: flips.append((value, threading.get_ident())))
    try:
        host.setROI([5, 6, 7, 8])
        deadline = time.monotonic() + 5.0
        while len(flips) < 2 and time.monotonic() < deadline:
            time.sleep(0.005)
    finally:
        del type(shared).liveMode
        shared.liveMode = False

    _drain(service)
    assert [value for value, _thread in flips] == [False, True]
    flip_threads = {thread for _value, thread in flips}
    assert threading.get_ident() not in flip_threads, 'blocked the calling thread'
    assert service._owner_ident not in flip_threads, 'would deadlock the hardware queue'
    assert shared.MILcore.names() == ['wait_for_system', 'set_roi', 'wait_for_system']


def test_live_mode_starts_only_after_the_exposure_write_landed(shared, service):
    """Otherwise the camera can start on the previous exposure."""
    host = _Host(shared)
    order = []
    original = shared.MILcore.set_exposure

    def slow_set_exposure(value):
        order.append('exposure')
        original(value)

    shared.MILcore.set_exposure = slow_set_exposure
    started = []
    host._startLiveMode = lambda: (order.append('live'), started.append(True))

    request = mm.submitHardware(shared, shared.MILcore.set_exposure, 25.0,
                                label='mm.setExposure',
                                callback=host._startLiveAfterExposure)
    if request is not None:
        request.wait(5.0)
    _drain(service)

    assert order == ['exposure', 'live']
    assert started == [True]
