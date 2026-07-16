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
