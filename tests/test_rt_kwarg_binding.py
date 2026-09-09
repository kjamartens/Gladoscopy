"""Tests for T-G2: node kwargs are coerced once, at bind time, using the type
declared in `__function_metadata__`.

Before this, `"type"` only picked a widget class: the value travelled as a
string, was re-quoted into a Python string literal on every frame, and was
re-parsed inside the node body. Notably `LogScale="False"` is a *truthy string*,
so an unchecked bool kwarg still read as True inside a node doing a bare
`if self.log_scale:`.
"""
from __future__ import annotations

import sys
import types

import pytest

import glados_pycromanager.AutonomousMicroscopy.Real_Time_Analysis.FFT_im  # noqa: F401
import glados_pycromanager.GUI.utils as utils
from glados_pycromanager.autonomous import registry
from glados_pycromanager.errors import NodeDispatchError

NODE = "ZZ_bind_node.FakeNode"


class FakeBoundNode:
    def __init__(self, core, **kwargs):
        self.core = core
        self.kwargs = kwargs


@pytest.fixture
def fake_node():
    """A registered node module with one kwarg of each interesting type."""
    mod = types.ModuleType("ZZ_bind_node")

    def __function_metadata__():
        return {
            "FakeNode": {
                "required_kwargs": [
                    {"name": "Count", "description": "n", "type": int},
                ],
                "optional_kwargs": [
                    {"name": "Enabled", "description": "on/off", "default": True, "type": bool},
                    {"name": "Strength", "description": "s", "default": 0.25, "type": float},
                    {"name": "Label", "description": "l", "default": "x", "type": str},
                    {"name": "Untyped", "description": "u", "default": "x"},
                ],
                "help_string": "fake",
                "input": [],
                "output": [],
            }
        }

    mod.__function_metadata__ = __function_metadata__
    mod.FakeNode = FakeBoundNode
    sys.modules["ZZ_bind_node"] = mod
    registry._REGISTRY[NODE] = FakeBoundNode
    registry.clear_metadata_cache()
    utils.clear_resolve_node_obj_cache()
    try:
        yield mod
    finally:
        del sys.modules["ZZ_bind_node"]
        registry._REGISTRY.pop(NODE, None)
        registry.clear_metadata_cache()
        utils.clear_resolve_node_obj_cache()


def _bind(*args, **kwargs):
    """bindKwargsFromGUIFunction(...).resolve() -- the dict the node is called with."""
    bound = utils.bindKwargsFromGUIFunction(*args, **kwargs)
    return None if bound is None else bound.resolve()


def _current_data(**overrides):
    data = {
        "__selectedDropdownEntryRTAnalysis__": "Fake node",
        "__displayNameFunctionNameMap__": [("Fake node", NODE)],
        f"LineEdit#{NODE}#Count": "7",
        f"LineEdit#{NODE}#Enabled": "False",
        f"LineEdit#{NODE}#Strength": "0.75",
        f"LineEdit#{NODE}#Label": "hello",
        f"LineEdit#{NODE}#Untyped": "42",
    }
    data.update(overrides)
    return data


# --- coerceKwargValue ------------------------------------------------------

@pytest.mark.parametrize("text,expected", [
    ("True", True), ("true", True), ("1", True), ("yes", True),
    ("False", False), ("false", False), ("0", False), ("no", False),
])
def test_bool_strings_coerce(text, expected):
    assert utils.coerceKwargValue(text, bool) is expected


def test_int_and_float_coerce():
    assert utils.coerceKwargValue("7", int) == 7
    assert utils.coerceKwargValue(" 0.75 ", float) == 0.75


def test_str_and_fileloc_are_left_alone():
    assert utils.coerceKwargValue("C:/data/x.tif", str) == "C:/data/x.tif"
    assert utils.coerceKwargValue("C:/data/x.tif", 'fileLoc') == "C:/data/x.tif"
    assert utils.coerceKwargValue("anything", None) == "anything"


def test_unparseable_value_falls_back_to_the_original_string(caplog):
    with caplog.at_level("WARNING"):
        assert utils.coerceKwargValue("not-a-number", float, "Strength", "Node") == "not-a-number"
    assert "Strength" in caplog.text


def test_non_strings_pass_through_untouched():
    sentinel = object()
    assert utils.coerceKwargValue(sentinel, float) is sentinel
    assert utils.coerceKwargValue(3, int) == 3


# --- bindKwargsFromGUIFunction --------------------------------------------

def test_bound_kwargs_carry_declared_types(fake_node):
    names, values = ["Count", "Enabled", "Strength", "Label", "Untyped"], ["7", "False", "0.75", "hello", "42"]
    bound = _bind(NODE, names, values, skipInput=True)
    assert bound == {"Count": 7, "Enabled": False, "Strength": 0.75,
                     "Label": "hello", "Untyped": "42"}
    assert bound["Enabled"] is False
    assert isinstance(bound["Strength"], float)


def test_missing_required_value_returns_none(fake_node):
    bound = _bind(NODE, ["Count"], [""], skipInput=True)
    assert bound is None


def test_optional_kwarg_the_gui_never_supplied_is_simply_absent(fake_node):
    """The eval-text path indexes methodKwargValues positionally here, so a
    kwarg missing from the GUI dict is an IndexError rather than a fallback to
    the node's own default. The binder looks kwargs up by name."""
    bound = _bind(NODE, ["Count", "Enabled"], ["7", "True"], skipInput=True)
    assert bound == {"Count": 7, "Enabled": True}


def test_empty_optional_value_is_skipped(fake_node):
    bound = _bind(
        NODE, ["Count", "Strength"], ["7", ""], skipInput=True)
    assert bound == {"Count": 7}


