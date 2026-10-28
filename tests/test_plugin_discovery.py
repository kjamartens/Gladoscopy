"""Verify autonomous-microscopy nodes drop into AppData and load.

This locks in the discovery contract described in ADR 0002 — a `.py`
dropped into the per-user AppData folder gets imported by the matching
subpackage and its top-level symbols become reachable. Phase 6 will
extract this into `glados_pycromanager/plugins/discovery.py`; until
then we test the current `__init__.py`-driven loader by clean-importing
the subpackage with a monkeypatched `appdirs.user_data_dir`.
"""
from __future__ import annotations

import importlib
import sys
import textwrap
from pathlib import Path

import pytest


PLUGIN_BODY = textwrap.dedent(
    '''
    """Drop-in test plugin for tests/test_plugin_discovery."""

    def __function_metadata__():
        return {
            "DropInNode": {
                "name": "DropInNode",
                "displayName": "Drop-In Node",
                "kwargs": {},
            }
        }


    def DropInNode(**kwargs):
        return "dropin-ran"
    '''
).strip()


def _seed_dropin(appdata_root: Path, subfolder: str, module_name: str = "DropInNode") -> Path:
    """Write a single .py into the AppData subfolder the loader walks."""
    target_dir = appdata_root / "Glados-PycroManager" / "AutonomousMicroscopy" / subfolder
    target_dir.mkdir(parents=True, exist_ok=True)
    plugin = target_dir / f"{module_name}.py"
    plugin.write_text(PLUGIN_BODY)
    return plugin


def _clean_reimport(qualname: str):
    """Drop every cached `qualname[.*]` module then import qualname fresh."""
    for cached in list(sys.modules):
        if cached == qualname or cached.startswith(qualname + "."):
            del sys.modules[cached]
    return importlib.import_module(qualname)


@pytest.fixture
def isolated_appdata(tmp_path, monkeypatch):
    """Point both `appdirs` references at a tmp dir and clean up sys.modules."""
    root = tmp_path / "appdata"
    root.mkdir()
    monkeypatch.setattr("appdirs.user_data_dir", lambda *a, **kw: str(root))
    return root


def test_dropin_plugin_loads_from_appdata(isolated_appdata):
    plugin_path = _seed_dropin(isolated_appdata, "Analysis_Measurements")
    assert plugin_path.exists()

    pkg = _clean_reimport("glados_pycromanager.AutonomousMicroscopy.Analysis_Measurements")

    # AppData walk is now deferred — must call _load_appdata() explicitly
    # (mirrors what GladosNodzFlowChart_dockWidget.__init__ does at dock construction).
    pkg._load_appdata()

    # The discovery loader appends every discovered module to __all__ and
    # injects it into the package's globals dict.
    assert "DropInNode" in pkg.__all__
    assert hasattr(pkg, "DropInNode")
    fn = getattr(pkg, "DropInNode").DropInNode
    assert callable(fn)
    assert fn() == "dropin-ran"

    metadata = getattr(pkg, "DropInNode").__function_metadata__()
    assert "DropInNode" in metadata
    assert metadata["DropInNode"]["displayName"] == "Drop-In Node"


def test_dropin_works_in_realtime_subfolder(isolated_appdata):
    _seed_dropin(isolated_appdata, "Real_Time_Analysis", module_name="DropInRT")
    pkg = _clean_reimport(
        "glados_pycromanager.AutonomousMicroscopy.Real_Time_Analysis"
    )
    pkg._load_appdata()
    assert "DropInRT" in pkg.__all__


def test_dropin_works_in_customfunctions(isolated_appdata):
    _seed_dropin(isolated_appdata, "CustomFunctions", module_name="DropInCustom")
    pkg = _clean_reimport(
        "glados_pycromanager.AutonomousMicroscopy.CustomFunctions"
    )
    pkg._load_appdata()
    assert "DropInCustom" in pkg.__all__


def test_load_node_modules_picks_up_tmp_file(tmp_path):
    """Direct test of the Phase 6.2 helper — no package reload involved."""
    from glados_pycromanager.plugins.discovery import load_node_modules

    folder = tmp_path / "drop_zone"
    folder.mkdir()
    (folder / "AdHocNode.py").write_text(PLUGIN_BODY)
    (folder / "Broken.py").write_text("1 / 0  # raises ZeroDivisionError\n")

    modules, failures = load_node_modules(str(folder), prefix="")
    names = [m.__name__ for m in modules]
    assert "AdHocNode" in names
    # And the helper surfaces (rather than swallows) errors.
    assert any(f.module_name == "Broken" for f in failures)
    failed = next(f for f in failures if f.module_name == "Broken")
    assert isinstance(failed.error, ZeroDivisionError)


