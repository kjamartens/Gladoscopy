"""Node crashes that used to hang a recipe (item 5 of the recipe robustness plan).

* the inline-script node referenced a module-level ``shared_data`` that
  ``executor.py`` never had (NameError on every run);
* scoringEnd only assigned ``readableText`` on the *error* path, so a passing
  test with a reporting node attached raised NameError;
* a scoring-decision error stopped the run silently;
* the relative-stage node raised NameError when no stage was chosen.
"""
from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock

from glados_pycromanager.autonomous import executor


def _flow():
    flow = executor.FlowchartExecutorMixin()
    flow.shared_data = SimpleNamespace(core=MagicMock(), mdaMode=False,
                                       warningErrorInfoInfo={'Info': {'Other': None}})
    flow.core = flow.shared_data.core
    flow.nodes = []
    flow.fullRunOngoing = True
    flow.finishedEmits = MagicMock()
    flow._nodeFailed = MagicMock()
    return flow


def test_inline_script_runs_against_the_flowchart_core():
    flow = _flow()
    node = SimpleNamespace(name='inline_1', InlineScriptInfo="core.set_exposure(12)\nshared_data.core.snap_image()")
    flow.runInlineScriptCallAction(node)
    flow.core.set_exposure.assert_called_once_with(12)
    flow.core.snap_image.assert_called_once()
    flow.finishedEmits.assert_called_once_with(node)


def test_inline_script_error_fails_the_node_instead_of_continuing():
    flow = _flow()
    node = SimpleNamespace(name='inline_1', InlineScriptInfo="core.set_exposure(12)\n1/0\ncore.snap_image()")
    flow.runInlineScriptCallAction(node)
    flow.core.snap_image.assert_not_called()
    flow.finishedEmits.assert_not_called()
    assert 'ZeroDivisionError' in flow._nodeFailed.call_args.args[1]


def test_stage_node_without_a_chosen_stage_fails_cleanly():
    flow = _flow()
    node = SimpleNamespace(name='stage_1', MMconfigInfo=SimpleNamespace(relstage_string_storage=[]))
    flow.MMstageChangeRan(node)
    flow._nodeFailed.assert_called_once()
    flow.core.set_relative_position.assert_not_called()


def _scoring_flow(decision):
    flow = _flow()
    flow.evaluateGraph = MagicMock(return_value=[])
    flow.decisionWidget = SimpleNamespace(testCurrentDecision=decision)
    flow.set_readable_text_after_dialogChange = MagicMock(return_value='<b>Score:</b> 1')
    flow._advanceToNextPosition = MagicMock()
    flow._abortRun = MagicMock()
    flow.acquiringStart = MagicMock()
    flow._slack_send_enabled = MagicMock(return_value=True)
    return flow


def test_passing_score_with_reporting_node_does_not_raise(monkeypatch):
    sent = []
    import glados_pycromanager.notify.slack as slack
    monkeypatch.setattr(slack, 'send_slack_message', lambda cfg, text: sent.append(text))
    reporting = SimpleNamespace(name='reporting_1', status='idle')
    monkeypatch.setattr(executor.nodz_utils, 'getConnectedNodes', lambda node, attr: [reporting])
    flow = _scoring_flow(lambda: True)
    flow.shared_data.config = SimpleNamespace(webhook_config=None)

    flow.scoringEnd(SimpleNamespace(name='scoringEnd_1', attrs=[], status='running'))

    assert sent and '*Score:*' in sent[0]
    assert reporting.status == 'finished'
    flow._abortRun.assert_not_called()


def test_scoring_decision_error_stops_the_run(monkeypatch):
    monkeypatch.setattr(executor.nodz_utils, 'getConnectedNodes', lambda node, attr: [])

    def broken():
        raise KeyError('score')
    flow = _scoring_flow(broken)
    node = SimpleNamespace(name='scoringEnd_1', attrs=[], status='running')

    flow.scoringEnd(node)

    assert node.status == 'error'
    flow._abortRun.assert_called_once()
    flow._advanceToNextPosition.assert_not_called()
