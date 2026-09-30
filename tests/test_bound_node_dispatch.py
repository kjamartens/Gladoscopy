"""Tests for T-G4: RT-analysis dispatch is bound once, not eval'ed per frame.

`realTimeAnalysis_run` used to rebuild a Python call expression from the kwarg
dict and `eval()` it on every analysed frame; `realTimeAnalysis_visualisation`
did the same on the GUI thread. Both now call the node's method directly with a
kwargs dict resolved once (`BoundNode`), rebinding only when the parameter panel
actually changed.
"""
from __future__ import annotations

import sys
import types

import pytest

import glados_pycromanager.GUI.utils as utils
from glados_pycromanager.autonomous import registry

NODE = "ZZ_dispatch_node.FakeNode"


class RecordingNode:
    def __init__(self, core, **kwargs):
        self.core = core
        self.initKwargs = kwargs
        self.calls = []

    def run(self, image, metadata, shared_data, core, **kwargs):
        self.calls.append(("run", image, metadata, shared_data, core, kwargs))
        return "ran"

    def end(self, core, **kwargs):
        self.calls.append(("end", core, kwargs))
        return "ended"

    def visualise(self, image, metadata, core, napariLayer, **kwargs):
        self.calls.append(("visualise", image, metadata, core, napariLayer, kwargs))
        return "visualised"


@pytest.fixture
def fake_node():
    mod = types.ModuleType("ZZ_dispatch_node")

    def __function_metadata__():
        return {
            "FakeNode": {
                "required_kwargs": [
                    {"name": "Count", "description": "n", "type": int},
                ],
                "optional_kwargs": [
                    {"name": "Enabled", "description": "e", "default": True, "type": bool},
                ],
                "help_string": "fake",
                "input": [],
                "output": [],
            }
        }

    mod.__function_metadata__ = __function_metadata__
    mod.FakeNode = RecordingNode
    sys.modules["ZZ_dispatch_node"] = mod
    registry._REGISTRY[NODE] = RecordingNode
    registry.clear_metadata_cache()
    utils.clear_resolve_node_obj_cache()
    try:
        yield mod
    finally:
        del sys.modules["ZZ_dispatch_node"]
        registry._REGISTRY.pop(NODE, None)
        registry.clear_metadata_cache()
        utils.clear_resolve_node_obj_cache()


def _current_data(**overrides):
    data = {
        "__selectedDropdownEntryRTAnalysis__": "Fake node",
        "__displayNameFunctionNameMap__": [("Fake node", NODE)],
        f"LineEdit#{NODE}#Count": "3",
        f"LineEdit#{NODE}#Enabled": "True",
    }
    data.update(overrides)
    return data


def test_run_end_and_visualise_call_the_node_directly(fake_node):
    info = _current_data()
    node = utils.realTimeAnalysis_init(info, core="CORE")

    assert utils.realTimeAnalysis_run(node, info, "IMG", "META", "SHARED", None) == "ran"
    assert utils.realTimeAnalysis_visualisation(node, info, "IMG", "META", None, "LAYER") == "visualised"
    assert utils.realTimeAnalysis_end(node, info, "CORE") == "ended"

    kinds = [call[0] for call in node.calls]
    assert kinds == ["run", "visualise", "end"]
    assert node.calls[0][1:5] == ("IMG", "META", "SHARED", None)
    assert node.calls[0][5] == {"Count": 3, "Enabled": True}
    assert node.calls[1][1:5] == ("IMG", "META", None, "LAYER")
    assert node.calls[2][1] == "CORE"
    assert node.calls[2][2] == {"Count": 3, "Enabled": True}


def test_the_binding_is_built_once_across_many_frames(fake_node, monkeypatch):
    info = _current_data()
    node = utils.realTimeAnalysis_init(info, core=None)

    builds = {"n": 0}
    real_build = utils.buildBoundNode

    def counting_build(*args, **kwargs):
        builds["n"] += 1
        return real_build(*args, **kwargs)

    monkeypatch.setattr(utils, "buildBoundNode", counting_build)
    for _ in range(50):
        utils.realTimeAnalysis_run(node, info, "IMG", "META", None, None)
    assert builds["n"] == 0  # init already bound it; no per-frame rebuild


def test_editing_a_parameter_mid_run_is_picked_up(fake_node):
    """currentData is mutated in place by the parameter panel; a cached binding
    must not freeze the values the user sees."""
    info = _current_data()
    node = utils.realTimeAnalysis_init(info, core=None)
    utils.realTimeAnalysis_run(node, info, "IMG", "META", None, None)
    assert node.calls[-1][5] == {"Count": 3, "Enabled": True}

    info[f"LineEdit#{NODE}#Count"] = "9"
    utils.realTimeAnalysis_run(node, info, "IMG", "META", None, None)
    assert node.calls[-1][5] == {"Count": 9, "Enabled": True}


