"""Load Windows' own MSVC C++ runtime before PyQt5 can load its outdated copy.

PyQt5 ships an old ``MSVCP140.dll`` in ``PyQt5/Qt5/bin``. Whichever ``msvcp140.dll``
a process loads first is the one every later module gets, and pymmcore is built
against a newer one: once PyQt5's copy is in, ``pymmcore.CMMCore()`` dies with an
access violation. A conda-based Python hides this because its own, newer
``MSVCP140.dll`` sits next to ``python.exe`` and wins; uv's Python (python-build-standalone)
ships none, so on a uv ``.venv`` any import order with Qt first crashed -- the test
suite, for one. Loading the system copy (VC++ redistributable, ``System32``) first
makes the import order irrelevant. Best-effort: it does nothing off Windows, when
some ``msvcp140.dll`` is already loaded, or when the system has none.
"""
from __future__ import annotations

import os
import sys


def preload_system_msvcp140() -> str | None:
    """Load ``System32\\msvcp140.dll`` if no msvcp140 is loaded yet; return its path."""
    if sys.platform != 'win32':
        return None
    try:
        import ctypes
        from ctypes import wintypes
        kernel32 = ctypes.WinDLL('kernel32', use_last_error=True)
        kernel32.GetModuleHandleW.argtypes = [wintypes.LPCWSTR]
        kernel32.GetModuleHandleW.restype = wintypes.HMODULE
        if kernel32.GetModuleHandleW('msvcp140.dll'):
            return None  # too late to choose, or conda's copy is already in
        path = os.path.join(os.environ.get('SystemRoot', r'C:\Windows'), 'System32', 'msvcp140.dll')
        if not os.path.isfile(path):
            return None
        ctypes.WinDLL(path)
        return path
    except OSError:
        return None
