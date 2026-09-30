"""Unit tests for glados_pycromanager.GUI.frame_ring.FrameRing (T-A7).

The ring is the hand-off point between the frameReady callback (which runs
synchronously on pymmcore-plus' MDA thread) and the consumer thread that does
the real per-frame work, so its contract is worth pinning down: bounded,
overwrite-oldest, drop-counting, and never a lost wake-up.
"""

import threading

import pytest

from glados_pycromanager.GUI.frame_ring import DEFAULT_CAPACITY, FrameRing


def test_default_capacity_is_small():
    assert FrameRing().capacity == DEFAULT_CAPACITY == 4


def test_rejects_zero_capacity():
    with pytest.raises(ValueError):
        FrameRing(0)


def test_empty_ring_pops_none():
    ring = FrameRing(2)
    assert ring.pop_next() is None
    assert ring.pop_latest() is None
    assert len(ring) == 0
    assert ring.dropped == 0
    assert ring.pushed == 0


def test_fifo_order_within_capacity():
    ring = FrameRing(3)
    for i in range(3):
        assert ring.push(i, {'n': i}) is True
    assert len(ring) == 3
    assert ring.pop_next() == (0, {'n': 0})
    assert ring.pop_next() == (1, {'n': 1})
    assert ring.pop_next() == (2, {'n': 2})
    assert ring.pop_next() is None
    assert ring.dropped == 0
    assert ring.pushed == 3


def test_push_overwrites_oldest_and_counts_drops():
    ring = FrameRing(2)
    ring.push('a', {})
    ring.push('b', {})
    # Third push is over capacity: it drops 'a' and reports False.
    assert ring.push('c', {}) is False
    assert len(ring) == 2
    assert ring.dropped == 1
    assert ring.pushed == 3
    assert ring.pop_next()[0] == 'b'
    assert ring.pop_next()[0] == 'c'


def test_pop_latest_discards_older_frames_as_drops():
    ring = FrameRing(4)
    for name in 'abcd':
        ring.push(name, {})
    assert ring.pop_latest()[0] == 'd'
    assert len(ring) == 0
    assert ring.dropped == 3
    assert ring.pop_latest() is None


def test_event_is_set_on_push_and_cleared_when_drained():
    ring = FrameRing(2)
    assert ring.wait(timeout=0) is False
    ring.push('a', {})
    ring.push('b', {})
    assert ring.wait(timeout=0) is True
    ring.pop_next()
    # Still a frame queued -> the consumer must stay awake.
    assert ring.event.is_set() is True
    ring.pop_next()
    assert ring.event.is_set() is False


def test_clear_does_not_count_as_drops_reset_does_zero_counters():
    ring = FrameRing(2)
    ring.push('a', {})
    ring.push('b', {})
    ring.push('c', {})  # one drop
    ring.clear()
    assert len(ring) == 0
    assert ring.dropped == 1
    assert ring.event.is_set() is False
    ring.reset()
    assert ring.dropped == 0
    assert ring.pushed == 0


def test_producer_never_blocks_and_consumer_sees_every_kept_frame():
    """A producer far faster than its consumer must not stall, and pushed must
    equal (received + dropped) once both sides are done."""
    ring = FrameRing(4)
    received = []
    stop = threading.Event()

    def consume():
        while not stop.is_set():
            ring.wait(timeout=0.05)
            while True:
                item = ring.pop_next()
                if item is None:
                    break
                received.append(item[0])
        while True:
            item = ring.pop_next()
            if item is None:
                return
            received.append(item[0])

    consumer = threading.Thread(target=consume)
    consumer.start()
    try:
        for i in range(2000):
            ring.push(i, {})
    finally:
        stop.set()
        ring.event.set()
        consumer.join(timeout=10)

    assert not consumer.is_alive()
    assert ring.pushed == 2000
    assert len(received) + ring.dropped == 2000
    # Whatever survived must have arrived in acquisition order.
    assert received == sorted(received)
