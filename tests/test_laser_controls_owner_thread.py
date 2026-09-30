"""The laser controls submit hardware intents instead of blocking (T-B4).

`LaserControlScripts.py` is the site-specific laser UI. Three of its slots were
named in `CLAUDE.md` as standing violations of threading invariant 1:
`ResetLasersTrigger` issues ~100 TriggerScope serial round trips in one click,
`armLaser` sleeps 0.1 s per repeat frame mid-conversation, and `blinkUV` sleeps
for the whole blink between its on and off writes -- all on the GUI thread.

They now hand the work to the `MicroscopeService` owner thread (T-B3). What is
asserted here:

1. The **serial command sequence is unchanged** -- this drives real hardware,
   so the refactor must be observationally identical at the wire.
2. The work really leaves the calling thread when a service is running, and
   really runs inline when one is not (tests, the napari-plugin path).
3. Widget reads stay on the caller (a hardware thread must not read `form`),
   and widget writes are marshalled back.
"""
from __future__ import annotations

import json
import os
import threading
import time

import pytest

import glados_pycromanager.GUI.LaserControlScripts as lcs
from glados_pycromanager.Core.microscope_service import MicroscopeService


class FakeCore:
    """Records every property write, and which thread made it."""

    def __init__(self):
        self.commands = []
        self.threads = set()
        self.properties = {}

    def set_property(self, device, prop, value):
        self.commands.append((device, prop, value))
        self.threads.add(threading.get_ident())
        self.properties[(device, prop)] = value

    def get_property(self, device, prop):
        self.threads.add(threading.get_ident())
        if (device, prop) == ('TriggerScopeMM-Hub', 'Serial Receive'):
            return 'OK'
        return self.properties.get((device, prop), '0')


class FakeWidget:
    def __init__(self, text='', checked=False):
        self._text = str(text)
        self._checked = checked
        self.style = None

    def isChecked(self):
        return self._checked

    def text(self):
        return self._text

    def setText(self, value):
        self._text = str(value)

    def setStyleSheet(self, value):
        self.style = value


class FakeForm:
    """`form` is addressed by generated attribute names; make them on demand."""

    def __init__(self, **texts):
        self._widgets = {}
        for name, text in texts.items():
            self._widgets[name] = FakeWidget(text)
        self.VerboseBox = _FakeVerboseBox()

    def __getattr__(self, name):
        if name.startswith('_'):
            raise AttributeError(name)
        return self._widgets.setdefault(name, FakeWidget())


class _FakeVerboseBox:
    def __init__(self):
        self.text = ''

    def setPlainText(self, value):
        self.text = value

    def toPlainText(self):
        return self.text


class FakeSharedData:
    def __init__(self, service=None):
        self.microscope_service = service


def _mm_json():
    path = os.path.join(os.path.dirname(lcs.__file__), 'MM_PycroManager_JSON.json')
    with open(path) as fh:
        return json.load(fh)


@pytest.fixture
def laser_module(monkeypatch):
    """`LaserControlScripts` wired to fakes, with no service running."""
    core = FakeCore()
    form = FakeForm()
    monkeypatch.setattr(lcs, 'core', core, raising=False)
    monkeypatch.setattr(lcs, 'form', form, raising=False)
    monkeypatch.setattr(lcs, 'MM_JSON', _mm_json(), raising=False)
    monkeypatch.setattr(lcs, 'shared_data', FakeSharedData(), raising=False)
    # _onGuiThread would otherwise try to build a napari bridge.
    monkeypatch.setattr(lcs, '_onGuiThread', lambda fn: fn())
    return lcs, core, form


@pytest.fixture
def with_service(laser_module):
    """The same fakes, plus a running owner thread."""
    module, core, form = laser_module
    service = MicroscopeService(object(), name='LaserTestService').start()
    module.shared_data.microscope_service = service
    yield module, core, form, service
    service.stop()


def _drain(service, timeout=5.0):
    """Wait for the service queue to empty."""
    done = service.submit(lambda: None, label='barrier')
    done.wait(timeout)


