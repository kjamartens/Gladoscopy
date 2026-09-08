"""Coverage for the T-C3 continuous-sequence live path.

`run_liveSequence_worker` replaces the legacy "live mode is a 999-frame MDA
restarted in a loop" behaviour with a plain continuous sequence acquisition
read out of the circular buffer. It is backend-blind — it only calls the MIL
primitives added in T-C1 — which is exactly what makes it testable here
against `FakeMicroscopeInterfaceLayer` with no hardware and no acquisition
engine.

The handler is built with `object.__new__` rather than `napariHandler(...)`:
the real `__init__` wants a live napari viewer and a full `Shared_data`, and
none of that is what these tests are about. The frame-ring consumer is stubbed
out so pushed frames stay in the ring for assertions instead of being drained
into the (absent) display path.
"""
from __future__ import annotations

import time
from collections import deque
from threading import Event, Thread

import numpy as np
import pytest

import glados_pycromanager.GUI.napariGlados as napariGlados
from glados_pycromanager.GUI.frame_ring import FrameRing
from glados_pycromanager.GUI.sharedFunctions import Config
from tests.fakes.fake_mil import FakeMicroscopeInterfaceLayer

JOIN_TIMEOUT_S = 5.0


class _SeededFakeMIL(FakeMicroscopeInterfaceLayer):
    """A fake MIL that loads `frames` into the buffer at sequence start.

    A test cannot simply pre-fill the buffer: the worker clears it before
    starting the sequence, precisely so the first displayed frame is not a
    stale one. Seeding at start time is both deterministic (every frame is in
    the buffer before the worker's first `get_remaining_image_count()`) and
    faithful to what the camera actually does.
    """

    def __init__(self, frames=()):
        super().__init__()
        self._seed_frames = list(frames)

    def start_continuous_sequence_acquisition(self, interval_ms=0):
        super().start_continuous_sequence_acquisition(interval_ms)
        for image, metadata in self._seed_frames:
            self.push_frame(image, metadata)


class _StubSharedData:
    """The handful of `Shared_data` attributes the live worker touches."""

    def __init__(self, mil, config):
        self.MILcore = mil
        self.config = config
        self.allMDAslicesRendered = None
        self.RTAnalysisQueuesThreads = []
        self.mdaMode = False
        self.liveMode = True
        self.perf_labels: dict[int, str] = {}
        self.debugImageArrivalTimes = []
        self.debugImageDisplayTimes = []
        self._headless = True
        self.backend = "Python"

    def register_perf_thread_label(self, native_id, label):
        self.perf_labels[native_id] = label

    def unregister_perf_thread_label(self, native_id):
        self.perf_labels.pop(native_id, None)


def _make_handler(mil, config):
    """A napariHandler with only what run_liveSequence_worker reaches for."""
    handler = object.__new__(napariGlados.napariHandler)
    handler.shared_data = _StubSharedData(mil, config)
    handler.liveOrMda = "live"
    handler.acqstate = True
    handler.frame_ring = FrameRing(64)
    handler._frame_ring_thread = None
    handler._frame_ring_stop = Event()
    handler.visualisation_queue = deque(maxlen=10)
    handler._new_image = Event()
    # Set by run_MILCoreAcquisition_worker's outer finally; the dispatch tests
    # below run that method for real.
    handler._worker_stopped_event = Event()

    # Record the consumer lifecycle instead of starting a real thread, so the
    # frames the worker pushes stay in the ring where a test can see them.
    handler.consumer_starts = []
    handler.consumer_stops = []
    handler._start_frame_ring_consumer = lambda needs_every_frame: (
        handler.consumer_starts.append(needs_every_frame)
    )
    handler._stop_frame_ring_consumer = lambda: handler.consumer_stops.append(True)
    return handler


def _run_until_frames(handler, expected_pushes):
    """Run the worker in a thread until it has pushed `expected_pushes` frames."""
    thread = Thread(target=handler.run_liveSequence_worker, args=(None,), daemon=True)
    thread.start()
    deadline = time.monotonic() + JOIN_TIMEOUT_S
    while handler.frame_ring.pushed < expected_pushes and time.monotonic() < deadline:
        time.sleep(0.005)
    handler.acqstate = False
    thread.join(timeout=JOIN_TIMEOUT_S)
    assert not thread.is_alive(), "run_liveSequence_worker did not exit"
    assert handler.frame_ring.pushed >= expected_pushes, (
        f"only {handler.frame_ring.pushed} frames reached the ring"
    )
    return thread


