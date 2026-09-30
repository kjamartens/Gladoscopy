"""Tests for the T-G1 node-metadata cache.

`__function_metadata__()` rebuilds a fresh nested dict literal on every call,
and the GUI/dispatch path called it several times per analysed frame — then
serialised the result into a "key: value\\n" blob only to regex it straight back
out. `registry.get_metadata()` caches the dict per module stem and the
`*FromFunction` helpers now read it directly.
"""
from __future__ import annotations

import sys
import types

import pytest

# Real node modules, loaded so the sys.modules stem lookup can find them.
import glados_pycromanager.AutonomousMicroscopy.CustomFunctions.Strobo_lasers  # noqa: F401
import glados_pycromanager.AutonomousMicroscopy.Real_Time_Analysis.FFT_im  # noqa: F401
import glados_pycromanager.GUI.utils as utils
from glados_pycromanager.autonomous import registry


@pytest.fixture
def counting_node_module():
    """Install a throwaway node module whose metadata calls are counted."""
    calls = {"n": 0}
    mod = types.ModuleType("ZZ_fake_metadata_node")

    def __function_metadata__():
        calls["n"] += 1
        return {
            "FakeNode": {
                "required_kwargs": [
                    {"name": "alpha", "description": "a", "type": float},
                ],
                "optional_kwargs": [
                    {"name": "beta", "description": "b", "default": 2, "type": int,
                     "display_text": "Beta value"},
                ],
                "help_string": "fake",
                "input": [],
                "output": [],
            }
        }

    mod.__function_metadata__ = __function_metadata__
    sys.modules["ZZ_fake_metadata_node"] = mod
    registry.clear_metadata_cache()
    utils.clear_resolve_node_obj_cache()
    try:
        yield calls
    finally:
        del sys.modules["ZZ_fake_metadata_node"]
        registry.clear_metadata_cache()
        utils.clear_resolve_node_obj_cache()


def test_metadata_is_built_once_per_module(counting_node_module):
    first = registry.get_metadata("ZZ_fake_metadata_node")
    for _ in range(10):
        registry.get_metadata("ZZ_fake_metadata_node.FakeNode")
    assert counting_node_module["n"] == 1
    # Same object handed back, not a rebuilt copy.
    assert registry.get_metadata("ZZ_fake_metadata_node") is first


def test_clear_metadata_cache_forces_a_rebuild(counting_node_module):
    registry.get_metadata("ZZ_fake_metadata_node")
    registry.clear_metadata_cache()
    registry.get_metadata("ZZ_fake_metadata_node")
    assert counting_node_module["n"] == 2


def test_kwarg_helpers_do_not_rebuild_metadata(counting_node_module):
    """The whole point: a per-frame kwarg lookup costs no metadata rebuild."""
    for _ in range(5):
        assert utils.reqKwargsFromFunction("ZZ_fake_metadata_node.FakeNode") == ["alpha"]
        assert utils.optKwargsFromFunction("ZZ_fake_metadata_node.FakeNode") == ["beta"]
    assert counting_node_module["n"] == 1


def test_display_name_prefers_display_text(counting_node_module):
    assert utils.displayNameFromKwarg("ZZ_fake_metadata_node.FakeNode", "beta") == "Beta value"
    # No display_text declared -> the raw kwarg name.
    assert utils.displayNameFromKwarg("ZZ_fake_metadata_node.FakeNode", "alpha") == "alpha"


def test_helpers_are_tolerant_of_an_unusable_name(counting_node_module):
    assert utils.reqKwargsFromFunction("ZZ_fake_metadata_node.NoSuchFunction") == []
    assert utils.optKwargsFromFunction("ZZ_fake_metadata_node.NoSuchFunction") == []
    assert utils.displayNameFromKwarg("ZZ_fake_metadata_node.NoSuchFunction", "beta") == "beta"


def test_real_nodes_still_report_their_kwargs():
    """Regression guard against the blob-and-regex behaviour this replaced."""
    assert utils.reqKwargsFromFunction("FFT_im.RealTimeFFT") == []
    assert utils.optKwargsFromFunction("FFT_im.RealTimeFFT") == [
        "LogScale", "WindowTaper", "WindowTaperStrength",
    ]
    # display_text values contain spaces; the old regex captured whole lines.
    assert utils.displayNameFromKwarg(
        "Strobo_lasers.set_strobo_lasers", "pulse_frames_405"
    ) == "405 nm - Which frames on?"
    strobo_req = utils.reqKwargsFromFunction("Strobo_lasers.set_strobo_lasers")
    assert "pulse_len_405" in strobo_req and "power_pct_750" in strobo_req
