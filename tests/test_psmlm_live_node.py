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


# --------------------------------------------------------------------------
# Regression: the napari async-slicing IndexError
# --------------------------------------------------------------------------

class RecordingPointsLayer:
    """Records the order and count of attribute assignments."""

    #Both forms: `current_*` governs points added later (which is what the node
    #relies on), the bare names style points already present.
    _NAMES = ('symbol', 'size', 'face_color',
              'border_color', 'edge_color', 'border_width', 'edge_width')
    STYLE = set(_NAMES) | {f'current_{n}' for n in _NAMES}

    def __init__(self):
        object.__setattr__(self, 'assignments', [])
        object.__setattr__(self, 'selected_data', set())
        object.__setattr__(self, 'data', np.empty((0, 2)))

    def __setattr__(self, name, value):
        self.assignments.append(name)
        object.__setattr__(self, name, value)

    @property
    def style_count(self):
        return sum(1 for a in self.assignments if a in self.STYLE)

    @property
    def data_count(self):
        return self.assignments.count('data')


class RecordingGroup(dict):
    def __getitem__(self, name):
        if name not in self:
            layer = RecordingPointsLayer() if 'localizations' in name else FakeLayer()
            dict.__setitem__(self, name, layer)
        return dict.__getitem__(self, name)


def test_point_style_is_applied_once_not_per_frame(node, frame):
    """Every style assignment emits a napari event whose handler re-reads the
    layer's view data through the previous slice's indices. Doing that per frame,
    right after the point count changed, races napari 0.7's async slicing and
    raises IndexError out of Points._view_data."""
    group = RecordingGroup()
    for t in range(5):
        _run(node, frame, t=t)
        node.visualise(frame, {'Axes': {'time': t}}, None, group, srSigma=1.0)
    points = group['pSMLM: localizations']
    assert points.data_count == 5
    #Styled on the first visualise only.
    assert 0 < points.style_count <= len(RecordingPointsLayer.STYLE)
    assert points.assignments.count('current_symbol') == 1


def test_point_data_is_assigned_after_the_style(node, frame):
    """So the style events fire while the data and napari's slice indices still
    agree with each other."""
    group = RecordingGroup()
    _run(node, frame)
    node.visualise(frame, {'Axes': {'time': 0}}, None, group, srSigma=1.0)
    assignments = group['pSMLM: localizations'].assignments
    assert assignments.index('current_symbol') < assignments.index('data')


def test_a_stale_selection_is_cleared_before_the_data_shrinks(node, frame):
    """A selection referring to points that no longer exist is the same stale-index
    bug by another route."""
    group = RecordingGroup()
    _run(node, frame)
    node.visualise(frame, {'Axes': {'time': 0}}, None, group, srSigma=1.0)
    points = group['pSMLM: localizations']
    points.selected_data = {0, 1}
    points.assignments.clear()
    _run(node, frame, t=1)
    node.visualise(frame, {'Axes': {'time': 1}}, None, group, srSigma=1.0)
    assert points.assignments.index('selected_data') < points.assignments.index('data')
    assert points.selected_data == set()


def test_an_empty_selection_is_not_reassigned_every_frame(node, frame):
    group = RecordingGroup()
    _run(node, frame)
    node.visualise(frame, {'Axes': {'time': 0}}, None, group, srSigma=1.0)
    points = group['pSMLM: localizations']
    points.assignments.clear()
    _run(node, frame, t=1)
    node.visualise(frame, {'Axes': {'time': 1}}, None, group, srSigma=1.0)
    assert 'selected_data' not in points.assignments


def test_points_are_open_red_rings_on_a_real_napari_layer(node, frame):
    """Regression: they came up as filled white discs.

    napari stores face/border colour **per point**, so styling a still-empty layer
    styles nothing and the points added next take napari's defaults. Only the
    `current_*` properties govern points added later. Asserted against a real
    napari Points layer, because a fake would happily accept either API.
    """
    points_module = pytest.importorskip('napari.layers')
    points = points_module.Points(name='locs')

    class RealGroup(dict):
        def __getitem__(self, name):
            if name == 'pSMLM: localizations':
                return points
            if name not in self:
                dict.__setitem__(self, name, FakeLayer())
            return dict.__getitem__(self, name)

    _run(node, frame)
    node.visualise(frame, {'Axes': {'time': 0}}, None, RealGroup(), srSigma=1.0)

    assert len(points.data) == 2
    assert np.allclose(points.face_color, 0.0), 'fill must be transparent, not white'
    assert np.allclose(points.border_color, [[1, 0, 0, 1]] * 2), 'border must be red'
    assert list(points.size) == [8, 8]


def test_the_sr_canvas_is_not_re_pushed_when_unchanged(node, frame):
    """Regression: scrubbing was very slow.

    The SR canvas is the frame upsampled 10x per axis (up to 400 MB). Re-assigning
    it makes napari re-slice, rescan contrast and re-upload to the GPU, and a scrub
    revisits frames that are already stamped -- so every slider step was paying that
    to push a byte-identical array.
    """
    group = RecordingGroup()
    _run(node, frame)
    node.visualise(frame, {'Axes': {'time': 0}}, None, group, srSigma=1.0)
    sr = group['pSMLM: SR render']
    pushes_after_first = 0

    class Counting(FakeLayer):
        pass

    #Re-visualise the same (already stamped) frame several times.
    before = node._sr_pushed_version
    for _ in range(5):
        node.visualise(frame, {'Axes': {'time': 0}}, None, group, srSigma=1.0)
    assert node._sr_pushed_version == before, 'unchanged canvas must not be re-pushed'
    assert pushes_after_first == 0


def test_a_new_frame_does_re_push_the_sr_canvas(node, frame):
    group = RecordingGroup()
    _run(node, frame, t=0)
    node.visualise(frame, {'Axes': {'time': 0}}, None, group, srSigma=1.0)
    pushed = node._sr_pushed_version
    _run(node, frame, t=1)
    node.visualise(frame, {'Axes': {'time': 1}}, None, group, srSigma=1.0)
    assert node._sr_pushed_version != pushed
