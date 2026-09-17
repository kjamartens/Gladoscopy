"""Re-render real-time-analysis overlays while scrubbing a finished acquisition.

Dragging napari's time/z slider after an acquisition moves the image but leaves
every RT-analysis overlay frozen on the last analysed frame. This controller
watches `dims.events.current_step` and, for each registered node, restores that
frame's stored snapshot (`GUI/rt_history.py`) and calls the node's `visualise()`
again -- so the overlay follows the slider, using the node's own unmodified script.

Frames the analysis never saw (the per-node queue drops a frame whenever the node
is still busy with the previous one) are **re-analysed on demand**, off the GUI
thread, and the result is stored so a second visit is instant.

Threading:

- The scrub handler and everything napari runs on the **GUI thread**.
- On-demand re-analysis runs on a single daemon worker thread, latest-request-wins,
  and marshals its visualisation back through the napari bridge. `pSMLM`-class
  analysis is far too slow to run inside a slider callback.
- Replay is **inert during live/MDA mode**, so the acquisition display path -- which
  drives `dims.set_current_step` itself, once per frame -- never triggers it, and
  the two never fight over the same layers.
"""

import logging
import threading

import numpy as np

from qtpy.QtCore import QObject, QTimer

import glados_pycromanager.GUI.rt_history as rt_history
import glados_pycromanager.GUI.utils as utils

#: Fallback if the Advanced Settings value cannot be read.
DEFAULT_DEBOUNCE_MS = 120

#: How long the on-demand re-analysis worker waits for a request before
#: re-checking that it should still be running.
_WORKER_POLL_S = 0.5


def _plan(shared_data):
    """`(dimensionOrder, n_entries, uniqueEntries)` for the current acquisition."""
    try:
        return utils.getAcquisitionDimensions(shared_data)
    except Exception:
        logging.debug('Replay: could not resolve acquisition dimensions', exc_info=True)
        return None


def read_frame(shared_data, layer_name, slice_index):
    """The raw frame at `slice_index`, from the display zarr.

    Replay deliberately does not retain frames -- the multi-dimensional display
    store already holds every one of them, uncompressed and one frame per chunk,
    so re-reading is both cheap and free of duplicate memory.
    """
    if not layer_name:
        return None
    store = None
    try:
        store = shared_data.mdaZarrData.get(layer_name)
    except (AttributeError, TypeError):
        store = None
    if store is None:
        #No multi-dimensional store (a frame-by-frame or live layer): fall back to
        #the layer's own data, which for those is the frame itself.
        try:
            layer = shared_data.napariViewer.layers[layer_name]
            data = np.asarray(layer.data)
        except (AttributeError, KeyError, IndexError, TypeError):
            return None
        if data.ndim <= 2:
            return data
        try:
            return data[tuple(slice_index[:data.ndim - 2])]
        except (IndexError, TypeError):
            return None
    try:
        return np.asarray(store[tuple(slice_index) + (slice(None), slice(None))])
    except (IndexError, TypeError, ValueError):
        logging.debug('Replay: could not read slice %s of %r', slice_index, layer_name)
        return None


