"""T-F4: the periodic warning check must not rebuild icons several times a second.

`NodeScene`'s 1 Hz timer cleared `warningErrorInfoInfo['Warnings']` and then
appended to it up to three more times. Every one of those writes went through
`Dict_Specific_WarningErrorInfo.__setitem__`, which took a **full dict copy**
into `oldValue` (a value no reader ever takes) and then drove
`updateAutonousErrorWarningInfo` -- icon-folder lookups, pixmap builds and a loop
over every node -- on the GUI thread. Forever, including during acquisition.

These tests pin the three fixes: one assignment per check, one notification per
event-loop turn, and no check at all while live mode or an MDA is running.
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
def shared_mod(qapp):
    from glados_pycromanager.GUI import sharedFunctions

    return sharedFunctions


@pytest.fixture(scope="module")
def nodz(qapp):
    import glados_pycromanager.GUI.nodz.nodz_main as nodz_main

    return nodz_main


def _drain_event_loop(qapp):
    """Let zero-delay singleShot timers fire."""
    from PyQt5.QtCore import QCoreApplication, QEventLoop

    QCoreApplication.processEvents(QEventLoop.AllEvents, 100)
    QCoreApplication.processEvents(QEventLoop.AllEvents, 100)


class _RecordingRoot:
    """Stands in for `Shared_data` as the notification target."""

    loadingOngoing = False

    def __init__(self):
        self.calls = []

    def on_warningErrorInfoInfo_changed(self, oldValue=None, errorType=None):
        self.calls.append((oldValue, errorType))


@pytest.fixture
def wei(shared_mod, qapp):
    """A warning dict whose notifications land in a recording parent.

    Construction itself writes (``_convert_nested`` reassigns every nested value
    through ``__setitem__``), so settle and discard that before handing the dict
    to a test -- otherwise every assertion counts one extra notification.
    """
    root = _RecordingRoot()
    d = shared_mod.Dict_Specific_WarningErrorInfo(
        {"Warnings": [], "Errors": []}, parent=root, errorType=None
    )
    _drain_event_loop(qapp)
    root.calls.clear()
    return d, root


# ------------------------------------------------------- no full-dict copying


def test_setitem_does_not_snapshot_the_whole_dict(wei, qapp):
    d, root = wei
    d["Warnings"] = ["a", "b"]
    _drain_event_loop(qapp)
    assert d.oldValue is None, "the oldValue full-dict copy must be gone"
    assert root.calls, "the change must still be notified"


def test_nothing_reads_old_value(wei, qapp):
    """The notification signature keeps `oldValue`, always as None."""
    d, root = wei
    d["Warnings"] = ["first"]
    d["Warnings"] = ["second"]
    _drain_event_loop(qapp)
    assert all(call[0] is None for call in root.calls)


# ------------------------------------------------------------- coalescing


def test_several_writes_in_one_turn_cause_one_rebuild(wei, qapp):
    d, root = wei
    for i in range(10):
        d["Warnings"] = ["warning {0}".format(i)]
    assert root.calls == [], "notification is deferred, not delivered inline"

    _drain_event_loop(qapp)
    assert len(root.calls) == 1, "ten writes in one turn must collapse to one rebuild"
    assert d["Warnings"] == ["warning 9"], "the final value is still the last write"


def test_a_later_turn_notifies_again(wei, qapp):
    d, root = wei
    d["Warnings"] = ["one"]
    _drain_event_loop(qapp)
    assert len(root.calls) == 1

    d["Warnings"] = ["two"]
    _drain_event_loop(qapp)
    assert len(root.calls) == 2, "coalescing must not swallow the next change"


def test_notification_is_synchronous_without_a_gui_thread(wei, monkeypatch):
    """Off the GUI thread a zero-delay QTimer would never fire, so don't defer."""
    d, root = wei
    monkeypatch.setattr(
        type(d), "_can_defer_notification", staticmethod(lambda: False)
    )
    d["Warnings"] = ["sync"]
    assert len(root.calls) == 1, "must deliver inline when it cannot defer"


