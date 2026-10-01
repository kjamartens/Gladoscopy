"""Recipe stage handling against a real MMCore (pymmcore-plus demo config).

Reported crash: starting a full run died in `startNewScoreAcqAtPos` ->
`getDevicesOfDeviceType` with `'list' object has no attribute
'get_loaded_devices'`. Three separate faults:

* `Shared_data.core` is only assigned on the napari-plugin path; on the
  standalone app it stayed its `[]` placeholder, so everything handed
  `shared_data.core` (recipe code, node functions) got an empty list;
* `getDevicesOfDeviceType` was a Java-only copy (`.size()/.get()/.to_string()`);
* the MIL had no absolute stage moves (`set_position` / `set_xy_position`),
  which the position tour needs.
"""
from __future__ import annotations

import os
from types import SimpleNamespace

import pytest

pymmcore_plus = pytest.importorskip("pymmcore_plus")

from glados_pycromanager.Core.microscopeInterfaceLayer import MicroscopeInterfaceLayer
from glados_pycromanager.GUI.FlowChart_dockWidgets import GladosNodzFlowChart_dockWidget


@pytest.fixture(scope="module")
def mil():
    if os.environ.get("CI") == "true":
        pytest.skip("CMMCorePlus() hits a native access violation on the GitHub windows-latest runner")
    core = pymmcore_plus.CMMCorePlus()
    core.loadSystemConfiguration()  # bundled demo config
    layer = MicroscopeInterfaceLayer()
    layer.set_core(core)
    return layer


def test_shared_data_core_falls_back_to_the_mil(mil):
    from glados_pycromanager.GUI.sharedFunctions import Shared_data
    shared = Shared_data()
    assert shared.core == []            # nothing bound yet: keep the placeholder
    shared.MILcore = mil
    assert shared.core is mil           # standalone: the MIL, not []
    explicit = object()
    shared.core = explicit              # napari-plugin path assigns a real core
    assert shared.core is explicit


def test_get_devices_of_device_type_works_on_the_mil(mil):
    flow = SimpleNamespace(shared_data=SimpleNamespace(MILcore=mil))
    xy = GladosNodzFlowChart_dockWidget.getDevicesOfDeviceType(flow, 'XYStageDevice')
    z = GladosNodzFlowChart_dockWidget.getDevicesOfDeviceType(flow, 'StageDevice')
    assert xy == ['XY']
    assert 'Z' in z


def test_absolute_stage_moves(mil):
    mil.set_xy_position('XY', 12.0, -3.5)
    mil.set_position('Z', 7.0)
    mil.wait_for_system()
    x, y = mil.get_xy_stage_position('XY')
    # The demo XY stage snaps to its step size (~0.015 um).
    assert x == pytest.approx(12.0, abs=0.05) and y == pytest.approx(-3.5, abs=0.05)
    assert mil.get_position('Z') == pytest.approx(7.0, abs=0.05)


def test_position_tour_moves_the_real_stages(mil, monkeypatch):
    """startNewScoreAcqAtPos end to end on the demo core (no owner thread: inline)."""
    from glados_pycromanager.autonomous import executor
    import glados_pycromanager.GUI.MMcontrols as MMcontrols
    monkeypatch.setattr(MMcontrols, 'guiThreadCall', lambda sd, fn: fn())
    flow = executor.FlowchartExecutorMixin()
    flow.shared_data = SimpleNamespace(MILcore=mil, microscope_service=None, mdaMode=False,
                                       warningErrorInfoInfo={'Info': {'Other': None}})
    flow.getDevicesOfDeviceType = lambda t: GladosNodzFlowChart_dockWidget.getDevicesOfDeviceType(flow, t)
    flow.fullRunOngoing = True
    flow.fullRunCurrentPos = 0
    flow.fullRunPositions = {'nrPositions': 1, 0: {'STAGES': ['XY', 'Z'], 'XY': [4.0, 5.0], 'Z': [2.0]}}
    scored = []
    flow.runScoring = lambda: scored.append(True)

    flow.startNewScoreAcqAtPos()

    assert scored == [True]
    x, y = mil.get_xy_stage_position('XY')
    assert x == pytest.approx(4.0, abs=0.05) and y == pytest.approx(5.0, abs=0.05)
    assert mil.get_position('Z') == pytest.approx(2.0, abs=0.05)
