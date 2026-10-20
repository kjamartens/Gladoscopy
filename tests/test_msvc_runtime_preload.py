"""The package preloads System32's C++ runtime before PyQt5 loads its older copy.

PyQt5 bundles msvcp140.dll 14.26. Once Qt has loaded it, Micro-Manager device
adapters built with VS 2022 17.10+ bind to it by name and crash with an access
violation in initializeDevice (see glados_pycromanager/_msvc_runtime.py).
"""

import json
import os
import subprocess
import sys

import pytest

pytestmark = pytest.mark.skipif(sys.platform != 'win32', reason='Windows DLL loading')


def _run(code: str) -> subprocess.CompletedProcess:
    env = dict(os.environ, QT_QPA_PLATFORM='offscreen')
    return subprocess.run([sys.executable, '-c', code], capture_output=True, text=True,
                          timeout=180, check=False, env=env)


_LOADED_RUNTIMES = """
import json, psutil
def loaded(name):
    return sorted({m.path for m in psutil.Process().memory_maps()
                   if m.path.lower().endswith('\\\\' + name)})
"""


def test_qt_shares_the_preloaded_system_runtime():
    result = _run(_LOADED_RUNTIMES + """
import glados_pycromanager
from glados_pycromanager._msvc_runtime import preload_system_msvc_runtime
preloaded = preload_system_msvc_runtime()
import PyQt5.QtWidgets
print(json.dumps({'preloaded': preloaded, 'msvcp140': loaded('msvcp140.dll')}))
""")
    assert result.returncode == 0, result.stderr[-2000:]
    out = json.loads(result.stdout.strip().splitlines()[-1])
    system_copy = [p for p in out['preloaded'] if p.lower().endswith('\\msvcp140.dll')]
    if not system_copy:
        pytest.skip('System32 msvcp140.dll is missing or older than PyQt5\'s')
    # Exactly one plain msvcp140.dll in the process, and it is System32's, not Qt's.
    assert [p.lower() for p in out['msvcp140']] == [system_copy[0].lower()]


def test_preload_is_a_no_op_once_qt_is_loaded():
    result = _run("""
import json, PyQt5.QtCore
from glados_pycromanager._msvc_runtime import preload_system_msvc_runtime
print(json.dumps(preload_system_msvc_runtime()))
""")
    # PyQt5 came first, so the package __init__'s own call found Qt loaded too.
    assert result.returncode == 0, result.stderr[-2000:]
    assert json.loads(result.stdout.strip().splitlines()[-1]) == []


def test_demo_camera_initialises_with_qt_loaded():
    """The real regression: DemoCamera crashed in initializeDevice with Qt loaded."""
    try:
        from pymmcore_plus import find_micromanager
        mm_path = find_micromanager()
    except Exception:
        mm_path = None
    if not mm_path or not os.path.isfile(os.path.join(mm_path, 'mmgr_dal_DemoCamera.dll')):
        pytest.skip('no Micro-Manager install with the DemoCamera adapter')
    result = _run(f"""
import glados_pycromanager
from PyQt5.QtWidgets import QApplication
app = QApplication([])
import pymmcore
core = pymmcore.CMMCore()
core.setDeviceAdapterSearchPaths([{mm_path!r}])
core.loadDevice('Camera', 'DemoCamera', 'DCam')
core.initializeDevice('Camera')
print('ok')
""")
    assert result.returncode == 0, f'exit {result.returncode}: {result.stderr[-2000:]}'
    assert result.stdout.strip().endswith('ok')
