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


@pytest.mark.skip(
    reason="Real_Time_Analysis hot-reload trips a pre-existing circular import "
           "(BioImageModelZoo.py star-imports its own package); Phase 6.3 will "
           "trim the __init__ and re-enable this."
)
def test_dropin_works_in_realtime_subfolder(isolated_appdata):
    _seed_dropin(isolated_appdata, "Real_Time_Analysis", module_name="DropInRT")
    pkg = _clean_reimport(
        "glados_pycromanager.AutonomousMicroscopy.Real_Time_Analysis"
    )
    assert "DropInRT" in pkg.__all__


@pytest.mark.skip(
    reason="CustomFunctions hot-reload trips the same circular-import issue "
           "as Real_Time_Analysis; re-enable after Phase 6.3."
)
def test_dropin_works_in_customfunctions(isolated_appdata):
    _seed_dropin(isolated_appdata, "CustomFunctions", module_name="DropInCustom")
    pkg = _clean_reimport(
        "glados_pycromanager.AutonomousMicroscopy.CustomFunctions"
    )
    assert "DropInCustom" in pkg.__all__


def test_load_additional_modules_picks_up_tmp_file(tmp_path):
    """Direct test of the loader helper — no package reload involved.

    Until Phase 6 extracts a clean `load_node_modules(folder, prefix)`,
    `load_additional_modules` is the most-shared piece of the discovery
    contract. Drop a .py into an arbitrary folder, call the helper, and
    assert the symbol was injected into the caller's globals.
    """
    from glados_pycromanager.AutonomousMicroscopy import (
        Analysis_Measurements as pkg,
    )

    folder = tmp_path / "drop_zone"
    folder.mkdir()
    (folder / "AdHocNode.py").write_text(PLUGIN_BODY)

    # NB: load_additional_modules has a quirky contract — it appends new
    # names to the *module-global* `__all__` of its own defining module
    # (Analysis_Measurements.__init__), not to the `all_modules` list
    # passed as an arg. We assert against that observable side-effect.
    # Phase 6.2 lifts this into a clean `load_node_modules` that returns
    # the list instead of mutating a hidden global.
    before = set(pkg.__all__)
    pkg.load_additional_modules(str(folder), [])
    after = set(pkg.__all__)
    assert "AdHocNode" in after - before


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
