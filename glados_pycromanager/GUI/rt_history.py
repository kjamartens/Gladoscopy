"""Retained real-time-analysis results, keyed by acquisition axes.

A real-time-analysis node's `visualise()` runs once per analysed frame and
overwrites its layer, so when an acquisition ends the overlay shows whatever the
last frame produced. Dragging napari's time/z slider afterwards moves the image but
leaves the overlay frozen on that final frame.

This module keeps what is needed to re-render an overlay for *any* frame. The unit
it stores is the per-frame **state snapshot** that subprocess isolation already
builds (`AnalysisClass._build_state_snapshot`, from a node's `__snapshot_attrs__`)
-- which exists precisely because a napari layer cannot cross a process boundary, so
`visualise()` runs against a main-process shadow instance refreshed from that dict.
That snapshot is by construction "the state visualise() needs for this frame", so
retaining one per frame is the whole feature, and no node script has to change.

What is deliberately **not** stored is the raw frame. The multi-dimensional display
zarr already holds every frame, uncompressed and one frame per chunk, so replay
re-reads it by slice index rather than duplicating gigabytes in RAM.

Qt-free and napari-free by design, so it is testable headlessly -- same posture as
`frame_ring.py` and `frame_writer.py`. The GUI-thread scrub handler lives separately.
"""

import logging
import sys
import threading
from collections import OrderedDict
from dataclasses import dataclass, field
from typing import Any

import numpy as np

#: Default ceiling on retained results, shared across every running node.
DEFAULT_HISTORY_BUDGET_MB = 256

#: Types worth measuring individually when accounting for a snapshot's size.
_SIZED_TYPES = (np.ndarray,)


def axes_key(axes, dim_order=None):
    """A hashable, order-independent key for one frame's position in the plan.

    Mirrors `napariGlados._axes_key` (sorted `(name, value)` pairs) but optionally
    *projects* onto `dim_order` first. That projection matters because a frame's
    `metadata['Axes']` can legitimately carry keys the acquisition plan's own axes
    do not -- the same subset semantics `_backfill_missing_slices` preserves.

    Returns None when a dimension of `dim_order` is missing from `axes`, i.e. the
    frame cannot be placed in the plan.
    """
    if axes is None:
        return None
    if dim_order is None:
        return tuple(sorted((str(k), _plain(v)) for k, v in axes.items()))
    try:
        return tuple(sorted((str(d), _plain(axes[d])) for d in dim_order))
    except KeyError:
        return None


def _plain(value):
    """Normalise numpy scalars to plain Python.

    A `np.int64(3)` and an `int(3)` hash equal, so a key built from either matches
    -- but they pickle and repr differently, and history keys are compared against
    both `metadata['Axes']` (plain) and `unique_entries` lookups (numpy). Normalise
    so logs and equality are unambiguous.
    """
    item = getattr(value, 'item', None)
    if callable(item):
        try:
            return item()
        except (AttributeError, ValueError):
            pass
    return value


def axes_from_current_step(current_step, dim_order, unique_entries):
    """Map napari's `dims.current_step` back to an axes dict.

    The inverse of the display path's `np.searchsorted`: that path sets
    `set_current_step` with the searchsorted *indices*, so `current_step` holds
    indices into `unique_entries[dim]` and this looks the values back up.

    Note the corollary, which is why the frame read needs no searchsorted of its
    own: `current_step[:len(dim_order)]` **is** the zarr slice index.

    Returns None when the step cannot be placed -- it is shorter than the plan's
    dimensions (under-specified; guessing the rest would silently show the wrong
    frame) or an index is out of range (possible transiently while a layer is being
    rebuilt). Both are ordinary, so callers should treat None as "skip", not "error".
    """
    if current_step is None or not dim_order:
        return None
    #A napari layer over a k-dimensional plan has ndim == k + 2 (y, x), so a longer
    #step is normal; a shorter one is not.
    if len(current_step) < len(dim_order):
        logging.debug('current_step %s is shorter than the plan dimensions %s; '
                      'cannot place the frame', tuple(current_step), list(dim_order))
        return None

    axes = {}
    for index, dim in enumerate(dim_order):
        values = unique_entries.get(dim) if hasattr(unique_entries, 'get') else None
        if values is None:
            return None
        step = int(current_step[index])
        if step < 0 or step >= len(values):
            logging.debug('current_step index %d is out of range for dimension %r '
                          '(%d values)', step, dim, len(values))
            return None
        axes[dim] = _plain(values[step])
    return axes


