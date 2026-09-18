"""Depth limits on the two hand-offs to the Qt/GUI thread.

Both the live/MDA display worker (`run_napariVisualisation_worker` -> the
`yielded` signal -> `napariUpdateLive`) and each RT-analysis node's overlay
thread (`_do_visualise` -> `_visualise_on_main_thread`) reach the GUI thread
through a **queued** Qt connection. Neither used to check whether the GUI thread
had drawn the previous payload before sending the next one.

The display path's existing gate does not help, and in fact makes it worse:
`_should_display_now` decides on `now - shared_data.last_display_update_time`,
and that stamp is only written at the *end* of a completed GUI update. It
therefore measures starvation rather than backlog -- once the GUI thread is
behind, `elapsed` only grows, so the gate passes every time. Payloads then
accumulate in Qt's event queue and the displayed frame drifts further and
further behind the camera, without bound, for as long as the acquisition runs.

The fix is a one-deep slot per hand-off, claimed by the producer and released by
the GUI-side slot. A refused producer **drops** its frame: overload has to
degrade into frame-dropping with bounded latency, which is the entire point.
"""
from __future__ import annotations

import time

from glados_pycromanager.GUI.napariGlados import (
    DISPLAY_INFLIGHT_TIMEOUT_S,
    _claim_display_slot,
    _release_display_slot,
)


class _SharedData:
    def __init__(self):
        self.displayUpdateInFlight = None


# -- display path ---------------------------------------------------------

def test_second_claim_is_refused_until_the_first_is_released():
    shared = _SharedData()
    assert _claim_display_slot(shared) is True
    assert _claim_display_slot(shared) is False
    assert _claim_display_slot(shared) is False
    _release_display_slot(shared)
    assert _claim_display_slot(shared) is True


def test_release_is_idempotent_and_safe_when_nothing_is_outstanding():
    shared = _SharedData()
    _release_display_slot(shared)
    _release_display_slot(shared)
    assert _claim_display_slot(shared) is True


def test_a_never_acknowledged_payload_is_watchdogged_rather_than_wedging_forever():
    """A yielded signal that never arrives must not silence the display."""
    shared = _SharedData()
    assert _claim_display_slot(shared) is True
    # Pretend the claim happened longer ago than the watchdog allows.
    shared.displayUpdateInFlight = time.monotonic() - (DISPLAY_INFLIGHT_TIMEOUT_S + 1)
    assert _claim_display_slot(shared) is True


def test_a_missing_attribute_does_not_break_the_claim():
    """Shared_data built before this field existed, or a test double."""
    class _Bare:
        pass

    bare = _Bare()
    assert _claim_display_slot(bare) is True
    assert bare.displayUpdateInFlight is not None


def test_backlog_stays_bounded_against_a_gui_slower_than_the_camera():
    """The property that actually matters: latency must not grow without bound.

    Simulates the reported configuration -- frames arriving faster than the GUI
    thread can draw them -- and asserts the number of payloads outstanding never
    exceeds one, however long the run.
    """
    shared = _SharedData()
    outstanding = 0
    peak = 0
    sent = 0
    #GUI draws one frame for every three that arrive.
    for frame in range(300):
        if _claim_display_slot(shared):
            outstanding += 1
            sent += 1
            peak = max(peak, outstanding)
        if frame % 3 == 2 and outstanding:
            outstanding -= 1
            _release_display_slot(shared)

    assert peak == 1, f'display payloads queued up {peak} deep'
    #And it must still make progress, not deadlock into sending nothing.
    assert sent >= 90


# -- RT-analysis overlay path --------------------------------------------

def _visualisation_thread():
    """An instance with the slot machinery but no QThread/napari construction."""
    from glados_pycromanager.GUI.AnalysisClass import (
        AnalysisThread_customFunction_Visualisation as Vis,
    )

    obj = Vis.__new__(Vis)
    obj._visualise_in_flight = None
    return obj


def test_overlay_slot_is_one_deep():
    vis = _visualisation_thread()
    assert vis._claim_visualise_slot() is True
    assert vis._claim_visualise_slot() is False
    vis._visualise_in_flight = None
    assert vis._claim_visualise_slot() is True


def test_overlay_slot_has_a_watchdog():
    from glados_pycromanager.GUI.AnalysisClass import RT_VISUALISE_INFLIGHT_TIMEOUT_S

    vis = _visualisation_thread()
    assert vis._claim_visualise_slot() is True
    vis._visualise_in_flight = time.monotonic() - (RT_VISUALISE_INFLIGHT_TIMEOUT_S + 1)
    assert vis._claim_visualise_slot() is True


def test_overlay_slot_is_released_even_when_visualise_raises():
    """One failing overlay frame must not silence the node for the session."""
    vis = _visualisation_thread()

    def _boom(*args, **kwargs):
        raise RuntimeError('node visualise() failed')

    vis._visualise_paired = _boom
    assert vis._claim_visualise_slot() is True
    try:
        vis._visualise_on_main_thread((None, None, None, None, None, None, None))
    except RuntimeError:
        pass
    assert vis._visualise_in_flight is None
    assert vis._claim_visualise_slot() is True
