"""T-F8 (MMcontrols half): hardware writes on commit, not per pixel or per notch.

`on_sliderChanged` did two hardware getters plus a `set_property` for **every**
`valueChanged` emission -- i.e. every pixel of a slider drag -- and a single
mouse-wheel notch over the z-stage widget triggered its own `set_relative_position`
plus two position read-backs, so a fast scroll queued a burst of them.

These tests pin what changed (when the write happens) and what did not (what the
write is, and how far the stage ends up moving).
"""
from __future__ import annotations

import os

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
def ui_cls(qapp):
    from glados_pycromanager.GUI.MMcontrols import MMConfigUI

    return MMConfigUI


def _settle(timer, timeout_ms=2000):
    from PyQt5.QtCore import QCoreApplication, QElapsedTimer, QEventLoop

    clock = QElapsedTimer()
    clock.start()
    while timer is not None and timer.isActive() and clock.elapsed() < timeout_ms:
        QCoreApplication.processEvents(QEventLoop.AllEvents, 20)
    QCoreApplication.processEvents(QEventLoop.AllEvents, 20)


# ------------------------------------------------------------ slider writes


@pytest.fixture
def slider_host(ui_cls, qapp):
    """An object carrying the real slider-write methods over a recording core."""

    from PyQt5.QtCore import QObject

    def _make():
        # A QObject, because the production code parents its timers to `self`
        # so they are destroyed with the widget.
        obj = type("FakeUI", (QObject,), {})()
        obj.SLIDER_WRITE_DEBOUNCE_MS = ui_cls.SLIDER_WRITE_DEBOUNCE_MS
        obj.writes = []
        obj._writeSliderProperty = lambda cid, val: obj.writes.append((cid, val))
        for name in (
            "_scheduleSliderPropertyWrite",
            "_flushSliderPropertyWrites",
        ):
            setattr(obj, name, getattr(ui_cls, name).__get__(obj))
        return obj

    return _make


def test_a_drag_writes_the_device_once(slider_host):
    host = slider_host()
    for value in range(100):
        host._scheduleSliderPropertyWrite("cfg", value)
    assert host.writes == [], "no device traffic while the handle is moving"

    _settle(host._sliderWriteTimer)
    assert host.writes == [("cfg", 99)], "one write, carrying the final value"


def test_release_flushes_immediately(slider_host):
    """`sliderReleased` is connected straight to the flush."""
    host = slider_host()
    host._scheduleSliderPropertyWrite("cfg", 42)
    assert host.writes == []

    host._flushSliderPropertyWrites()
    assert host.writes == [("cfg", 42)]
    assert not host._sliderWriteTimer.isActive(), "flushing disarms the timer"


def test_each_slider_keeps_its_own_pending_value(slider_host):
    host = slider_host()
    host._scheduleSliderPropertyWrite("a", 1)
    host._scheduleSliderPropertyWrite("b", 2)
    host._scheduleSliderPropertyWrite("a", 3)
    host._flushSliderPropertyWrites()
    assert dict(host.writes) == {"a": 3, "b": 2}


def test_flushing_twice_does_not_rewrite(slider_host):
    host = slider_host()
    host._scheduleSliderPropertyWrite("cfg", 7)
    host._flushSliderPropertyWrites()
    host._flushSliderPropertyWrites()
    assert host.writes == [("cfg", 7)]


def test_flushing_nothing_is_a_no_op(slider_host):
    host = slider_host()
    host._flushSliderPropertyWrites()
    assert host.writes == []


def test_one_failing_slider_does_not_block_the_others(slider_host):
    """A device error on one config must not strand the rest of the batch."""
    host = slider_host()
    seen = []

    def _write(cid, val):
        seen.append(cid)
        if cid == "bad":
            raise RuntimeError("device says no")

    host._writeSliderProperty = _write
    host._scheduleSliderPropertyWrite("bad", 1)
    host._scheduleSliderPropertyWrite("good", 2)
    host._flushSliderPropertyWrites()
    assert seen == ["bad", "good"]


def test_typed_values_are_written_straight_through(ui_cls):
    """A typed value is a deliberate commit; only drags are deferred."""
    import inspect

    source = inspect.getsource(ui_cls.on_sliderChanged)
    assert "if fromSlider:" in source
    assert "self._scheduleSliderPropertyWrite(config_id, trueValue)" in source
    assert "self._writeSliderProperty(config_id, trueValue)" in source


