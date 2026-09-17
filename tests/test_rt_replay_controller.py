"""Scrub-driven replay of RT-analysis overlays."""

import logging
import threading

import numpy as np
import pytest

#Imported before any QApplication exists: utils pulls in QtWebEngineWidgets,
#which Qt requires to be imported first ("QtWebEngineWidgets must be imported or
#Qt.AA_ShareOpenGLContexts must be set before a QCoreApplication instance is
#created").
import glados_pycromanager.GUI.utils as utils  # noqa: F401  (import order matters)
from glados_pycromanager.GUI import rt_history

pytest.importorskip('qtpy')


@pytest.fixture(scope='module')
def qapp():
    from qtpy.QtWidgets import QApplication
    app = QApplication.instance() or QApplication([])
    return app


# --------------------------------------------------------------------------
# Fakes
# --------------------------------------------------------------------------

class FakeEvent:
    def __init__(self):
        self.callbacks = []

    def connect(self, cb):
        self.callbacks.append(cb)

    def disconnect(self, cb):
        self.callbacks.remove(cb)

    def emit(self):
        for cb in list(self.callbacks):
            cb(None)


class FakeDims:
    def __init__(self, current_step=(0, 0)):
        self.current_step = current_step

        class Events:
            pass

        self.events = Events()
        self.events.current_step = FakeEvent()


class FakeViewer:
    def __init__(self, current_step=(0, 0)):
        self.dims = FakeDims(current_step)
        self.layers = {}


class FakeGroup:
    def __init__(self):
        self.names = ['Overlay']
        self.primary = 'primary-layer'


class RecordingNode:
    """Stands in for an RT-analysis node instance."""

    def __init__(self):
        self.locs = None
        self.visualised = []
        self.ran = []

    def visualise(self, image, metadata, core, napariLayer, **kwargs):
        self.visualised.append((self.locs, metadata, None if image is None else image.copy()))
        return napariLayer

    def run(self, image, metadata, shared_data, core, **kwargs):
        self.ran.append(metadata)
        self.locs = np.array([[float(image.mean())]])
        return 'ok'


class FakeConfig:
    class rt_analysis_config:
        replay_debounce_ms = 0
        replay_history_budget_mb = 8


class FakeSharedData:
    """Two-dimensional plan: time 0..2, z 10/20; a 3x2 zarr-ish store."""

    def __init__(self, viewer):
        self.napariViewer = viewer
        self.liveMode = False
        self.mdaMode = False
        self.config = FakeConfig()
        self._mdaModeParamsGeneration = 1
        self.mdaZarrData = {'MDA': np.arange(3 * 2 * 4 * 4).reshape(3, 2, 4, 4)}
        self.newestLayerName = 'MDA'
        self._rt_replay = rt_history.RTReplayRegistry(budget_bytes=1 << 20)

    @property
    def rt_replay(self):
        return self._rt_replay


DIM_ORDER = ['time', 'z']
UNIQUE = {'time': np.array([0, 1, 2]), 'z': np.array([10, 20])}


@pytest.fixture
def controller(qapp, monkeypatch):
    import glados_pycromanager.GUI.rt_replay as rt_replay

    monkeypatch.setattr(utils, 'getAcquisitionDimensions',
                        lambda _sd: (DIM_ORDER, [3, 2], UNIQUE))
    #Dispatch straight to the node instead of through the kwarg-binding machinery.
    monkeypatch.setattr(utils, 'realTimeAnalysis_visualisation',
                        lambda node, info, im, md, core, layer: node.visualise(im, md, core, layer))
    monkeypatch.setattr(utils, 'realTimeAnalysis_run',
                        lambda node, info, im, md, sd, core, **kw: node.run(im, md, sd, core))
    monkeypatch.setattr(utils, 'realTimeAnalysis_snapshotAttrs', lambda _info: ['locs'])
    monkeypatch.setattr(utils, 'realTimeAnalysis_init',
                        lambda _info, core=None, nodzInfo=None: RecordingNode())

    viewer = FakeViewer()
    shared = FakeSharedData(viewer)
    ctrl = rt_replay.RTReplayController(shared, debounce_ms=0)
    ctrl.attach(viewer)
    return ctrl, shared, viewer


