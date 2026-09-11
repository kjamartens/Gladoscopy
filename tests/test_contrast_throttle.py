"""_maybe_refresh_contrast() now defers to napari's own native
"once"/"continuous" auto-contrast toggle (`layer._keep_auto_contrast`, driven
by napari's AutoScaleButtons in its built-in layer controls) instead of
running unconditionally:

- New live/MDA/album layers default to `_keep_auto_contrast = True`
  ("continuous") at creation -- see the layer-creation sites in
  napariGlados.py and napariHelperFunctions.py.
- While `True`, this function still throttles to every Nth displayed frame
  (visualisation_config.contrast_refresh_every_n_frames) rather than
  recomputing on every single frame: bench_live_display measured a full
  min/max scan as ~25-30% of steady-state frame time, and this is the only
  place doing the recompute for the frameByFrame path, whose in-place data
  mutation bypasses napari's own slicing pipeline entirely.
- While `False` (the user picked "once", or dragged the contrast sliders
  manually), this function must do nothing at all -- that is the whole point
  of those two modes: the displayed range stays exactly where the user left
  it.

(The multiDstack path no longer calls this function at all -- its
`dims.set_current_step` already runs napari's normal slicing pipeline, which
natively recomputes contrast on every re-slice while `_keep_auto_contrast` is
True, and does nothing while it's False.)
"""
from __future__ import annotations

from glados_pycromanager.GUI.napariGlados import (
    _get_contrast_frame_counters,
    _maybe_refresh_contrast,
)


class _Layer:
    def __init__(self, keep_auto_contrast=True):
        self.refreshes = 0
        self._keep_auto_contrast = keep_auto_contrast

    def reset_contrast_limits(self):
        self.refreshes += 1


class _SharedData:
    def __init__(self, every_n=10):
        self.config = type(
            "Config",
            (),
            {
                "visualisation_config": type(
                    "Vis", (), {"contrast_refresh_every_n_frames": every_n}
                )()
            },
        )()


def _frames_that_refresh(seed, n_frames=25, every_n=10, keep_auto_contrast=True):
    shared_data = _SharedData(every_n)
    _get_contrast_frame_counters(shared_data)["MDA"] = seed
    layer = _Layer(keep_auto_contrast=keep_auto_contrast)
    fired = []
    for frame in range(1, n_frames + 1):
        before = layer.refreshes
        _maybe_refresh_contrast(shared_data, layer, "MDA")
        if layer.refreshes > before:
            fired.append(frame)
    return fired


def test_minus_one_seed_refreshes_on_the_first_frame():
    """The -1 seed: frame 1, then every Nth."""
    assert _frames_that_refresh(seed=-1) == [1, 11, 21]


def test_framebyframe_seed_waits_for_the_full_interval():
    """The 0 seed keeps its existing behaviour -- add_image() already fitted it."""
    assert _frames_that_refresh(seed=0) == [10, 20]


def test_the_seed_only_shifts_phase_not_rate():
    """Both seeds refresh at the same rate; only the first refresh moves."""
    assert len(_frames_that_refresh(seed=-1, n_frames=100)) == \
        len(_frames_that_refresh(seed=0, n_frames=100))


def test_interval_of_one_refreshes_every_frame():
    """contrast_refresh_every_n_frames=1 restores the pre-throttle behaviour."""
    assert _frames_that_refresh(seed=-1, n_frames=5, every_n=1) == [1, 2, 3, 4, 5]


class TestGatedByNativeContinuousToggle:
    def test_no_refresh_at_all_when_not_continuous(self):
        """`_keep_auto_contrast = False` (napari's "once" already fired, or the
        user is holding a manual/slider-set range) must suppress every refresh,
        not just throttle them -- nothing should touch the displayed range."""
        assert _frames_that_refresh(seed=0, n_frames=50, keep_auto_contrast=False) == []

    def test_refreshes_periodically_when_continuous(self):
        assert _frames_that_refresh(seed=0, n_frames=25, keep_auto_contrast=True) == [10, 20]

    def test_missing_attribute_defaults_to_no_refresh(self):
        """A layer object with no `_keep_auto_contrast` attribute at all must
        not be treated as continuous by default -- fail safe/quiet, not loud."""
        shared_data = _SharedData(10)
        _get_contrast_frame_counters(shared_data)["MDA"] = 0

        class _BareLayer:
            def __init__(self):
                self.refreshes = 0

            def reset_contrast_limits(self):
                self.refreshes += 1

        layer = _BareLayer()
        for _ in range(25):
            _maybe_refresh_contrast(shared_data, layer, "MDA")
        assert layer.refreshes == 0


class TestLayerCreationDefaultsToContinuous:
    def test_framebyframe_and_multidstack_creation_seed_continuous_true(self):
        """Both live/MDA layer-creation sites in napariGlados.py must default
        the native napari toggle to continuous ('True'), not silently keep
        napari's own default -- the whole feature is "continuous auto-selected
        on layer creation, overridable by the user."""
        import inspect

        import glados_pycromanager.GUI.napariGlados as napariGlados

        source = inspect.getsource(napariGlados._napariUpdateLive_locked)
        assert source.count("layer._keep_auto_contrast = True") >= 2, (
            "expected both the frameByFrame and multiDstack layer-creation "
            "branches to default to continuous auto-contrast"
        )
        assert "layer._keep_auto_contrast = False" not in source