def test_reset_sequence_is_unchanged(laser_module):
    """The wire-level contract: same commands, same order, as before T-B4."""
    module, core, _form = laser_module

    module.ResetLasersTrigger()

    sends = [value for device, prop, value in core.commands if prop == 'Serial Send']
    expected = []
    for i in range(5):
        expected += ['PAC'+str(i+1), 'BAD'+str(i+1)+'-0', 'BAL'+str(i+1)+'-0']
    expected.append('*')
    assert sends == expected
    # Two toggles per laser, so each laser ends where it started.
    onoff = [c for c in core.commands if c[1] == 'State']
    assert len(onoff) == 10


def test_reset_runs_inline_without_a_service(laser_module):
    module, core, _form = laser_module

    module.ResetLasersTrigger()

    assert core.commands, 'nothing was sent'
    assert core.threads == {threading.get_ident()}


def test_reset_leaves_the_calling_thread_when_a_service_runs(with_service):
    module, core, _form, service = with_service
    caller = threading.get_ident()

    module.ResetLasersTrigger()
    _drain(service)

    assert core.commands, 'nothing was sent'
    assert caller not in core.threads


def test_blink_uv_does_not_sleep_on_the_calling_thread(with_service):
    module, core, _form, service = with_service

    started = time.perf_counter()
    module.blinkUV(300)  # 0.3 s of sleep inside the job
    elapsed = time.perf_counter() - started

    assert elapsed < 0.1, 'blinkUV blocked its caller'
    _drain(service)
    sends = [value for _d, prop, value in core.commands if prop == 'Serial Send']
    assert sends == ['PAC9', 'SAO9-65535', 'SAO9-0']


def test_arm_laser_reads_widgets_on_the_caller_and_sends_on_the_service(with_service):
    """A hardware thread must never touch `form`."""
    module, core, form, service = with_service
    form.BlinkFrames_Edit_Laser_0.setText('2')
    form.Delay_Edit_Laser_0.setText('3')
    form.Length_Edit_Laser_0.setText('4')
    caller = threading.get_ident()
    read_threads = []

    original = FakeWidget.text

    def recording_text(self):
        read_threads.append(threading.get_ident())
        return original(self)

    FakeWidget.text = recording_text
    try:
        module.armLaser(0)
    finally:
        FakeWidget.text = original
    _drain(service)

    assert read_threads and set(read_threads) == {caller}
    assert caller not in core.threads
    sends = [value for _d, prop, value in core.commands if prop == 'Serial Send']
    assert sends[0] == 'PAC1'
    assert sends[-2:] == ['BAD1-3', 'BAL1-4']


def test_arm_laser_sequence_matches_the_pre_refactor_commands(laser_module):
    module, core, form = laser_module
    form.BlinkFrames_Edit_Laser_1.setText('2')
    form.Delay_Edit_Laser_1.setText('5')
    form.Length_Edit_Laser_1.setText('7')

    module.armLaser(1)

    sends = [value for _d, prop, value in core.commands if prop == 'Serial Send']
    # k=0 writes the power level, k=1 writes the zero-power repeat; each is
    # followed by the PAS transition command, then the delay/length pair.
    assert sends[0] == 'PAC2'
    assert sends[1].startswith('PAO2-0-')
    assert sends[2] == 'PAS2-1-1'
    assert sends[3] == 'PAO2-1-0'
    assert sends[4] == 'PAS2-1-1'
    assert sends[5:] == ['BAD2-5', 'BAL2-7']


def test_ts_response_reads_the_serial_response_once(laser_module):
    """It used to make three identical reads to show one answer."""
    module, core, _form = laser_module
    reads = []
    original = FakeCore.get_property

    def counting_get(self, device, prop):
        reads.append((device, prop))
        return original(self, device, prop)

    FakeCore.get_property = counting_get
    try:
        module.TS_Response_verbose()
    finally:
        FakeCore.get_property = original

    assert reads == [('TriggerScopeMM-Hub', 'Serial Receive')]


def test_intensity_write_is_queued_and_recorded_immediately(with_service):
    """The T-F8 duplicate-write skip must survive the write being async."""
    module, core, _form, service = with_service

    module.ChangeIntensityLaser(0, 40)
    assert module._lastWrittenLaserIntensity[0] == 40
    _drain(service)

    writes = [c for c in core.commands if c[1] == 'Volts']
    assert len(writes) == 1
    assert core.threads and threading.get_ident() not in core.threads
