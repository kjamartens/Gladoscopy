"""Coverage for `MicroscopeInterfaceLayer`'s hardware serialization lock.

The lock (`_hw_lock`, applied via the `@_hardware_locked` decorator) enforces
threading invariant 2 of `claude_throughput_project.md`: all microscope access
is serialized regardless of the calling thread. Commit `cd01032` exists because
two threads drove the same core object concurrently and produced a native access
violation / JVM fatal crash.

Three properties matter and are asserted here:

1. **Re-entrancy.** MIL methods compose (`get_image_width()` calls `get_roi()`),
   so a plain `Lock` would self-deadlock on the very first call.
2. **Mutual exclusion.** Two threads' calls do not interleave inside the core.
3. **The cache-hit fast path is lock-free.** `get_exposure()` / `get_pixel_size_um()`
   must return a cached value *without* acquiring the lock, so the per-frame
   display path is not serialized behind a slow stage move.
"""
from __future__ import annotations

import threading
from unittest.mock import MagicMock

import pytest

from glados_pycromanager.Core.microscopeInterfaceLayer import (
    MicroscopeInstance,
    MicroscopeInterfaceLayer,
)


@pytest.fixture
def mil():
    """A MIL forced onto the MMCore-Plus branch with a MagicMock core.

    `set_core` would classify a MagicMock as UNKNOWN, so the backend tag is set
    directly -- backend *detection* is covered by test_microscope_interface_layer.py.
    """
    m = MicroscopeInterfaceLayer()
    m.core = MagicMock()
    m._mi = MicroscopeInstance.MMCORE_PLUS
    return m


def test_composed_mil_calls_do_not_deadlock(mil):
    """get_image_width() -> get_roi(); both are locked, so the lock must be re-entrant."""
    mil.core.getROI.return_value = (0, 0, 512, 256)

    # A non-re-entrant lock would hang here forever rather than fail, so guard
    # the call with a watchdog thread instead of trusting pytest to time out.
    result = {}

    def call():
        result['width'] = mil.get_image_width()
        result['height'] = mil.get_image_height()

    t = threading.Thread(target=call, daemon=True)
    t.start()
    t.join(timeout=5)
    assert not t.is_alive(), "get_image_width() deadlocked -- _hw_lock is not re-entrant"
    assert result == {'width': 512, 'height': 256}


def test_lock_is_reentrant_for_the_calling_thread(mil):
    """Holding the lock and then calling a locked method must not block."""
    mil.core.getROI.return_value = (0, 0, 64, 64)
    with mil._hw_lock:
        assert mil.get_roi() == (0, 0, 64, 64)


def test_concurrent_calls_do_not_interleave_inside_the_core(mil):
    """Two threads hammering MIL must never be inside the core at the same time.

    This is the crash class the lock exists to close: interleaved writes from two
    threads to the same native core (or the same TriggerScope serial port).
    """
    inside = 0
    overlaps = []
    guard = threading.Lock()

    def slow_set_property(*_args, **_kwargs):
        nonlocal inside
        with guard:
            inside += 1
            if inside > 1:
                overlaps.append(inside)
        # Long enough that unsynchronized threads would reliably overlap here.
        threading.Event().wait(0.002)
        with guard:
            inside -= 1

    mil.core.setProperty.side_effect = slow_set_property

    def worker(n):
        for i in range(n):
            mil.set_property('Dev', 'Prop', i)

    threads = [threading.Thread(target=worker, args=(8,)) for _ in range(4)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=30)

    assert not any(t.is_alive() for t in threads)
    assert overlaps == [], f"two threads were inside core.setProperty at once: {overlaps}"
    assert mil.core.setProperty.call_count == 32


def test_exposure_cache_hit_does_not_take_the_lock(mil):
    """The per-frame display gate must not block on a held hardware lock."""
    mil.core.getExposure.return_value = 25.0
    assert mil.get_exposure() == 25.0  # populates the cache

    got = []

    # Hold the lock from another thread, simulating an in-flight slow stage move.
    released = threading.Event()
    holding = threading.Event()

    def hold():
        with mil._hw_lock:
            holding.set()
            released.wait(timeout=10)

    holder = threading.Thread(target=hold, daemon=True)
    holder.start()
    assert holding.wait(timeout=5)

    mil._pixel_size_um_cache = 0.1

    def read_cached():
        got.append(mil.get_exposure())
        got.append(mil.get_pixel_size_um())
    reader = threading.Thread(target=read_cached, daemon=True)
    reader.start()
    reader.join(timeout=5)
    released.set()
    holder.join(timeout=5)

    assert not reader.is_alive(), "a cache-hit get_exposure() blocked on the hardware lock"
    assert got == [25.0, 0.1]
    # Only the one uncached call ever reached the hardware.
    assert mil.core.getExposure.call_count == 1


def test_uncached_exposure_read_does_take_the_lock(mil):
    """A cache *miss* must still be serialized -- it touches the core."""
    mil.core.getExposure.return_value = 30.0
    mil.invalidate_exposure_cache()

    finished = threading.Event()
    holding = threading.Event()
    released = threading.Event()

    def hold():
        with mil._hw_lock:
            holding.set()
            released.wait(timeout=10)

    holder = threading.Thread(target=hold, daemon=True)
    holder.start()
    assert holding.wait(timeout=5)

    def read_uncached():
        mil.get_exposure()
        finished.set()

    reader = threading.Thread(target=read_uncached, daemon=True)
    reader.start()
    assert not finished.wait(timeout=0.25), "an uncached get_exposure() bypassed the hardware lock"

    released.set()
    holder.join(timeout=5)
    assert finished.wait(timeout=5)
    reader.join(timeout=5)


def test_decorated_methods_keep_their_signature_and_docstring():
    """functools.wraps must be intact, or introspection-driven callers break."""
    import inspect

    assert MicroscopeInterfaceLayer.set_property.__name__ == 'set_property'
    assert list(inspect.signature(MicroscopeInterfaceLayer.set_property).parameters) == [
        'self', 'device_name', 'property_name', 'newval',
    ]
    assert MicroscopeInterfaceLayer.get_image.__doc__ is not None
    assert 'Get the most recently snapped image' in MicroscopeInterfaceLayer.get_image.__doc__
