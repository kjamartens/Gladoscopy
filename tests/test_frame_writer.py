"""T-D3: the zarr write gets its own thread and its own buffer.

A zarr write is disk-bound -- ~9 ms for a 1024x1024 uint16 frame -- and it used
to run on the frame-ring consumer, the same thread that feeds the display and
every RT-analysis queue. That capped the whole frame path at roughly 110 fps,
and once the camera outran it the overwrite-oldest ring shed frames that
MMCORE_PLUS has no NDTiff store to recover.

`ZarrFrameWriter` moves the write behind its own queue. The two properties that
matter, and that these tests pin, are that it **absorbs bursts** (a backlog that
fits the memory budget costs the frame path nothing) and that when it cannot, it
**pushes back rather than dropping silently** -- the opposite of `FrameRing`,
where a stale display frame is worthless and dropping is correct.
"""
from __future__ import annotations

import threading
import time

import numpy as np
import pytest

from glados_pycromanager.GUI.frame_writer import (
    MIN_CAPACITY,
    ZarrFrameWriter,
)


class FakeArray:
    """An array-like that records writes, optionally slowly."""

    def __init__(self, shape=(16, 8, 8), dtype=np.uint16, delay=0.0):
        self.shape = shape
        self.dtype = np.dtype(dtype)
        self.delay = delay
        self.writes = []
        self._lock = threading.Lock()
        self.gate = None  # set to an Event to hold every write

    def __setitem__(self, key, value):
        if self.gate is not None:
            self.gate.wait()
        if self.delay:
            time.sleep(self.delay)
        with self._lock:
            self.writes.append((key, value))


@pytest.fixture
def writer_factory():
    created = []

    def make(array, **kwargs):
        writer = ZarrFrameWriter(array, **kwargs)
        writer.start()
        created.append(writer)
        return writer

    yield make
    for writer in created:
        writer.close(timeout=5)


def _frame(value=1, shape=(8, 8)):
    return np.full(shape, value, dtype=np.uint16)


# -- the basic contract ---------------------------------------------------

def test_submitted_frames_reach_the_array(writer_factory):
    array = FakeArray()
    writer = writer_factory(array)

    for i in range(5):
        writer.submit((i, slice(None), slice(None)), _frame(i))
    stats = writer.close(timeout=5)

    assert stats["written"] == 5
    assert stats["dropped"] == 0
    assert [key[0] for key in (k for k, _ in array.writes)] == [0, 1, 2, 3, 4]


def test_close_drains_the_backlog_before_returning(writer_factory):
    """Nothing may read the store until every queued frame has landed."""
    array = FakeArray(delay=0.005)
    writer = writer_factory(array)

    for i in range(20):
        writer.submit((i, slice(None), slice(None)), _frame(i))
    stats = writer.close(timeout=30)

    assert stats["written"] == 20
    assert len(array.writes) == 20


def test_a_failing_write_is_counted_and_does_not_kill_the_thread(writer_factory):
    class Exploding(FakeArray):
        def __setitem__(self, key, value):
            if key[0] == 1:
                raise ValueError("boom")
            super().__setitem__(key, value)

    array = Exploding()
    writer = writer_factory(array)

    for i in range(4):
        writer.submit((i, slice(None), slice(None)), _frame(i))
    stats = writer.close(timeout=5)

    assert stats["failed"] == 1
    assert stats["written"] == 3  # the thread survived and kept going


# -- sizing ---------------------------------------------------------------

def test_capacity_is_budgeted_in_bytes_not_frames():
    """A frame-count bound means something different per camera; a byte budget
    does not."""
    small = ZarrFrameWriter(FakeArray(shape=(4, 512, 512)),
                            memory_budget_bytes=64 * 1024 * 1024)
    large = ZarrFrameWriter(FakeArray(shape=(4, 2048, 2048)),
                            memory_budget_bytes=64 * 1024 * 1024)

    # 512^2 uint16 = 0.5 MB -> 128 frames; 2048^2 uint16 = 8 MB -> 8 frames.
    assert small.capacity == 128
    assert large.capacity == 8
    assert small.capacity > large.capacity


def test_capacity_never_falls_below_the_floor():
    """A queue of one is a rendezvous, not a buffer."""
    writer = ZarrFrameWriter(FakeArray(shape=(4, 4096, 4096)),
                             memory_budget_bytes=1024)

    assert writer.capacity == MIN_CAPACITY


def test_an_array_that_cannot_describe_itself_still_buffers():
    class Opaque:
        pass

    assert ZarrFrameWriter(Opaque()).capacity == MIN_CAPACITY


# -- burst absorption and backpressure ------------------------------------

