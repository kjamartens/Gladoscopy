"""T-H3: the MDA focus device is set at acquisition start, not per keystroke.

`get_MDA_events_from_GUI` called `MILcore.set_focus_device(...)` -- a hardware
call, ~257 ms on the Java bridge -- on every rebuild of the plan, and in its
`else` branch on every rebuild with the z widget disabled too. The z-stack only
needs it once, before the acquisition starts. `_applyFocusDevice()` keeps the
old choice (selected stage if z is enabled, the default otherwise or when the
stage is rejected) and both acquire paths call it before starting the worker.
"""
from __future__ import annotations

import inspect
import os
from types import SimpleNamespace

import pytest

pytest.importorskip("PyQt5.QtWidgets")


@pytest.fixture(scope="module")
def mda_cls():
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from PyQt5.QtCore import QCoreApplication, Qt
    from PyQt5.QtWidgets import QApplication

    QCoreApplication.setAttribute(Qt.AA_ShareOpenGLContexts, True)
    QApplication.instance() or QApplication([])
    from glados_pycromanager.Core.MDAGlados import MDAGlados

    return MDAGlados


class _RecordingMIL:
    def __init__(self, rejects=()):
        self.calls = []
        self._rejects = set(rejects)

    def set_focus_device(self, device):
        self.calls.append(device)
        if device in self._rejects:
            raise RuntimeError(f"no such device: {device}")


def _host(mda_cls, *, show_z, stage, rejects=()):
    mil = _RecordingMIL(rejects)
    obj = SimpleNamespace(
        GUI_show_z=show_z,
        z_stage_sel=stage,
        shared_data=SimpleNamespace(MILcore=mil, _defaultFocusDevice="DefaultZ"),
    )
    obj._applyFocusDevice = mda_cls._applyFocusDevice.__get__(obj)
    return obj, mil


# ------------------------------------------------------------ behaviour


def test_the_selected_stage_is_applied_when_z_is_enabled(mda_cls):
    obj, mil = _host(mda_cls, show_z=True, stage="PiezoZ")
    obj._applyFocusDevice()
    assert mil.calls == ["PiezoZ"]


def test_the_default_is_applied_when_z_is_disabled(mda_cls):
    obj, mil = _host(mda_cls, show_z=False, stage="PiezoZ")
    obj._applyFocusDevice()
    assert mil.calls == ["DefaultZ"]


def test_the_default_is_applied_when_no_stage_was_ever_selected(mda_cls):
    obj, mil = _host(mda_cls, show_z=True, stage=None)
    obj._applyFocusDevice()
    assert mil.calls == ["DefaultZ"]


def test_a_rejected_stage_falls_back_to_the_default(mda_cls):
    obj, mil = _host(mda_cls, show_z=True, stage="Gone", rejects={"Gone"})
    obj._applyFocusDevice()
    assert mil.calls == ["Gone", "DefaultZ"]


# ------------------------------------------------------------ placement


def test_the_rebuild_makes_no_hardware_focus_call(mda_cls):
    source = inspect.getsource(mda_cls.get_MDA_events_from_GUI)
    code = "\n".join(l for l in source.splitlines() if not l.strip().startswith("#"))
    assert "set_focus_device" not in code
    assert "self.z_stage_sel = self.z_oneDstageDropdown.currentText()" in code


@pytest.mark.parametrize("method", ["MDA_acq_from_GUI", "MDA_acq_from_Node"])
def test_both_acquire_paths_apply_it_before_starting(mda_cls, method):
    source = inspect.getsource(getattr(mda_cls, method))
    assert source.index("self.flushMDAEventsUpdate()") < source.index("self._applyFocusDevice()")
    assert source.index("self._applyFocusDevice()") < source.index("self.shared_data.mdaMode = True")
