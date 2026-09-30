"""T-F5: the graph error check must not be quadratic, and not run per mouse-move.

`checkNodesOnErrors` assigned `node.errorInfo` inside a loop over all nodes, and
the `errorInfo` **setter** calls `updateAutonousErrorWarningInfo` -- the full
icon-rebuild chain, which itself loops over every node. Inside the same loop it
also called `evaluateGraph()`, which walks every item in the QGraphicsScene. It
was wired to eight graph signals including `signal_NodeMoved`, so dragging a node
re-ran that quadratic sweep, with disk I/O, on every mouse-move event.

These tests pin: one `evaluateGraph()` per check, one icon refresh per check
(regardless of node count), the error text still being computed correctly, and
the signal path being debounced while direct callers stay immediate.
"""
from __future__ import annotations

import os

import pytest

pytest.importorskip("PyQt5.QtWidgets")


@pytest.fixture(scope="module")
def qapp():
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from PyQt5.QtCore import QCoreApplication, Qt
    from PyQt5.QtWidgets import QApplication

    QCoreApplication.setAttribute(Qt.AA_ShareOpenGLContexts, True)
    return QApplication.instance() or QApplication([])


@pytest.fixture(scope="module")
def flowchart_mod(qapp):
    from glados_pycromanager.GUI import FlowChart_dockWidgets

    return FlowChart_dockWidgets


@pytest.fixture(scope="module")
def widget_cls(flowchart_mod):
    return flowchart_mod.GladosNodzFlowChart_dockWidget


class _FakeNode:
    """A node whose `errorInfo` setter is as expensive as the real one."""

    def __init__(self, name, sockets, refresh_sink):
        self.name = name
        self.sockets = sockets
        self._errorInfo = ""
        self._refresh_sink = refresh_sink

    @property
    def errorInfo(self):
        return self._errorInfo

    @errorInfo.setter
    def errorInfo(self, value):
        self._errorInfo = value
        # The real setter calls updateAutonousErrorWarningInfo here.
        self._refresh_sink.append(("setter", self.name))


class _FakeSharedData:
    loadingOngoing = False


@pytest.fixture
def checker(widget_cls, monkeypatch, flowchart_mod):
    """A bare object carrying the real check methods over fake graph state."""

    def _make(node_specs, connections=(), loadingOngoing=False):
        refreshes = []
        obj = type("FakeChart", (), {})()
        obj.ERROR_CHECK_DEBOUNCE_MS = widget_cls.ERROR_CHECK_DEBOUNCE_MS
        obj.shared_data = _FakeSharedData()
        obj.shared_data.loadingOngoing = loadingOngoing
        obj.nodes = [_FakeNode(n, s, refreshes) for n, s in node_specs]
        obj.cleanupNodeList = lambda: None

        evaluations = []

        def _evaluateGraph():
            evaluations.append(1)
            return list(connections)

        obj.evaluateGraph = _evaluateGraph
        obj.checkNodesOnErrors = widget_cls.checkNodesOnErrors.__get__(obj)
        obj.scheduleCheckNodesOnErrors = (
            widget_cls.scheduleCheckNodesOnErrors.__get__(obj)
        )

        monkeypatch.setattr(
            flowchart_mod.utils,
            "updateAutonousErrorWarningInfo",
            lambda *a, **kw: refreshes.append(("batch", None)),
        )
        return obj, evaluations, refreshes

    return _make


def _specs(n, sockets=True):
    return [("node%d" % i, {"in": object()} if sockets else {}) for i in range(n)]


# ------------------------------------------------------- hoisted evaluateGraph


@pytest.mark.parametrize("n_nodes", [1, 5, 25])
def test_graph_is_evaluated_once_per_check(checker, n_nodes):
    obj, evaluations, _ = checker(_specs(n_nodes))
    obj.checkNodesOnErrors()
    assert len(evaluations) == 1, "evaluateGraph walks the whole scene; hoist it"


# ------------------------------------------------------ batched icon refresh


@pytest.mark.parametrize("n_nodes", [1, 5, 25])
def test_icons_are_refreshed_once_per_check(checker, n_nodes):
    obj, _, refreshes = checker(_specs(n_nodes))
    obj.checkNodesOnErrors()
    assert refreshes == [("batch", None)], (
        "the per-node errorInfo setter must be bypassed; one refresh after the loop"
    )


