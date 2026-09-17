"""The pSMLM_live demo node: multi-layer, analysed-frame display, side-by-side SR."""

import numpy as np
import pytest

pytest.importorskip('scipy')

import glados_pycromanager.AutonomousMicroscopy.Real_Time_Analysis  # noqa: F401,E402
from glados_pycromanager.AutonomousMicroscopy.Real_Time_Analysis.pSMLM_live import (  # noqa: E402
    SR_UPSAMPLING,
    pSMLM_live,
)
from glados_pycromanager.GUI.layer_group import normalise_layer_specs  # noqa: E402


class FakeLayer:
    def __init__(self):
        self.data = None

    def __setattr__(self, name, value):
        object.__setattr__(self, name, value)


class FakeGroup(dict):
    """Addressed by name, like NapariLayerGroup."""

    def __getitem__(self, name):
        if name not in self:
            dict.__setitem__(self, name, FakeLayer())
        return dict.__getitem__(self, name)


@pytest.fixture
def node():
    return pSMLM_live(None)


@pytest.fixture
def frame():
    rng = np.random.default_rng(0)
    image = rng.normal(100, 5, (64, 64))
    image[20, 30] += 500
    image[40, 50] += 500
    return image


def _run(node, frame, t=0):
    return node.run(frame, {'Axes': {'time': t}}, None, None, ROIradius=3, stdmult=2)


# --------------------------------------------------------------------------
# Declaration
# --------------------------------------------------------------------------

def test_declares_three_layers_that_normalise(node):
    specs, is_legacy = normalise_layer_specs(node.visualise_init())
    assert is_legacy is False
    assert [s.name for s in specs] == [
        'pSMLM: analysed frame', 'pSMLM: localizations', 'pSMLM: SR render']


def test_the_sr_layer_is_the_only_one_placed_beside(node):
    specs, _ = normalise_layer_specs(node.visualise_init())
    placements = {s.name: s.placement for s in specs}
    assert placements['pSMLM: SR render'] == 'right'
    assert placements['pSMLM: analysed frame'] == 'overlay'
    assert placements['pSMLM: localizations'] == 'overlay'


def test_the_sr_layer_is_scaled_by_the_upsampling_factor(node):
    specs, _ = normalise_layer_specs(node.visualise_init())
    by_name = {s.name: s for s in specs}
    raw = by_name['pSMLM: analysed frame'].scale[-1]
    sr = by_name['pSMLM: SR render'].scale[-1]
    #Same world extent, 10x the pixels -- which is what makes both take the same
    #placement offset.
    assert sr == pytest.approx(raw / SR_UPSAMPLING)


def test_metadata_snapshot_contract_excludes_the_sr_canvas():
    """Snapshotting the canvas would ship 100-400 MB per frame across the
    subprocess boundary; only the localization list travels."""
    from glados_pycromanager.autonomous.registry import get_metadata
    entry = get_metadata('pSMLM_live')['pSMLM_live']
    assert entry['__snapshot_attrs__'] == ['SMLMlocs']
    assert entry['__replayable__'] is True
    assert entry['__runInSubprocess__'] is True


def test_declared_snapshot_attrs_are_what_run_writes(node, frame):
    from glados_pycromanager.GUI.AnalysisClass import _build_state_snapshot
    from glados_pycromanager.autonomous.registry import get_metadata
    _run(node, frame)
    snapshot = _build_state_snapshot(
        node, get_metadata('pSMLM_live')['pSMLM_live']['__snapshot_attrs__'])
    assert list(snapshot) == ['SMLMlocs']
    assert snapshot['SMLMlocs'].shape[1] == 2


# --------------------------------------------------------------------------
# Analysis
# --------------------------------------------------------------------------

def test_run_finds_the_planted_spots(node, frame):
    result = _run(node, frame)
    assert 'localizations' in result
    assert len(node.SMLMlocs) == 2


def test_run_survives_a_frame_with_nothing_in_it(node):
    node.run(np.zeros((32, 32)), {'Axes': {'time': 0}}, None, None,
             ROIradius=3, stdmult=2)
    assert node.SMLMlocs.shape == (0, 2)


