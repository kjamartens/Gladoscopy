"""Tests for utils.realTimeAnalysis_runInSubprocess (the opt-in flag that
routes a node through AnalysisProcess_customFunction instead of
AnalysisThread_customFunction, plus the global Adv. settings kill switch
shared_data.config.rt_analysis_config.subprocess_isolation on top of it --
see https://github.com/kjamartens/Gladoscopy/issues/16).
"""
from __future__ import annotations

from types import SimpleNamespace

# Ensure both node modules are loaded into sys.modules so _resolve_node_obj
# (a sys.modules stem lookup, not an eval) can find them by name.
import glados_pycromanager.AutonomousMicroscopy.Real_Time_Analysis.EndAtFrame  # noqa: F401
import glados_pycromanager.AutonomousMicroscopy.Real_Time_Analysis.FFT_im  # noqa: F401
import glados_pycromanager.GUI.utils as utils
from glados_pycromanager.GUI.sharedFunctions import Config

FFT_RT_ANALYSIS_INFO = {
    "__selectedDropdownEntryRTAnalysis__": "Real-Time FFT",
    "__displayNameFunctionNameMap__": [("Real-Time FFT", "FFT_im.RealTimeFFT")],
}

END_AT_FRAME_RT_ANALYSIS_INFO = {
    "__selectedDropdownEntryRTAnalysis__": "Example - influence the run by stopping it at a set frame",
    "__displayNameFunctionNameMap__": [
        ("Example - influence the run by stopping it at a set frame", "EndAtFrame.EndAtFrame")
    ],
}


def _fake_shared_data(subprocess_isolation: str):
    cfg = Config()
    cfg.rt_analysis_config.subprocess_isolation = subprocess_isolation
    return SimpleNamespace(config=cfg)


def test_fft_node_opts_into_subprocess_isolation():
    assert utils.realTimeAnalysis_runInSubprocess(FFT_RT_ANALYSIS_INFO) is True


def test_node_without_the_flag_defaults_to_false():
    assert utils.realTimeAnalysis_runInSubprocess(END_AT_FRAME_RT_ANALYSIS_INFO) is False


def test_no_shared_data_keeps_pure_per_node_behaviour():
    """Call sites without shared_data (e.g. older/test callers) are unaffected
    by the global setting -- it can only be consulted when shared_data is
    actually passed in."""
    assert utils.realTimeAnalysis_runInSubprocess(FFT_RT_ANALYSIS_INFO, None) is True


def test_global_setting_true_keeps_the_per_node_opt_in():
    shared_data = _fake_shared_data("True")
    assert utils.realTimeAnalysis_runInSubprocess(FFT_RT_ANALYSIS_INFO, shared_data) is True


def test_global_setting_false_overrides_a_node_that_opted_in():
    shared_data = _fake_shared_data("False")
    assert utils.realTimeAnalysis_runInSubprocess(FFT_RT_ANALYSIS_INFO, shared_data) is False


def test_global_setting_false_does_not_change_a_node_that_never_opted_in():
    shared_data = _fake_shared_data("False")
    assert utils.realTimeAnalysis_runInSubprocess(END_AT_FRAME_RT_ANALYSIS_INFO, shared_data) is False


# --- T-G10: the __needsLiveCore__ opt-out ---------------------------------

import glados_pycromanager.AutonomousMicroscopy.Real_Time_Analysis.LaserAdjustment  # noqa: E402,F401

LASER_ADJUSTMENT_RT_ANALYSIS_INFO = {
    "__selectedDropdownEntryRTAnalysis__": "LaserAdj",
    "__displayNameFunctionNameMap__": [("LaserAdj", "LaserAdjustment.laser_adjustment")],
}

ADVANCED_LASER_RT_ANALYSIS_INFO = {
    "__selectedDropdownEntryRTAnalysis__": "Advanced laser adjustment",
    "__displayNameFunctionNameMap__": [
        ("Advanced laser adjustment", "LaserAdjustment.laser_adjustment_advanced")
    ],
}


def test_a_node_needing_the_live_core_is_never_isolated():
    """`core`, `shared_data` and `nodzInfo` are all None inside the child, so a
    node reading any of them in run() must stay on the QThread path."""
    assert utils.realTimeAnalysis_runInSubprocess(LASER_ADJUSTMENT_RT_ANALYSIS_INFO) is False
    assert utils.realTimeAnalysis_runInSubprocess(ADVANCED_LASER_RT_ANALYSIS_INFO) is False


def test_end_at_frame_needs_shared_data_to_abort_the_acquisition():
    assert utils.realTimeAnalysis_runInSubprocess(END_AT_FRAME_RT_ANALYSIS_INFO) is False


def test_needs_live_core_beats_an_explicit_opt_in(monkeypatch):
    """Precedence: __needsLiveCore__ wins over __runInSubprocess__, so a node
    cannot accidentally opt into an isolation it cannot survive."""
    from glados_pycromanager.autonomous import registry

    monkeypatch.setitem(
        registry._METADATA_CACHE, "ZZ_conflicting",
        {"Node": {"__needsLiveCore__": True, "__runInSubprocess__": True}},
    )
    rt_info = {
        "__selectedDropdownEntryRTAnalysis__": "Conflicting",
        "__displayNameFunctionNameMap__": [("Conflicting", "ZZ_conflicting.Node")],
    }
    assert utils.realTimeAnalysis_runInSubprocess(rt_info) is False


def test_a_node_declaring_neither_is_never_blindly_isolated(monkeypatch):
    """An undeclared node reaches the default *and* the live-context scan (see
    tests/test_subprocess_node_migration.py). This one's source cannot be
    resolved at all, which counts as needing the live context."""
    from glados_pycromanager.autonomous import registry

    monkeypatch.setitem(registry._METADATA_CACHE, "ZZ_silent", {"Node": {}})
    rt_info = {
        "__selectedDropdownEntryRTAnalysis__": "Silent",
        "__displayNameFunctionNameMap__": [("Silent", "ZZ_silent.Node")],
    }
    assert utils.realTimeAnalysis_runInSubprocess(rt_info) is False
    utils.clear_resolve_node_obj_cache()
