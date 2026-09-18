"""Keep the GUI process off Windows' efficiency cores.

Why this exists
---------------
On a hybrid Intel part (the reported machine is an i7-1355U: **2 performance
cores + 8 efficiency cores at 15 W**), Windows does two things to a process that
is not in the foreground:

1. it drops the foreground priority boost, and
2. it lets **EcoQoS** power-throttle the process, which in practice parks its
   threads on the efficiency cores.

Glados runs the Qt/GUI thread, the frame-ring consumer, the zarr writer, an
RT-analysis proxy thread, an RT-analysis visualisation thread and (for an
isolated node) a whole separate Python process. On two real cores that is
already tight; throttled to efficiency cores it is not enough, which is why the
live display visibly collapses when the napari window is not the active window.

Neither call changes behaviour on any other platform, and both are entirely
best-effort: a failure is logged at DEBUG and the app carries on exactly as
before. This is a scheduling hint, not a correctness mechanism -- nothing may
depend on it having worked.

Deliberately **not** done here: raising the GUI thread's own `QThread` priority.
The competing work is in other threads and another process, so a thread-level
nudge inside this process does not address the hybrid-core placement that is the
actual problem.
"""

import ctypes
import logging
import sys

logger = logging.getLogger(__name__)

#: SetPriorityClass. Above-normal rather than HIGH: HIGH_PRIORITY_CLASS outranks
#: most of the system and can starve the very drivers and services the
#: acquisition depends on. Above-normal is enough to win against ordinary
#: background work without that risk.
ABOVE_NORMAL_PRIORITY_CLASS = 0x00008000

#: SetProcessInformation / PROCESS_INFORMATION_CLASS.ProcessPowerThrottling
_PROCESS_POWER_THROTTLING = 4
_PROCESS_POWER_THROTTLING_CURRENT_VERSION = 1
_PROCESS_POWER_THROTTLING_EXECUTION_SPEED = 0x1


class _PROCESS_POWER_THROTTLING_STATE(ctypes.Structure):
    _fields_ = [
        ('Version', ctypes.c_uint32),
        ('ControlMask', ctypes.c_uint32),
        ('StateMask', ctypes.c_uint32),
    ]


def _kernel32():
    """kernel32 with explicit signatures.

    Both details matter on 64-bit Windows and both bit this once:

    * `GetCurrentProcess()` returns the pseudo-handle `(HANDLE)-1`. Left at
      ctypes' default `restype` of 32-bit `c_int` it is truncated to
      `0x00000000FFFFFFFF`, and every call made with it fails with "The handle
      is invalid". It must be declared `c_void_p`.
    * `ctypes.get_last_error()` only reports anything for a library opened with
      `use_last_error=True`; via the shared `ctypes.windll` cache it always
      returns 0, so a real failure is reported as "WinError 0: success".
    """
    kernel32 = ctypes.WinDLL('kernel32', use_last_error=True)  # type: ignore[attr-defined]
    kernel32.GetCurrentProcess.restype = ctypes.c_void_p
    kernel32.GetCurrentProcess.argtypes = []
    kernel32.SetPriorityClass.restype = ctypes.c_int
    kernel32.SetPriorityClass.argtypes = [ctypes.c_void_p, ctypes.c_uint32]
    kernel32.SetProcessInformation.restype = ctypes.c_int
    kernel32.SetProcessInformation.argtypes = [
        ctypes.c_void_p, ctypes.c_int, ctypes.c_void_p, ctypes.c_uint32]
    return kernel32


def _set_priority_class():
    kernel32 = _kernel32()
    handle = kernel32.GetCurrentProcess()
    if not kernel32.SetPriorityClass(handle, ABOVE_NORMAL_PRIORITY_CLASS):
        raise ctypes.WinError(ctypes.get_last_error())  # type: ignore[attr-defined]


def _opt_out_of_ecoqos():
    """Ask Windows not to power-throttle this process.

    `ControlMask` says "I am specifying the execution-speed policy";
    `StateMask = 0` says "and the policy is: off". Setting ControlMask without
    clearing StateMask would request the opposite -- throttling *on*.
    """
    kernel32 = _kernel32()
    handle = kernel32.GetCurrentProcess()
    state = _PROCESS_POWER_THROTTLING_STATE(
        Version=_PROCESS_POWER_THROTTLING_CURRENT_VERSION,
        ControlMask=_PROCESS_POWER_THROTTLING_EXECUTION_SPEED,
        StateMask=0,
    )
    ok = kernel32.SetProcessInformation(
        handle, _PROCESS_POWER_THROTTLING, ctypes.byref(state), ctypes.sizeof(state))
    if not ok:
        raise ctypes.WinError(ctypes.get_last_error())  # type: ignore[attr-defined]


def apply_foreground_scheduling_hints(enabled=True):
    """Best-effort. Returns the list of hints that actually applied.

    `enabled` is the user's Advanced-settings switch; False makes this a no-op
    so the behaviour can be turned off without a code change.
    """
    if not enabled:
        logger.debug('Foreground scheduling hints disabled by configuration')
        return []
    if not sys.platform.startswith('win'):
        return []

    applied = []
    for name, fn in (('priority class', _set_priority_class),
                     ('EcoQoS opt-out', _opt_out_of_ecoqos)):
        try:
            fn()
        except Exception as exc:
            # Older Windows (SetProcessInformation is Windows 8+), a locked-down
            # policy, or a non-CPython ctypes surprise. Never fatal.
            logger.debug('Could not apply %s: %s', name, exc)
        else:
            applied.append(name)

    if applied:
        logger.info('Applied Windows scheduling hints (%s) so the display is not '
                    'throttled to efficiency cores when the window is unfocused',
                    ', '.join(applied))
    return applied
