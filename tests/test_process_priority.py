"""Windows scheduling hints applied once at startup.

On a hybrid CPU (the reported machine is an i7-1355U: 2 performance + 8
efficiency cores at 15 W) Windows drops the foreground boost and lets EcoQoS
power-throttle a process that is not the active window -- in practice parking
its threads on the efficiency cores. That is the mechanism behind "the
visualisation drops to 10 fps, especially when napari is not the main window".

These are scheduling *hints*: nothing may depend on them having worked, so the
contract under test is mostly that failure is silent and harmless.
"""
from __future__ import annotations

import ctypes
import sys

import pytest

from glados_pycromanager.observability import process_priority
from glados_pycromanager.observability.process_priority import (
    ABOVE_NORMAL_PRIORITY_CLASS,
    apply_foreground_scheduling_hints,
)


def test_disabled_is_a_no_op():
    assert apply_foreground_scheduling_hints(enabled=False) == []


def test_a_failing_call_is_swallowed_not_raised(monkeypatch):
    """Older Windows, or a locked-down policy. Must never be fatal."""
    monkeypatch.setattr(sys, 'platform', 'win32')

    def _boom():
        raise OSError('nope')

    monkeypatch.setattr(process_priority, '_set_priority_class', _boom)
    monkeypatch.setattr(process_priority, '_opt_out_of_ecoqos', _boom)
    assert apply_foreground_scheduling_hints() == []


def test_one_failing_hint_does_not_block_the_other(monkeypatch):
    monkeypatch.setattr(sys, 'platform', 'win32')
    monkeypatch.setattr(process_priority, '_set_priority_class',
                        lambda: (_ for _ in ()).throw(OSError('nope')))
    monkeypatch.setattr(process_priority, '_opt_out_of_ecoqos', lambda: None)
    assert apply_foreground_scheduling_hints() == ['EcoQoS opt-out']


@pytest.mark.skipif(not sys.platform.startswith('win'), reason='Windows only')
def test_it_actually_raises_the_priority_class():
    """Verified against the OS, not assumed.

    This is also the regression guard for the 64-bit ctypes trap that made the
    first version a silent no-op: `GetCurrentProcess()` returns the pseudo-handle
    (HANDLE)-1, and at ctypes' default 32-bit `restype` it is truncated, so every
    call fails with "the handle is invalid" -- while `ctypes.get_last_error()`
    reports 0 ("success") because `ctypes.windll` is not opened with
    `use_last_error=True`.
    """
    applied = apply_foreground_scheduling_hints()
    assert 'priority class' in applied

    kernel32 = ctypes.WinDLL('kernel32', use_last_error=True)
    kernel32.GetCurrentProcess.restype = ctypes.c_void_p
    kernel32.GetPriorityClass.restype = ctypes.c_uint32
    kernel32.GetPriorityClass.argtypes = [ctypes.c_void_p]
    assert kernel32.GetPriorityClass(kernel32.GetCurrentProcess()) == ABOVE_NORMAL_PRIORITY_CLASS


@pytest.mark.skipif(not sys.platform.startswith('win'), reason='Windows only')
def test_the_process_handle_is_not_truncated():
    """Directly pins the `restype` fix above."""
    kernel32 = process_priority._kernel32()
    handle = kernel32.GetCurrentProcess()
    #The pseudo-handle is -1 widened to pointer size, i.e. all bits set.
    assert handle == (1 << (8 * ctypes.sizeof(ctypes.c_void_p))) - 1