def _register(shared, node=None, history=None):
    session = rt_history.RTReplaySession(
        key='node', node=node or RecordingNode(), analysis_info={},
        group=FakeGroup(), is_legacy=False,
        history=history or rt_history.RTNodeHistory(1 << 20, label='TestNode'),
        source_layer_name='MDA', label='TestNode')
    return shared.rt_replay.register(session)


# --------------------------------------------------------------------------
# Axes / slice mapping
# --------------------------------------------------------------------------

def test_current_axes_reads_the_slider_position(controller):
    ctrl, _shared, viewer = controller
    viewer.dims.current_step = (2, 1, 0, 0)
    assert ctrl.current_axes() == {'time': 2, 'z': 20}


def test_current_slice_index_needs_no_searchsorted(controller):
    """The display path sets current_step *to* the searchsorted indices."""
    ctrl, _shared, viewer = controller
    viewer.dims.current_step = (2, 1, 0, 0)
    assert ctrl.current_slice_index() == (2, 1)


def test_short_current_step_yields_nothing(controller):
    ctrl, _shared, viewer = controller
    viewer.dims.current_step = (1,)
    assert ctrl.current_axes() is None
    assert ctrl.current_slice_index() is None


# --------------------------------------------------------------------------
# The inert gate
# --------------------------------------------------------------------------

def test_replay_is_inert_during_live_mode(controller):
    """The acquisition display path drives current_step itself, once per frame."""
    ctrl, shared, viewer = controller
    session = _register(shared)
    session.history.record(rt_history.axes_key({'time': 0, 'z': 10}), {'locs': 1}, generation=1)
    shared.liveMode = True
    assert ctrl.replay_now() == 0
    assert session.node.visualised == []


def test_replay_is_inert_during_mda_mode(controller):
    ctrl, shared, _viewer = controller
    _register(shared)
    shared.mdaMode = True
    assert ctrl.replay_now() == 0


def test_replay_is_inert_while_suspended(controller):
    ctrl, shared, _viewer = controller
    _register(shared)
    shared.rt_replay.suspended = True
    assert ctrl.replay_now() == 0


def test_slider_events_are_ignored_while_inert(controller):
    ctrl, shared, viewer = controller
    shared.mdaMode = True
    viewer.dims.events.current_step.emit()
    assert ctrl._timer.isActive() is False


def test_slider_events_schedule_a_replay(controller):
    ctrl, _shared, viewer = controller
    viewer.dims.events.current_step.emit()
    assert ctrl._timer.isActive() is True


# --------------------------------------------------------------------------
# Replay of stored results
# --------------------------------------------------------------------------

def test_a_stored_frame_is_replayed_with_its_own_snapshot(controller):
    ctrl, shared, viewer = controller
    session = _register(shared)
    session.history.record(rt_history.axes_key({'time': 1, 'z': 20}),
                           {'locs': np.array([[7.0]])},
                           {'Axes': {'time': 1, 'z': 20}}, generation=1)
    viewer.dims.current_step = (1, 1, 0, 0)
    assert ctrl.replay_now() == 1
    locs, metadata, image = session.node.visualised[-1]
    assert locs[0][0] == 7.0
    assert metadata['Axes'] == {'time': 1, 'z': 20}
    #...and the frame came from the store at that slice, not from anywhere else.
    assert np.array_equal(image, shared.mdaZarrData['MDA'][1, 1])


def test_scrubbing_between_frames_shows_each_frame_own_result(controller):
    ctrl, shared, viewer = controller
    session = _register(shared)
    for t in range(3):
        session.history.record(rt_history.axes_key({'time': t, 'z': 10}),
                               {'locs': np.array([[float(t)]])},
                               {'Axes': {'time': t, 'z': 10}}, generation=1)
    seen = []
    for t in range(3):
        viewer.dims.current_step = (t, 0, 0, 0)
        ctrl.replay_now()
        seen.append(session.node.visualised[-1][0][0][0])
    assert seen == [0.0, 1.0, 2.0]