def test_log_failures_emits_warning_per_failure(tmp_path, caplog):
    """Phase 6.5 contract — failures are *not* silent."""
    import logging

    from glados_pycromanager.plugins.discovery import (
        load_node_modules,
        log_failures,
    )

    folder = tmp_path / "drop_zone"
    folder.mkdir()
    (folder / "Broken1.py").write_text("raise RuntimeError('boom1')\n")
    (folder / "Broken2.py").write_text("raise RuntimeError('boom2')\n")

    _, failures = load_node_modules(str(folder), prefix="")
    assert len(failures) == 2

    with caplog.at_level(logging.WARNING, logger="glados_pycromanager.plugins.discovery"):
        log_failures(failures)

    warning_lines = [r.message for r in caplog.records if r.levelno == logging.WARNING]
    assert any("Broken1" in m for m in warning_lines)
    assert any("Broken2" in m for m in warning_lines)
    # And no silent swallowing — the count matches.
    assert sum(1 for m in warning_lines if "Plugin load failed" in m) == 2


def test_missing_appdata_subfolder_is_created(isolated_appdata):
    # No pre-seeded plugin file; the loader still has to create the
    # AppData/.../Analysis_Measurements directory tree and not raise.
    pkg = _clean_reimport(
        "glados_pycromanager.AutonomousMicroscopy.Analysis_Measurements"
    )
    created_dir = (
        isolated_appdata
        / "Glados-PycroManager"
        / "AutonomousMicroscopy"
        / "Analysis_Measurements"
    )
    assert created_dir.is_dir()
    # And the package still exposes its ship-with-the-source nodes.
    assert "AverageImage" in pkg.__all__


def test_dropin_does_not_leak_across_test_runs(isolated_appdata, monkeypatch):
    # Re-import the subpackage *without* the drop-in present. The previous
    # test's `DropInNode` must not survive into __all__.
    pkg = _clean_reimport(
        "glados_pycromanager.AutonomousMicroscopy.Analysis_Measurements"
    )
    assert "DropInNode" not in pkg.__all__


RELOAD_NODE = textwrap.dedent(
    '''
    def __function_metadata__():
        return {"ReloadNode": {"required_kwargs": [%s], "optional_kwargs": [],
                               "help_string": "", "display_name": "Reload node"}}


    class ReloadNode:
        pass
    '''
)


def _kwarg(name):
    return '{"name": "%s", "default": 1, "type": int, "description": ""}' % name


@pytest.fixture
def fake_node_package(tmp_path, monkeypatch):
    """A node package whose AppData folder is `tmp_path`, as the only one reloaded.

    Reloading the real node tree would import TensorFlow (~2 min).
    """
    import types

    from glados_pycromanager.autonomous import registry
    from glados_pycromanager.plugins import discovery

    pkg = types.ModuleType("fake_reload_pkg")
    pkg.__all__ = []
    pkg._appdata_loaded = False
    pkg._SOURCE_DIR = None
    pkg._APPDATA_DIR = str(tmp_path)
    pkg._register = lambda mods: pkg.__all__.extend(m.__name__ for m in mods)
    monkeypatch.setitem(sys.modules, "fake_reload_pkg", pkg)
    monkeypatch.setattr(discovery, "_NODE_PACKAGES", ["fake_reload_pkg"])
    saved_registry = dict(registry._REGISTRY)
    yield tmp_path / "ReloadNode.py"
    for name in [n for n in sys.modules if n.split(".")[-1] == "ReloadNode"]:
        del sys.modules[name]
    registry._REGISTRY.clear()
    registry._REGISTRY.update(saved_registry)
    registry.clear_metadata_cache()
    from glados_pycromanager.GUI.utils import clear_resolve_node_obj_cache
    clear_resolve_node_obj_cache()


def test_reload_replaces_bare_stem_copy_of_appdata_node(fake_node_package):
    """The Controls dock's discovery (`functionNamesFromDir`) imports an AppData
    node as `sys.modules["ReloadNode"]`, which `_resolve_node_obj` checks first.
    A reload must replace that copy too, or the edited node's new kwargs never
    appear."""
    from glados_pycromanager.GUI import utils
    from glados_pycromanager.plugins.discovery import reload_all_node_modules

    node_file = fake_node_package
    node_file.write_text(RELOAD_NODE % _kwarg("a"))
    assert utils.functionNamesFromDir(str(node_file.parent))[0] == "ReloadNode.ReloadNode"
    assert "ReloadNode" in sys.modules
    assert utils.reqKwargsFromFunction("ReloadNode.ReloadNode") == ["a"]

    node_file.write_text(RELOAD_NODE % (_kwarg("a") + ", " + _kwarg("b")))
    n, failures = reload_all_node_modules()
    assert (n, failures) == (1, [])
    assert "ReloadNode" not in sys.modules
    assert utils.reqKwargsFromFunction("ReloadNode.ReloadNode") == ["a", "b"]


def test_reload_notifies_listeners(fake_node_package):
    from glados_pycromanager.plugins import discovery

    calls = []

    class Listener:
        def on_reload(self):
            calls.append(True)

    listener = Listener()
    discovery.add_reload_listener(listener.on_reload)
    discovery.reload_all_node_modules()
    assert calls == [True]
    del listener  # held weakly: a dropped listener is pruned, not called
    discovery.reload_all_node_modules()
    assert calls == [True]
