"""Recipe stage moves run on the hardware owner thread (recipe lag, item 11).

startNewScoreAcqAtPos moved every stage and waited for it on the GUI thread
at each position, and the relative-stage node did not wait at all - so the
next node (often an acquisition) could start while the stage was moving.
"""
from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from glados_pycromanager.autonomous import executor
import glados_pycromanager.GUI.MMcontrols as MMcontrols


class _Recorder:
    """Stands in for submitHardware/guiThreadCall and remembers the hops."""

    def __init__(self):
        self.hops = []

    def submit(self, shared_data, fn, *args, label=None, callback=None, **kw):
        self.hops.append(('owner', label))
        request = SimpleNamespace(result=None, exception=None)
        try:
            request.result = fn()
        except Exception as exc:
            request.exception = exc
        callback(request)

    def gui(self, shared_data, fn):
        self.hops.append(('gui', None))
        fn()


@pytest.fixture
def hops(monkeypatch):
    rec = _Recorder()
    monkeypatch.setattr(MMcontrols, 'submitHardware', rec.submit)
    monkeypatch.setattr(MMcontrols, 'guiThreadCall', rec.gui)
    return rec


def _flow():
    flow = executor.FlowchartExecutorMixin()
    core = MagicMock()
    flow.shared_data = SimpleNamespace(core=core, MILcore=core, mdaMode=False,
                                       warningErrorInfoInfo={'Info': {'Other': None}})
    flow.core = core
    flow.nodes = []
    flow.fullRunOngoing = True
    flow.fullRunCurrentPos = 0
    flow.fullRunPositions = {'nrPositions': 2, 0: {'STAGES': ['XY', 'Z', ''], 'XY': [1.0, 2.0], 'Z': [5.0]}}
    flow.getDevicesOfDeviceType = MagicMock(return_value=['XY'])
    flow.runScoring = MagicMock()
    flow.finishedEmits = MagicMock()
    return flow


def test_position_move_runs_on_owner_thread_then_scores_on_gui(hops):
    flow = _flow()
    flow.startNewScoreAcqAtPos()

    flow.core.set_xy_position.assert_called_once_with('XY', 1.0, 2.0)
    flow.core.set_position.assert_called_once_with('Z', 5.0)
    assert flow.core.wait_for_system.call_count == 2
    assert [h[0] for h in hops.hops] == ['owner', 'gui']
    flow.runScoring.assert_called_once()


def test_failed_position_move_stops_the_run(hops):
    flow = _flow()
    flow.core.set_xy_position.side_effect = RuntimeError('XY stage timeout')
    flow.startNewScoreAcqAtPos()

    flow.runScoring.assert_not_called()
    assert flow._runAborted is True
    assert 'XY stage timeout' in flow.shared_data.warningErrorInfoInfo['Info']['Other'][0]


def test_stop_during_a_move_does_not_start_scoring(hops):
    flow = _flow()
    flow.core.wait_for_system.side_effect = lambda: flow._abortRun('stopped', user_requested=True)
    flow.startNewScoreAcqAtPos()
    flow.runScoring.assert_not_called()


def test_relative_stage_node_waits_before_finishing(hops):
    flow = _flow()
    node = SimpleNamespace(name='stage_1', status='running', MMconfigInfo=SimpleNamespace(
        relstage_string_storage=[['__chosenRelStage__', 'Z'], ['Z', '2.5']]))
    order = []
    flow.core.set_relative_position.side_effect = lambda *a: order.append('move')
    flow.core.wait_for_system.side_effect = lambda: order.append('wait')
    flow.finishedEmits.side_effect = lambda n: order.append('finished')

    flow.MMstageChangeRan(node)

    flow.core.set_relative_position.assert_called_once_with('Z', 2.5)
    assert order == ['move', 'wait', 'finished']


def test_no_owner_thread_inline_failure_still_fails_the_node(monkeypatch):
    # With no service, submitHardware runs fn inline and the exception propagates.
    def inline(shared_data, fn, *a, label=None, callback=None, **k):
        callback(SimpleNamespace(result=fn(), exception=None))
    monkeypatch.setattr(MMcontrols, 'submitHardware', inline)
    monkeypatch.setattr(MMcontrols, 'guiThreadCall', lambda sd, fn: fn())
    flow = _flow()
    flow._nodeFailed = MagicMock()
    flow.core.set_relative_position.side_effect = RuntimeError('no stage')
    node = SimpleNamespace(name='stage_1', status='running', MMconfigInfo=SimpleNamespace(
        relstage_string_storage=[['__chosenRelStage__', 'Z'], ['Z', '1']]))

    flow.MMstageChangeRan(node)

    flow._nodeFailed.assert_called_once()
    flow.finishedEmits.assert_not_called()