def _frames(n, shape=(4, 6)):
    return [
        (np.full(shape, i, dtype=np.uint16), {"FrameNumber": i}) for i in range(n)
    ]


@pytest.fixture
def config():
    cfg = Config()
    cfg.mda_config.live_mode_method = "sequence"
    cfg.mda_config.vis_method = "frameByFrame"
    return cfg


# ---- sequence lifecycle ----------------------------------------------


def test_clears_buffer_then_starts_continuous_sequence(config):
    mil = _SeededFakeMIL(_frames(1))
    handler = _make_handler(mil, config)

    _run_until_frames(handler, 1)

    # Started free-running (interval 0), and the stale-frame clear happened.
    assert mil._continuous_starts == [0.0]
    assert mil._clear_buffer_calls >= 1
    # The display-only path takes the shallow ring, not the storage one.
    assert handler.consumer_starts == [False]
    assert handler.consumer_stops == [True]


def test_sequence_is_not_running_after_stop(config):
    mil = _SeededFakeMIL(_frames(1))
    handler = _make_handler(mil, config)

    _run_until_frames(handler, 1)

    assert mil._stop_seq_calls >= 1
    assert mil.is_sequence_running() is False


def test_stop_and_drain_still_run_when_the_pull_raises(config):
    """The finally block is the only thing that stops the camera."""
    mil = _SeededFakeMIL(_frames(1))
    handler = _make_handler(mil, config)

    def boom():
        raise RuntimeError("backend blew up mid-pull")

    mil.get_last_image_and_metadata = boom

    thread = Thread(target=handler.run_liveSequence_worker, args=(None,), daemon=True)
    thread.start()
    thread.join(timeout=JOIN_TIMEOUT_S)
    assert not thread.is_alive()

    assert mil.is_sequence_running() is False
    assert handler.consumer_stops == [True]


# ---- pull policy -----------------------------------------------------


def test_latest_policy_shows_the_newest_frame_and_drops_the_backlog(config):
    config.mda_config.live_pull_policy = "latest"
    mil = _SeededFakeMIL(_frames(3))
    handler = _make_handler(mil, config)

    _run_until_frames(handler, 1)

    # Peek takes the newest of the three; the clear that follows discards the
    # two it skipped, so the buffer cannot grow behind a slow display.
    assert handler.frame_ring.pushed == 1
    image, metadata = handler.frame_ring.pop_next()
    assert int(image[0][0]) == 2
    assert metadata["FrameNumber"] == 2
    assert mil.get_remaining_image_count() == 0


def test_sequential_policy_delivers_every_frame_in_order(config):
    config.mda_config.live_pull_policy = "sequential"
    mil = _SeededFakeMIL(_frames(3))
    handler = _make_handler(mil, config)

    _run_until_frames(handler, 3)

    assert handler.frame_ring.pushed == 3
    delivered = []
    while True:
        item = handler.frame_ring.pop_next()
        if item is None:
            break
        delivered.append(item[1]["FrameNumber"])
    assert delivered == [0, 1, 2]


def test_unknown_pull_policy_falls_back_to_latest(config):
    # A hand-edited config JSON can hold anything; only an explicit
    # 'sequential' may take the overflow-capable path.
    config.mda_config.live_pull_policy = "nonsense"
    mil = _SeededFakeMIL(_frames(3))
    handler = _make_handler(mil, config)

    _run_until_frames(handler, 1)
    assert handler.frame_ring.pushed == 1


# ---- synthesised metadata --------------------------------------------


def test_metadata_carries_monotonic_time_axis_and_hardware_constants(config):
    config.mda_config.live_pull_policy = "sequential"
    mil = _SeededFakeMIL(_frames(2))
    mil.set_exposure(37.0)
    mil._pixel_size_um = 0.65
    mil.set_roi((0, 0, 6, 4))
    handler = _make_handler(mil, config)

    _run_until_frames(handler, 2)

    first = handler.frame_ring.pop_next()[1]
    second = handler.frame_ring.pop_next()[1]
    assert first["Axes"] == {"time": 0}
    assert second["Axes"] == {"time": 1}
    assert first["Exposure"] == 37.0
    assert first["PixelSize_um"] == 0.65
    assert tuple(first["ROI"]) == (0, 0, 6, 4)
    assert "Time" in first
    # The backend's own tags survive alongside the synthesised keys.
    assert first["FrameNumber"] == 0


