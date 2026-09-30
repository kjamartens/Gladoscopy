"""LivePollPacer: the live pull loop's idle schedule, and the service's
interruptible idle wait that lets a long pacing sleep coexist with UI requests.
"""
import threading
import time

import pytest

from glados_pycromanager.GUI.napariGlados import LivePollPacer, napariHandler


def test_before_the_first_frame_the_pacer_polls_finely():
    pacer = LivePollPacer(0.05, clock=lambda: 0.0)
    assert pacer.idle_sleep() == pytest.approx(0.05 * LivePollPacer.FINE_FRACTION)


def test_after_a_frame_it_sleeps_most_of_the_interval_then_polls_finely():
    pacer = LivePollPacer(0.05)
    pacer.frame_arrived(now=10.0)
    # Right after a frame: one coarse idle up to 90 % of the interval.
    assert pacer.idle_sleep(now=10.0) == pytest.approx(0.045)
    assert pacer.idle_sleep(now=10.03) == pytest.approx(0.015)
    # Past the coarse window: fine steps, so latency stays ~1.5 ms.
    assert pacer.idle_sleep(now=10.046) == pytest.approx(0.0015)
    assert pacer.idle_sleep(now=10.2) == pytest.approx(0.0015)


def test_polls_per_frame_drop_from_about_twenty_to_a_handful():
    """Simulate a 55 ms camera (50 ms exposure + readout) and count polls."""
    t = [0.0]
    pacer = LivePollPacer(0.05, clock=lambda: t[0])
    frame_times = [i * 0.055 for i in range(1, 101)]
    polls = 0
    next_frame = 0
    while next_frame < len(frame_times):
        polls += 1
        if t[0] >= frame_times[next_frame]:
            pacer.frame_arrived()
            next_frame += 1
        else:
            t[0] += pacer.idle_sleep()
    per_frame = polls / len(frame_times)
    assert per_frame < 10, per_frame  # was ~21 with the flat 0.5 ms idle


def test_interval_estimate_tracks_the_real_frame_interval():
    pacer = LivePollPacer(0.05)
    for i in range(60):
        pacer.frame_arrived(now=i * 0.1)
    assert pacer.interval_s == pytest.approx(0.1, rel=0.05)


def test_one_long_stall_cannot_inflate_the_estimate_into_oversleeping():
    pacer = LivePollPacer(0.05)
    pacer.frame_arrived(now=0.0)
    pacer.frame_arrived(now=5.0)  # owner thread was busy for 5 s
    assert pacer.interval_s == pytest.approx(0.05 * (1 + LivePollPacer.EMA_ALPHA))


@pytest.mark.parametrize('exposure', [0, None, 'garbage', -3])
def test_unknown_exposure_falls_back_to_the_finest_step(exposure):
    pacer = LivePollPacer(exposure)
    assert pacer.idle_sleep(now=0.0) == LivePollPacer.MIN_IDLE_S


def test_idle_never_exceeds_the_cap_for_long_exposures():
    pacer = LivePollPacer(2.0)
    pacer.frame_arrived(now=0.0)
    assert pacer.idle_sleep(now=0.0) == LivePollPacer.MAX_IDLE_S


def test_handler_poll_floor_is_the_pacer_floor():
    assert napariHandler.LIVE_SEQUENCE_POLL_S == LivePollPacer.MIN_IDLE_S


# --- MicroscopeService: callable idle_sleep, woken early by requests ---------

@pytest.fixture
def service():
    from glados_pycromanager.Core.microscope_service import MicroscopeService

    class FakeMIL:
        def get_exposure(self):
            return 20.0

    svc = MicroscopeService(FakeMIL())
    svc.start()
    yield svc
    svc.stop()


def test_callable_idle_sleep_is_reevaluated_each_idle(service):
    calls = []

    def idle():
        calls.append(time.perf_counter())
        return 0.001

    service.start_streaming(lambda: False, idle_sleep=idle, label='paced')
    try:
        deadline = time.time() + 2.0
        while len(calls) < 5 and time.time() < deadline:
            time.sleep(0.005)
    finally:
        service.stop_streaming()
    assert len(calls) >= 5


def test_a_request_ends_a_long_pacing_idle_early(service):
    """The pacer may ask for up to 50 ms; a stage move must not wait that out."""
    service.start_streaming(lambda: False, idle_sleep=lambda: 10.0, label='slow')
    try:
        time.sleep(0.02)  # let the loop enter its idle wait
        t0 = time.perf_counter()
        assert service.proxy().get_exposure() == 20.0
        assert time.perf_counter() - t0 < 0.03
    finally:
        service.stop_streaming()


def test_a_raising_idle_callable_does_not_kill_the_stream(service):
    pulls = []

    def pull():
        pulls.append(1)
        return False

    def idle():
        raise RuntimeError('pacer bug')

    service.start_streaming(pull, idle_sleep=idle, label='buggy pacer')
    try:
        deadline = time.time() + 2.0
        while len(pulls) < 3 and time.time() < deadline:
            time.sleep(0.005)
        assert service.is_streaming
    finally:
        service.stop_streaming()
    assert len(pulls) >= 3


def test_a_pull_that_skipped_frames_does_not_inflate_the_interval():
    """Under the `latest` policy one pull can consume several camera frames;
    counting that gap as one interval used to feed back into oversleeping."""
    pacer = LivePollPacer(0.05)
    t = 0.0
    pacer.frame_arrived(now=t)
    for _ in range(50):
        t += 0.1
        pacer.frame_arrived(now=t, frames=2)  # two 50 ms frames per pull
    assert pacer.interval_s == pytest.approx(0.05, rel=0.01)