def test_a_stale_generation_is_not_replayed(controller):
    """Results from a previous acquisition describe a different plan."""
    ctrl, shared, viewer = controller
    session = _register(shared)
    session.history.record(rt_history.axes_key({'time': 0, 'z': 10}),
                           {'locs': 1}, generation=99)
    viewer.dims.current_step = (0, 0, 0, 0)
    ctrl.replay_now()
    assert session.node.visualised == []


def test_a_disabled_session_is_skipped(controller):
    ctrl, shared, viewer = controller
    session = _register(shared)
    session.history.record(rt_history.axes_key({'time': 0, 'z': 10}), {'locs': 1}, generation=1)
    session.enabled = False
    assert ctrl.replay_now() == 0


def test_a_non_replayable_session_is_skipped(controller):
    ctrl, shared, _viewer = controller
    session = _register(shared)
    session.history.record(rt_history.axes_key({'time': 0, 'z': 10}), {'locs': 1}, generation=1)
    session.replayable = False
    assert ctrl.replay_now() == 0


def test_a_failing_visualise_never_raises_into_the_slider_callback(controller, caplog):
    """Whatever the node does, a scrub must not raise."""
    ctrl, shared, viewer = controller

    class Exploding(RecordingNode):
        def visualise(self, *a, **k):
            raise RuntimeError('boom')

    session = _register(shared, node=Exploding())
    session.history.record(rt_history.axes_key({'time': 0, 'z': 10}), {'locs': 1}, generation=1)
    with caplog.at_level(logging.WARNING):
        assert ctrl.replay_now() == 0
    #Not disabled on the first failure -- see the transient-failure tests below.
    assert session.enabled is True


def test_legacy_sessions_get_the_bare_layer(controller):
    ctrl, shared, viewer = controller
    session = _register(shared)
    session.is_legacy = True
    session.history.record(rt_history.axes_key({'time': 0, 'z': 10}),
                           {'locs': 1}, generation=1)
    assert session.visualisation_target == 'primary-layer'
    assert ctrl.replay_now() == 1


# --------------------------------------------------------------------------
# On-demand re-analysis
# --------------------------------------------------------------------------

def test_a_gap_triggers_re_analysis_and_caches_the_result(controller, monkeypatch):
    """Frames the analysis never saw are computed lazily rather than left stale."""
    ctrl, shared, viewer = controller
    session = _register(shared)
    done = threading.Event()

    import glados_pycromanager.GUI.rt_replay as rt_replay
    monkeypatch.setattr(rt_replay, 'get_bridge',
                        lambda _sd: type('B', (), {'submit': staticmethod(lambda fn: done.set())})(),
                        raising=False)

    viewer.dims.current_step = (2, 0, 0, 0)
    assert ctrl.replay_now() == 0                 # nothing stored for this frame
    #Re-analysis is deliberately NOT triggered by the render tick -- it waits for
    #the slider to settle, so a drag does not keep the analysis worker busy.
    assert ctrl.reanalyse_now() == 1
    key = rt_history.axes_key({'time': 2, 'z': 10})
    for _ in range(100):
        if session.history.get(key, 1) is not None:
            break
        threading.Event().wait(0.02)
    entry = session.history.get(key, 1)
    assert entry is not None, 'the gap should have been filled by re-analysis'
    #Second visit is a cache hit: it renders, and does not re-run.
    assert ctrl.replay_now() == 1


def test_re_analysis_never_touches_the_acquisition_node(controller):
    """Re-running run() on the acquisition's own instance would corrupt what it
    accumulated during the acquisition."""
    ctrl, shared, _viewer = controller
    session = _register(shared)
    replay_node = ctrl._replay_node_for(session)
    assert replay_node is not session.node
    assert ctrl._replay_node_for(session) is replay_node      # reused, not rebuilt


