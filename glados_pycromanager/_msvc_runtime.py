"""Load the system's MSVC C++ runtime before PyQt5 loads its own (Windows only).

PyQt5 bundles ``msvcp140.dll`` 14.26 (2020) in ``PyQt5/Qt5/bin``. Windows resolves a
DLL import by name to an already-loaded module of that name, so once Qt is loaded,
every Micro-Manager device adapter (``mmgr_dal_*.dll``, which links plain
``msvcp140.dll``) gets Qt's old copy. Adapters built with Visual Studio 2022 17.10 or
later crash on a runtime older than 14.40 (the ``std::mutex`` constexpr-constructor
change): an access violation in ``initializeDevice`` / ``loadSystemConfiguration``,
e.g. the DemoCamera of a 2026 nightly. Importing ``pymmcore`` first no longer helps:
its wheel carries its own name-mangled copy (``pymmcore.libs/msvcp140-<hash>.dll``),
which leaves plain ``msvcp140.dll`` unclaimed.

Loading the System32 copies first makes them the ones Qt and the adapters share. The
runtime is backwards compatible, so Qt runs fine on the newer one. Stdlib-only and
best-effort: nothing may depend on it having worked.
"""

import ctypes
import importlib.util
import logging
import os
import sys

# The C++ runtime DLLs PyQt5 bundles. vcruntime140 is loaded by Python itself already.
RUNTIME_DLLS = ('msvcp140.dll', 'msvcp140_1.dll', 'msvcp140_2.dll', 'concrt140.dll')

_preloaded = []  # keeps the handles alive for the life of the process


def _file_version(path):
    """(major, minor, build, revision) of a DLL, or None when unreadable."""
    try:
        import ctypes.wintypes as wintypes
        version = ctypes.WinDLL('version')
        size = version.GetFileVersionInfoSizeW(path, None)
        if not size:
            return None
        buf = ctypes.create_string_buffer(size)
        if not version.GetFileVersionInfoW(path, 0, size, buf):
            return None
        info = ctypes.c_void_p()
        length = wintypes.UINT()
        if not version.VerQueryValueW(buf, '\\', ctypes.byref(info), ctypes.byref(length)):
            return None
        ms, ls = ctypes.cast(info, ctypes.POINTER(wintypes.DWORD * 4)).contents[2:4]
        return (ms >> 16, ms & 0xFFFF, ls >> 16, ls & 0xFFFF)
    except (OSError, AttributeError, ValueError):
        return None


def _pyqt5_bin_dir():
    """PyQt5's bundled Qt ``bin`` folder, found without importing PyQt5."""
    try:
        spec = importlib.util.find_spec('PyQt5')
    except (ImportError, ValueError):
        return None
    if spec is None or not spec.submodule_search_locations:
        return None
    return os.path.join(list(spec.submodule_search_locations)[0], 'Qt5', 'bin')


def preload_system_msvc_runtime():
    """Load System32's C++ runtime DLLs where they are newer than PyQt5's bundled ones.

    Returns the list of DLL paths loaded. Does nothing off Windows, or once PyQt5 has
    been imported (Qt's copy is then already the process-wide one).
    """
    if sys.platform != 'win32' or _preloaded:
        return list(_preloaded)
    if 'PyQt5.QtCore' in sys.modules:
        logging.debug('PyQt5 already loaded; cannot preload the system MSVC runtime')
        return []
    system32 = os.path.join(os.environ.get('SystemRoot', r'C:\Windows'), 'System32')
    qt_bin = _pyqt5_bin_dir()
    for name in RUNTIME_DLLS:
        system_dll = os.path.join(system32, name)
        if not os.path.isfile(system_dll):
            continue
        system_version = _file_version(system_dll)
        bundled = os.path.join(qt_bin, name) if qt_bin else None
        bundled_version = _file_version(bundled) if bundled and os.path.isfile(bundled) else None
        if system_version is None or (bundled_version is not None and system_version < bundled_version):
            continue
        try:
            ctypes.WinDLL(system_dll)
        except OSError as exc:
            logging.debug('Could not preload %s: %s', system_dll, exc)
            continue
        _preloaded.append(system_dll)
    return list(_preloaded)