def test_metadata_passes_through_metadata_refactor_unchanged(config):
    """No MDAEvent on this path, so refactor must be a pass-through."""
    import glados_pycromanager.GUI.utils as utils

    handler = _make_handler(FakeMicroscopeInterfaceLayer(), config)
    metadata = handler._live_sequence_metadata(
        {"FrameNumber": 5}, 5, {"Exposure": 10.0, "PixelSize_um": 1.0, "ROI": (0, 0, 4, 4)}
    )
    assert utils.metadata_refactor(dict(metadata), None)["Axes"] == {"time": 5}


def test_hardware_constants_are_read_once_per_acquisition(config, monkeypatch):
    config.mda_config.live_pull_policy = "sequential"
    mil = _SeededFakeMIL(_frames(3))

    calls = {"exposure": 0, "pixel_size": 0, "roi": 0}
    for name, key in (
        ("get_exposure", "exposure"),
        ("get_pixel_size_um", "pixel_size"),
        ("get_roi", "roi"),
    ):
        original = getattr(mil, name)

        def counted(_original=original, _key=key):
            calls[_key] += 1
            return _original()

        setattr(mil, name, counted)

    handler = _make_handler(mil, config)
    _run_until_frames(handler, 3)

    # Three frames, but one hardware read each -- these are @_hardware_locked
    # MIL calls on the real thing, and a per-frame read would put the live loop
    # in contention with the GUI thread's stage/config calls.
    assert calls == {"exposure": 1, "pixel_size": 1, "roi": 1}


# ---- dispatch: 'mda' still selects the legacy worker ------------------


def _make_dispatch_handler(config, monkeypatch):
    mil = FakeMicroscopeInterfaceLayer()
    handler = _make_handler(mil, config)
    handler.shared_data.liveMode = True
    # run_MILCoreAcquisition_worker reads the *module-level* `shared_data`
    # global (bound in runNapariPycroManager) for config and perf labels.
    monkeypatch.setattr(napariGlados, "shared_data", handler.shared_data, raising=False)
    monkeypatch.setattr(napariGlados, "cleanUpTemporaryFiles", lambda **kw: None)
    return handler


def test_sequence_method_selects_the_new_worker(config, monkeypatch):
    config.mda_config.live_mode_method = "sequence"
    handler = _make_dispatch_handler(config, monkeypatch)

    taken = []

    def fake_sequence_worker(parent):
        taken.append("sequence")
        handler.acqstate = False

    def fail_acquisition(*args, **kwargs):
        raise AssertionError("legacy Acquisition path must not be used")

    handler.run_liveSequence_worker = fake_sequence_worker
    monkeypatch.setattr(napariGlados, "Acquisition", fail_acquisition)

    # run_MILCoreAcquisition_worker is a napari @thread_worker: calling it
    # builds a FunctionWorker without starting a thread, and .work() runs the
    # wrapped body synchronously.
    handler.run_MILCoreAcquisition_worker(parent=handler).work()
    assert taken == ["sequence"]


def test_mda_method_still_selects_the_legacy_acquisition_path(config, monkeypatch):
    config.mda_config.live_mode_method = "mda"
    handler = _make_dispatch_handler(config, monkeypatch)

    taken = []

    class _FakeAcquisition:
        def __init__(self, *args, **kwargs):
            taken.append("acquisition")

        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

        def acquire(self, events):
            handler.acqstate = False

    def fail_sequence_worker(parent):
        raise AssertionError("sequence worker must not run when method == 'mda'")

    handler.run_liveSequence_worker = fail_sequence_worker
    monkeypatch.setattr(napariGlados, "Acquisition", _FakeAcquisition)

    handler.run_MILCoreAcquisition_worker(parent=handler).work()
    assert taken == ["acquisition"]


# ---- T-C4: multiDstack must not engage on the sequence live path -----


def _record_zarr_writes(handler):
    writes = []
    handler._try_write_frame_to_zarr = lambda image, metadata: writes.append(metadata)
    return writes