def _copy_value(value):
    """Copy a snapshot value so later in-place mutation cannot reach the history.

    This is the subtle half of recording. A snapshot built in the **subprocess**
    path arrives already copied, because it was unpickled out of the worker's
    queue. One built **in-process** by `_build_state_snapshot` holds bare
    references to the node's own attributes -- and a node that reuses a buffer
    (`self.canvas[...] += x`) would then rewrite every history entry it ever made.
    """
    if isinstance(value, np.ndarray):
        return np.array(value, copy=True)
    if isinstance(value, dict):
        return {k: _copy_value(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_copy_value(v) for v in value]
    if isinstance(value, tuple):
        return tuple(_copy_value(v) for v in value)
    #Remaining snapshot types are immutable scalars (int/float/bool/str/bytes/None).
    return value


def _sizeof(value):
    """Approximate retained bytes. Exact for arrays, indicative for the rest."""
    if isinstance(value, _SIZED_TYPES):
        return int(value.nbytes)
    if isinstance(value, dict):
        return sum(_sizeof(k) + _sizeof(v) for k, v in value.items())
    if isinstance(value, (list, tuple)):
        return sum(_sizeof(v) for v in value)
    try:
        return sys.getsizeof(value)
    except TypeError:
        return 0


@dataclass(frozen=True)
class HistoryEntry:
    """One analysed frame's replayable state."""

    snapshot: dict
    metadata: dict
    generation: Any
    nbytes: int


class RTNodeHistory:
    """Bounded, drop-oldest history of one node's per-frame results.

    Thread-safe: recording happens on the analysis worker threads, reading on the
    GUI thread.
    """

    def __init__(self, budget_bytes, label='RT-analysis node'):
        self.budget_bytes = int(budget_bytes)
        self.label = label
        self._entries = OrderedDict()
        self._lock = threading.Lock()
        self._nbytes = 0
        self.dropped = 0
        self._warned_eviction = False

    def __len__(self):
        with self._lock:
            return len(self._entries)

    @property
    def nbytes(self):
        with self._lock:
            return self._nbytes

    def set_budget(self, budget_bytes):
        """Re-cap the store, evicting immediately if it is now over."""
        with self._lock:
            self.budget_bytes = int(budget_bytes)
            self._evict_locked()

    def record(self, key, snapshot, metadata=None, generation=None):
        """Store one frame's snapshot. Returns True if it was kept.

        Values are copied -- see `_copy_value`.
        """
        if key is None or not snapshot:
            return False
        if self.budget_bytes <= 0:
            return False

        entry_snapshot = {k: _copy_value(v) for k, v in snapshot.items()}
        size = _sizeof(entry_snapshot)
        entry = HistoryEntry(snapshot=entry_snapshot,
                             metadata=dict(metadata) if metadata else {},
                             generation=generation, nbytes=size)

        with self._lock:
            previous = self._entries.pop(key, None)
            if previous is not None:
                self._nbytes -= previous.nbytes
            self._entries[key] = entry
            self._nbytes += size
            self._evict_locked()
            return key in self._entries

    def _evict_locked(self):
        while self._entries and self._nbytes > self.budget_bytes:
            _, evicted = self._entries.popitem(last=False)
            self._nbytes -= evicted.nbytes
            self.dropped += 1
            if not self._warned_eviction:
                self._warned_eviction = True
                #Once, not per frame: at a 2-8 MB/frame snapshot this fires
                #continuously and the message is the same every time.
                logging.warning(
                    'Retained RT-analysis results for %s exceeded their %.0f MB budget; '
                    'dropping the oldest frames. Scrubbing to a dropped frame will '
                    're-run the analysis instead. Raise the budget in Advanced '
                    'Settings, or set "__replayable__": False on this node.',
                    self.label, self.budget_bytes / (1024 * 1024))

    def get(self, key, generation=None):
        """The entry for `key`, or None.

        A generation mismatch reads as a miss: history from a previous acquisition
        describes a different plan, so replaying it would place the wrong overlay on
        the frame. Keyed on `shared_data._mdaModeParamsGeneration`, the same counter
        the dimension cache uses, which makes invalidation independent of teardown
        ordering -- no need to clear the store at acquisition start, which would
        race the RT threads being created before the zarr exists.
        """
        with self._lock:
            entry = self._entries.get(key)
            if entry is None:
                return None
            if generation is not None and entry.generation != generation:
                return None
            return entry

    def keys(self):
        with self._lock:
            return list(self._entries)

    def clear(self):
        with self._lock:
            self._entries.clear()
            self._nbytes = 0
            self._warned_eviction = False


@dataclass
class RTReplaySession:
    """Everything needed to re-render one node's overlay for an arbitrary frame.

    This must outlive the RT-analysis thread that produced it. The thread object is
    deleted at acquisition end (`create_real_time_analysis_thread` connects
    `finished` to `deleteLater`) and the node instance is only reachable through it,
    so the session is what holds the node, its layers and its history alive. The
    layers themselves already survive -- `stop()` never removes them.
    """

    key: str
    node: Any
    analysis_info: dict
    group: Any
    is_legacy: bool
    history: RTNodeHistory
    source_layer_name: str | None = None
    label: str = 'RT-analysis node'
    enabled: bool = True
    replayable: bool = True
    _reported_inert: bool = field(default=False, repr=False)

    @property
    def visualisation_target(self):
        """What this node's `visualise()` expects: a bare layer, or the group."""
        if self.group is None:
            return None
        return self.group.primary if self.is_legacy else self.group

    def note_snapshot(self, snapshot):
        """Disable replay for a node whose snapshot carries nothing.

        A node that declares no `__snapshot_attrs__` snapshots `{}`. Replaying that
        would `__dict__.update({})` and call `visualise()` against whatever the node
        currently holds -- rendering the *last* analysed frame's overlay identically
        at every scrub position, which looks like it works and is silently wrong.
        Better to do nothing and say so.
        """
        if snapshot:
            return True
        if not self._reported_inert:
            self._reported_inert = True
            self.enabled = False
            logging.info(
                'Real-time analysis %s declares no "__snapshot_attrs__", so its '
                'overlay cannot be replayed while scrubbing. Declare the attributes '
                'its visualise() reads to enable it.', self.label)
        return False


class RTReplayRegistry:
    """The live replay sessions, one per running/finished RT-analysis node."""

    def __init__(self, budget_bytes=DEFAULT_HISTORY_BUDGET_MB * 1024 * 1024):
        self._sessions = OrderedDict()
        self._lock = threading.Lock()
        self.budget_bytes = int(budget_bytes)
        self.suspended = False

    def __len__(self):
        with self._lock:
            return len(self._sessions)

    @property
    def sessions(self):
        with self._lock:
            return list(self._sessions.values())

    def register(self, session):
        with self._lock:
            self._sessions[session.key] = session
        self.rebalance_budget()
        return session

    def get(self, key):
        with self._lock:
            return self._sessions.get(key)

    def unregister(self, key):
        with self._lock:
            session = self._sessions.pop(key, None)
        if session is not None:
            session.history.clear()
            self.rebalance_budget()
        return session

    def session_for_layer(self, layer_name):
        """The session owning `layer_name`, if any."""
        for session in self.sessions:
            group = session.group
            if group is not None and layer_name in getattr(group, 'names', ()):
                return session
        return None

    def rebalance_budget(self):
        """Split the global budget evenly across the live sessions."""
        sessions = self.sessions
        if not sessions:
            return
        share = self.budget_bytes // max(1, len(sessions))
        for session in sessions:
            session.history.set_budget(share)

    def set_budget(self, budget_bytes):
        self.budget_bytes = int(budget_bytes)
        self.rebalance_budget()

    def clear(self):
        with self._lock:
            sessions = list(self._sessions.values())
            self._sessions.clear()
        for session in sessions:
            session.history.clear()
