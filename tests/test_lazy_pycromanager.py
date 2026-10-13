"""L2.3 of claude_launcher_project.md: pycromanager, ndtiff and dask load on first use.

A PyMMCorePlus session used to import pycromanager at startup (MIL, napariGlados,
MDAGlados), which costs ~2.7 s: ndstorage -> dask.array -> xarray -> pandas. Node
metadata names ``ndtiff.NDTiffDataset`` as a port type and plugin discovery reads that
metadata at startup, so ``lazy_imports`` gives it a tag that stands in for the class
without importing ndtiff. The startup-wide check is
``test_node_packages_import_light.py::test_startup_modules_do_not_import_pycromanager_or_dask``.
"""

import inspect
import json
import os
import pickle
import subprocess
import sys

import pytest

from glados_pycromanager import lazy_imports


def _run(code: str) -> dict:
    result = subprocess.run([sys.executable, '-c', code], capture_output=True, text=True,
                            timeout=180, check=False)
    assert result.returncode == 0, result.stderr[-2000:]
    return json.loads(result.stdout.strip().splitlines()[-1])


# -- the ndtiff type tag ------------------------------------------------------------
def test_tag_works_as_a_type_without_importing_ndtiff():
    out = _run("""
import json, pickle, sys
from glados_pycromanager.lazy_imports import ndtiff
tag = ndtiff.NDTiffDataset
types = [tag, list]
print(json.dumps({
    'same_object': ndtiff.NDTiffDataset is tag,
    'is_type': isinstance(tag, type),
    'in_list': tag in types,
    'list_not_in': dict not in types,
    'repr': repr(tag),
    'isinstance_other': isinstance(object(), tag),
    'pickle': pickle.loads(pickle.dumps(tag)) is tag,
    'ndtiff_imported': 'ndtiff' in sys.modules,
    'dask_imported': 'dask.array' in sys.modules,
}))
""")
    assert out == {'same_object': True, 'is_type': True, 'in_list': True, 'list_not_in': True,
                   'repr': "<class 'ndtiff.NDTiffDataset'>", 'isinstance_other': False,
                   'pickle': True, 'ndtiff_imported': False, 'dask_imported': False}


def test_tag_equals_the_real_class_once_ndtiff_is_loaded():
    real = pytest.importorskip('ndtiff').NDTiffDataset
    tag = lazy_imports.ndtiff.NDTiffDataset
    assert tag == real and real == tag
    assert real in [tag] and tag in [real]  # the node-port check in FlowChart_dockWidgets
    assert issubclass(real, tag)
    assert not isinstance(object(), tag)
    assert tag.as_array is real.as_array  # any other attribute forwards to the class
    assert lazy_imports.ndtiff.NDTiffDataset is tag
    assert pickle.loads(pickle.dumps(tag)) is tag


def test_calling_the_tag_constructs_the_real_class(monkeypatch):
    ndtiff = pytest.importorskip('ndtiff')
    calls = []

    class Fake:
        def __init__(self, *args, **kwargs):
            calls.append((args, kwargs))
    monkeypatch.setattr(ndtiff, 'NDTiffDataset', Fake)
    made = lazy_imports.ndtiff.NDTiffDataset('some/dir', writable=True)
    assert isinstance(made, Fake) and calls == [(('some/dir',), {'writable': True})]


def test_other_attributes_import_the_module():
    ndtiff = pytest.importorskip('ndtiff')
    assert lazy_imports.ndtiff.NDRAMDataset is ndtiff.NDRAMDataset
    with pytest.raises(AttributeError):
        lazy_imports.ndtiff.something = 1


# -- backend detection --------------------------------------------------------------
def test_mil_detects_pymmcore_without_importing_pycromanager():
    out = _run("""
import json, sys
import pymmcore
import glados_pycromanager.Core.microscopeInterfaceLayer as MIL
mil = MIL.MicroscopeInterfaceLayer()
mil.set_core(pymmcore.CMMCore())
before = 'pycromanager' in sys.modules
import pycromanager
lazy_name_works = MIL.PycroManagerCore is pycromanager.Core
print(json.dumps({'mi': mil.MI().name, 'pycromanager_before': before,
                  'lazy_name_works': lazy_name_works}))
""")
    assert out == {'mi': 'PYCROMANAGER_PYTHON', 'pycromanager_before': False,
                   'lazy_name_works': True}


def test_mil_still_detects_a_pycromanager_core_once_imported():
    import glados_pycromanager.Core.microscopeInterfaceLayer as MIL
    from pycromanager import Core
    core = object.__new__(Core)  # no bridge; detection is an isinstance check
    assert MIL.MicroscopeInterfaceLayer._detect_microscope_instance(core) is \
        MIL.MicroscopeInstance.PYCROMANAGER_JAVA


# -- MDAGlados' initial plan --------------------------------------------------------
@pytest.fixture(scope='module')
def mda_cls():
    os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
    from glados_pycromanager.Core.MDAGlados import MDAGlados
    return MDAGlados


@pytest.fixture
def host(mda_cls):
    return type('Host', (), {'mda': mda_cls.mda,
                             '_mdaEventsForAcquisition': mda_cls._mdaEventsForAcquisition})()


def test_initial_plan_is_built_on_first_read(host):
    host._mda = None
    host._pendingInitialMDAKwargs = dict(num_time_points=3, time_interval_s=0)
    events = host.mda
    assert len(events) == 3 and host._pendingInitialMDAKwargs is None
    assert host.mda is events  # cached


def test_acquisition_gets_the_initial_plan(host):
    host._mda = None
    host._pendingInitialMDAKwargs = dict(num_time_points=2, time_interval_s=0)
    assert len(host._mdaEventsForAcquisition()) == 2


def test_assigning_a_plan_drops_the_pending_initial_one(host):
    host._mda = None
    host._pendingInitialMDAKwargs = dict(num_time_points=3, time_interval_s=0)
    host.mda = ['explicit']
    assert host.mda == ['explicit'] and host._pendingInitialMDAKwargs is None


def test_constructor_defers_and_rebuild_discards_the_initial_plan(mda_cls):
    init_src = inspect.getsource(mda_cls.__init__)
    assert 'multi_d_acquisition_events(' not in init_src
    assert '_pendingInitialMDAKwargs = copy.deepcopy(' in init_src
    rebuild_src = inspect.getsource(mda_cls.get_MDA_events_from_GUI)
    assert 'self._pendingInitialMDAKwargs = None' in rebuild_src


def test_pending_plan_is_never_persisted():
    from pathlib import Path
    root = Path(__file__).resolve().parents[1] / 'glados_pycromanager'
    assert "'_pendingInitialMDAKwargs'" in (root / 'GUI' / 'utils.py').read_text(encoding='utf-8')
    assert "'_pendingInitialMDAKwargs'" in (root / 'GUI' / 'nodz' / 'nodz_main.py').read_text(encoding='utf-8')