def test_multidstack_is_overridden_to_framebyframe_during_live(config):
    config.mda_config.vis_method = "multiDstack"
    handler = _make_handler(_SeededFakeMIL(), config)

    assert handler._effective_vis_method() == "multiDstack"  # not live yet
    handler._live_sequence_active = True
    assert handler._effective_vis_method() == "frameByFrame"


def test_framebyframe_config_is_left_alone(config):
    config.mda_config.vis_method = "frameByFrame"
    handler = _make_handler(_SeededFakeMIL(), config)
    handler._live_sequence_active = True
    assert handler._effective_vis_method() == "frameByFrame"


def test_no_zarr_write_for_live_frames_when_multidstack_configured(config):
    """The black-slice failure mode: a store nothing can index back out."""
    config.mda_config.vis_method = "multiDstack"
    handler = _make_handler(_SeededFakeMIL(), config)
    writes = _record_zarr_writes(handler)

    handler._live_sequence_active = True
    handler._process_ring_frame(np.zeros((4, 6), dtype=np.uint16), {"Axes": {"time": 0}})

    assert writes == []
    # The frame still reaches the display/RT queues -- this suppresses storage,
    # not the preview itself.
    assert len(handler.visualisation_queue) == 1


def test_mda_frames_still_write_to_zarr_when_multidstack_configured(config):
    config.mda_config.vis_method = "multiDstack"
    handler = _make_handler(_SeededFakeMIL(), config)
    writes = _record_zarr_writes(handler)

    # Not the live sequence path -> MDA multiDstack behaviour is untouched.
    handler._live_sequence_active = False
    handler._process_ring_frame(np.zeros((4, 6), dtype=np.uint16), {"Axes": {"time": 0}})

    assert len(writes) == 1


def test_the_configured_setting_is_never_written_back(config):
    """An override for the duration of live mode, not a settings change."""
    config.mda_config.vis_method = "multiDstack"
    mil = _SeededFakeMIL(_frames(1))
    handler = _make_handler(mil, config)

    _run_until_frames(handler, 1)

    assert config.mda_config.vis_method == "multiDstack"
    # ...and the override is lifted once live mode is over.
    assert handler._live_sequence_active is False
    assert handler._effective_vis_method() == "multiDstack"


def test_override_is_lifted_even_when_the_pull_raises(config):
    config.mda_config.vis_method = "multiDstack"
    mil = _SeededFakeMIL(_frames(1))
    handler = _make_handler(mil, config)
    mil.get_last_image_and_metadata = lambda: (_ for _ in ()).throw(RuntimeError("boom"))

    thread = Thread(target=handler.run_liveSequence_worker, args=(None,), daemon=True)
    thread.start()
    thread.join(timeout=JOIN_TIMEOUT_S)
    assert not thread.is_alive()

    assert handler._live_sequence_active is False


def test_the_override_is_logged_once_with_a_reason(config, caplog):
    config.mda_config.vis_method = "multiDstack"
    handler = _make_handler(_SeededFakeMIL(_frames(1)), config)

    with caplog.at_level("INFO"):
        _run_until_frames(handler, 1)

    forced = [r for r in caplog.records if "forced to 'frameByFrame'" in r.getMessage()]
    assert len(forced) == 1
    assert "multiDstack" in forced[0].getMessage()


def test_no_override_logged_when_framebyframe_configured(config, caplog):
    config.mda_config.vis_method = "frameByFrame"
    handler = _make_handler(_SeededFakeMIL(_frames(1)), config)

    with caplog.at_level("INFO"):
        _run_until_frames(handler, 1)

    assert not [r for r in caplog.records if "forced to 'frameByFrame'" in r.getMessage()]


def test_override_is_lifted_when_the_ring_consumer_fails_to_start(config, monkeypatch):
    """A stuck override would silently downgrade the *next* MDA's multiDstack."""
    config.mda_config.vis_method = "multiDstack"
    handler = _make_handler(_SeededFakeMIL(_frames(1)), config)
    monkeypatch.setattr(
        handler,
        "_start_frame_ring_consumer",
        lambda needs_every_frame: (_ for _ in ()).throw(RuntimeError("no thread")),
    )

    thread = Thread(target=handler.run_liveSequence_worker, args=(None,), daemon=True)
    thread.start()
    thread.join(timeout=JOIN_TIMEOUT_S)
    assert not thread.is_alive()

    assert handler._live_sequence_active is False
    assert handler._effective_vis_method() == "multiDstack"