def test_run_does_not_build_the_sr_canvas(node, frame):
    """It is built in visualise(), in the main process -- that is the whole point."""
    _run(node, frame)
    assert node.sr_canvas.shape == (1, 1)


# --------------------------------------------------------------------------
# Visualisation
# --------------------------------------------------------------------------

def test_visualise_shows_the_analysed_frame_not_the_newest(node, frame):
    """The answer to 'my localizations are always one frame behind': the node draws
    the frame its own run() analysed."""
    _run(node, frame)
    group = FakeGroup()
    node.visualise(frame, {'Axes': {'time': 0}}, None, group, srSigma=1.0)
    assert np.array_equal(group['pSMLM: analysed frame'].data, frame)


def test_visualise_writes_points_as_row_col(node, frame):
    _run(node, frame)
    group = FakeGroup()
    node.visualise(frame, {'Axes': {'time': 0}}, None, group, srSigma=1.0)
    coords = group['pSMLM: localizations'].data
    assert coords.shape == (2, 2)
    #pSMLM reports (x, y); napari points are (row, col), so the columns swap.
    assert np.allclose(np.sort(coords[:, 0]), np.sort(node.SMLMlocs[:, 1]))


def test_visualise_builds_the_sr_canvas_at_the_upsampled_size(node, frame):
    _run(node, frame)
    group = FakeGroup()
    node.visualise(frame, {'Axes': {'time': 0}}, None, group, srSigma=1.0)
    assert node.sr_canvas.shape == (64 * SR_UPSAMPLING, 64 * SR_UPSAMPLING)
    assert group['pSMLM: SR render'].data is node.sr_canvas


def test_replaying_a_frame_does_not_double_count_it(node, frame):
    """Scrubbing back and forth must not keep adding the same localizations."""
    _run(node, frame)
    group = FakeGroup()
    node.visualise(frame, {'Axes': {'time': 0}}, None, group, srSigma=1.0)
    first = float(node.sr_canvas.sum())
    for _ in range(5):
        node.visualise(frame, {'Axes': {'time': 0}}, None, group, srSigma=1.0)
    assert float(node.sr_canvas.sum()) == pytest.approx(first)


def test_a_new_frame_does_accumulate(node, frame):
    group = FakeGroup()
    _run(node, frame, t=0)
    node.visualise(frame, {'Axes': {'time': 0}}, None, group, srSigma=1.0)
    first = float(node.sr_canvas.sum())
    _run(node, frame, t=1)
    node.visualise(frame, {'Axes': {'time': 1}}, None, group, srSigma=1.0)
    assert float(node.sr_canvas.sum()) > first


def test_an_empty_frame_leaves_the_points_layer_empty(node):
    blank = np.zeros((32, 32))
    node.run(blank, {'Axes': {'time': 0}}, None, None, ROIradius=3, stdmult=2)
    group = FakeGroup()
    node.visualise(blank, {'Axes': {'time': 0}}, None, group, srSigma=1.0)
    assert group['pSMLM: localizations'].data.shape == (0, 2)


def test_a_frame_size_change_reallocates_the_canvas(node, frame):
    group = FakeGroup()
    _run(node, frame)
    node.visualise(frame, {'Axes': {'time': 0}}, None, group, srSigma=1.0)
    bigger = np.zeros((96, 96))
    node.run(bigger, {'Axes': {'time': 1}}, None, None, ROIradius=3, stdmult=2)
    node.visualise(bigger, {'Axes': {'time': 1}}, None, group, srSigma=1.0)
    assert node.sr_canvas.shape == (96 * SR_UPSAMPLING, 96 * SR_UPSAMPLING)


def test_a_node_built_without_a_core_still_scales_its_layers():
    """A subprocess-isolated node is constructed with core=None."""
    specs, _ = normalise_layer_specs(pSMLM_live(None).visualise_init())
    assert all(s.scale is not None for s in specs)
