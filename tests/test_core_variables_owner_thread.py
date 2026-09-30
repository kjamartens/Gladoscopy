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
