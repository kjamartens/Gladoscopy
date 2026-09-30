"""Dedicated writer threads for per-frame storage: the multiDstack zarr, and NDTiff.

Why this exists
---------------
`FrameRing` (see `frame_ring.py`) takes frames off pymmcore-plus' acquisition
thread. Its consumer then did three things per frame: refactor the metadata, fan
the frame out to the visualisation and RT-analysis queues, and **write the frame
into the zarr store**. Only the last one is slow: measured at roughly 9-13 ms for
a 1024x1024 uint16 frame, it is disk bandwidth, and it scales with frame size
(about four times that for a 2048x2048 sensor).

That put a hard ceiling on the whole consumer. Once the camera outran it the ring
overflowed, and because the ring is overwrite-oldest, the frames it shed were
gone -- which for `MMCORE_PLUS` means gone entirely, since that backend has no
NDTiff store to recover them from. The display can afford to drop frames; storage
cannot.

`ZarrFrameWriter` moves the write onto its own thread behind its own queue, so
the ring consumer is fast again (metadata plus two `deque.append`s) and disk
latency is absorbed by a buffer instead of being charged to the frame path.

Semantics -- and how they differ from `FrameRing`
-------------------------------------------------
* **Bounded by bytes, not by frames.** A frame-count bound means something
  completely different on a 512x512 camera than on a 2048x2048 one. The queue
  sizes itself from a memory budget and the actual frame size.
* **Backpressure, not overwrite-oldest.** `FrameRing` drops the oldest frame
  because for a display a stale frame is worthless. Here a dropped frame is lost
  data, so `submit` *blocks* while the queue is full, pushing back on the caller
  until the disk catches up.
* **Bounded blocking.** The block has a timeout. An untimed one would turn a
  stalled disk into a hung acquisition that cannot even be cancelled; on timeout
  the frame is counted as dropped and logged loudly, so the failure is visible
  rather than silent.

What this can and cannot promise
--------------------------------
It absorbs **bursts**: any overrun whose backlog fits the memory budget costs
nothing. It cannot fix a **sustained** overrun -- if the camera produces data
faster than the disk absorbs it, no buffer of any size is enough, and the only
remaining choices are to slow the acquisition or to lose frames. `max_depth` and
`blocked_seconds` are recorded precisely so that case is diagnosable after the
fact instead of being a mystery.

Frames are queued by reference, not copied -- the same assumption `FrameRing`
already makes about the acquisition callback handing over a frame it does not
subsequently reuse.

`FrameWriter` holds all of that and knows nothing about the sink; a subclass says
how one frame is written. `ZarrFrameWriter` assigns into an array slice.
`NDTiffFrameWriter` (T-D8) calls `NDTiffDataset.put_image`, which is how the
pymmcore-plus backend gets an NDTiff archive without writing inline on the frame
path.
"""

import json
import logging
import threading
import time
from queue import Empty, Full, Queue

#: Memory the queue may hold in frames-in-flight. 256 MB is roughly 120 frames of
#: 1024x1024 uint16 or 30 of 2048x2048 -- seconds of burst at realistic rates,
#: while staying small next to the working set of a machine running napari.
DEFAULT_MEMORY_BUDGET_BYTES = 256 * 1024 * 1024

#: Never size the queue below this, however large a single frame is: a queue of
#: one is not a buffer, it is a rendezvous.
MIN_CAPACITY = 8

#: How long `submit` will wait for room before giving up on a frame. Long enough
#: to ride out a disk hiccup, short enough that a wedged disk does not make the
#: acquisition unstoppable.
DEFAULT_SUBMIT_TIMEOUT_S = 5.0

#: How long `close` waits for the backlog to reach disk.
DEFAULT_CLOSE_TIMEOUT_S = 60.0

_SENTINEL = object()


