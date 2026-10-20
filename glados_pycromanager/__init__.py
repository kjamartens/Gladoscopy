"""
glados_pycromanager package initialization file.
"""

# Before anything imports PyQt5: Qt's bundled C++ runtime is too old for current
# Micro-Manager device adapters (see _msvc_runtime.py).
from glados_pycromanager._msvc_runtime import preload_system_msvc_runtime

preload_system_msvc_runtime()
