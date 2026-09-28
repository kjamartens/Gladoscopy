"""An MDA that fails or is refused must still report "done" (recipe robustness).

``run_MILCoreAcquisition_worker`` used to call ``parent.mdaacqdonefunction()``
only on the happy path, so an acquisition that raised left a recipe's
acquisition node 'running' forever and ``mdaMode`` stuck on. The worker's
``finally`` now calls ``_report_failed_mda``, which emits
``mda_acq_done_signal(False)``; ``MDAGlados.MDA_acq_finished(False)`` then marks
the node as errored instead of triggering its downstream graph.
"""
from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock

from glados_pycromanager.Core.MDAGlados import MDAGlados
from glados_pycromanager.GUI.napariGlados import napariHandler


def test_report_failed_mda_resets_mode_and_reports_false():
    handler = SimpleNamespace(acqstate=True, shared_data=SimpleNamespace(
        MILcore=MagicMock(), mdaMode=True))
    parent = MagicMock()

    napariHandler._report_failed_mda(handler, parent)

    assert handler.acqstate is False
    assert handler.shared_data.mdaMode is False
    handler.shared_data.MILcore.stop_sequence_acquisition.assert_called_once()
    parent.mdaacqdonefunction.assert_called_once_with(success=False)


def test_report_failed_mda_still_reports_when_stop_raises():
    mil = MagicMock()
    mil.stop_sequence_acquisition.side_effect = RuntimeError('bridge gone')
    handler = SimpleNamespace(acqstate=True, shared_data=SimpleNamespace(MILcore=mil, mdaMode=True))
    parent = MagicMock()

    napariHandler._report_failed_mda(handler, parent)

    parent.mdaacqdonefunction.assert_called_once_with(success=False)


def _mda_stub(node):
    stub = SimpleNamespace(
        shared_data=SimpleNamespace(mda_acq_done_signal=MagicMock(), _mdaMode=True),
        resetMDAbutton=MagicMock(),
        MDA_completed=MagicMock(),
        _resolve_finished_acquisition_data=MagicMock(),
        nodeInfo=node,
    )
    stub.MDA_acq_finished = MDAGlados.MDA_acq_finished.__get__(stub)
    stub._MDA_acq_failed = MDAGlados._MDA_acq_failed.__get__(stub)
    return stub


def test_failed_mda_marks_node_error_and_does_not_continue_recipe():
    flowChart = MagicMock()
    node = SimpleNamespace(name='acquisition_1', status='running', flowChart=flowChart)
    stub = _mda_stub(node)

    stub.MDA_acq_finished(False)

    flowChart._nodeFailed.assert_called_once()
    assert flowChart._nodeFailed.call_args.args[0] is node
    stub.MDA_completed.emit.assert_not_called()
    stub._resolve_finished_acquisition_data.assert_not_called()
    assert stub.shared_data._mdaMode is False
    stub.resetMDAbutton.assert_called_once()


def test_failed_gui_mda_without_node_just_resets():
    stub = _mda_stub(None)
    stub.MDA_acq_finished(False)
    stub.resetMDAbutton.assert_called_once()
    stub.MDA_completed.emit.assert_not_called()


def test_disconnect_of_already_disconnected_slot_is_tolerated():
    stub = _mda_stub(None)
    stub.shared_data.mda_acq_done_signal.disconnect.side_effect = TypeError('not connected')
    stub.MDA_acq_finished(False)  # must not raise
    stub.resetMDAbutton.assert_called_once()


# --- one listener at a time -------------------------------------------------

from PyQt5.QtCore import QObject, pyqtSignal

from glados_pycromanager.Core.MDAGlados import claim_mda_done_signal


class _Shared(QObject):
    mda_acq_done_signal = pyqtSignal(bool)


class _Listener(QObject):
    def __init__(self):
        super().__init__()
        self.calls = []

    def done(self, success=True):
        self.calls.append(success)


def test_claim_drops_a_stale_listener_from_another_instance():
    shared = _Shared()
    stale, fresh = _Listener(), _Listener()
    claim_mda_done_signal(shared, stale.done)   # its MDA never reported
    claim_mda_done_signal(shared, fresh.done)

    shared.mda_acq_done_signal.emit(True)

    assert stale.calls == []
    assert fresh.calls == [True]


def test_claim_tolerates_a_listener_that_disconnected_itself():
    shared = _Shared()
    first, second = _Listener(), _Listener()
    claim_mda_done_signal(shared, first.done)
    shared.mda_acq_done_signal.disconnect(first.done)
    claim_mda_done_signal(shared, second.done)

    shared.mda_acq_done_signal.emit(False)

    assert second.calls == [False]


def test_node_acquisition_refused_while_an_mda_is_running():
    flowChart = MagicMock()
    node = SimpleNamespace(name='acquisition_2', status='running', flowChart=flowChart)
    stub = SimpleNamespace(shared_data=SimpleNamespace(mdaMode=True),
                           flushMDAEventsUpdate=MagicMock(), flushMDAStateSave=MagicMock(),
                           core=MagicMock())

    MDAGlados.MDA_acq_from_Node(stub, node)

    flowChart._nodeFailed.assert_called_once()
    stub.core.set_exposure.assert_not_called()