class FrameWriter:
    """Writes `(destination, image)` pairs to a sink from one thread.

    Subclasses implement `_write(destination, image)`; everything else -- the
    byte-bounded queue, backpressure, drain-on-close and the statistics -- is here.
    `frame_nbytes` sizes the queue for a sink that cannot describe its frames;
    otherwise the size is read off the target's `dtype` and last two `shape` axes.
    """

    def __init__(self, target, memory_budget_bytes=DEFAULT_MEMORY_BUDGET_BYTES,
                 submit_timeout_s=DEFAULT_SUBMIT_TIMEOUT_S, name='GladosFrameWriter',
                 frame_nbytes=None):
        self.target = target
        self._submit_timeout_s = float(submit_timeout_s)
        self._name = name
        self._capacity = self._capacity_for(target, memory_budget_bytes, frame_nbytes)
        self._queue = Queue(maxsize=self._capacity)
        self._thread = None
        self._stopping = threading.Event()
        self._lock = threading.Lock()
        self._submitted = 0
        self._written = 0
        self._dropped = 0
        self._failed = 0
        self._max_depth = 0
        self._blocked_seconds = 0.0
        self._last_written_tag = None

    @staticmethod
    def _capacity_for(array, memory_budget_bytes, frame_nbytes=None):
        """Queue depth in frames, from the budget and one frame's footprint."""
        try:
            if frame_nbytes is not None:
                frame_bytes = int(frame_nbytes)
            else:
                itemsize = array.dtype.itemsize
                height, width = array.shape[-2], array.shape[-1]
                frame_bytes = int(itemsize) * int(height) * int(width)
        except Exception:
            # An array-like that cannot describe itself: fall back to the floor
            # rather than refusing to buffer at all.
            logging.debug('FrameWriter: could not size frames, using MIN_CAPACITY')
            return MIN_CAPACITY
        if frame_bytes <= 0:
            return MIN_CAPACITY
        return max(MIN_CAPACITY, int(memory_budget_bytes // frame_bytes))

    # -- introspection ----------------------------------------------------
    @property
    def capacity(self) -> int:
        """Queue depth in frames, derived from the memory budget."""
        return self._capacity

    @property
    def depth(self) -> int:
        return self._queue.qsize()

    @property
    def submitted(self) -> int:
        return self._submitted

    @property
    def written(self) -> int:
        return self._written

    @property
    def dropped(self) -> int:
        """Frames given up on after `submit` waited out its timeout."""
        return self._dropped

    @property
    def failed(self) -> int:
        """Frames the write itself raised on."""
        return self._failed

    @property
    def max_depth(self) -> int:
        """Deepest the queue ever got -- how much burst was actually absorbed."""
        return self._max_depth

    @property
    def blocked_seconds(self) -> float:
        """Total time `submit` spent waiting for room, i.e. real backpressure."""
        return self._blocked_seconds

    @property
    def last_written_tag(self):
        """Caller's tag for the most recent frame that actually reached disk.

        The display needs this. A queued write means the frame path can be well
        ahead of the disk -- up to a full queue -- so a viewer pointed at the
        frame that just *arrived* would be reading slices the writer has not
        written yet, and rendering them as black. Pointing it here instead shows
        the newest frame that genuinely exists: slightly behind live, never
        empty.
        """
        return self._last_written_tag

    @property
    def is_running(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    # -- lifecycle --------------------------------------------------------
    def start(self):
        if self.is_running:
            return
        self._stopping.clear()
        self._thread = threading.Thread(target=self._run, name=self._name, daemon=True)
        self._thread.start()
        logging.debug('%s started (queue capacity %d frames)', type(self).__name__, self._capacity)

    def submit(self, slice_tuple, image, tag=None) -> bool:
        """Queue one frame. Blocks while full; False if the frame was dropped.

        Blocking is the point: it pushes back on the frame path instead of
        quietly discarding data the caller believes is being stored.

        `tag` is an opaque caller-side label for the frame, published as
        `last_written_tag` once the write lands. It exists so the caller does not
        have to reverse-engineer an index out of `slice_tuple`.
        """
        if self._stopping.is_set():
            return False
        with self._lock:
            self._submitted += 1
        started_waiting = time.perf_counter()
        try:
            self._queue.put((slice_tuple, image, tag), timeout=self._submit_timeout_s)
        except Full:
            waited = time.perf_counter() - started_waiting
            with self._lock:
                self._dropped += 1
                self._blocked_seconds += waited
                dropped = self._dropped
            logging.warning(
                '%s: storage queue full for %.1fs, frame dropped '
                '(%d dropped so far) -- the disk is not keeping up with the camera',
                type(self).__name__, waited, dropped)
            return False
        waited = time.perf_counter() - started_waiting
        depth = self._queue.qsize()
        with self._lock:
            # Only count a wait that actually blocked; an uncontended put still
            # measures a few microseconds and would drown the real signal.
            if waited > 0.001:
                self._blocked_seconds += waited
            if depth > self._max_depth:
                self._max_depth = depth
        return True

    def close(self, timeout=DEFAULT_CLOSE_TIMEOUT_S):
        """Drain the backlog, stop the thread, and report what happened.

        Must complete before anything reads the store or releases the directory
        underneath it.
        """
        thread = self._thread
        if thread is None:
            return self.stats()
        self._stopping.set()
        try:
            self._queue.put(_SENTINEL, timeout=timeout)
        except Full:
            logging.warning('%s: could not enqueue stop sentinel; '
                            'backlog may be abandoned', type(self).__name__)
        thread.join(timeout=timeout)
        if thread.is_alive():
            logging.warning('%s did not finish within %.0fs; '
                            '%d frames may not have reached disk', type(self).__name__, timeout, self.depth)
        self._thread = None
        stats = self.stats()
        level = logging.WARNING if (stats['dropped'] or stats['failed']) else logging.INFO
        logging.log(level,
                    '%s: %d/%d frames written (dropped %d, failed %d), '
                    'peak queue depth %d/%d, %.2fs spent under backpressure',
                    type(self).__name__, stats['written'], stats['submitted'], stats['dropped'],
                    stats['failed'], stats['max_depth'], self._capacity,
                    stats['blocked_seconds'])
        return stats

    def stats(self) -> dict:
        with self._lock:
            return {
                'submitted': self._submitted,
                'written': self._written,
                'dropped': self._dropped,
                'failed': self._failed,
                'max_depth': self._max_depth,
                'blocked_seconds': self._blocked_seconds,
                'capacity': self._capacity,
                'last_written_tag': self._last_written_tag,
            }

    # -- writer thread ----------------------------------------------------
    def _run(self):
        while True:
            try:
                item = self._queue.get(timeout=0.1)
            except Empty:
                # Only leave on the sentinel, never on an idle timeout: a gap
                # between frames is not the end of an acquisition.
                continue
            if item is _SENTINEL:
                return
            slice_tuple, image, tag = item
            try:
                self._write(slice_tuple, image)
                with self._lock:
                    self._written += 1
                    # Published only after the write returns, so a reader of
                    # last_written_tag can trust that slice exists on disk.
                    self._last_written_tag = tag
            except Exception:
                with self._lock:
                    self._failed += 1
                logging.exception('%s: write to %s failed (frame lost)',
                                  type(self).__name__, slice_tuple)

    def _write(self, destination, image):
        raise NotImplementedError


class ZarrFrameWriter(FrameWriter):
    """Writes `(slice_tuple, image)` pairs into a zarr array from one thread.

    Deliberately knows nothing about metadata, acquisition axes or napari: the
    caller computes the destination index and hands over a plain array, which
    keeps this unit-testable against any object supporting `__setitem__`.
    """

    def __init__(self, array, memory_budget_bytes=DEFAULT_MEMORY_BUDGET_BYTES,
                 submit_timeout_s=DEFAULT_SUBMIT_TIMEOUT_S, name='GladosZarrWriter'):
        super().__init__(array, memory_budget_bytes=memory_budget_bytes,
                         submit_timeout_s=submit_timeout_s, name=name)

    @property
    def array(self):
        return self.target

    def _write(self, destination, image):
        self.target[destination] = image


def json_safe_metadata(metadata):
    """A JSON-encodable copy of a frame's metadata dict.

    `NDTiffDataset.put_image` `json.dumps` the metadata, and pymmcore-plus' frame
    metadata carries objects that do not encode (the `MDAEvent`, numpy scalars).
    Anything unencodable becomes its `str()`, rather than failing the frame.
    """
    if not metadata:
        return {}
    return json.loads(json.dumps(metadata, default=str))


class NDTiffFrameWriter(FrameWriter):
    """Writes frames into an `ndstorage.NDTiffDataset` from one thread (T-D8).

    `destination` is `(coordinates, metadata)`: the NDTiff coordinate dict
    (str keys, int or str values) and the frame's metadata, made JSON-safe here on
    the writer thread rather than on the frame path. The caller must hand over a
    metadata dict nobody else mutates -- a shallow copy is enough. `frame_nbytes`
    is required because a dataset cannot describe its frames before the first one.
    The dataset's `finish()` is the caller's, after `close()` has drained the queue.
    """

    def __init__(self, dataset, frame_nbytes, memory_budget_bytes=DEFAULT_MEMORY_BUDGET_BYTES,
                 submit_timeout_s=DEFAULT_SUBMIT_TIMEOUT_S, name='GladosNDTiffWriter'):
        super().__init__(dataset, memory_budget_bytes=memory_budget_bytes,
                         submit_timeout_s=submit_timeout_s, name=name,
                         frame_nbytes=frame_nbytes)

    @property
    def dataset(self):
        return self.target

    def _write(self, destination, image):
        coordinates, metadata = destination
        self.target.put_image(coordinates, image, json_safe_metadata(metadata))