class RTReplayController(QObject):
    """Drives overlay replay from napari's dimension slider."""

    def __init__(self, shared_data, debounce_ms=None):
        super().__init__()
        self._shared_data = shared_data
        self._viewer = None
        self._connected = False
        self._replaying = False

        if debounce_ms is None:
            debounce_ms = getattr(shared_data.config.rt_analysis_config,
                                  'replay_debounce_ms', DEFAULT_DEBOUNCE_MS)
        try:
            self._debounce_ms = max(0, int(debounce_ms))
        except (TypeError, ValueError):
            self._debounce_ms = DEFAULT_DEBOUNCE_MS

        #A slider drag emits current_step per pixel; coalesce into one re-render.
        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.timeout.connect(self.replay_now)

        #Latest-request-wins re-analysis worker. Started lazily: a session that
        #never scrubs into a gap never pays for a thread.
        self._request = None
        self._request_event = threading.Event()
        self._request_lock = threading.Lock()
        self._worker = None
        self._worker_stop = threading.Event()
        #Throwaway node instances used for re-analysis, one per session key. Never
        #the acquisition's own node: re-running run() on that would pollute the
        #state it accumulated during the acquisition (pSMLM appends every frame it
        #analyses to its localization table).
        self._replay_nodes = {}

    # -- wiring ------------------------------------------------------------

    def attach(self, viewer=None):
        viewer = viewer if viewer is not None else getattr(self._shared_data, 'napariViewer', None)
        if viewer is None or self._connected:
            return False
        self._viewer = viewer
        try:
            viewer.dims.events.current_step.connect(self._on_current_step)
        except AttributeError:
            logging.debug('Replay: viewer has no dims.events.current_step')
            return False
        self._connected = True
        return True

    def detach(self):
        if self._connected and self._viewer is not None:
            try:
                self._viewer.dims.events.current_step.disconnect(self._on_current_step)
            except (AttributeError, TypeError, ValueError):
                pass
        self._connected = False
        self._timer.stop()
        self._worker_stop.set()
        self._request_event.set()

    # -- the scrub gate ----------------------------------------------------

    def _is_inert(self):
        shared = self._shared_data
        #During an acquisition the display path drives current_step itself, once
        #per frame, and owns these layers.
        if getattr(shared, 'liveMode', False) or getattr(shared, 'mdaMode', False):
            return True
        if shared.rt_replay.suspended:
            return True
        #Re-entrancy: a node's visualise() may read (or touch) viewer.dims.
        return self._replaying

    def _on_current_step(self, event=None):
        if self._is_inert():
            return
        self._timer.start(self._debounce_ms)

    # -- replay ------------------------------------------------------------

    def current_axes(self):
        """The axes dict for the viewer's current slider position, or None."""
        plan = _plan(self._shared_data)
        if not plan:
            return None
        dim_order, _n, unique = plan
        try:
            step = tuple(int(s) for s in self._viewer.dims.current_step)
        except (AttributeError, TypeError, ValueError):
            return None
        return rt_history.axes_from_current_step(step, dim_order, unique)

    def current_slice_index(self):
        """The zarr slice index for the current slider position.

        No searchsorted needed: the display path sets `current_step` *to* the
        searchsorted indices, so the leading entries already are the slice index.
        """
        plan = _plan(self._shared_data)
        if not plan:
            return None
        dim_order, _n, _u = plan
        try:
            step = tuple(int(s) for s in self._viewer.dims.current_step)
        except (AttributeError, TypeError, ValueError):
            return None
        if len(step) < len(dim_order):
            return None
        return step[:len(dim_order)]

    def replay_now(self):
        """Re-render every registered node's overlay for the current frame."""
        if self._is_inert() or self._viewer is None:
            return 0
        axes = self.current_axes()
        slice_index = self.current_slice_index()
        if axes is None or slice_index is None:
            return 0

        key = rt_history.axes_key(axes)
        generation = getattr(self._shared_data, '_mdaModeParamsGeneration', None)
        rendered = 0
        self._replaying = True
        try:
            for session in self._shared_data.rt_replay.sessions:
                if not (session.enabled and session.replayable):
                    continue
                entry = session.history.get(key, generation)
                if entry is None:
                    #Never analysed (the node was busy when this frame arrived) --
                    #compute it off-thread rather than leaving a stale overlay.
                    self._request_reanalysis(session, key, axes, slice_index, generation)
                    continue
                if self._render(session, entry.snapshot, entry.metadata, slice_index):
                    rendered += 1
        finally:
            self._replaying = False
        return rendered

    def _render(self, session, snapshot, metadata, slice_index):
        """Restore a snapshot onto the node and call its visualise()."""
        image = read_frame(self._shared_data, session.source_layer_name, slice_index)
        target = session.visualisation_target
        if target is None:
            return False
        try:
            session.node.__dict__.update(snapshot)
            utils.realTimeAnalysis_visualisation(
                session.node, session.analysis_info, image, metadata, None, target)
            return True
        except Exception:
            logging.exception('Replay of %s failed; disabling it for this node',
                              session.label)
            session.enabled = False
            return False

    # -- on-demand re-analysis --------------------------------------------

    def _replay_node_for(self, session):
        """A throwaway node instance for re-analysis.

        Never the acquisition's own instance: `run()` accumulates (pSMLM appends
        each frame's localizations to its table), so re-running it while scrubbing
        would corrupt the results the acquisition produced.
        """
        node = self._replay_nodes.get(session.key)
        if node is None:
            node = utils.realTimeAnalysis_init(session.analysis_info, core=None, nodzInfo=None)
            self._replay_nodes[session.key] = node
        return node

    def _request_reanalysis(self, session, key, axes, slice_index, generation):
        with self._request_lock:
            #Latest request wins: mid-drag, every intermediate frame would
            #otherwise queue up behind a slow analysis.
            self._request = (session, key, axes, tuple(slice_index), generation)
        self._request_event.set()
        self._ensure_worker()

    def _ensure_worker(self):
        if self._worker is not None and self._worker.is_alive():
            return
        self._worker_stop.clear()
        self._worker = threading.Thread(target=self._worker_loop,
                                        name='RT-replay-reanalysis', daemon=True)
        self._worker.start()

    def _worker_loop(self):
        while not self._worker_stop.is_set():
            self._request_event.wait(_WORKER_POLL_S)
            self._request_event.clear()
            with self._request_lock:
                request, self._request = self._request, None
            if request is None:
                continue
            try:
                self._reanalyse(*request)
            except Exception:
                logging.exception('On-demand re-analysis failed')

    def _reanalyse(self, session, key, axes, slice_index, generation):
        image = read_frame(self._shared_data, session.source_layer_name, slice_index)
        if image is None:
            return
        metadata = {'Axes': dict(axes)}
        node = self._replay_node_for(session)
        utils.realTimeAnalysis_run(node, session.analysis_info, image, metadata,
                                   self._shared_data, None, nodzInfo=None)

        from glados_pycromanager.GUI.AnalysisClass import _build_state_snapshot
        snapshot = _build_state_snapshot(
            node, utils.realTimeAnalysis_snapshotAttrs(session.analysis_info))
        if not snapshot:
            return
        #Store it, so scrubbing back here is a cache hit rather than a second
        #re-analysis.
        session.history.record(key, snapshot, metadata, generation=generation)

        #napari only on the GUI thread.
        from glados_pycromanager.GUI.napari_bridge import get_bridge
        try:
            get_bridge(self._shared_data).submit(
                lambda _viewer: self._render(session, snapshot, metadata, slice_index))
        except Exception:
            logging.exception('Could not hand a re-analysed frame back to the GUI thread')


def get_replay_controller(shared_data):
    """The session's replay controller, created and attached on first use."""
    controller = getattr(shared_data, '_rt_replay_controller', None)
    if controller is None:
        controller = RTReplayController(shared_data)
        shared_data._rt_replay_controller = controller
    if not controller._connected:
        controller.attach()
    return controller
