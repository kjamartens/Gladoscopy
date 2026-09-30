"""Structural tests for `glados_pycromanager.autonomous.executor`.

Phase 8.4 moved the runtime methods of the autonomous flowchart out of
`GladosNodzFlowChart_dockWidget` into the `FlowchartExecutorMixin`
class plus a top-level `WorkerSignals` + `generalNodzCallActionWorker`
pair. The dock widget now inherits from the mixin.

Running the executor end-to-end against a real recipe requires a Java
or `mmcore_plus` backend, a Qt event loop, and a recipe file — none of
which exist in CI. So these tests verify the *contracts* the move was
meant to preserve:

* every expected method survived the move and is reachable on the dock
  widget class (i.e. the MRO is wired up correctly);
* the worker classes are importable from both the new home and from
  the back-compat re-export on `FlowChart_dockWidgets`;
* the mixin remains framework-free in its declaration (it can be
  subclassed without instantiating Qt).
"""
from __future__ import annotations

import pytest

from glados_pycromanager.autonomous import executor


# Methods that lived in the NodzFlowChart Node-specific region.
NODE_SPECIFIC_METHODS = {
    "update_scoring_end",
    "update_plugs_fromDialog",
    "changeConfigStorageInNodz",
    "changeRelStageStorageInNodz",
    "AnalysisNode_DEBUG_started",
    "AnalysisNode_started",
    "analysisNode_finished",
    "CustomFunctionNode_started",
    "CustomFunctionNode_finished",
    "MMstageChangeRan",
    "MMconfigChangeRan",
    "acquiringStart",
    "acquiringEnd",
    "initStart",
    "initEnd",
    "scoringStart",
    "scoringEnd",
    "earlyScoringFail",
    "and_logicCallAction",
    "timerCallAction",
    "storeDataCallAction",
    "changeGlobalVarCallAction",
    "newGlobalVarCallAction",
    "ifStatementCallAction",
    "runInlineScriptCallAction",
    "runCaseSwitchCallAction",
    "runslackReportCallAction",
}

# Methods that lived in the NodzFlowChart runs region.
RUN_METHODS = {
    "fullAutonomousRunStart",
    "startNewScoreAcqAtPos",
    "runInitOnly",
    "runScoringOnly",
    "runScoring",
    "runAcquiring",
    "interruptRun",
    "_slack_send_enabled",
    "openSlackSettingsDialog",
    "debugScoring",
}


def test_mixin_carries_node_specific_methods():
    missing = NODE_SPECIFIC_METHODS - set(dir(executor.FlowchartExecutorMixin))
    assert not missing, f"mixin lost methods: {sorted(missing)}"


def test_mixin_carries_run_methods():
    missing = RUN_METHODS - set(dir(executor.FlowchartExecutorMixin))
    assert not missing, f"mixin lost methods: {sorted(missing)}"


def test_workers_live_in_executor_module():
    assert hasattr(executor, "WorkerSignals")
    assert hasattr(executor, "generalNodzCallActionWorker")


def test_back_compat_reexports_on_flowchart_module():
    """Old import sites continue to resolve."""
    from glados_pycromanager.GUI import FlowChart_dockWidgets as f

    assert f.WorkerSignals is executor.WorkerSignals
    assert f.generalNodzCallActionWorker is executor.generalNodzCallActionWorker
    assert f.FlowchartExecutorMixin is executor.FlowchartExecutorMixin


def test_dock_widget_inherits_mixin():
    from glados_pycromanager.GUI.FlowChart_dockWidgets import (
        GladosNodzFlowChart_dockWidget,
    )

    mro_names = [cls.__name__ for cls in GladosNodzFlowChart_dockWidget.__mro__]
    assert "FlowchartExecutorMixin" in mro_names
    nodz_idx = mro_names.index("Nodz")
    mixin_idx = mro_names.index("FlowchartExecutorMixin")
    assert mixin_idx < nodz_idx, "mixin must precede Nodz in MRO so its overrides win"


@pytest.mark.parametrize("name", sorted(NODE_SPECIFIC_METHODS | RUN_METHODS))
def test_methods_reachable_on_dock_widget(name: str):
    from glados_pycromanager.GUI.FlowChart_dockWidgets import (
        GladosNodzFlowChart_dockWidget,
    )

    assert callable(getattr(GladosNodzFlowChart_dockWidget, name))


def test_mixin_is_plain_python_class():
    """No Qt base — instantiating a bare mixin subclass must not require a QApplication."""

    class _Bare(executor.FlowchartExecutorMixin):
        pass

    obj = _Bare()
    assert isinstance(obj, executor.FlowchartExecutorMixin)
