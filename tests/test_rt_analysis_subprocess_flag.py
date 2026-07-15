"""Tests for utils.realTimeAnalysis_runInSubprocess (the opt-in flag that
routes a node through AnalysisProcess_customFunction instead of
AnalysisThread_customFunction -- see
https://github.com/kjamartens/Gladoscopy/issues/16).
"""
from __future__ import annotations

# Ensure both node modules are loaded into sys.modules so _resolve_node_obj
# (a sys.modules stem lookup, not an eval) can find them by name.
import glados_pycromanager.AutonomousMicroscopy.Real_Time_Analysis.EndAtFrame  # noqa: F401
import glados_pycromanager.AutonomousMicroscopy.Real_Time_Analysis.FFT_im  # noqa: F401
import glados_pycromanager.GUI.utils as utils


def test_fft_node_opts_into_subprocess_isolation():
    rt_analysis_info = {
        "__selectedDropdownEntryRTAnalysis__": "Real-Time FFT",
        "__displayNameFunctionNameMap__": [("Real-Time FFT", "FFT_im.RealTimeFFT")],
    }
    assert utils.realTimeAnalysis_runInSubprocess(rt_analysis_info) is True


def test_node_without_the_flag_defaults_to_false():
    rt_analysis_info = {
        "__selectedDropdownEntryRTAnalysis__": "Example - influence the run by stopping it at a set frame",
        "__displayNameFunctionNameMap__": [
            ("Example - influence the run by stopping it at a set frame", "EndAtFrame.EndAtFrame")
        ],
    }
    assert utils.realTimeAnalysis_runInSubprocess(rt_analysis_info) is False
