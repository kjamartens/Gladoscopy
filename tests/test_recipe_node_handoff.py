"""Node-to-node hand-off goes through the event loop (recipe lag, item 10).

finishedEmits used to emit the downstream signal inline, so the next node's
callAction ran nested inside the previous one: a chain of synchronous nodes -
and the whole position loop - was one ever-growing stack the GUI never
returned from.
"""
from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from glados_pycromanager.GUI.FlowChart_dockWidgets import (
    GladosNodzFlowChart_dockWidget, NodeSignalManager)


@pytest.fixture(scope="module")
def qapp():
    # Same as test_logger_widget_tail: a windowed QApplication next to the
    # QtWebEngine this module imports crashes natively at interpreter exit.
    import os
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from PyQt5.QtCore import QCoreApplication, Qt
    from PyQt5.QtWidgets import QApplication
    QCoreApplication.setAttribute(Qt.AA_ShareOpenGLContexts, True)
    yield QApplication.instance() or QApplication([])


def _flow():
    flow = SimpleNamespace(updateCoreVariables=MagicMock(), update=MagicMock(),
                           shared_data=SimpleNamespace(warningErrorInfoInfo={'Info': {'LastNodeRan': None}}))
    flow._emitNodeFinished = lambda node: GladosNodzFlowChart_dockWidget._emitNodeFinished(flow, node)
    return flow


def _node(name):
    signals = NodeSignalManager()
    signals.add_signal('Finished')
    return SimpleNamespace(name=name, status='running', customFinishedEmits=signals, customDataEmits=None)


def test_downstream_starts_from_the_event_loop_not_inline(qapp):
    flow = _flow()
    node = _node('timer_1')
    started = []
    node.customFinishedEmits.signals[0].connect(lambda: started.append(True))

    GladosNodzFlowChart_dockWidget.finishedEmits(flow, node)

    assert node.status == 'finished'
    assert started == []          # not inline
    qapp.processEvents()
    assert started == [True]


def test_long_synchronous_chain_keeps_a_flat_stack(qapp):
    # Inline, every node added its frames on top of the previous one's; with
    # the deferral the stack depth at each node start is the same.
    flow = _flow()
    depths = []
    nodes = [_node(f'n{i}') for i in range(300)]
    for i, node in enumerate(nodes[:-1]):
        nxt = nodes[i + 1]
        def start_next(nxt=nxt):
            depths.append(len(__import__('inspect').stack(0)))
            GladosNodzFlowChart_dockWidget.finishedEmits(flow, nxt)
        node.customFinishedEmits.signals[0].connect(start_next)

    GladosNodzFlowChart_dockWidget.finishedEmits(flow, nodes[0])
    for _ in range(1000):
        qapp.processEvents()
        if nodes[-1].status == 'finished':
            break

    assert nodes[-1].status == 'finished'
    assert max(depths) - min(depths) < 5
    for node in nodes:
        node.customFinishedEmits.deleteLater()
    qapp.processEvents()


def test_node_with_several_finished_plugs_emits_once(qapp):
    signals = NodeSignalManager()
    signals.add_signal('Succeed')
    signals.add_signal('Fail')
    calls = []
    signals.signals[0].connect(lambda: calls.append(1))
    signals.emit_all_signals()
    assert calls == [1]


def test_node_text_failure_does_not_stop_the_chain(qapp):
    flow = _flow()
    flow.set_readable_text_after_dialogChange = MagicMock(side_effect=KeyError('wait_time'))
    node = _node('timer_1')
    node.dialogInfo = object()
    started = []
    node.customFinishedEmits.signals[0].connect(lambda: started.append(True))

    GladosNodzFlowChart_dockWidget.finishedEmits(flow, node)
    qapp.processEvents()

    assert started == [True]
