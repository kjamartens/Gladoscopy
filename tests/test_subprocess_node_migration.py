"""T-G10: guards for RT-analysis nodes that run in a separate process.

A subprocess-isolated node's `visualise()` runs against a *shadow* instance in
the main process (a napari layer cannot cross a process boundary), refreshed only
from the attributes the node declares in `"__snapshot_attrs__"` (T-G5). So any
attribute `visualise()` reads that `run()` produces **must** be declared, or the
overlay silently freezes at whatever `__init__` left there -- a failure with no
error message anywhere.

That is checked here by reading each node's own source, so it holds for every
node without needing a live napari layer, a microscope, or a spawned worker.
"""
from __future__ import annotations

import ast
import inspect
import textwrap

import pytest

import glados_pycromanager.AutonomousMicroscopy.Real_Time_Analysis as rt_pkg
import glados_pycromanager.GUI.utils as utils


def _self_attributes(func, ctx):
    """Names of `self.<attr>` used in `func` under the given AST context."""
    try:
        source = textwrap.dedent(inspect.getsource(func))
    except (OSError, TypeError):
        return set()
    tree = ast.parse(source)
    return {
        node.attr
        for node in ast.walk(tree)
        if isinstance(node, ast.Attribute)
        and isinstance(node.value, ast.Name)
        and node.value.id == 'self'
        and isinstance(node.ctx, ctx)
    }


def _rt_nodes():
    """(dotted name, class, metadata entry) for every shipped RT-analysis node."""
    found = []
    for module_name in dir(rt_pkg):
        module = getattr(rt_pkg, module_name)
        meta_fn = getattr(module, '__function_metadata__', None)
        if not callable(meta_fn) or not isinstance(getattr(module, '__name__', None), str):
            continue
        stem = module.__name__.rsplit('.', 1)[-1]
        for fn_name, entry in meta_fn().items():
            node_cls = getattr(module, fn_name, None)
            if node_cls is not None:
                found.append((f"{stem}.{fn_name}", node_cls, entry))
    return found


def _isolated_nodes():
    return [(name, cls, entry) for name, cls, entry in _rt_nodes()
            if entry.get('__runInSubprocess__') and not entry.get('__needsLiveCore__')]


def _rt_info(dotted):
    return {
        "__selectedDropdownEntryRTAnalysis__": dotted,
        "__displayNameFunctionNameMap__": [(dotted, dotted)],
    }


def test_the_shipped_node_set_is_what_we_think_it_is():
    names = {name for name, _cls, _entry in _rt_nodes()}
    assert {"FFT_im.RealTimeFFT", "SharpnessValue.SharpnessValue",
            "EndAtFrame.EndAtFrame", "LaserAdjustment.laser_adjustment"} <= names


@pytest.mark.parametrize("dotted,node_cls,entry", _isolated_nodes(),
                         ids=[name for name, _c, _e in _isolated_nodes()])
def test_isolated_nodes_declare_what_visualise_reads_from_run(dotted, node_cls, entry):
    """The one failure mode subprocess isolation introduces, caught statically."""
    visualise = getattr(node_cls, 'visualise', None)
    if visualise is None:
        pytest.skip(f"{dotted} has no visualise()")
    produced_by_run = _self_attributes(getattr(node_cls, 'run'), ast.Store)
    read_by_visualise = _self_attributes(visualise, ast.Load)
    declared = set(entry.get('__snapshot_attrs__', []))
    missing = (produced_by_run & read_by_visualise) - declared
    assert not missing, (
        f"{dotted}: visualise() reads {sorted(missing)}, which run() writes in the "
        f"child process. Add them to __snapshot_attrs__ or the overlay freezes."
    )


@pytest.mark.parametrize("dotted,node_cls,entry", _isolated_nodes(),
                         ids=[name for name, _c, _e in _isolated_nodes()])
def test_isolated_nodes_do_not_touch_live_context_in_run(dotted, node_cls, entry):
    """`core`, `shared_data` and `nodzInfo` are all None inside the child. A node
    that reads one of them in run() must declare __needsLiveCore__ instead."""
    source = textwrap.dedent(inspect.getsource(getattr(node_cls, 'run')))
    tree = ast.parse(source)
    forbidden = {'shared_data', 'core'}
    used = {
        node.value.id
        for node in ast.walk(tree)
        if isinstance(node, ast.Attribute)
        and isinstance(node.value, ast.Name)
        and node.value.id in forbidden
    }
    assert not used, (
        f"{dotted}: run() reads {sorted(used)}, which is None in the child process. "
        f"Declare __needsLiveCore__, or read the equivalent from the frame metadata."
    )


@pytest.mark.parametrize("dotted,_cls,_entry", _isolated_nodes(),
                         ids=[name for name, _c, _e in _isolated_nodes()])
def test_isolated_nodes_actually_route_to_the_subprocess_path(dotted, _cls, _entry):
    assert utils.realTimeAnalysis_runInSubprocess(_rt_info(dotted)) is True


def test_sharpness_value_is_isolated_and_mirrors_its_metric():
    entry = dict(_rt_nodes_by_name()["SharpnessValue.SharpnessValue"])
    assert entry.get('__runInSubprocess__') is True
    assert utils.realTimeAnalysis_snapshotAttrs(
        _rt_info("SharpnessValue.SharpnessValue")) == ["currentValue"]


def _rt_nodes_by_name():
    return {name: entry for name, _cls, entry in _rt_nodes()}
