"""Work from a stopped run cannot drive a later run (recipe item 15).

A timer, worker or cancelled MDA from a run the user stopped can finish after
the next run started - when `_runAborted` is already cleared again. Nodes are
stamped with the run generation when they start; a stale finish is dropped.
The Timer node is a GUI-thread QTimer instead of a sleeping pool thread.
"""
from __future__ import annotations

import os
import time
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from glados_pycromanager.autonomous import executor
from glados_pycromanager.GUI.FlowChart_dockWidgets import GladosNodzFlowChart_dockWidget


@pytest.fixture(scope="module")
def qapp():
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from PyQt5.QtCore import QCoreApplication, Qt
    from PyQt5.QtWidgets import QApplication
    QCoreApplication.setAttribute(Qt.AA_ShareOpenGLContexts, True)
    yield QApplication.instance() or QApplication([])


def _flow():
    flow = executor.FlowchartExecutorMixin()
    flow.shared_data = SimpleNamespace(mdaMode=False, warningErrorInfoInfo={'Info': {'Other': None}})
    flow.nodes = []
    flow.fullRunOngoing = False
    return flow


def test_a_node_from_a_stopped_run_is_stale_in_the_next_run():
    flow = _flow()
    assert flow._beginRun('a full run')
    node = SimpleNamespace(name='timer_1', status='running')
    node._runGeneration = flow.currentRunGeneration()      # what nodeRan stamps
    assert not flow.isStaleNode(node)

    flow._abortRun('stopped', user_requested=True)
    assert flow._beginRun('a full run')

    assert flow.isStaleNode(node)
    assert not flow.isStaleNode(SimpleNamespace(name='initStart_0'))  # never stamped


def test_stale_finish_does_not_emit(qapp):
    flow = _flow()
    flow._beginRun('x')
    emitted = []
    node = SimpleNamespace(name='timer_1', _runGeneration=flow.currentRunGeneration(),
                           customFinishedEmits=SimpleNamespace(signals=[1], emit_all_signals=lambda: emitted.append(1)),
                           customDataEmits=None)
    flow._abortRun('stopped', user_requested=True)
    flow._beginRun('x')

    GladosNodzFlowChart_dockWidget._emitNodeFinished(flow, node)
    assert emitted == []


def test_stale_worker_failure_does_not_abort_the_new_run():
    flow = _flow()
    flow._beginRun('x')
    node = SimpleNamespace(name='analysis_1', status='running', _runGeneration=flow.currentRunGeneration())
    flow._abortRun('stopped', user_requested=True)
    flow._beginRun('x')
    flow.fullRunOngoing = True

    class _Worker:
        error = 'ValueError: late'
        nodzType = 'AnalysisNode'
    worker = _Worker()
    flow._nodeWorkerDone(worker, node, MagicMock())

    assert flow._runAborted is False
    assert flow.fullRunOngoing is True


def test_timer_node_finishes_from_the_event_loop(qapp, monkeypatch):
    flow = _flow()
    flow.finishedEmits = MagicMock()
    monkeypatch.setattr(executor.utils, 'nodz_dataFromGeneralAdvancedLineEditDialog',
                        lambda info, fc: {'wait_time': [0.05]})
    node = SimpleNamespace(name='timer_1', timerInfo={}, flowChart=None)

    flow.timerCallAction(node)
    flow.finishedEmits.assert_not_called()           # no blocking sleep

    deadline = time.monotonic() + 2
    while not flow.finishedEmits.called and time.monotonic() < deadline:
        qapp.processEvents()
        time.sleep(0.005)
    flow.finishedEmits.assert_called_once_with(node)
