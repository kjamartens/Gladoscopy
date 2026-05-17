"""Tests for `glados_pycromanager.autonomous.recipe_io`.

The module's two functions are thin glue over `QFileDialog` plus the
inherited Nodz `saveGraph` / `loadGraph_KM`. We don't have a checked-in
example recipe to round-trip, so these tests patch the file-dialog
calls and the Nodz methods to verify the glue contracts: dialog
invocation, `.json` suffix coercion, counter reset on load, status
message on success, message-box on failure.
"""
from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from glados_pycromanager.autonomous import recipe_io


@pytest.fixture
def fake_flowchart() -> MagicMock:
    """Return a `MagicMock` shaped like the dock widget the module expects."""
    fc = MagicMock()
    fc.nodes = ["existing-node"]
    fc.nodeInfo = {
        "__init__": {"NodeCounter": 5, "NodeCounterNeverReset": 5},
        "AnalysisNode": {"NodeCounter": 7, "NodeCounterNeverReset": 11},
        "MMConfigNode": {"NodeCounter": 2, "NodeCounterNeverReset": 4},
    }
    fc.shared_data = SimpleNamespace(
        warningErrorInfoInfo={"Info": {"Other": []}},
    )
    return fc


def test_store_graph_json_no_filename_is_noop(monkeypatch, fake_flowchart):
    monkeypatch.setattr(
        recipe_io.QFileDialog,
        "getSaveFileName",
        lambda *a, **kw: ("", "*.json"),
    )
    recipe_io.store_graph_json(fake_flowchart)
    fake_flowchart.saveGraph.assert_not_called()


def test_store_graph_json_passes_filename_to_savegraph(monkeypatch, fake_flowchart, tmp_path):
    target = tmp_path / "recipe.json"
    monkeypatch.setattr(
        recipe_io.QFileDialog,
        "getSaveFileName",
        lambda *a, **kw: (str(target), "*.json"),
    )
    recipe_io.store_graph_json(fake_flowchart)
    fake_flowchart.saveGraph.assert_called_once_with(str(target))


def test_store_graph_json_appends_json_suffix(monkeypatch, fake_flowchart, tmp_path):
    target = tmp_path / "recipe_without_suffix"
    monkeypatch.setattr(
        recipe_io.QFileDialog,
        "getSaveFileName",
        lambda *a, **kw: (str(target), "*.json"),
    )
    recipe_io.store_graph_json(fake_flowchart)
    args, _ = fake_flowchart.saveGraph.call_args
    assert args[0].endswith(".json")


def test_load_graph_json_no_filename_is_noop(monkeypatch, fake_flowchart):
    monkeypatch.setattr(
        recipe_io.QFileDialog,
        "getOpenFileName",
        lambda *a, **kw: ("", "*.json"),
    )
    recipe_io.load_graph_json(fake_flowchart)
    fake_flowchart.clearGraph.assert_not_called()
    fake_flowchart.loadGraph_KM.assert_not_called()


def test_load_graph_json_resets_counters_and_loads(monkeypatch, fake_flowchart, tmp_path):
    target = tmp_path / "in.json"
    target.write_text("{}", encoding="utf-8")
    monkeypatch.setattr(
        recipe_io.QFileDialog,
        "getOpenFileName",
        lambda *a, **kw: (str(target), "*.json"),
    )
    recipe_io.load_graph_json(fake_flowchart)

    fake_flowchart.clearGraph.assert_called_once_with()
    assert fake_flowchart.nodes == []
    # internal "__init__" entry must be left alone
    assert fake_flowchart.nodeInfo["__init__"]["NodeCounter"] == 5
    # every non-internal type must be reset
    assert fake_flowchart.nodeInfo["AnalysisNode"]["NodeCounter"] == 0
    assert fake_flowchart.nodeInfo["AnalysisNode"]["NodeCounterNeverReset"] == 0
    assert fake_flowchart.nodeInfo["MMConfigNode"]["NodeCounter"] == 0
    assert fake_flowchart.nodeInfo["MMConfigNode"]["NodeCounterNeverReset"] == 0
    fake_flowchart.loadGraph_KM.assert_called_once_with(str(target))
    assert fake_flowchart.shared_data.warningErrorInfoInfo["Info"]["Other"] == [
        "Loaded " + str(target),
    ]


def test_load_graph_json_pops_warning_dialog_on_failure(monkeypatch, fake_flowchart, tmp_path):
    target = tmp_path / "broken.json"
    target.write_text("{}", encoding="utf-8")
    monkeypatch.setattr(
        recipe_io.QFileDialog,
        "getOpenFileName",
        lambda *a, **kw: (str(target), "*.json"),
    )
    fake_flowchart.loadGraph_KM.side_effect = ValueError("boom")

    seen = {}

    class _StubMessageBox:
        Warning = object()
        Ok = object()

        def __init__(self):
            seen["constructed"] = True

        def setIcon(self, icon):
            seen["icon"] = icon

        def setText(self, text):
            seen["text"] = text

        def setWindowTitle(self, title):
            seen["title"] = title

        def setStandardButtons(self, buttons):
            seen["buttons"] = buttons

        def exec_(self):
            seen["execed"] = True

    monkeypatch.setattr(recipe_io, "QMessageBox", _StubMessageBox)
    recipe_io.load_graph_json(fake_flowchart)

    assert seen.get("execed") is True
    assert "broken.json" in seen.get("text", "")
