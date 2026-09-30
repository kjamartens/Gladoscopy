"""Bounded frame hand-off buffer between an acquisition callback and a consumer.

Why this exists
---------------
`napariGlados.grab_image_liveVis_PyMMCore` is connected to
`core.mda.events.frameReady` with an explicit ``Qt.DirectConnection``, so it runs
*synchronously on pymmcore-plus' own MDA thread*: every microsecond spent in that
callback happens in front of the next camera frame. Anything beyond taking the
frame off the acquisition thread -- metadata refactoring, storage writes, the
analysis fan-out -- therefore belongs to a consumer thread, and the callback
itself should be a pure hand-off.

`FrameRing` is that hand-off point. It is deliberately tiny and
dependency-free (stdlib only) so it stays unit-testable without Qt, napari or a
microscope.

Semantics
---------
* Bounded. When the ring is full, `push` overwrites the **oldest** entry and
  increments `dropped` -- the producer is never blocked and never grows memory
  without limit. Dropping the oldest (rather than refusing the newest) keeps the
  display path on the freshest frame.
* Single producer, single consumer is the intended use, but every operation is
  taken under one lock, so extra callers are safe (just not fast).
* `wait()` blocks on a `threading.Event` that is set inside the lock on push and
  cleared inside the lock once the ring runs empty, so a consumer can never miss
  a wake-up for a frame that is still queued.
"""

import threading
from collections import deque

#: Default ring depth. Small on purpose: for the display path a backlog is
#: worthless (the newest frame supersedes it), and a shallow ring surfaces a slow
#: consumer as a `dropped` count instead of as latency. Callers that must not
#: lose frames (e.g. the multiDstack MDA zarr writer) pass a larger capacity.
DEFAULT_CAPACITY = 4


class FrameRing:
    """A bounded, overwrite-oldest (image, metadata) buffer."""

    __slots__ = ('_capacity', '_buf', '_lock', '_new_frame', '_dropped', '_pushed')

    def __init__(self, capacity: int = DEFAULT_CAPACITY):
        if capacity < 1:
            raise ValueError(f'FrameRing capacity must be >= 1, got {capacity}')
        self._capacity = int(capacity)
        self._buf = deque()
        self._lock = threading.Lock()
        self._new_frame = threading.Event()
        self._dropped = 0
        self._pushed = 0

    # -- introspection ----------------------------------------------------
    @property
    def capacity(self) -> int:
        return self._capacity

    @property
    def dropped(self) -> int:
        """Frames overwritten before a consumer got to them."""
        return self._dropped

    @property
    def pushed(self) -> int:
        """Frames handed over by the producer, dropped ones included."""
        return self._pushed

    @property
    def event(self) -> threading.Event:
        """The Event a consumer may wait on directly (see `wait`)."""
        return self._new_frame

    def __len__(self) -> int:
        with self._lock:
            return len(self._buf)

    # -- producer side ----------------------------------------------------
    def push(self, image, metadata) -> bool:
        """Hand a frame over. Returns False if this push dropped an older frame.

        Never blocks on the consumer, never raises on a full ring.
        """
        with self._lock:
            overwrote = len(self._buf) >= self._capacity
            if overwrote:
                self._buf.popleft()
                self._dropped += 1
            self._buf.append((image, metadata))
            self._pushed += 1
            # Set inside the lock: a consumer only clears the event while
            # holding the lock and seeing an empty ring, so this ordering makes
            # a lost wake-up impossible.
            self._new_frame.set()
        return not overwrote

    # -- consumer side ----------------------------------------------------
    def pop_next(self):
        """Oldest queued frame as `(image, metadata)`, or None if empty."""
        with self._lock:
            if not self._buf:
                self._new_frame.clear()
                return None
            item = self._buf.popleft()
            if not self._buf:
                self._new_frame.clear()
            return item

    def pop_latest(self):
        """Newest queued frame, discarding any older ones (counted as dropped).

        For a display consumer that only ever wants the freshest frame.
        """
        with self._lock:
            if not self._buf:
                self._new_frame.clear()
                return None
            item = self._buf.pop()
            self._dropped += len(self._buf)
            self._buf.clear()
            self._new_frame.clear()
            return item

    def wait(self, timeout=None) -> bool:
        """Block until a frame is available or `timeout` (seconds) elapses."""
        return self._new_frame.wait(timeout)

    def clear(self) -> None:
        """Discard queued frames without counting them as drops."""
        with self._lock:
            self._buf.clear()
            self._new_frame.clear()

    def reset(self) -> None:
        """Empty the ring and zero the counters (call before a new run)."""
        with self._lock:
            self._buf.clear()
            self._new_frame.clear()
            self._dropped = 0
            self._pushed = 0
