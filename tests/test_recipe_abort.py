"""Stopping an autonomous run actually stops it.

``interruptRun`` used to be just ``_mdaModeAcqData.abort()``: a no-op (or an
AttributeError) on MMCORE_PLUS, possibly aborting the *live* acquisition, and
the run then carried on at the next position anyway. ``_abortRun`` now sets
``_runAborted`` (checked where every downstream node starts), clears the run
flags, and cancels the acquisition on whichever backend runs it.
"""
from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock

import glados_pycromanager.Core.microscopeInterfaceLayer as MIL
from glados_pycromanager.autonomous import executor
from glados_pycromanager.GUI.nodz.nodz_main import NodeItem


def _flow(mdaMode=False, backend=MIL.MicroscopeInstance.MMCORE_PLUS, nodes=()):
    flow = executor.FlowchartExecutorMixin()
    mil = MagicMock()
    mil.MI.return_value = backend
    flow.shared_data = SimpleNamespace(
        mdaMode=mdaMode, MILcore=mil, _mdaModeAcqData=MagicMock(),
        warningErrorInfoInfo={'Info': {'Other': None}})
    flow.fullRunOngoing = True
    flow.singleRunOngoing = True
    flow.nodes = list(nodes)
    flow.startNewScoreAcqAtPos = MagicMock()
    return flow


def test_interrupt_stops_run_and_cancels_mmcore_plus_mda():
    flow = _flow(mdaMode=True)
    flow.interruptRun()

    assert flow._runAborted is True
    assert flow.fullRunOngoing is False
    flow.shared_data.MILcore.core.mda.cancel.assert_called_once()
    flow.shared_data._mdaModeAcqData.abort.assert_not_called()


def test_interrupt_aborts_pycromanager_acquisition():
    flow = _flow(mdaMode=True, backend=MIL.MicroscopeInstance.PYCROMANAGER_JAVA)
    flow.interruptRun()
    flow.shared_data._mdaModeAcqData.abort.assert_called_once()


def test_interrupt_leaves_live_mode_acquisition_alone():
    # _mdaModeAcqData is also set by live mode; with no MDA running it must not be aborted.
    flow = _flow(mdaMode=False, backend=MIL.MicroscopeInstance.PYCROMANAGER_JAVA)
    flow.interruptRun()
    flow.shared_data._mdaModeAcqData.abort.assert_not_called()
    flow.shared_data.MILcore.core.mda.cancel.assert_not_called()


def test_aborted_run_does_not_move_to_next_position():
    flow = _flow()
    flow.fullRunPositions = {'nrPositions': 5}
    flow.fullRunCurrentPos = 1
    flow._abortRun('test')
    flow._advanceToNextPosition()
    flow.startNewScoreAcqAtPos.assert_not_called()
    assert flow.fullRunCurrentPos == 1


def test_last_position_ends_the_full_run():
    flow = _flow()
    flow._runAborted = False
    flow.fullRunPositions = {'nrPositions': 2}
    flow.fullRunCurrentPos = 1
    flow._advanceToNextPosition()
    assert flow.fullRunOngoing is False
    flow.startNewScoreAcqAtPos.assert_not_called()


def test_begin_run_refuses_while_a_full_run_is_going():
    flow = _flow()
    flow._runAborted = False
    assert flow._beginRun('scoring only') is False
    assert 'interrupt' in flow.shared_data.warningErrorInfoInfo['Info']['Other'][0]


def test_begin_run_after_stop_clears_the_stop():
    flow = _flow()
    flow._abortRun('test')
    assert flow._beginRun('a full run') is True
    assert flow._runAborted is False


def test_node_does_not_start_once_the_run_is_stopped():
    node = SimpleNamespace(name='timer_1', status='idle', n_connect_at_start_finished=0,
                           flowChart=SimpleNamespace(_runAborted=True), callAction=MagicMock())
    NodeItem.oneConnectionAtStartIsFinished(node)
    assert node.status == 'idle'
    assert node.n_connect_at_start_finished == 0
    node.callAction.assert_not_called()


def test_interrupt_resets_running_nodes_and_keeps_finished_ones():
    running = SimpleNamespace(status='running')
    finished = SimpleNamespace(status='finished')
    flow = _flow(nodes=[running, finished])
    flow.interruptRun()
    assert running.status == 'idle'
    assert finished.status == 'finished'


def test_failure_marks_running_nodes_error():
    running = SimpleNamespace(status='running')
    flow = _flow(nodes=[running])
    flow._abortRun('analysis_1 failed')
    assert running.status == 'error'