def test_slider_release_is_connected_to_the_flush(ui_cls):
    import inspect

    source = inspect.getsource(ui_cls.addSlider)
    assert "sliderReleased.connect(self._flushSliderPropertyWrites)" in source


def test_the_write_itself_is_unchanged(ui_cls):
    """Same two getters, same set_property -- only the timing and thread moved.

    T-B4 moved the body out of `_writeSliderProperty` (which now only queues it)
    into `_setUnderlyingConfigProperty`, shared with the edit field; both config
    kinds have exactly one property underneath. The lookups and the write are
    still the same three calls, now on the hardware owner thread.
    """
    import inspect

    assert "submitHardware" in inspect.getsource(ui_cls._writeSliderProperty)

    source = inspect.getsource(ui_cls._setUnderlyingConfigProperty)
    assert "get_available_configs" in source
    assert "get_config_data" in source
    assert "set_property(device_label,property_name,value)" in source


# ------------------------------------------------------------- wheel notches


@pytest.fixture
def wheel_host(ui_cls, qapp):
    from PyQt5.QtCore import QObject

    def _make():
        obj = type("FakeUI", (QObject,), {})()
        obj.STAGE_WHEEL_DEBOUNCE_MS = ui_cls.STAGE_WHEEL_DEBOUNCE_MS
        obj.moves = []
        obj.moveOneDStage = lambda amount, steps=1: obj.moves.append((amount, steps))
        for name in ("_accumulateStageWheel", "_flushStageWheel"):
            setattr(obj, name, getattr(ui_cls, name).__get__(obj))
        return obj

    return _make


def test_a_scroll_burst_becomes_one_move(wheel_host):
    host = wheel_host()
    for _ in range(10):
        host._accumulateStageWheel(1)
    assert host.moves == [], "nothing moves while the scroll is in flight"

    _settle(host._stageWheelTimer)
    assert host.moves == [(2, 10)], "one move covering the same total distance"


def test_direction_is_preserved(wheel_host):
    host = wheel_host()
    for _ in range(4):
        host._accumulateStageWheel(-1)
    host._flushStageWheel()
    assert host.moves == [(-2, 4)]


def test_opposing_notches_cancel(wheel_host):
    """Three up and three down left the stage where it started before, too."""
    host = wheel_host()
    for notch in (1, 1, 1, -1, -1, -1):
        host._accumulateStageWheel(notch)
    host._flushStageWheel()
    assert host.moves == [], "a net-zero scroll must not touch the stage"


def test_net_direction_wins(wheel_host):
    host = wheel_host()
    for notch in (1, 1, 1, -1):
        host._accumulateStageWheel(notch)
    host._flushStageWheel()
    assert host.moves == [(2, 2)]


def test_the_accumulator_resets_between_bursts(wheel_host):
    host = wheel_host()
    host._accumulateStageWheel(1)
    host._flushStageWheel()
    host._accumulateStageWheel(1)
    host._flushStageWheel()
    assert host.moves == [(2, 1), (2, 1)]


def test_steps_multiplies_the_distance(ui_cls):
    """`steps` scales the relative move; default 1 leaves button clicks alone."""
    import inspect

    source = inspect.getsource(ui_cls.moveOneDStage)
    assert "def moveOneDStage(self,amount,steps=1):" in source
    assert "np.sign(amount)*steps*self.moveoneDstagesmallAmount" in source
    assert "np.sign(amount)*steps*self.moveoneDstagelargeAmount" in source


def test_both_wheel_paths_are_coalesced(ui_cls):
    """The z-stage widget and the napari canvas both scroll the same stage."""
    import inspect

    assert "_accumulateStageWheel" in inspect.getsource(ui_cls.eventFilter)
    canvas = inspect.getsource(ui_cls.imageScrollToZ_setup) if hasattr(
        ui_cls, "imageScrollToZ_setup"
    ) else None
    if canvas is None:  # the callback lives inside another method
        module_source = inspect.getsource(inspect.getmodule(ui_cls))
        assert module_source.count("self._accumulateStageWheel(1 if delta > 0 else -1)") == 2
