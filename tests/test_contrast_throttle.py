"""T-E2: the multiDstack path throttles auto-contrast like frameByFrame does.

`_keep_auto_contrast = True` makes napari run `reset_contrast_limits()` -- a
full min/max scan of the freshly decompressed slice -- on every re-slice, and
the multiDstack path re-slices once per dimension per frame. The frameByFrame
path had already replaced that with `_keep_auto_contrast = False` plus the
throttled `_maybe_refresh_contrast`; multiDstack now uses the same pair.

The seeds differ, and that is the part worth pinning: frameByFrame seeds its
counter at 0 because `add_image()` is handed a real frame that napari fits
contrast to, while multiDstack hands `add_image()` a zarr store that is still
all zeros, so it seeds at -1 to force a refresh on the very first update frame
rather than showing a dark stack for N frames at every MDA start.
"""
from __future__ import annotations

from glados_pycromanager.GUI.napariGlados import (
    _get_contrast_frame_counters,
    _maybe_refresh_contrast,
)


class _Layer:
    def __init__(self):
        self.refreshes = 0

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


def _frames_that_refresh(seed, n_frames=25, every_n=10):
    shared_data = _SharedData(every_n)
    _get_contrast_frame_counters(shared_data)["MDA"] = seed
    layer = _Layer()
    fired = []
    for frame in range(1, n_frames + 1):
        before = layer.refreshes
        _maybe_refresh_contrast(shared_data, layer, "MDA")
        if layer.refreshes > before:
            fired.append(frame)
    return fired


def test_multidstack_seed_refreshes_on_the_first_frame():
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
