"""Regression: a state file missing a section must not stop the app starting.

`glados_state.json` holds three independent top-level sections -- `MDA`,
`MMControls`, `GlobalData` -- written by different code paths at different times.
Any of them can legitimately be absent: a fresh install has none, a section only
appears once its widgets have been saved at least once, and
`save_config_to_json` rebuilds the file with **only** `GlobalData` when the
previous one was unreadable.

Three loaders indexed their section directly, so a file without it raised
`KeyError: 'MMControls'` (or `'MDA'`) during widget construction and the app
never opened:

    MMcontrols.LoadAllMMFromJSON        -> KeyError, no handler at all
    napariGlados.dockWidget_MDA         -> KeyError, outside its own `except`
    Analysis_dockWidgets                -> KeyError, outside its own `except`

This is exactly what a truncated state file produced in the field. These tests
pin the tolerant reads and the file-level helper.
"""
from __future__ import annotations

import inspect
import json
import os

import pytest


# ------------------------------------------------------- the shared helper


@pytest.fixture
def appdata(tmp_path, monkeypatch):
    from glados_pycromanager.io import appdata as appdata_mod

    monkeypatch.setattr(appdata_mod.appdirs, "user_data_dir", lambda *a, **kw: str(tmp_path))
    return appdata_mod


def _write_state(appdata_mod, payload):
    path = appdata_mod.glados_state_path()
    with open(path, "w") as fh:
        fh.write(payload if isinstance(payload, str) else json.dumps(payload))
    return path


def test_missing_file_reads_as_empty(appdata):
    assert appdata.load_glados_state() == {}


def test_a_complete_file_reads_back(appdata):
    payload = {"MDA": {"a": 1}, "MMControls": {"b": 2}, "GlobalData": {}}
    _write_state(appdata, payload)
    assert appdata.load_glados_state() == payload


def test_a_corrupt_file_reads_as_empty(appdata):
    """A truncated write is exactly how this failure reached a user."""
    _write_state(appdata, '{"GlobalData": {"a": 1}, "MDA": {"b')
    assert appdata.load_glados_state() == {}


def test_a_non_object_file_reads_as_empty(appdata):
    _write_state(appdata, "[1, 2, 3]")
    assert appdata.load_glados_state() == {}


def test_sections_are_absent_not_invented(appdata):
    """The helper reports what is there; callers supply their own defaults."""
    _write_state(appdata, {"GlobalData": {}, "schema_version": 1})
    state = appdata.load_glados_state()
    assert "MDA" not in state and "MMControls" not in state
    assert state.get("MDA", {}) == {}
    assert state.get("MMControls", {}) == {}


# ------------------------------------------ a corrupt file is not destroyed


def test_overwriting_a_corrupt_file_keeps_a_copy(appdata):
    """Losing MDA/MMControls silently is how the settings vanished."""
    from glados_pycromanager.GUI.sharedFunctions import Config

    path = _write_state(appdata, '{"MDA": {"exposure": 100}, "MMCon')
    appdata.save_config_to_json(Config())

    backups = [
        name
        for name in os.listdir(os.path.dirname(path))
        if name.startswith("glados_state.json.corrupt-")
    ]
    assert backups, "the unreadable file must be preserved before overwriting"
    with open(os.path.join(os.path.dirname(path), backups[0])) as fh:
        assert fh.read() == '{"MDA": {"exposure": 100}, "MMCon'


def test_a_readable_file_keeps_its_other_sections(appdata):
    """The normal path must still preserve MDA/MMControls untouched."""
    from glados_pycromanager.GUI.sharedFunctions import Config

    _write_state(appdata, {"MDA": {"exposure": 100}, "MMControls": {"x": 1}})
    appdata.save_config_to_json(Config())

    state = appdata.load_glados_state()
    assert state["MDA"] == {"exposure": 100}
    assert state["MMControls"] == {"x": 1}
    assert "GlobalData" in state


# ------------------------------------------------------------ the loaders


def test_mm_controls_loader_tolerates_a_missing_section():
    pytest.importorskip("PyQt5.QtWidgets")
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from glados_pycromanager.GUI.MMcontrols import MMConfigUI

    source = inspect.getsource(MMConfigUI.LoadAllMMFromJSON)
    assert "gladosInfo.get('MMControls', {})" in source
    assert "gladosInfo['MMControls']" not in source


def test_mda_dock_loader_tolerates_a_missing_section():
    pytest.importorskip("PyQt5.QtWidgets")
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    import glados_pycromanager.GUI.napariGlados as napariGlados

    source = inspect.getsource(napariGlados.dockWidget_MDA.__init__)
    assert "gladosInfo.get('MDA', {})" in source
    assert "gladosInfo['MDA']" not in source
    assert "except KeyError:" in source, "an empty section falls back to defaults"


def test_analysis_dockwidget_loader_tolerates_a_missing_section():
    pytest.importorskip("PyQt5.QtWidgets")
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    import glados_pycromanager.GUI.Analysis_dockWidgets as analysis_dock

    source = inspect.getsource(analysis_dock)
    assert "gladosInfo.get('MDA', {})" in source
    assert "gladosInfo['MDA']" not in source


def test_an_empty_section_raises_keyerror_on_the_field_reads():
    """That is the mechanism both MDA loaders rely on to reach their default."""
    mdaInfo = {}
    with pytest.raises(KeyError):
        mdaInfo["num_time_points"]
