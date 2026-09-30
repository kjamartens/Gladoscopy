"""Coverage for the hardware owner thread (T-B3).

Threading invariant 2: the core has exactly one owning thread and everything
else submits requests to it. `MicroscopeService` is that thread;
`MicroscopeProxy` is the MIL-shaped facade worker code keeps calling
synchronously.

The properties that matter here:

1. **Every call really runs on the owner thread** -- that is the whole point.
2. **Priority ordering.** A frame-path request queued behind a burst of UI
   intents is serviced first.
3. **Re-entrancy.** A request that itself calls back into the service runs
   inline instead of deadlocking (MIL methods compose, and the streaming pull
   loop calls in).
4. **Streaming mode still services requests.** A stage move issued during live
   mode must not wait out the acquisition.
5. **Failure modes are caller-visible**: the backend's exception is re-raised
   on the caller's thread, a stopped service fails queued requests rather than
   hanging them, and the proxy falls back to a direct call when there is no
   owner thread to submit to.
"""
from __future__ import annotations

import threading
import time
from unittest.mock import MagicMock

import pytest

from glados_pycromanager.Core.microscope_service import (
    MicroscopeProxy,
    MicroscopeService,
    Priority,
    ServiceError,
    ServiceStopped,
    ServiceTimeout,
)


class FakeMIL:
    """Just enough MIL surface to see which thread a call ran on."""

    def __init__(self):
        self.core = object()
        self.calls = []
        self.call_threads = []

    def get_exposure(self):
        self.calls.append('get_exposure')
        self.call_threads.append(threading.get_ident())
        return 20.0

    def set_exposure(self, value):
        self.calls.append(('set_exposure', value))
        self.call_threads.append(threading.get_ident())

    def boom(self):
        raise ValueError('backend said no')

    def slow(self, seconds):
        time.sleep(seconds)
        return 'slow done'


@pytest.fixture
def service():
    svc = MicroscopeService(FakeMIL(), name='TestMicroscopeService')
    svc.start()
    yield svc
    svc.stop()


def test_calls_run_on_the_owner_thread(service):
    caller = threading.get_ident()

    assert service.call_mil('get_exposure') == 20.0

    (ran_on,) = service.mil.call_threads
    assert ran_on != caller
    assert service.is_owner_thread() is False


def test_proxy_preserves_the_mil_api(service):
    proxy = service.proxy()

    assert proxy.get_exposure() == 20.0
    proxy.set_exposure(7.5)

    assert service.mil.calls == ['get_exposure', ('set_exposure', 7.5)]
    # Non-callables fall through to the real MIL.
    assert proxy.core is service.mil.core
    assert proxy.mil is service.mil


def test_backend_exception_is_reraised_on_the_caller(service):
    with pytest.raises(ValueError, match='backend said no'):
        service.proxy().boom()


def test_frame_priority_overtakes_queued_ui_intents():
    """A FRAME request queued behind NORMAL ones is serviced first."""
    order = []
    gate = threading.Event()
    svc = MicroscopeService(FakeMIL(), name='PriorityService')
    try:
        svc.start()
        # Block the owner thread so the rest of the queue builds up behind it.
        svc.submit(gate.wait, 5.0, label='gate')
        for i in range(4):
            svc.submit(order.append, f'normal{i}', priority=Priority.NORMAL)
        frame = svc.submit(order.append, 'frame', priority=Priority.FRAME)
        gate.set()
        frame.wait(5.0)

        assert order[0] == 'frame'
    finally:
        gate.set()
        svc.stop()


def test_fifo_within_one_priority():
    order = []
    gate = threading.Event()
    svc = MicroscopeService(FakeMIL(), name='FifoService')
    try:
        svc.start()
        svc.submit(gate.wait, 5.0, label='gate')
        requests = [svc.submit(order.append, i) for i in range(5)]
        gate.set()
        requests[-1].wait(5.0)

        assert order == [0, 1, 2, 3, 4]
    finally:
        gate.set()
        svc.stop()


def test_a_request_can_call_back_into_the_service(service):
    """Re-entrancy: MIL methods compose, so this must not deadlock."""
    def nested():
        assert service.is_owner_thread()
        return service.call_mil('get_exposure')

    assert service.call(nested, label='nested') == 20.0