def test_latest_request_wins(controller):
    ctrl, shared, _viewer = controller
    session = _register(shared)
    ctrl._worker_stop.set()                       # keep the worker from draining
    ctrl._request_reanalysis(session, 'k1', {'time': 0}, (0, 0), 1)
    ctrl._request_reanalysis(session, 'k2', {'time': 1}, (1, 0), 1)
    assert ctrl._request[1] == 'k2'


# --------------------------------------------------------------------------
# read_frame
# --------------------------------------------------------------------------

def test_read_frame_pulls_the_right_slice(controller):
    _ctrl, shared, _viewer = controller
    from glados_pycromanager.GUI.rt_replay import read_frame
    assert np.array_equal(read_frame(shared, 'MDA', (2, 1)),
                          shared.mdaZarrData['MDA'][2, 1])


def test_read_frame_without_a_store_is_none(controller):
    _ctrl, shared, _viewer = controller
    from glados_pycromanager.GUI.rt_replay import read_frame
    assert read_frame(shared, None, (0, 0)) is None
    assert read_frame(shared, 'NoSuchLayer', (0, 0)) is None


def test_read_frame_out_of_range_is_none(controller):
    _ctrl, shared, _viewer = controller
    from glados_pycromanager.GUI.rt_replay import read_frame
    assert read_frame(shared, 'MDA', (99, 99)) is None


def test_detach_is_idempotent_and_stops_the_timer(controller):
    ctrl, _shared, viewer = controller
    ctrl.detach()
    ctrl.detach()
    assert ctrl._connected is False
    assert viewer.dims.events.current_step.callbacks == []


# --------------------------------------------------------------------------
# Transient render failures
# --------------------------------------------------------------------------

class FlakyNode(RecordingNode):
    """Fails a fixed number of times, then works."""

    def __init__(self, failures):
        super().__init__()
        self.remaining_failures = failures

    def visualise(self, image, metadata, core, napariLayer, **kwargs):
        if self.remaining_failures > 0:
            self.remaining_failures -= 1
            raise IndexError('index 52 is out of bounds for axis 0 with size 52')
        return super().visualise(image, metadata, core, napariLayer, **kwargs)


def _store(session, t=0):
    session.history.record(rt_history.axes_key({'time': t, 'z': 10}),
                           {'locs': np.array([[1.0]])},
                           {'Axes': {'time': t, 'z': 10}}, generation=1)


def test_one_transient_failure_does_not_disable_replay(controller):
    """napari slices asynchronously, so a scrub can legitimately land mid-re-slice
    and raise an IndexError that says nothing about the node."""
    ctrl, shared, viewer = controller
    session = _register(shared, node=FlakyNode(failures=1))
    _store(session)
    viewer.dims.current_step = (0, 0, 0, 0)
    assert ctrl.replay_now() == 0
    assert session.enabled is True
    #The next scrub works.
    assert ctrl.replay_now() == 1
    assert session.enabled is True


def test_a_success_resets_the_failure_count(controller):
    ctrl, shared, viewer = controller
    session = _register(shared, node=FlakyNode(failures=1))
    _store(session)
    viewer.dims.current_step = (0, 0, 0, 0)
    ctrl.replay_now()
    ctrl.replay_now()                     # succeeds, clearing the tally
    assert ctrl._render_failures.get(session.key) is None


def test_a_consistently_broken_node_is_still_disabled(controller):
    ctrl, shared, viewer = controller
    from glados_pycromanager.GUI.rt_replay import RENDER_FAILURES_BEFORE_DISABLE
    session = _register(shared, node=FlakyNode(failures=99))
    _store(session)
    viewer.dims.current_step = (0, 0, 0, 0)
    for _ in range(RENDER_FAILURES_BEFORE_DISABLE):
        ctrl.replay_now()
    assert session.enabled is False


