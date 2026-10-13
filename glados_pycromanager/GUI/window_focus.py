"""Bring one of our windows to the front on Windows, without making it stay there.

Windows' foreground lock refuses ``raise_()``/``activateWindow()`` to a process that
does not own the foreground. That covers a launch from a busy terminal, and a running
Glados asked by a second launch to show itself. Two helpers get round it the
supported way:

* ``bring_to_front_once(widget)``: topmost, then not-topmost. The window ends at the top
  of the normal z-order, and any window activated later goes above it (unlike
  ``Qt.WindowStaysOnTopHint``).
* ``allow_set_foreground(pid)``: called by the process that *does* own the foreground (the
  second launch, which the user just clicked) to let ``pid`` take it.

Everything is best-effort: a failure leaves the window where it was. Nothing may
depend on this having worked.
"""

import sys

HWND_TOPMOST, HWND_NOTOPMOST = -1, -2
SWP_NOSIZE, SWP_NOMOVE, SWP_NOACTIVATE = 0x0001, 0x0002, 0x0010
SW_RESTORE = 9


def _user32():
    import ctypes
    user32 = ctypes.WinDLL('user32', use_last_error=True)
    user32.SetWindowPos.argtypes = [ctypes.c_void_p, ctypes.c_void_p, ctypes.c_int,
                                    ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_uint]
    user32.SetForegroundWindow.argtypes = [ctypes.c_void_p]
    user32.ShowWindow.argtypes = [ctypes.c_void_p, ctypes.c_int]
    user32.IsIconic.argtypes = [ctypes.c_void_p]
    user32.AllowSetForegroundWindow.argtypes = [ctypes.c_uint]
    return user32


def bring_to_front_once(widget, activate: bool = False) -> None:
    """Put ``widget``'s window above every normal window now (and focus it if ``activate``)."""
    widget.raise_()
    if activate:
        widget.activateWindow()
    if sys.platform != 'win32':
        return
    try:
        import ctypes
        user32 = _user32()
        hwnd = ctypes.c_void_p(int(widget.winId()))
        if user32.IsIconic(hwnd):
            user32.ShowWindow(hwnd, SW_RESTORE)
        flags = SWP_NOMOVE | SWP_NOSIZE | (0 if activate else SWP_NOACTIVATE)
        user32.SetWindowPos(hwnd, ctypes.c_void_p(HWND_TOPMOST), 0, 0, 0, 0, flags)
        user32.SetWindowPos(hwnd, ctypes.c_void_p(HWND_NOTOPMOST), 0, 0, 0, 0, flags)
        if activate:
            user32.SetForegroundWindow(hwnd)
    except Exception:
        pass


def allow_set_foreground(pid: int) -> None:
    """Let process ``pid`` take the foreground (we must own it ourselves)."""
    if sys.platform != 'win32':
        return
    try:
        _user32().AllowSetForegroundWindow(int(pid))
    except Exception:
        pass
