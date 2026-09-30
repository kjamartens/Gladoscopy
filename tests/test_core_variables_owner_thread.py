"""`updateCoreVariables` collects its snapshot off the GUI thread (T-B4).

The nodz flowchart keeps a dict of "core variables" -- stage positions, config
group values, pixel size, ROI. Refreshing it is one hardware read per stage plus
one `ConfigInfo` per config group, and it runs on **every node finish** in a
recipe, on the GUI thread. On the Java backend that is tens of ~257 ms bridge
round trips in the middle of a running acquisition.

It now collects on the `MicroscopeService` owner thread and swaps the finished
dict in with one assignment. Asserted here without constructing a real
`NodzFlowChart` (that needs a full Qt widget tree): the two methods are bound to
a bare object, which is enough to pin the dispatch, the atomic swap and the
inline fallback.
"""
from __future__ import annotations

import threading

import pytest

from glados_pycromanager.Core.microscope_service import MicroscopeService
from glados_pycromanager.GUI.FlowChart_dockWidgets import (
    GladosNodzFlowChart_dockWidget as NodzFlowChart,
)


class _Host:
    """Just enough of a GladosNodzFlowChart_dockWidget to run the methods."""

    updateCoreVariables = NodzFlowChart.updateCoreVariables
    _refreshCoreVariables = NodzFlowChart._refreshCoreVariables
    createSingleCoreVar = NodzFlowChart.createSingleCoreVar

    def __init__(self, shared_data, collected=None):
        self.shared_data = shared_data
        self.coreVariables = {}
        self.collect_threads = []
        self._collected = collected if collected is not None else {'Pixel_size_um': {}}

    def _collectCoreVariables(self):
        self.collect_threads.append(threading.get_ident())
        return dict(self._collected)


class _SharedData:
    def __init__(self, service=None):
        self.microscope_service = service


def test_collects_inline_without_a_service():
    host = _Host(_SharedData())

    host.updateCoreVariables()

    assert host.collect_threads == [threading.get_ident()]
    assert 'Pixel_size_um' in host.coreVariables


def test_collects_on_the_owner_thread_when_a_service_runs():
    service = MicroscopeService(object(), name='CoreVarsTestService').start()
    host = _Host(_SharedData(service))
    owner = service._owner_ident
    try:
        host.updateCoreVariables()
        service.submit(lambda: None, label='barrier').wait(5.0)
    finally:
        service.stop()

    assert host.collect_threads == [owner]
    assert threading.get_ident() not in host.collect_threads
    assert 'Pixel_size_um' in host.coreVariables


def test_the_snapshot_is_swapped_in_atomically():
    """A reader must never see a half-filled dict."""
    service = MicroscopeService(object(), name='CoreVarsSwapService').start()
    host = _Host(_SharedData(service), collected={'a': {}, 'b': {}, 'c': {}})
    previous = host.coreVariables
    try:
        host.updateCoreVariables()
        service.submit(lambda: None, label='barrier').wait(5.0)
    finally:
        service.stop()

    assert host.coreVariables is not previous
    assert set(host.coreVariables) == {'a', 'b', 'c'}


def test_create_single_core_var_defaults_to_the_live_dict():
    host = _Host(_SharedData())

    host.createSingleCoreVar('x', 5, [int])
    target = {}
    host.createSingleCoreVar('y', 6, [int], target=target)

    assert host.coreVariables['x'] == {'type': [int], 'data': 5,
                                       'importance': 'Informative'}
    assert 'y' not in host.coreVariables
    assert target['y']['data'] == 6


@pytest.mark.parametrize('service', [None, 'stopped'])
def test_a_stopped_service_falls_back_to_inline(service):
    if service == 'stopped':
        service = MicroscopeService(object(), name='CoreVarsStoppedService')
    host = _Host(_SharedData(service))

    host.updateCoreVariables()

    assert host.collect_threads == [threading.get_ident()]


def test_requests_while_a_snapshot_is_queued_are_coalesced():
    # Every node start and finish asks for a snapshot; a burst of them must
    # not queue a full hardware read each.
    service = MicroscopeService(object(), name='CoreVarsCoalesceService').start()
    host = _Host(_SharedData(service))
    gate = threading.Event()
    try:
        service.submit(gate.wait, 5.0, label='hold the owner thread')
        for _ in range(10):
            host.updateCoreVariables()
        gate.set()
        service.submit(lambda: None, label='barrier').wait(5.0)
    finally:
        service.stop()
    assert len(host.collect_threads) == 1


def test_a_request_after_the_snapshot_started_gets_a_new_one():
    service = MicroscopeService(object(), name='CoreVarsRequeueService').start()
    host = _Host(_SharedData(service))
    try:
        host.updateCoreVariables()
        service.submit(lambda: None, label='barrier').wait(5.0)
        host.updateCoreVariables()
        service.submit(lambda: None, label='barrier').wait(5.0)
    finally:
        service.stop()
    assert len(host.collect_threads) == 2


def test_variable_display_text_is_cheap_for_big_values():
    import numpy as np
    from glados_pycromanager.GUI.FlowChart_dockWidgets import variableDisplayText
    assert variableDisplayText(np.zeros((100, 512, 512), np.uint16)) == 'ndarray (100, 512, 512) uint16'
    assert variableDisplayText(list(range(1000))) == 'list[1000]'
    assert variableDisplayText('x' * 500).endswith('…')
    assert len(variableDisplayText('x' * 500)) == 201
    assert variableDisplayText([1.5, 2.0]) == '[1.5, 2.0]'
    assert variableDisplayText(np.float64(3.0)) == '3.0'


def test_variables_table_does_not_write_into_live_variable_dicts(monkeypatch):
    from types import SimpleNamespace
    from unittest.mock import MagicMock
    import glados_pycromanager.GUI.FlowChart_dockWidgets as F
    monkeypatch.setattr(F, 'QTableWidgetItem', lambda text: text)
    live = {'data': 1, 'type': [int], 'importance': 'Informative'}
    node = SimpleNamespace(name='analysis_1', variablesNodz={'score': live})
    nodz = SimpleNamespace(updateCoreVariables=MagicMock(), globalVariables={}, coreVariables={},
                           obtainAllNodes=lambda: [node])
    table = MagicMock()
    widget = SimpleNamespace(nodzinstance=nodz, typeInfo=None, variablesTableWidget=table)
    widget._acceptsType = lambda types: F.VariablesBase._acceptsType(widget, types)

    F.VariablesBase.updateVariables(widget)

    assert set(live) == {'data', 'type', 'importance'}
    table.setRowCount.assert_called_once_with(1)
    table.setItem.assert_any_call(0, 1, 'analysis_1')
    table.setItem.assert_any_call(0, 2, 'score')