def test_a_burst_that_fits_the_budget_costs_the_caller_nothing(writer_factory):
    """The whole point: a slow disk must not be charged to the frame path."""
    array = FakeArray(delay=0.02)  # 20 ms/frame, far slower than the producer
    writer = writer_factory(array, memory_budget_bytes=64 * 1024 * 1024)
    assert writer.capacity >= 16

    started = time.perf_counter()
    for i in range(16):
        assert writer.submit((i, slice(None), slice(None)), _frame(i)) is True
    submit_elapsed = time.perf_counter() - started

    # 16 frames x 20 ms = 320 ms of writing, absorbed by the queue.
    assert submit_elapsed < 0.15
    stats = writer.close(timeout=30)
    assert stats["written"] == 16
    assert stats["dropped"] == 0


def test_a_full_queue_blocks_instead_of_dropping(writer_factory):
    """FrameRing would overwrite the oldest frame here. Storage must not."""
    array = FakeArray(shape=(64, 8, 8))
    array.gate = threading.Event()  # hold every write until released
    writer = writer_factory(array, memory_budget_bytes=MIN_CAPACITY * 128,
                            submit_timeout_s=10)
    capacity = writer.capacity

    # Fill the queue well past capacity from another thread; it must not lose
    # frames, it must wait.
    total = capacity + 5
    done = threading.Event()

    def produce():
        for i in range(total):
            writer.submit((i, slice(None), slice(None)), _frame(i))
        done.set()

    producer = threading.Thread(target=produce, daemon=True)
    producer.start()
    time.sleep(0.2)
    assert not done.is_set(), "producer should be blocked on a full queue"

    array.gate.set()  # let the disk catch up
    producer.join(timeout=10)
    stats = writer.close(timeout=10)

    assert done.is_set()
    assert stats["dropped"] == 0
    assert stats["written"] == total
    assert stats["blocked_seconds"] > 0  # real backpressure was recorded


def test_a_wedged_disk_drops_and_says_so_rather_than_hanging(writer_factory):
    """An untimed block would make a stalled disk an uncancellable acquisition."""
    array = FakeArray(shape=(64, 8, 8))
    array.gate = threading.Event()  # never released
    writer = writer_factory(array, memory_budget_bytes=MIN_CAPACITY * 128,
                            submit_timeout_s=0.2)

    results = [writer.submit((i, slice(None), slice(None)), _frame(i))
               for i in range(writer.capacity + 4)]

    assert results[0] is True
    assert False in results, "a wedged disk must eventually drop, not hang"
    assert writer.dropped >= 1
    array.gate.set()


def test_max_depth_records_how_much_burst_was_absorbed(writer_factory):
    array = FakeArray(shape=(64, 8, 8), delay=0.01)
    writer = writer_factory(array, memory_budget_bytes=64 * 1024 * 1024)

    for i in range(12):
        writer.submit((i, slice(None), slice(None)), _frame(i))
    writer.close(timeout=30)

    # Diagnosability: without this a sustained overrun is a mystery afterwards.
    assert writer.max_depth > 1


def test_submit_after_close_is_refused_not_silently_lost(writer_factory):
    array = FakeArray()
    writer = writer_factory(array)
    writer.close(timeout=5)

    assert writer.submit((0, slice(None), slice(None)), _frame()) is False


# -- what the display is allowed to render --------------------------------

def test_last_written_tag_is_none_until_something_lands(writer_factory):
    array = FakeArray()
    array.gate = threading.Event()
    writer = writer_factory(array)

    writer.submit((0, slice(None), slice(None)), _frame(), tag=(0,))

    assert writer.last_written_tag is None, "not on disk yet, must not be shown"
    array.gate.set()


def test_last_written_tag_follows_the_disk_not_the_queue(writer_factory):
    """The regression this fixes: with a queued write the frame path runs ahead
    of the disk, so a viewer pointed at the arrived frame renders unwritten
    slices as black."""
    array = FakeArray(shape=(64, 8, 8), delay=0.01)
    writer = writer_factory(array, memory_budget_bytes=64 * 1024 * 1024)

    for i in range(20):
        writer.submit((i, slice(None), slice(None)), _frame(i), tag=(i,))
    # Producer is well ahead here; whatever the display would show must already
    # be on disk.
    mid_flight = writer.last_written_tag
    assert mid_flight is None or mid_flight[0] < 19

    writer.close(timeout=30)
    assert writer.last_written_tag == (19,), "final frame must be shown once landed"


def test_a_failed_write_does_not_advance_the_display(writer_factory):
    """A slice that raised is still zeros; pointing the viewer at it shows black."""
    class Exploding(FakeArray):
        def __setitem__(self, key, value):
            if key[0] == 1:
                raise ValueError("boom")
            super().__setitem__(key, value)

    writer = writer_factory(Exploding())
    for i in range(2):
        writer.submit((i, slice(None), slice(None)), _frame(i), tag=(i,))
    writer.close(timeout=5)

    assert writer.last_written_tag == (0,)
