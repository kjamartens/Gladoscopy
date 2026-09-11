"""T-F10 part 2 + T-F8 laser half: no blind sleeps, no per-keystroke serial writes.

**T-F10 part 2.** `on_liveMode_value_change` / `on_mdaMode_value_change` each did
`time.sleep(0.1)` before dispatching to `acqModeChanged`. The sleep blocked
whichever thread flipped the flag -- usually the GUI thread, from a button slot --
and it did not make anything more synchronous: `acqModeChanged` is called
synchronously either side of it, so the only effect was to delay the dispatch.
The audit of every caller found exactly one that depended on the delay,
`MMcontrols.setROI`, which changes the ROI immediately after stopping live mode;
it now waits on the core explicitly.

**T-F8 laser half.** `ChangeIntensityLaserEditField` was wired to `textChanged`,
so typing "150" issued three serial writes and briefly drove the laser to 1 and
then 15. `drawplot` -- which clears and rebuilds roughly a hundred pyqtgraph items
-- was wired to `textChanged` on fifteen line edits.
"""
from __future__ import annotations

import inspect
import os
import time

import pytest

pytest.importorskip("PyQt5.QtWidgets")


@pytest.fixture(scope="module")
def qapp():
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from PyQt5.QtCore import QCoreApplication, Qt
    from PyQt5.QtWidgets import QApplication

    QCoreApplication.setAttribute(Qt.AA_ShareOpenGLContexts, True)
    return QApplication.instance() or QApplication([])


@pytest.fixture(scope="module")
def shared_mod(qapp):
    from glados_pycromanager.GUI import sharedFunctions

    return sharedFunctions


# --------------------------------------------------------- the sleeps are gone


@pytest.mark.parametrize(
    "method", ["on_liveMode_value_change", "on_mdaMode_value_change"]
)
def test_the_setter_no_longer_sleeps(shared_mod, method):
    source = inspect.getsource(getattr(shared_mod.Shared_data, method))
    body = "\n".join(
        line for line in source.splitlines() if not line.strip().startswith("#")
    )
    assert "time.sleep" not in body


@pytest.mark.parametrize(
    "method,handler",
    [
        ("on_liveMode_value_change", "_livemodeNapariHandler"),
        ("on_mdaMode_value_change", "_mdamodeNapariHandler"),
    ],
)
def test_the_dispatch_still_happens_and_is_immediate(shared_mod, method, handler):
    """The mode change must still reach acqModeChanged, synchronously."""
    calls = []

    obj = type("FakeShared", (), {})()
    obj._liveMode = obj._mdaMode = True
    setattr(
        obj,
        handler,
        type("H", (), {"acqModeChanged": lambda self, newSharedData=None: calls.append(newSharedData)})(),
    )

    started = time.monotonic()
    getattr(shared_mod.Shared_data, method)(obj)
    elapsed = time.monotonic() - started

    assert calls == [obj], "acqModeChanged must still be called, with self"
    assert elapsed < 0.05, "the caller waited %.3fs; the sleep should be gone" % elapsed


def test_a_hundred_toggles_cost_no_wall_clock(shared_mod):
    """0.1 s per flip was 20 s across a hundred toggles of a mode pair."""
    calls = []
    obj = type("FakeShared", (), {})()
    obj._liveMode = True
    obj._livemodeNapariHandler = type(
        "H", (), {"acqModeChanged": lambda self, newSharedData=None: calls.append(1)}
    )()

    started = time.monotonic()
    for _ in range(100):
        shared_mod.Shared_data.on_liveMode_value_change(obj)
    elapsed = time.monotonic() - started

    assert len(calls) == 100
    assert elapsed < 1.0, "100 dispatches took %.2fs" % elapsed


def test_the_unused_time_import_was_dropped(shared_mod):
    assert not hasattr(shared_mod, "time"), (
        "nothing in sharedFunctions uses `time` any more"
    )


# ------------------------------------------------- the one dependent caller


def test_set_roi_waits_on_the_core_instead_of_sleeping(qapp):
    """setROI changes the ROI right after stopping live mode.

    T-B4 split the two branches into their own methods -- `_setROI_hw` (queued
    on the hardware owner thread) and `_setROI_liveRestart` (its own short-lived
    thread, since it must wait for the acquisition worker) -- so the waits are
    asserted there. The contract is unchanged: one wait when live is off, two
    around the ROI change when it is on.
    """
    from glados_pycromanager.GUI.MMcontrols import MMConfigUI

    combined = (inspect.getsource(MMConfigUI.setROI)
                + inspect.getsource(MMConfigUI._setROI_hw)
                + inspect.getsource(MMConfigUI._setROI_liveRestart))
    assert "time.sleep(0.5)" not in combined, "the blind sleep is replaced by a wait"
    assert combined.count("wait_for_system()") == 3, (
        "the non-live branch waits once; the live branch waits after the stop "
        "and again after the ROI change"
    )


