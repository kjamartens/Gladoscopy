"""A node worker that raises must still report back (recipe robustness).

``generalNodzCallActionWorker.run`` used to emit ``finished`` only on the
happy path, so any exception in a node's function left the node 'running'
and the whole recipe hung with nothing on screen. ``_startNodeWorker`` now
routes failures to ``_nodeFailed``, which marks the node and stops the run.
"""
from __future__ import annotations

import time
from types import SimpleNamespace

import pytest
from PyQt5.QtCore import QThreadPool

from glados_pycromanager.autonomous import executor


@pytest.fixture(scope="module")
def qapp():
    from PyQt5.QtWidgets import QApplication
    return QApplication.instance() or QApplication([])


class _Flowchart(executor.FlowchartExecutorMixin):
    def __init__(self):
        self.thread_pool = QThreadPool()
        self.shared_data = SimpleNamespace(
            warningErrorInfoInfo={'Info': {'Other': None, 'LastNodeRan': None}})
        self.fullRunOngoing = True
        self.singleRunOngoing = True
        self.succeeded = []


def _wait_until(qapp, predicate, timeout_s=5.0):
    deadline = time.monotonic() + timeout_s
    while not predicate() and time.monotonic() < deadline:
        qapp.processEvents()
        time.sleep(0.005)
    return predicate()


def _run(qapp, flow, node, nodzType, args, on_success):
    flow._startNodeWorker(node, nodzType, args, on_success)
    assert _wait_until(qapp, lambda: not flow.__dict__.get('_activeNodeWorkers')), \
        "worker slot never ran"


def test_raising_worker_marks_node_error_and_stops_run(qapp, monkeypatch):
    def boom(*a, **k):
        raise ValueError("bad kwarg")
    monkeypatch.setattr(executor.registry, "dispatch_from_eval_text", boom)

    flow = _Flowchart()
    node = SimpleNamespace(name='analysis_1', status='running', output=None)
    _run(qapp, flow, node, 'AnalysisNode',
         {"evalText": "x()", "nodeDict": {}, "node": node, "core": None, "shared_data": None},
         lambda: flow.succeeded.append(node))

    assert node.status == 'error'
    assert flow.succeeded == []
    assert flow.fullRunOngoing is False
    assert 'bad kwarg' in flow.shared_data.warningErrorInfoInfo['Info']['Other'][0]


def test_raising_success_callback_is_also_a_node_failure(qapp):
    flow = _Flowchart()
    node = SimpleNamespace(name='timer_1', status='running')

    def finish():
        raise KeyError('__output__')
    _run(qapp, flow, node, 'Timer', {"wait_time": 0}, finish)

    assert node.status == 'error'
    assert flow.fullRunOngoing is False


def test_successful_worker_runs_callback_once(qapp):
    flow = _Flowchart()
    node = SimpleNamespace(name='timer_1', status='running')
    _run(qapp, flow, node, 'Timer', {"wait_time": 0}, lambda: flow.succeeded.append(node))

    assert flow.succeeded == [node]
    assert node.status == 'running'  # finishedEmits (not called here) owns 'finished'
    assert flow.fullRunOngoing is True
