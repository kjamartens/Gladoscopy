"""The napari plugin imports with a QApplication napari already created.

napari builds its QApplication without ``AA_ShareOpenGLContexts`` before it imports a
plugin, so any module-scope ``PyQt5.QtWebEngineWidgets`` import on the plugin's import
chain fails with "QtWebEngineWidgets must be imported or Qt.AA_ShareOpenGLContexts must
be set before a QCoreApplication instance is created". QtWebEngine is only imported
where a web view is actually built (``ui/markdown_view.py``, ``UserManualWidget``).
"""

import os
import subprocess
import sys


def test_dock_widget_imports_after_qapplication_without_webengine():
    code = """
import os, sys
from PyQt5.QtWidgets import QApplication
app = QApplication(sys.argv)
import glados_pycromanager._dock_widget as dw
assert dw.MainWidget is not None
print('webengine' if 'PyQt5.QtWebEngineWidgets' in sys.modules else 'clean', flush=True)
os._exit(0)
"""
    env = dict(os.environ, QT_QPA_PLATFORM='offscreen')
    result = subprocess.run([sys.executable, '-c', code], capture_output=True, text=True,
                            timeout=300, check=False, env=env)
    assert result.returncode == 0, result.stderr[-3000:]
    assert result.stdout.strip().splitlines()[-1] == 'clean'
