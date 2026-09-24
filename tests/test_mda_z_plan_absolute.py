"""build_absolute_z_plan(): z_start/z_end are *absolute* stage positions
(setZStart()/setZEnd() capture the stage's current absolute position), but
used to be fed straight into useq's "relative" z_plan key -- which treats a
value list as literal offsets from wherever the stage happens to be when the
MDA actually starts. A z-stack set up around an absolute position of e.g.
53-55 therefore asked the stage to jump ~53 and ~55 units *away* from its
current position, instead of sweeping the absolute 53..55 range -- the likely
cause of a real z-stage move timing out / behaving unexpectedly during an MDA.

These tests pin the fix: an absolute "top"/"bottom" (useq ZTopBottom) plan
built from min/max/abs of the panel values, independent of start<->end order
or step sign, and verify it round-trips through useq into the expected
absolute position list.
"""
from __future__ import annotations

import pytest
import useq

from glados_pycromanager.Core.MDAGlados import build_absolute_z_plan


def test_start_below_end_with_positive_step():
    plan = build_absolute_z_plan(z_start=53.2, z_end=55.65, z_step=0.245)
    assert plan == {"top": 55.65, "bottom": 53.2, "step": 0.245, "go_up": True}


def test_start_above_end_with_negative_step_still_normalises_to_top_bottom():
    # The old step-distance widget sign-corrects z_step to be negative when
    # start > end; top/bottom/step must still come out valid (top >= bottom,
    # step > 0) regardless of that sign.
    plan = build_absolute_z_plan(z_start=55.65, z_end=53.2, z_step=-0.245)
    assert plan == {"top": 55.65, "bottom": 53.2, "step": 0.245, "go_up": False}


def test_default_zero_one_one_values_produce_a_valid_two_plane_plan():
    # get_MDA_events_from_GUI's None-guard falls back to (z_start, z_step, z_end)
    # = (0, 1, 1) when the panel has no usable values.
    plan = build_absolute_z_plan(z_start=0, z_end=1, z_step=1)
    assert plan == {"top": 1, "bottom": 0, "step": 1, "go_up": True}


def test_zero_step_falls_back_to_a_positive_step_instead_of_an_invalid_plan():
    plan = build_absolute_z_plan(z_start=1.0, z_end=2.0, z_step=0)
    assert plan["step"] == 1


def test_resulting_plan_visits_the_absolute_range_via_useq():
    plan = build_absolute_z_plan(z_start=53.2, z_end=55.65, z_step=0.245)
    sequence = useq.MDASequence(
        axis_order="tz",
        time_plan={"interval": 0, "loops": 1},
        z_plan=plan,
        channels=[{"config": "DAPI", "exposure": 10}],
    )
    positions = list(sequence.z_plan)
    assert positions[0] == pytest.approx(53.2)
    assert positions[-1] == pytest.approx(55.65)
    assert all(53.2 - 1e-6 <= z <= 55.65 + 1e-6 for z in positions)
