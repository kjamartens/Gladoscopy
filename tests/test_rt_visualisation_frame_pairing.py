"""An overlay must be drawn against the state the frame it shows produced.

The visualisation payload carries the image by value but the node by reference,
and the visualisation thread deliberately runs slower than the analysis
(`visualise_delay` plus the configured display FPS). So `run()` normally processes
several more frames -- overwriting the node's attributes in place -- between a
frame being queued for display and actually being drawn. Without pairing, the
overlay shows frame N's image with frame N+k's results, which is what put pSMLM's
localizations on the wrong frame.
"""

import numpy as np
import pytest

#Imported before any QApplication exists: utils pulls in QtWebEngineWidgets, which
#Qt requires to be imported first.
import glados_pycromanager.GUI.utils as utils  # noqa: F401  (import order matters)

pytest.importorskip('qtpy')


@pytest.fixture(scope='module')
def qapp():
    from qtpy.QtWidgets import QApplication
    return QApplication.instance() or QApplication([])


class Node:
    """Stands in for an RT-analysis node whose run() overwrites its results."""

    def __init__(self):
        self.locs = None
        self.tally = 0
        self.drawn = []

    def run(self, frame):
        self.locs = f'locs-for-{frame}'
        self.tally += 1                      # accumulates; must not be rewound

    def visualise(self, image, metadata, core, layer, **kwargs):
        self.drawn.append((image, self.locs))
        return layer


@pytest.fixture
def visualiser(qapp, monkeypatch):
    """A visualisation thread object without starting its thread."""
    from glados_pycromanager.GUI import AnalysisClass

    monkeypatch.setattr(
        AnalysisClass.utils, 'realTimeAnalysis_visualisation',
        lambda node, info, image, metadata, core, layer: node.visualise(
            image, metadata, core, layer))
    #Keep napariOverlay out of it: we are testing dispatch, not layer creation.
    monkeypatch.setattr(AnalysisClass, 'napariOverlay',
                        lambda *a, **k: type('O', (), {'layer': 'L', 'group': None,
                                                       'is_legacy': True,
                                                       'refreshPlacement': lambda self: False})())

    class Config:
        class visualisation_config:
            fps = 60

    class SharedData:
        napariViewer = None
        config = Config()

        def register_perf_thread_label(self, *a):
            pass

        def unregister_perf_thread_label(self, *a):
            pass

    monkeypatch.setattr(AnalysisClass.utils, 'realTimeAnalysis_getDelay', lambda *a, **k: 1)
    return AnalysisClass.AnalysisThread_customFunction_Visualisation(
        Node(), SharedData(), analysisInfo={'__selectedDropdownEntryRTAnalysis__': 'test'})


def _payload(node, image, snapshot):
    return (node, {}, image, {'Axes': {'time': 0}}, None, None, snapshot)


def test_the_overlay_uses_the_state_the_shown_frame_produced(visualiser):
    """The regression, stated directly."""
    node = Node()
    node.run('frame-1')
    snapshot = {'locs': node.locs}            # taken when frame-1 was queued

    #run() moves on while frame-1 waits in the visualisation queue.
    node.run('frame-2')
    node.run('frame-3')

    visualiser._visualise_on_main_thread(_payload(node, 'frame-1', snapshot))

    image, locs = node.drawn[-1]
    assert image == 'frame-1'
    assert locs == 'locs-for-frame-1', 'the overlay must not show a later frame\'s results'


def test_without_pairing_the_overlay_shows_the_newest_results(visualiser):
    """Pins the old behaviour, so the payload cannot silently lose its snapshot."""
    node = Node()
    node.run('frame-1')
    node.run('frame-2')
    #A six-element payload is the pre-fix shape, and a node declaring no
    #__snapshot_attrs__ still produces one.
    visualiser._visualise_on_main_thread(
        (node, {}, 'frame-1', {'Axes': {'time': 0}}, None, None))
    image, locs = node.drawn[-1]
    assert image == 'frame-1'
    assert locs == 'locs-for-frame-2'


def test_an_empty_snapshot_falls_back_to_the_unpaired_path(visualiser):
    node = Node()
    node.run('frame-1')
    node.run('frame-2')
    visualiser._visualise_on_main_thread(_payload(node, 'frame-1', {}))
    assert node.drawn[-1][1] == 'locs-for-frame-2'


def test_accumulated_state_is_not_rewound_by_rendering(visualiser):
    """For an in-process node this is the live instance run() is still using, so a
    node that accumulates (a counter, a running total) must not lose whatever
    happened while the frame sat in the queue."""
    node = Node()
    node.run('frame-1')
    snapshot = {'locs': node.locs}
    node.run('frame-2')
    node.run('frame-3')
    assert node.tally == 3

    visualiser._visualise_on_main_thread(_payload(node, 'frame-1', snapshot))

    assert node.tally == 3, 'the accumulator must survive'
    assert node.locs == 'locs-for-frame-3', 'the live state must be restored'


def test_state_is_restored_even_when_visualise_raises(visualiser):
    node = Node()
    node.run('frame-1')
    snapshot = {'locs': node.locs}
    node.run('frame-2')

    def boom(*a, **k):
        raise RuntimeError('boom')

    node.visualise = boom
    with pytest.raises(RuntimeError):
        visualiser._visualise_on_main_thread(_payload(node, 'frame-1', snapshot))
    assert node.locs == 'locs-for-frame-2'


def test_an_attribute_absent_before_rendering_is_removed_again(visualiser):
    """A snapshot key the node does not have yet must not be left behind."""
    node = Node()
    visualiser._visualise_on_main_thread(
        _payload(node, 'frame-1', {'onlyInSnapshot': 42}))
    assert not hasattr(node, 'onlyInSnapshot')


def test_array_results_are_paired_too(visualiser):
    node = Node()
    node.locs = np.array([[1.0, 2.0]])
    snapshot = {'locs': node.locs.copy()}
    node.locs = np.array([[9.0, 9.0], [8.0, 8.0]])

    visualiser._visualise_on_main_thread(_payload(node, 'frame-1', snapshot))

    _image, drawn = node.drawn[-1]
    assert np.array_equal(drawn, [[1.0, 2.0]])
    assert len(node.locs) == 2, 'live state restored'