def test_deferral_is_declined_when_no_application_exists(shared_mod, monkeypatch):
    import PyQt5.QtWidgets as QtWidgets

    monkeypatch.setattr(QtWidgets.QApplication, "instance", staticmethod(lambda: None))
    assert shared_mod.Dict_Specific_WarningErrorInfo._can_defer_notification() is False


# ------------------------------------------------- the periodic check itself


class _FakeWidget:
    def __init__(self, ok):
        self.ok = ok

    def assessDecision(self):
        return self.ok

    def assessScan(self):
        return self.ok


class _FakeSharedData:
    def __init__(self, liveMode=False, mdaMode=False):
        self.liveMode = liveMode
        self.mdaMode = mdaMode
        self.warningErrorInfoInfo = {}
        self.writes = []

    def record(self, value):
        self.writes.append(value)


class _RecordingWarnings(dict):
    def __init__(self, sink):
        super().__init__()
        self._sink = sink

    def __setitem__(self, key, value):
        self._sink.record((key, list(value)))
        super().__setitem__(key, value)


class _FakeParent:
    def __init__(self, shared_data, widgets_ok=True):
        self.shared_data = shared_data
        self.decisionWidget = _FakeWidget(widgets_ok)
        self.scanningWidget = _FakeWidget(widgets_ok)


@pytest.fixture
def scene(nodz):
    """A bare object carrying NodeScene's warning-check methods."""

    def _make(nodes, liveMode=False, mdaMode=False, widgets_ok=True):
        obj = type("FakeScene", (), {})()
        obj.nodes = nodes
        shared = _FakeSharedData(liveMode=liveMode, mdaMode=mdaMode)
        shared.warningErrorInfoInfo = _RecordingWarnings(shared)
        parent = _FakeParent(shared, widgets_ok=widgets_ok)
        obj.parent = lambda: parent
        for name in ("_acquisitionOngoing", "collectWarnings", "regular_callAction"):
            setattr(obj, name, getattr(nodz.NodeScene, name).__get__(obj))
        return obj, shared

    return _make


_COMPLETE_GRAPH = [
    "initStart_1", "initEnd_1", "scoringStart_1",
    "scoringEnd_1", "acqStart_1", "acqEnd_1",
]


def test_warnings_are_written_exactly_once_per_check(scene):
    obj, shared = scene(nodes=[])
    obj.regular_callAction()
    assert len(shared.writes) == 1, "the clear-then-append pattern must be gone"
    assert shared.writes[0][0] == "Warnings"


def test_warning_content_is_unchanged(scene):
    """All three warnings still appear, with their original wording."""
    obj, shared = scene(nodes=[], widgets_ok=False)
    warnings = obj.collectWarnings()
    assert any(w.startswith("Missing the following required nodes: ") for w in warnings)
    assert "Decision widget is missing information." in warnings
    assert "Scanning widget is missing information." in warnings


def test_a_complete_graph_reports_no_missing_nodes(scene):
    obj, shared = scene(nodes=_COMPLETE_GRAPH, widgets_ok=True)
    assert obj.collectWarnings() == []


def test_missing_node_warning_lists_only_what_is_absent(scene):
    obj, _ = scene(nodes=[n for n in _COMPLETE_GRAPH if "acqEnd" not in n])
    warnings = obj.collectWarnings()
    assert len(warnings) == 1
    assert "acqEnd" in warnings[0]
    assert "initStart" not in warnings[0]


@pytest.mark.parametrize("live,mda", [(True, False), (False, True), (True, True)])
def test_check_is_skipped_during_acquisition(scene, live, mda):
    obj, shared = scene(nodes=[], liveMode=live, mdaMode=mda)
    obj.regular_callAction()
    assert shared.writes == [], "no GUI-thread rebuild while frames are flowing"


def test_check_resumes_once_acquisition_stops(scene):
    obj, shared = scene(nodes=[], liveMode=True)
    obj.regular_callAction()
    assert shared.writes == []

    obj.parent().shared_data.liveMode = False
    obj.regular_callAction()
    assert len(shared.writes) == 1, "the next tick after acquisition must update"


def test_missing_shared_data_is_not_an_acquisition(nodz):
    obj = type("FakeScene", (), {})()
    obj.parent = lambda: type("P", (), {})()
    assert nodz.NodeScene._acquisitionOngoing(obj) is False