def test_refresh_cost_does_not_grow_with_node_count(checker):
    small, _, small_refreshes = checker(_specs(2))
    small.checkNodesOnErrors()
    small_count = len(small_refreshes)

    large, _, large_refreshes = checker(_specs(40))
    large.checkNodesOnErrors()

    assert small_count == len(large_refreshes) == 1


# --------------------------------------------------------- unchanged results


def test_unconnected_node_with_sockets_is_flagged(checker):
    obj, _, _ = checker(_specs(3))
    obj.checkNodesOnErrors()
    assert all(n.errorInfo == "No downstream connections found." for n in obj.nodes)


def test_node_without_sockets_is_not_flagged(checker):
    obj, _, _ = checker(_specs(3, sockets=False))
    obj.checkNodesOnErrors()
    assert all(n.errorInfo == "" for n in obj.nodes)


def test_a_connected_node_is_cleared(checker):
    """`findConnectedToNode(downstream=True)` matches the node in connection[1]."""
    obj, _, _ = checker(
        [("a", {"in": 1}), ("b", {"in": 1})],
        connections=[("a.out", "b.in")],
    )
    obj.checkNodesOnErrors()
    by_name = {n.name: n.errorInfo for n in obj.nodes}
    assert by_name["b"] == "", "b is the destination of a connection"
    assert by_name["a"] == "No downstream connections found."


def test_stale_error_is_cleared_on_recheck(checker):
    obj, _, _ = checker([("a", {"in": 1}), ("b", {"in": 1})])
    obj.checkNodesOnErrors()
    b = next(n for n in obj.nodes if n.name == "b")
    assert b.errorInfo != ""

    obj.evaluateGraph = lambda: [("a.out", "b.in")]
    obj.checkNodesOnErrors()
    assert b.errorInfo == "", "each pass must reset before re-deciding"


def test_check_is_skipped_while_loading(checker):
    obj, evaluations, refreshes = checker(_specs(3), loadingOngoing=True)
    obj.checkNodesOnErrors()
    assert evaluations == [] and refreshes == []


# ------------------------------------------------------------- the debounce


def test_signals_are_wired_to_the_debounced_slot(widget_cls):
    import inspect

    source = inspect.getsource(widget_cls.__init__)
    for signal in (
        "signal_NodeMoved",
        "signal_NodeEdited",
        "signal_PlugConnectedStartConnection",
        "signal_SocketConnectedStartConnection",
        "signal_AttrEdited",
        "signal_NodeFullyInitialisedNodeItself",
        "signal_PlugDisconnected",
        "signal_SocketDisconnected",
    ):
        assert (
            "%s.connect(self.scheduleCheckNodesOnErrors)" % signal in source
        ), "%s must go through the coalescing timer" % signal


def test_schedule_restarts_one_timer_instead_of_checking(checker, qapp):
    from PyQt5.QtCore import QTimer

    obj, evaluations, _ = checker(_specs(3))
    timer = QTimer()
    timer.setSingleShot(True)
    timer.timeout.connect(obj.checkNodesOnErrors)
    obj._errorCheckTimer = timer

    # A drag: many signal emissions in quick succession.
    for _ in range(50):
        obj.scheduleCheckNodesOnErrors("node0", object())
    assert evaluations == [], "a drag in progress must not run the sweep"
    assert timer.isActive()

    timer.stop()


def test_schedule_accepts_every_signal_signature(checker):
    """The eight signals carry three different payload shapes."""
    obj, _, _ = checker(_specs(1))
    obj._errorCheckTimer = None  # forces the immediate fallback path
    obj.scheduleCheckNodesOnErrors()
    obj.scheduleCheckNodesOnErrors("name", object())
    obj.scheduleCheckNodesOnErrors(object())


def test_schedule_without_a_timer_checks_immediately(checker):
    """Before __init__ builds the timer, the old synchronous behaviour stands."""
    obj, evaluations, _ = checker(_specs(2))
    obj.scheduleCheckNodesOnErrors()
    assert len(evaluations) == 1


def test_direct_callers_are_not_debounced(checker):
    """Six call sites call checkNodesOnErrors() directly and expect it to run."""
    obj, evaluations, _ = checker(_specs(2))
    obj._errorCheckTimer = object()  # would swallow a scheduled call
    obj.checkNodesOnErrors()
    assert len(evaluations) == 1
