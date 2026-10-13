"""L2.5 of claude_launcher_project.md: the circular buffer is allocated on the owner thread.

Allocating a 4096 MB buffer commits the memory (~1.75 s) and was the whole PyMMCorePlus
"backend up" step. ``GUI_napari._allocate_circular_buffer`` queues it as the
MicroscopeService's first job, where it overlaps the napari viewer build. What keeps
that safe is pinned here: it runs on the owner thread, it holds MIL's hardware lock (a
direct MIL call waits for it), and a request queued after it runs after it. The Python
backend starts headless with a small placeholder buffer and gets its size the same way.
"""

import inspect
import threading
import types
from unittest.mock import MagicMock

import pytest

from glados_pycromanager.Core.microscope_service import MicroscopeService
from glados_pycromanager.Core.microscopeInterfaceLayer import (
    MicroscopeInstance,
    MicroscopeInterfaceLayer,
)
from glados_pycromanager.GUI import GUI_napari


def _mil(mi=MicroscopeInstance.MMCORE_PLUS):
    m = MicroscopeInterfaceLayer()
    m.core = MagicMock()
    m._mi = mi
    return m


def test_allocation_runs_first_on_the_owner_thread_under_the_hardware_lock():
    mil = _mil()
    started, release = threading.Event(), threading.Event()
    ran_on = []

    def slow_allocation(size_mb):
        ran_on.append(threading.get_ident())
        started.set()
        release.wait(10)
    mil.core.setCircularBufferMemoryFootprint.side_effect = slow_allocation
    mil.core.getFocusDevice.return_value = 'Z'
    service = MicroscopeService(mil, name='BufferTestService').start()
    try:
        shared = types.SimpleNamespace(MILcore=mil, microscope_service=service)
        request = GUI_napari._allocate_circular_buffer(shared, 4096)
        assert started.wait(5)
        queued_after = service.submit(lambda: 'after', label='queued after')
        direct_done = threading.Event()
        threading.Thread(target=lambda: (mil.get_focus_device(), direct_done.set()),
                         daemon=True).start()
        assert not direct_done.wait(0.25), 'a direct MIL call ran during the allocation'
        assert not queued_after.done
        release.set()
        assert request.wait(5) is None
        assert queued_after.wait(5) == 'after'
        assert direct_done.wait(5)
    finally:
        release.set()
        service.stop()
    mil.core.setCircularBufferMemoryFootprint.assert_called_once_with(4096)
    assert ran_on and ran_on[0] != threading.get_ident()


def test_without_a_service_it_allocates_inline():
    mil = _mil(MicroscopeInstance.PYCROMANAGER_PYTHON)
    shared = types.SimpleNamespace(MILcore=mil, microscope_service=None)
    assert GUI_napari._allocate_circular_buffer(shared, 512) is None
    mil.core.set_circular_buffer_memory_footprint.assert_called_once_with(512)


def test_no_size_means_nothing_to_allocate():
    mil = _mil()
    shared = types.SimpleNamespace(MILcore=mil, microscope_service=None)
    assert GUI_napari._allocate_circular_buffer(shared, None) is None
    mil.core.setCircularBufferMemoryFootprint.assert_not_called()


def test_the_size_is_applied_to_a_real_core():
    pymmcore_plus = pytest.importorskip('pymmcore_plus')
    core = pymmcore_plus.CMMCorePlus()
    core.loadSystemConfiguration()  # bundled demo config
    mil = MicroscopeInterfaceLayer()
    mil.set_core(core)
    service = MicroscopeService(mil, name='RealBufferService').start()
    try:
        shared = types.SimpleNamespace(MILcore=mil, microscope_service=service)
        GUI_napari._allocate_circular_buffer(shared, 64).wait(30)
    finally:
        service.stop()
    assert core.getCircularBufferMemoryFootprint() == 64


def test_startup_queues_the_allocation_instead_of_making_it_inline():
    src = inspect.getsource(GUI_napari.main)
    assert 'setCircularBufferMemoryFootprint' not in src
    assert src.count('HEADLESS_PLACEHOLDER_BUFFER_MB if python_backend') == 2
    assert src.index('start_microscope_service()') < \
        src.index('_allocate_circular_buffer(shared_data, circular_buffer_mb)')


def test_the_gui_build_reads_hardware_only_after_the_viewer_exists():
    from glados_pycromanager.GUI import napariGlados
    src = inspect.getsource(napariGlados.runNapariPycroManager)
    read = src.index('get_focus_device()')
    assert src.index('InitateNapariUI(napariViewer)') < read < src.index('dockWidget_MMcontrol()')
