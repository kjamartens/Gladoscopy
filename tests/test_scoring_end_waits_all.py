"""scoringEnd starts only once every connected analysis finished.

It used to be an ANY node: the first finished analysis started it, and it read
the other analyses' ``__output__`` - still holding the previous position's
values - so the decision could pass or fail on mixed-position data.
"""
from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock

from glados_pycromanager.GUI.nodz.nodz_main import NodeItem


def _node(name, n_inputs):
    node = SimpleNamespace(name=name, status='idle', n_connect_at_start=n_inputs,
                           n_connect_at_start_finished=0, sockets={},
                           flowChart=MagicMock(_runAborted=False), callAction=MagicMock(),
                           callActionRelatedObject=None, update=MagicMock())
    node.waitsForAllInputs = lambda: NodeItem.waitsForAllInputs(node)
    node.WAIT_FOR_ALL_INPUTS_PREFIXES = NodeItem.WAIT_FOR_ALL_INPUTS_PREFIXES
    return node


def test_scoring_end_waits_for_every_input():
    node = _node('scoringEnd_0', 3)
    NodeItem.oneConnectionAtStartIsFinished(node)
    NodeItem.oneConnectionAtStartIsFinished(node)
    node.callAction.assert_not_called()
    NodeItem.oneConnectionAtStartIsFinished(node)
    node.callAction.assert_called_once_with(node)
    assert node.n_connect_at_start_finished == 0  # ready for the next position


def test_regular_node_still_starts_on_first_input():
    node = _node('timer_0', 3)
    NodeItem.oneConnectionAtStartIsFinished(node)
    node.callAction.assert_called_once_with(node)


def test_scoring_start_clears_previous_outputs(monkeypatch):
    from glados_pycromanager.autonomous import executor
    analysis = SimpleNamespace(name='analysisMeasurement_0', status='finished', sockets={}, plugs={},
                               topAttrs={}, bottomAttrs={},
                               scoring_analysis_currentData={'__output__': 42, 'kw': 1})
    monkeypatch.setattr(executor.nodz_utils, 'findConnectedToNode', lambda g, n, acc: ['analysisMeasurement_0'])
    flow = executor.FlowchartExecutorMixin()
    flow.preventScoring = False
    flow.nodes = [analysis]
    flow.evaluateGraph = MagicMock(return_value=[])
    flow.set_readable_text_after_dialogChange = MagicMock()
    flow.GraphToSignals = MagicMock()
    flow.finishedEmits = MagicMock()

    flow.scoringStart(SimpleNamespace(name='scoringStart_0'))

    assert '__output__' not in analysis.scoring_analysis_currentData
    assert analysis.scoring_analysis_currentData['kw'] == 1
    assert analysis.status == 'idle'
