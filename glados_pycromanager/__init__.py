"""
glados_pycromanager package initialization file.
"""

# Before anything here can import PyQt5: its bundled MSVCP140.dll crashes pymmcore
# on uv's Python (see win_runtime.py).
from glados_pycromanager.win_runtime import preload_system_msvcp140 as _preload_system_msvcp140

_preload_system_msvcp140()