def test_a_variable_kwarg_is_re_read_every_frame(fake_node):
    class _Nodz:
        nodes = []
        globalVariables = {"gvar": {"data": 1}}
        coreVariables = {}

    nodz = _Nodz()
    info = _current_data(**{
        f"ComboBoxSwitch#{NODE}#Count": "Variable",
        f"LineEditVariable#{NODE}#Count": "gvar@Global",
    })
    node = utils.realTimeAnalysis_init(info, core=None, nodzInfo=nodz)
    utils.realTimeAnalysis_run(node, info, "IMG", "META", None, None, nodzInfo=nodz)
    assert node.calls[-1][5]["Count"] == 1

    nodz.globalVariables["gvar"] = {"data": 7}
    utils.realTimeAnalysis_run(node, info, "IMG", "META", None, None, nodzInfo=nodz)
    assert node.calls[-1][5]["Count"] == 7


def test_the_eval_fallback_produces_the_same_call(fake_node):
    """GLADOS_RT_EVAL_DISPATCH=1 restores the pre-T-G4 path; it must still work."""
    info = _current_data()
    node = utils.realTimeAnalysis_init(info, core=None)
    assert utils._realTimeAnalysis_run_viaEval(node, info, "IMG", "META", "SHARED", None) == "ran"
    # The eval path re-quotes every value as a string literal - that difference
    # is exactly what T-G2 fixed, and why the fallback is a fallback.
    assert node.calls[-1][1:5] == ("IMG", "META", "SHARED", None)
    assert node.calls[-1][5] == {"Count": "3", "Enabled": "True"}


def test_bound_node_never_crosses_the_subprocess_boundary(fake_node):
    """The binding is stashed on the node instance, and the subprocess worker
    pickles every plain-data attribute of that instance back per frame. A dict
    or tuple here would ship the whole binding on every frame."""
    from glados_pycromanager.GUI.AnalysisClass import _SUBPROCESS_SNAPSHOT_TYPES

    info = _current_data()
    node = utils.realTimeAnalysis_init(info, core=None)
    snapshot = {k: v for k, v in vars(node).items()
                if isinstance(v, _SUBPROCESS_SNAPSHOT_TYPES)}
    assert utils._BOUND_NODE_ATTR in vars(node)
    assert utils._BOUND_NODE_ATTR not in snapshot


def test_a_slots_node_still_dispatches(fake_node):
    """A node that cannot carry the attribute just rebinds per call."""
    class SlotsNode:
        __slots__ = ('core', 'seen')

        def __init__(self, core, **kwargs):
            self.core = core
            self.seen = []

        def run(self, image, metadata, shared_data, core, **kwargs):
            self.seen.append(kwargs)
            return "ran"

    node = SlotsNode(None)
    info = _current_data()
    assert utils.realTimeAnalysis_run(node, info, "IMG", "META", None, None) == "ran"
    assert node.seen[-1] == {"Count": 3, "Enabled": True}


# --- every shipped RT-analysis node binds ---------------------------------

def _all_rt_node_functions():
    """(dotted name, metadata entry) for every function every RT node declares."""
    import glados_pycromanager.AutonomousMicroscopy.Real_Time_Analysis as rt_pkg

    found = []
    for module_name in dir(rt_pkg):
        module = getattr(rt_pkg, module_name)
        meta_fn = getattr(module, '__function_metadata__', None)
        if not callable(meta_fn) or not isinstance(getattr(module, '__name__', None), str):
            continue
        stem = module.__name__.rsplit('.', 1)[-1]
        for fn_name, entry in meta_fn().items():
            found.append((f"{stem}.{fn_name}", entry))
    return found


def test_every_shipped_rt_node_binds_from_its_declared_defaults():
    """Proxy for the manual "run every node once" check: each node's kwargs bind
    to the declared types from a GUI-shaped currentData built from its defaults."""
    functions = _all_rt_node_functions()
    assert len(functions) >= 7, f"expected the shipped RT nodes, found {functions}"

    for dotted, entry in functions:
        currentData = {
            "__selectedDropdownEntryRTAnalysis__": dotted,
            "__displayNameFunctionNameMap__": [(dotted, dotted)],
        }
        declared = {}
        for listName in ('required_kwargs', 'optional_kwargs'):
            for kwarg in entry.get(listName, []):
                currentData[f"LineEdit#{dotted}#{kwarg['name']}"] = str(kwarg.get('default', '1'))
                if 'type' in kwarg:
                    declared[kwarg['name']] = kwarg['type']

        bound = utils.buildBoundNode(currentData)
        assert bound.className == dotted
        assert bound.kwargs is not None, f"{dotted} failed to bind"
        resolved = bound.kwargs.resolve()
        for name in (kwarg['name'] for kwarg in entry.get('required_kwargs', [])):
            assert name in resolved, f"{dotted} lost required kwarg {name}"
        for name, declaredType in declared.items():
            if name in resolved and isinstance(declaredType, type) and declaredType is not str:
                assert isinstance(resolved[name], declaredType), (
                    f"{dotted}.{name} bound as {type(resolved[name])}, expected {declaredType}")