def test_set_roi_live_branch_orders_stop_wait_set_wait_start(qapp):
    """Ordering is the whole point: stop, settle, set, settle, restart."""
    from glados_pycromanager.GUI.MMcontrols import MMConfigUI

    live_branch = inspect.getsource(MMConfigUI._setROI_liveRestart)
    order = []
    for line in live_branch.splitlines():
        stripped = line.strip()
        if stripped.startswith("#"):
            continue
        if "liveMode = False" in stripped:
            order.append("stop")
        elif "wait_for_system()" in stripped:
            order.append("wait")
        elif "set_roi(" in stripped:
            order.append("set")
        elif "liveMode = True" in stripped:
            order.append("start")
    assert order == ["stop", "wait", "set", "wait", "start"]


def test_draw_roi_only_reads_and_needs_no_wait(qapp):
    """The other live-mode pause surrounded a pure query, so T-B4 dropped it.

    `get_sensor_size()` is a read. It used to be bracketed by a live-mode stop,
    a 0.2 s GUI-thread sleep and a restart; the owner thread serialises it
    against the live pull loop instead, so the query alone is enough.
    """
    from glados_pycromanager.GUI.MMcontrols import MMConfigUI

    source = inspect.getsource(MMConfigUI.drawROI)
    assert "get_sensor_size()" in source
    assert "set_roi(" not in source, (
        "if this ever writes to the core it needs the same explicit wait setROI got"
    )
    assert "time.sleep(0.2)" not in source, (
        "a read does not need a live-mode pause, let alone one that sleeps on "
        "the GUI thread"
    )


# ---------------------------------------------------- exposure live-restart


def test_exposure_field_wired_to_editing_finished(qapp):
    from glados_pycromanager.GUI.MMcontrols import MMConfigUI

    source = inspect.getsource(MMConfigUI.generalImagingLayout)
    assert "exposureTimeInputField.editingFinished.connect" in source
    assert "_onExposureFieldEditingFinished" in source


def test_exposure_editing_finished_does_nothing_extra_when_not_live(qapp):
    """The new value is already picked up lazily at the next snap/live-start;
    when live mode isn't running there is nothing to restart."""
    from unittest.mock import MagicMock, patch

    from glados_pycromanager.GUI.MMcontrols import MMConfigUI

    obj = MMConfigUI.__new__(MMConfigUI)
    obj.exposureTimeInputField = MagicMock()
    obj.exposureTimeInputField.text.return_value = "50"
    obj.storeAllControlValues = MagicMock()
    obj.shared_data = MagicMock()
    obj.shared_data.liveMode = False

    with patch("glados_pycromanager.GUI.MMcontrols.shared_data", obj.shared_data, create=True), \
         patch("threading.Thread") as thread_cls:
        obj._onExposureFieldEditingFinished()

    obj.storeAllControlValues.assert_called_once()
    thread_cls.assert_not_called()


def test_exposure_editing_finished_restarts_live_mode_when_live(qapp):
    """When live, a daemon thread must be spawned targeting
    _exposureChange_liveRestart with the parsed exposure -- patch
    threading.Thread itself rather than actually spawning one, so the test
    stays deterministic and leaves no background thread behind."""
    from unittest.mock import MagicMock, patch

    from glados_pycromanager.GUI.MMcontrols import MMConfigUI

    obj = MMConfigUI.__new__(MMConfigUI)
    obj.exposureTimeInputField = MagicMock()
    obj.exposureTimeInputField.text.return_value = "50"
    obj.storeAllControlValues = MagicMock()
    obj.shared_data = MagicMock()
    obj.shared_data.liveMode = True

    with patch("glados_pycromanager.GUI.MMcontrols.shared_data", obj.shared_data, create=True), \
         patch("threading.Thread") as thread_cls:
        obj._onExposureFieldEditingFinished()

    thread_cls.assert_called_once()
    _, kwargs = thread_cls.call_args
    assert kwargs["target"] == obj._exposureChange_liveRestart
    assert kwargs["args"] == (50.0,)
    assert kwargs["daemon"] is True
    thread_cls.return_value.start.assert_called_once()


def test_exposure_live_restart_waits_instead_of_sleeping(qapp):
    from glados_pycromanager.GUI.MMcontrols import MMConfigUI

    source = inspect.getsource(MMConfigUI._exposureChange_liveRestart)
    assert "time.sleep" not in source
    assert source.count("wait_for_system()") == 2, (
        "one wait after stopping live, one after the exposure change, before restart"
    )