# --------------------------------------------------------------------------
# Which layer replay reads frames from
# --------------------------------------------------------------------------

def test_a_stale_captured_layer_name_does_not_stop_the_frame_being_read(controller):
    """Regression: replay updated the localizations but not the analysed frame.

    The RT thread is usually started from the dock widget's Activate button, long
    before the acquisition that produces the frames exists, so the layer name
    captured at registration is stale or None. read_frame then returned None and
    every part of the node's visualise() guarded by `if image is not None` silently
    did nothing.
    """
    ctrl, shared, viewer = controller
    session = _register(shared)
    session.source_layer_name = 'Live'          # what existed at Activate time
    session.history.record(rt_history.axes_key({'time': 1, 'z': 0 if False else 10}),
                           {'locs': np.array([[1.0]])},
                           {'Axes': {'time': 1, 'z': 10}}, generation=1)
    viewer.dims.current_step = (1, 0, 0, 0)
    assert ctrl.replay_now() == 1
    _locs, _md, image = session.node.visualised[-1]
    assert image is not None, 'the analysed frame must still be read'
    assert np.array_equal(image, shared.mdaZarrData['MDA'][1, 0])


def test_the_current_acquisition_layer_wins_over_the_captured_one(controller):
    ctrl, shared, _viewer = controller
    session = _register(shared)
    session.source_layer_name = 'Live'
    assert ctrl._source_layer_name(session) == 'MDA'


def test_the_captured_name_is_used_when_it_is_the_one_with_a_store(controller):
    ctrl, shared, _viewer = controller
    session = _register(shared)
    session.source_layer_name = 'MDA'
    shared.newestLayerName = 'SomethingWithoutAStore'
    assert ctrl._source_layer_name(session) == 'MDA'


def test_a_name_with_no_store_is_still_returned_for_the_layer_data_fallback(controller):
    ctrl, shared, _viewer = controller
    session = _register(shared)
    session.source_layer_name = None
    shared.newestLayerName = 'Live'
    shared.mdaZarrData = {}
    assert ctrl._source_layer_name(session) == 'Live'


def test_no_layer_name_anywhere_is_none(controller):
    ctrl, shared, _viewer = controller
    session = _register(shared)
    session.source_layer_name = None
    shared.newestLayerName = None
    assert ctrl._source_layer_name(session) is None


def test_the_render_tick_does_not_queue_re_analysis(controller):
    """Regression: scrubbing was very slow.

    Requesting re-analysis from every render tick kept a CPU-bound, GIL-holding
    worker running for the whole duration of a drag. It now waits for the slider
    to settle, on its own longer timer, while already-stored frames still render
    at the fast debounce.
    """
    ctrl, shared, viewer = controller
    _register(shared)
    viewer.dims.current_step = (2, 0, 0, 0)
    ctrl.replay_now()
    assert ctrl._request is None


def test_a_slider_move_arms_both_timers_with_re_analysis_slower(controller):
    ctrl, _shared, viewer = controller
    from glados_pycromanager.GUI.rt_replay import REANALYSIS_SETTLE_MS
    viewer.dims.events.current_step.emit()
    assert ctrl._timer.isActive() and ctrl._reanalysis_timer.isActive()
    assert ctrl._reanalysis_timer.interval() >= REANALYSIS_SETTLE_MS
    assert ctrl._reanalysis_timer.interval() > ctrl._timer.interval()


def test_reanalyse_now_skips_frames_that_are_already_stored(controller):
    ctrl, shared, viewer = controller
    session = _register(shared)
    _store(session, t=2)
    viewer.dims.current_step = (2, 0, 0, 0)
    assert ctrl.reanalyse_now() == 0


def test_reanalyse_now_is_inert_during_acquisition(controller):
    ctrl, shared, viewer = controller
    _register(shared)
    shared.mdaMode = True
    viewer.dims.current_step = (2, 0, 0, 0)
    assert ctrl.reanalyse_now() == 0