def test_streaming_runs_the_pull_loop_on_the_owner_thread(service):
    pulls = []

    def pull_once():
        pulls.append(threading.get_ident())
        return len(pulls) < 5  # then report "nothing ready" and idle

    service.start_streaming(pull_once, idle_sleep=0.001, label='test stream')
    try:
        deadline = time.time() + 5.0
        while len(pulls) < 5 and time.time() < deadline:
            time.sleep(0.005)
    finally:
        service.stop_streaming()

    assert len(pulls) >= 5
    assert set(pulls) == {service._owner_ident}
    assert threading.get_ident() not in pulls


def test_requests_are_serviced_between_frame_pulls(service):
    """A UI intent issued during live mode must not wait out the acquisition."""
    stop = threading.Event()

    def pull_once():
        return not stop.is_set()

    service.start_streaming(pull_once, idle_sleep=0.001, label='busy stream')
    try:
        assert service.proxy().get_exposure() == 20.0
    finally:
        stop.set()
        service.stop_streaming()


def test_a_raising_pull_loop_leaves_streaming_but_keeps_the_service(service):
    def pull_once():
        raise RuntimeError('camera fell over')

    service.start_streaming(pull_once, idle_sleep=0.001, label='doomed')
    deadline = time.time() + 5.0
    while service.is_streaming and time.time() < deadline:
        time.sleep(0.005)

    assert service.is_streaming is False
    assert service.running is True
    assert service.call_mil('get_exposure') == 20.0


def test_double_streaming_is_refused(service):
    service.start_streaming(lambda: False, label='first')
    try:
        with pytest.raises(ServiceError):
            service.start_streaming(lambda: False, label='second')
    finally:
        service.stop_streaming()


def test_submitting_to_a_stopped_service_raises():
    svc = MicroscopeService(FakeMIL(), name='StoppedService')
    with pytest.raises(ServiceStopped):
        svc.submit(lambda: None, label='nope')


def test_stop_fails_queued_requests_instead_of_hanging_them():
    gate = threading.Event()
    svc = MicroscopeService(FakeMIL(), name='DrainService')
    svc.start()
    svc.submit(gate.wait, 5.0, label='gate')
    queued = svc.submit(lambda: 'never', label='queued')
    gate.set()
    svc.stop()

    with pytest.raises(ServiceStopped):
        queued.wait(1.0)


def test_a_blocking_call_times_out_rather_than_hanging(service):
    with pytest.raises(ServiceTimeout):
        service.call(time.sleep, 2.0, timeout=0.05, label='slow')
    # The owner thread is still finishing that sleep; leave it to the fixture.


def test_proxy_falls_back_to_a_direct_call_without_a_running_service():
    """Tests, the napari-plugin path and post-shutdown callers all hit this."""
    mil = FakeMIL()
    svc = MicroscopeService(mil, name='NeverStarted')
    proxy = MicroscopeProxy(svc)

    assert proxy.get_exposure() == 20.0
    assert mil.call_threads == [threading.get_ident()]


def test_request_completed_is_emitted_for_success_and_failure(service):
    """The reply signal T-B4's GUI slots will connect to.

    Connected DirectConnection here on purpose: the signal is emitted from the
    owner thread, and the default AutoConnection would *queue* it onto the
    thread that created the service -- which is exactly what production wants
    (a GUI slot receives it on the GUI thread) and exactly what a test with no
    event loop never sees.
    """
    from PyQt5.QtCore import Qt

    seen = []
    service.request_completed.connect(seen.append, Qt.DirectConnection)

    service.call_mil('get_exposure')
    with pytest.raises(ValueError):
        service.proxy().boom()

    deadline = time.time() + 2.0
    while len(seen) < 2 and time.time() < deadline:
        time.sleep(0.005)
    assert [r.label for r in seen] == ['MIL.get_exposure', 'MIL.boom']
    assert seen[0].exception is None
    assert isinstance(seen[1].exception, ValueError)


def test_shared_data_starts_and_stops_one_service():
    from glados_pycromanager.GUI.sharedFunctions import Shared_data

    shared = Shared_data()
    mil = MagicMock()
    mil.core = object()
    shared._MILcore = mil  # bypass the T-B2 mirror refresh

    service = shared.start_microscope_service(name='SharedDataService')
    try:
        assert service.running
        # Idempotent: same MIL, same service.
        assert shared.start_microscope_service() is service
        assert shared.microscope_proxy().mil is mil
    finally:
        shared.stop_microscope_service()

    assert service.running is False
    assert shared.microscope_service is None
    # Without a service the proxy accessor hands back the raw MIL.
    assert shared.microscope_proxy() is mil