def test_exposure_live_restart_orders_stop_wait_set_wait_start(qapp):
    """Mirrors setROI's live branch: stop, settle, set, settle, restart."""
    from glados_pycromanager.GUI.MMcontrols import MMConfigUI

    live_branch = inspect.getsource(MMConfigUI._exposureChange_liveRestart)
    order = []
    for line in live_branch.splitlines():
        stripped = line.strip()
        if stripped.startswith("#"):
            continue
        if "liveMode = False" in stripped:
            order.append("stop")
        elif "wait_for_system()" in stripped:
            order.append("wait")
        elif "set_exposure(" in stripped:
            order.append("set")
        elif "liveMode = True" in stripped:
            order.append("start")
    assert order == ["stop", "wait", "set", "wait", "start"]


# ------------------------------------------------------------- laser control


@pytest.fixture(scope="module")
def laser_mod(qapp):
    import glados_pycromanager.GUI.LaserControlScripts as laser

    return laser


def test_intensity_edit_is_wired_to_editing_finished(laser_mod):
    source = inspect.getsource(laser_mod)
    assert 'EditIntensity_Laser_" + str(i) + ".editingFinished.connect' in source
    assert 'EditIntensity_Laser_" + str(i) + ".textChanged.connect' not in source, (
        "a serial write per keystroke drove the laser through every partial value"
    )


def test_drawplot_triggers_are_debounced(laser_mod):
    source = inspect.getsource(laser_mod)
    for field in ("Delay_Edit_Laser_", "Length_Edit_Laser_", "BlinkFrames_Edit_Laser_"):
        assert (
            '%s" + str(i) + ".textChanged.connect(lambda: scheduleDrawplot(frameduration));'
            % field in source
        ), "%s must go through the debounce" % field
    assert "textChanged.connect(lambda: drawplot(frameduration))" not in source


def test_drawplot_stays_on_text_changed(laser_mod):
    """The plot is a live preview; editingFinished would leave it stale."""
    assert "DRAWPLOT_DEBOUNCE_MS" in dir(laser_mod)
    source = inspect.getsource(laser_mod.scheduleDrawplot)
    assert "setSingleShot(True)" in source
    assert "DRAWPLOT_DEBOUNCE_MS" in source


def test_schedule_drawplot_coalesces_a_burst(laser_mod, qapp, monkeypatch):
    from PyQt5.QtCore import QCoreApplication, QElapsedTimer, QEventLoop

    redraws = []
    monkeypatch.setattr(laser_mod, "drawplot", lambda fd: redraws.append(fd))
    monkeypatch.setattr(laser_mod, "_drawplotTimer", None)

    for _ in range(25):
        laser_mod.scheduleDrawplot(33.0)
    assert redraws == [], "nothing redraws while the user is still typing"

    clock = QElapsedTimer()
    clock.start()
    while not redraws and clock.elapsed() < 3000:
        QCoreApplication.processEvents(QEventLoop.AllEvents, 10)

    assert redraws == [33.0], "25 keystrokes must cost one rebuild"


def test_intensity_bookkeeping_lives_at_the_single_choke_point(laser_mod):
    """Both the slider and the edit field write through ChangeIntensityLaser."""
    source = inspect.getsource(laser_mod.ChangeIntensityLaser)
    assert "_lastWrittenLaserIntensity[laserID] = ValIntPerc" in source

    handler = inspect.getsource(laser_mod.ChangeIntensityLaserEditField)
    assert "_lastWrittenLaserIntensity.get(laserID) == newIntensity" in handler
    assert "_lastWrittenLaserIntensity[laserID] =" not in handler, (
        "recording it in two places lets the slider's writes go unrecorded"
    )


def test_a_focus_out_that_changed_nothing_writes_nothing(laser_mod, monkeypatch):
    """editingFinished fires on every focus-out, changed or not."""
    writes = []

    class _Field:
        def __init__(self, text):
            self._text = text

        def text(self):
            return self._text

    class _Form:
        EditIntensity_Laser_0 = _Field("40")

    monkeypatch.setattr(laser_mod, "form", _Form, raising=False)
    monkeypatch.setattr(
        laser_mod, "ChangeIntensityLaser",
        lambda laserID, value: (
            writes.append((laserID, value)),
            laser_mod._lastWrittenLaserIntensity.__setitem__(laserID, value),
        ),
        raising=False,
    )
    monkeypatch.setattr(laser_mod, "InitLaserSliders", lambda *a: None, raising=False)
    monkeypatch.setattr(laser_mod, "MM_JSON", {}, raising=False)
    laser_mod._lastWrittenLaserIntensity.clear()

    laser_mod.ChangeIntensityLaserEditField(0)
    assert writes == [(0, 40)]

    for _ in range(5):
        laser_mod.ChangeIntensityLaserEditField(0)
    assert writes == [(0, 40)], "an unchanged value must not repeat the serial write"

    _Form.EditIntensity_Laser_0 = _Field("70")
    laser_mod.ChangeIntensityLaserEditField(0)
    assert writes == [(0, 40), (0, 70)]

    laser_mod._lastWrittenLaserIntensity.clear()
