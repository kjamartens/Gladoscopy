"""Pure-Python event-list generation through `MIL.create_mda`.

`MicroscopeInterfaceLayer.create_mda` is a thin wrapper over
`pycromanager.multi_d_acquisition_events`. Both are pure Python, so we
can exercise the full event-construction path without a Micro-Manager
core. These tests lock in the per-axis count and the per-event payload
shape against representative synthetic acquisition plans.

Phase 8 (MDAGlados split) and Phase 10.8 (MDA event validation) will
add more tests against the higher-level `MDAGlados` path; for now this
file pins the layer that MDAGlados ultimately routes through.

**Latent bugs captured** in `MIL.create_mda` defaults (Phase 10.8 will
fix these on the MIL side rather than relying on callers to know):

  - `xy_positions=[]` *and* `xyz_positions=[]` together are rejected
    by pycromanager ("incompatible arguments that cannot be passed
    together"), so every test passes `xyz_positions=None`.
  - `xy_positions=[]` + `position_labels=[]` (both mutable defaults)
    silently produce zero events instead of raising. Tests pass
    `xy_positions=None, position_labels=None` to bypass.
  - `channels=[]` + `channel_exposures_ms=[]` similarly suppress event
    generation. Tests pass `channels=None, channel_exposures_ms=None`
    when channels are not the axis under test.
"""
from __future__ import annotations

import pytest

from glados_pycromanager.Core.microscopeInterfaceLayer import (
    MicroscopeInstance,
    MicroscopeInterfaceLayer,
)


@pytest.fixture
def mil_python(monkeypatch):
    """A MIL whose backend tag is forced to PYCROMANAGER_PYTHON.

    `create_mda` only checks the backend tag; it doesn't dereference
    `self._core`. So we can skip wiring a real/mock core entirely.
    """
    mil = MicroscopeInterfaceLayer()
    monkeypatch.setattr(mil, "MI", lambda: MicroscopeInstance.PYCROMANAGER_PYTHON)
    return mil


# Common "no-axis-here" overrides the MIL defaults can't supply.
SAFE_OVERRIDES = dict(
    channels=None,
    channel_exposures_ms=None,
    xy_positions=None,
    xyz_positions=None,
    position_labels=None,
)


def test_single_event_minimal_plan(mil_python):
    events = mil_python.create_mda(num_time_points=1, **SAFE_OVERRIDES)
    assert isinstance(events, list)
    assert len(events) == 1
    e = events[0]
    assert e["axes"] == {"time": 0}
    # `min_start_time` is only emitted when there's more than one time
    # point — single-event plan omits it.


def test_tcz_order_has_t_outermost_z_innermost(mil_python):
    events = mil_python.create_mda(
        num_time_points=2,
        time_interval_s=1.0,
        z_start=0.0,
        z_end=2.0,
        z_step=1.0,
        channel_group="Channel",
        channels=["DAPI", "FITC"],
        channel_exposures_ms=[100, 200],
        xy_positions=None,
        xyz_positions=None,
        position_labels=None,
        order="tcz",
    )
    # 2 (time) × 2 (channels) × 3 (z: 0,1,2) = 12 events.
    assert len(events) == 12

    # First event: t=0, c=DAPI, z=0.
    first = events[0]
    assert first["axes"] == {"time": 0, "channel": "DAPI", "z": 0}
    assert first["min_start_time"] == 0.0
    assert first["config_group"] == ["Channel", "DAPI"]
    assert first["exposure"] == 100
    assert float(first["z"]) == 0.0

    # Last event: t=1, c=FITC, z=2.
    last = events[-1]
    assert last["axes"] == {"time": 1, "channel": "FITC", "z": 2}
    assert last["min_start_time"] == 1.0
    assert last["config_group"] == ["Channel", "FITC"]
    assert last["exposure"] == 200
    assert float(last["z"]) == 2.0


def test_time_axis_only_produces_n_events(mil_python):
    events = mil_python.create_mda(
        num_time_points=5,
        time_interval_s=0.5,
        order="t",
        **SAFE_OVERRIDES,
    )
    assert len(events) == 5
    indices = [e["axes"]["time"] for e in events]
    assert indices == [0, 1, 2, 3, 4]
    starts = [float(e["min_start_time"]) for e in events]
    assert starts == pytest.approx([0.0, 0.5, 1.0, 1.5, 2.0])


def test_xy_positions_replicated_per_time(mil_python):
    xy = [(0.0, 0.0), (100.0, 0.0), (0.0, 100.0)]
    events = mil_python.create_mda(
        num_time_points=2,
        time_interval_s=0.0,
        channels=None,
        channel_exposures_ms=None,
        xy_positions=xy,
        xyz_positions=None,
        position_labels=None,
        order="tp",
    )
    # 2 (time) × 3 (xy positions) = 6 events.
    assert len(events) == 6
    pos_indices_per_t = [
        [e["axes"].get("position") for e in events if e["axes"]["time"] == t]
        for t in (0, 1)
    ]
    # Each timepoint should see every position once.
    assert sorted(pos_indices_per_t[0]) == [0, 1, 2]
    assert sorted(pos_indices_per_t[1]) == [0, 1, 2]


def test_unknown_backend_raises():
    mil = MicroscopeInterfaceLayer()
    # Default backend tag is UNKNOWN — no core set.
    with pytest.raises(ValueError, match="create_mda"):
        mil.create_mda(num_time_points=1)


@pytest.mark.parametrize(
    "backend",
    [
        MicroscopeInstance.PYCROMANAGER_JAVA,
        MicroscopeInstance.PYCROMANAGER_PYTHON,
        MicroscopeInstance.MMCORE_PLUS,
    ],
)
def test_every_real_backend_routes_through_multi_d_helper(monkeypatch, backend):
    mil = MicroscopeInterfaceLayer()
    monkeypatch.setattr(mil, "MI", lambda: backend)
    events = mil.create_mda(num_time_points=1, **SAFE_OVERRIDES)
    assert isinstance(events, list)
    assert len(events) == 1


def test_default_call_raises_due_to_mutex_defaults(mil_python):
    """Latent-bug regression test.

    Lock in the *current* surprising behavior: calling create_mda with
    only `num_time_points` and letting the rest fall through to MIL's
    mutable defaults (xy_positions=[] AND xyz_positions=[]) raises
    `ValueError` from pycromanager. Phase 10.8 should either pre-empt
    this with a typed MIL-side error or set saner defaults; this test
    will be the regression target.
    """
    with pytest.raises(ValueError, match="xyz_positions"):
        mil_python.create_mda(num_time_points=2, time_interval_s=0.5)
