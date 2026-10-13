"""Importing the node packages must not pull in heavy libraries (lazy-import-strategy.md).

The Controls dock imports every node module while it discovers RT nodes, on the GUI
thread, during startup. On 2026-10-13 that was 6.5-7.7 s of a ~23 s warm start, almost
all of it BioImageModelZoo's import-time bioimageio patches (bioimageio.spec/.core,
torch) and module-scope ``from scipy import signal`` (scipy.signal + scipy.stats, ~1 s).
Runs in a fresh interpreter so other tests' imports cannot hide a regression.
"""

import json
import subprocess
import sys

HEAVY = ['torch', 'torchvision', 'bioimageio.spec', 'bioimageio.core', 'tensorflow',
         'keras', 'csbdeep', 'stardist', 'cv2', 'diplib', 'segment_anything',
         'mobile_sam', 'timm', 'scipy.signal', 'scipy.stats',
         # L2.3: dask.array (+ xarray, pandas) is ~1 s; ndtiff and pycromanager pull it in.
         'dask.array', 'xarray', 'pandas', 'ndtiff', 'ndstorage', 'pycromanager']

_PROBE = f"""
import json, sys
import glados_pycromanager.GUI.utils  # already loaded in the app before node discovery
before = set(sys.modules)
import glados_pycromanager.AutonomousMicroscopy.Real_Time_Analysis
import glados_pycromanager.AutonomousMicroscopy.CustomFunctions
import glados_pycromanager.AutonomousMicroscopy.Analysis_Measurements
new = set(sys.modules) - before
print(json.dumps(sorted(m for m in {HEAVY!r} if m in new)))
"""


def test_node_packages_import_no_heavy_libraries():
    result = subprocess.run([sys.executable, '-c', _PROBE], capture_output=True, text=True,
                            timeout=240, check=False)
    assert result.returncode == 0, result.stderr[-2000:]
    loaded = json.loads(result.stdout.strip().splitlines()[-1])
    assert loaded == [], f'node packages imported heavy libraries at module scope: {loaded}'


#: What a PyMMCorePlus session must not import while starting up (L2.3 of
#: claude_launcher_project.md): pycromanager costs ~2.7 s, almost all of it
#: ndstorage -> dask.array -> xarray -> pandas. The Python and JAVA backends import
#: pycromanager when they start their backend, which is unavoidable there.
STARTUP_FORBIDDEN = ['pycromanager', 'ndstorage', 'ndtiff', 'dask.array', 'xarray', 'pandas']

_STARTUP_PROBE = f"""
import json, sys
import pymmcore  # what GUI/startup.py imports first
import glados_pycromanager.GUI.GUI_napari
import glados_pycromanager.GUI.FlowChart_dockWidgets  # the Autonomous dock
import glados_pycromanager.AutonomousMicroscopy.Real_Time_Analysis
import glados_pycromanager.AutonomousMicroscopy.CustomFunctions
import glados_pycromanager.AutonomousMicroscopy.Analysis_Measurements
from glados_pycromanager.autonomous import registry
for name in ('AverageImage', 'StarDist_image', 'pSMLM'):  # node metadata names ndtiff types
    registry.get_metadata(name)
print(json.dumps(sorted(m for m in {STARTUP_FORBIDDEN!r} if m in sys.modules)))
"""


def test_startup_modules_do_not_import_pycromanager_or_dask():
    result = subprocess.run([sys.executable, '-c', _STARTUP_PROBE], capture_output=True,
                            text=True, timeout=240, check=False)
    assert result.returncode == 0, result.stderr[-2000:]
    loaded = json.loads(result.stdout.strip().splitlines()[-1])
    assert loaded == [], f'startup imported {loaded}; make those imports lazy'
