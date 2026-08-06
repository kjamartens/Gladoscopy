"""Regression test for pSMLM's fullSMLMlocs accumulation.

Locks in the fix for a per-frame O(n^2) pattern: pSMLM.run() used to do
`self.fullSMLMlocs = pd.concat([self.fullSMLMlocs, new_df], ...)` on every
frame, copying the entire accumulated history each call. It now appends each
frame's DataFrame to a list (`_smlm_frames`) and concatenates lazily via the
`fullSMLMlocs` property, so per-frame accumulation is O(1) and the concat
cost is only paid when the full table is actually read.
"""

import pandas as pd
import pytest

from glados_pycromanager.AutonomousMicroscopy.Real_Time_Analysis.pSMLM import pSMLM


class _FakeCore:
    def get_pixel_size_um(self):
        return 1.0


@pytest.fixture
def psmlm():
    return pSMLM(core=_FakeCore(), ROIradius=3, stdmult=2)


def test_full_smlm_locs_empty_when_no_frames(psmlm):
    result = psmlm.fullSMLMlocs
    assert isinstance(result, pd.DataFrame)
    assert len(result) == 0


def test_full_smlm_locs_concatenates_appended_frames(psmlm):
    frame0 = pd.DataFrame({"x_pos": [1.0, 2.0], "y_pos": [3.0, 4.0]})
    frame1 = pd.DataFrame({"x_pos": [5.0], "y_pos": [6.0]})
    psmlm._smlm_frames.append(frame0)
    psmlm._smlm_frames.append(frame1)

    result = psmlm.fullSMLMlocs

    assert len(result) == 3
    assert list(result["x_pos"]) == [1.0, 2.0, 5.0]


def test_appending_frames_does_not_copy_or_mutate_prior_frames(psmlm):
    """Each frame is stored once and never touched again - the whole point of
    switching from an eager per-frame concat to a lazy list accumulation."""
    frames = [pd.DataFrame({"x_pos": [float(i)], "y_pos": [float(i)]}) for i in range(50)]
    for f in frames:
        psmlm._smlm_frames.append(f)

    # Same object identity as originally appended - proves nothing rebuilt/copied them.
    for original, stored in zip(frames, psmlm._smlm_frames):
        assert stored is original

    assert len(psmlm._smlm_frames) == 50
    assert len(psmlm.fullSMLMlocs) == 50