def test_variable_mode_values_are_resolved_not_coerced(fake_node):
    class _Node:
        variablesNodz = {"myvar": {"data": 12.5}}

    class _NodzInfo:
        nodes = []
        globalVariables = {"gvar": {"data": 99}}
        coreVariables = {}

    bound = _bind(
        NODE, ["Count", "Strength"], ["7", "gvar@Global"],
        methodKwargTypes=["Value", "Variable"], skipInput=True,
        nodzInfo=_NodzInfo(), nodeDict={"OtherNode": _Node()})
    assert bound == {"Count": 7, "Strength": 99}


def test_variable_from_another_node_is_read_live(fake_node):
    class _Node:
        variablesNodz = {"myvar": {"data": 12.5}}

    bound = _bind(
        NODE, ["Count", "Strength"], ["7", "myvar@OtherNode"],
        methodKwargTypes=["Value", "Variable"], skipInput=True,
        nodzInfo=None, nodeDict={"OtherNode": _Node()})
    assert bound == {"Count": 7, "Strength": 12.5}


# --- the currentData scanner and realTimeAnalysis_init ---------------------

def test_scanner_picks_the_widget_the_mode_switch_selects(fake_node):
    data = _current_data(**{
        f"ComboBoxSwitch#{NODE}#Strength": "Variable",
        f"LineEditVariable#{NODE}#Strength": "gvar@Global",
    })
    _method, names, values, modes = utils._rtAnalysisKwargsFromCurrentData(NODE, data)
    picked = dict(zip(names, values))
    assert picked["Strength"] == "gvar@Global"
    assert modes[names.index("Strength")] == "Variable"
    assert modes[names.index("Count")] == "Value"


def test_init_dispatches_with_typed_kwargs(fake_node):
    node = utils.realTimeAnalysis_init(_current_data(), core="CORE")
    assert isinstance(node, FakeBoundNode)
    assert node.core == "CORE"
    assert node.kwargs == {"Count": 7, "Enabled": False, "Strength": 0.75,
                           "Label": "hello", "Untyped": "42"}


def test_init_raises_a_clear_error_when_a_required_kwarg_is_empty(fake_node):
    data = _current_data(**{f"LineEdit#{NODE}#Count": ""})
    with pytest.raises(NodeDispatchError):
        utils.realTimeAnalysis_init(data, core=None)


def test_real_fft_node_binds_its_declared_types():
    rt_info = {
        "__selectedDropdownEntryRTAnalysis__": "Real-Time FFT",
        "__displayNameFunctionNameMap__": [("Real-Time FFT", "FFT_im.RealTimeFFT")],
        "LineEdit#FFT_im.RealTimeFFT#LogScale": "False",
        "LineEdit#FFT_im.RealTimeFFT#WindowTaper": "True",
        "LineEdit#FFT_im.RealTimeFFT#WindowTaperStrength": "0.4",
    }
    _method, names, values, modes = utils._rtAnalysisKwargsFromCurrentData(
        "FFT_im.RealTimeFFT", rt_info)
    bound = _bind("FFT_im.RealTimeFFT", names, values,
                                            methodKwargTypes=modes, skipInput=True)
    assert bound == {"LogScale": False, "WindowTaper": True, "WindowTaperStrength": 0.4}


def test_unresolvable_variable_falls_back_to_the_reference_text(fake_node, caplog):
    """An RT node started outside the graph (nodzInfo=None) must not crash on a
    Variable-mode kwarg -- it gets the raw reference text, as before."""
    with caplog.at_level("WARNING"):
        bound = _bind(
            NODE, ["Count", "Strength"], ["7", "gvar@Global"],
            methodKwargTypes=["Value", "Variable"], skipInput=True, nodzInfo=None)
    assert bound == {"Count": 7, "Strength": "gvar@Global"}
    assert "Strength" in caplog.text


# --- T-G3: Variable kwargs are closures, not values captured at bind time ---

class _LiveNodz:
    def __init__(self):
        self.nodes = []
        self.globalVariables = {"gvar": {"data": 1}}
        self.coreVariables = {}


def test_variable_kwargs_are_read_live_not_captured(fake_node):
    nodz = _LiveNodz()
    bound = utils.bindKwargsFromGUIFunction(
        NODE, ["Count", "Strength"], ["7", "gvar@Global"],
        methodKwargTypes=["Value", "Variable"], skipInput=True, nodzInfo=nodz)
    assert bound.resolve()["Strength"] == 1
    # The writer replaces the whole per-variable dict, then fills it in --
    # capturing one level deeper than the container would go stale here.
    nodz.globalVariables["gvar"] = {}
    nodz.globalVariables["gvar"]["data"] = 42
    assert bound.resolve()["Strength"] == 42


def test_a_node_variable_is_read_live_too(fake_node):
    class _Node:
        def __init__(self):
            self.variablesNodz = {"myvar": {"data": 1.5}}

    origin = _Node()
    bound = utils.bindKwargsFromGUIFunction(
        NODE, ["Count", "Strength"], ["7", "myvar@OtherNode"],
        methodKwargTypes=["Value", "Variable"], skipInput=True,
        nodzInfo=None, nodeDict={"OtherNode": origin})
    assert bound.resolve()["Strength"] == 1.5
    origin.variablesNodz["myvar"] = {"data": 9.5}
    assert bound.resolve()["Strength"] == 9.5


def test_resolve_without_variables_avoids_a_copy(fake_node):
    """The per-frame path resolves on every call; with no Variable kwargs that
    must not allocate a fresh dict each time."""
    bound = utils.bindKwargsFromGUIFunction(NODE, ["Count"], ["7"], skipInput=True)
    assert bound.variableGetters == {}
    assert bound.resolve() is bound.resolve()
