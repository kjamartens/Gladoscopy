"""Tests for T-G5: the subprocess state mirror is opt-in per node.

The child process used to pickle *every* picklable attribute of the node back to
the main-process visualisation shadow after every frame. For `RealTimeFFT` that
meant the full-size FFT array **and** the cached Tukey window crossing the
process boundary per frame, on top of the actual result.
"""
from __future__ import annotations

import sys
import types

import numpy as np
import pytest

import glados_pycromanager.AutonomousMicroscopy.Real_Time_Analysis.FFT_im  # noqa: F401
import glados_pycromanager.GUI.utils as utils
from glados_pycromanager.GUI.AnalysisClass import _build_state_snapshot

NODE = "ZZ_snapshot_node.FakeNode"


class _Node:
    def __init__(self):
        self.wanted = np.zeros((4, 4))
        self.bulky = np.zeros((512, 512))
        self.counter = 3
        self.live_handle = object()


@pytest.fixture
def declaring_node():
    mod = types.ModuleType("ZZ_snapshot_node")

    def __function_metadata__():
        return {
            "FakeNode": {
                "required_kwargs": [],
                "optional_kwargs": [],
                "help_string": "fake",
                "input": [],
                "output": [],
                "__snapshot_attrs__": ["wanted", "counter"],
            }
        }

    mod.__function_metadata__ = __function_metadata__
    sys.modules["ZZ_snapshot_node"] = mod
    utils.clear_resolve_node_obj_cache()
    from glados_pycromanager.autonomous import registry
    registry.clear_metadata_cache()
    try:
        yield {
            "__selectedDropdownEntryRTAnalysis__": "Fake node",
            "__displayNameFunctionNameMap__": [("Fake node", NODE)],
        }
    finally:
        del sys.modules["ZZ_snapshot_node"]
        registry.clear_metadata_cache()
        utils.clear_resolve_node_obj_cache()


def test_declared_attributes_are_mirrored(declaring_node):
    attrs = utils.realTimeAnalysis_snapshotAttrs(declaring_node)
    assert attrs == ["wanted", "counter"]
    snapshot = _build_state_snapshot(_Node(), attrs)
    assert set(snapshot) == {"wanted", "counter"}
    assert snapshot["counter"] == 3


def test_nothing_is_mirrored_when_nothing_is_declared():
    node = _Node()
    assert _build_state_snapshot(node, []) == {}


def test_a_snapshot_method_takes_precedence(declaring_node):
    class _WithMethod(_Node):
        def snapshot(self):
            return {"only": 1}

    assert _build_state_snapshot(_WithMethod(), ["wanted"]) == {"only": 1}


def test_a_failing_snapshot_method_does_not_kill_the_worker(caplog):
    class _Broken:
        def snapshot(self):
            raise RuntimeError("boom")

    with caplog.at_level("ERROR"):
        assert _build_state_snapshot(_Broken(), ["wanted"]) == {}
    assert "snapshot() failed" in caplog.text


def test_a_declared_but_unsnapshotable_attribute_is_skipped(declaring_node):
    node = _Node()
    snapshot = _build_state_snapshot(node, ["wanted", "live_handle", "missing"])
    assert set(snapshot) == {"wanted"}


def test_a_node_declaring_nothing_reports_no_attrs():
    rt_info = {
        "__selectedDropdownEntryRTAnalysis__": "Example - influence the run by stopping it at a set frame",
        "__displayNameFunctionNameMap__": [
            ("Example - influence the run by stopping it at a set frame", "EndAtFrame.EndAtFrame")
        ],
    }
    import glados_pycromanager.AutonomousMicroscopy.Real_Time_Analysis.EndAtFrame  # noqa: F401
    assert utils.realTimeAnalysis_snapshotAttrs(rt_info) == []


def test_fft_declares_exactly_what_visualise_reads():
    rt_info = {
        "__selectedDropdownEntryRTAnalysis__": "Real-Time FFT",
        "__displayNameFunctionNameMap__": [("Real-Time FFT", "FFT_im.RealTimeFFT")],
    }
    # `firstLayerInit` is set by visualise_init() on the shadow instance itself
    # and must not be clobbered from the child.
    assert utils.realTimeAnalysis_snapshotAttrs(rt_info) == ["fft_display"]


def test_a_non_node_info_reports_no_attrs():
    assert utils.realTimeAnalysis_snapshotAttrs("LiveModeVisualisation") == []
    assert utils.realTimeAnalysis_snapshotAttrs({}) == []
