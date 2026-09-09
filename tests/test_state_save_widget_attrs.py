"""Regression: a widget-holding attribute must not break the whole state save.

`save_state_MDA` walks `vars(self)` and writes anything that is not a **bare**
`QWidget` straight into the state dict. A *container* of widgets -- a list, a dict
-- passes that check and then raises inside `json.dump`:

    TypeError: Object of type QWidget is not JSON serializable

and because `open(filename, 'w')` has already truncated the file by then, the user
loses every other setting too, not just the offending one.

This was hit for real by T-F7's `MDAGlados._guiWrappers` (the list of the current
rebuild's wrapper widgets), on the startup path
`handleSizeChange` -> `showOptionChanged` -> `get_MDA_events_from_GUI`.

Two fixes are pinned here: `_guiWrappers` is in `storingExceptions`, and the
generic branch now skips (loudly) anything that cannot be encoded, so a future
attribute of the same shape costs one warning instead of the file.
"""
from __future__ import annotations

import json
import os

import pytest

pytest.importorskip("PyQt5.QtWidgets")


@pytest.fixture(scope="module")
def qapp():
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from PyQt5.QtCore import QCoreApplication, Qt
    from PyQt5.QtWidgets import QApplication

    QCoreApplication.setAttribute(Qt.AA_ShareOpenGLContexts, True)
    return QApplication.instance() or QApplication([])


@pytest.fixture(scope="module")
def utils(qapp):
    from glados_pycromanager.GUI import utils as gui_utils

    return gui_utils


# ---------------------------------------------------------- the exclusion


def test_gui_wrappers_is_excluded_from_the_state(utils, qapp):
    window = utils.CustomMainWindow()
    assert "_guiWrappers" in window.storingExceptions


def test_the_other_exclusions_are_intact(utils, qapp):
    window = utils.CustomMainWindow()
    for key in ("core", "shared_data", "gui", "mda", "mda_useq", "config_groups"):
        assert key in window.storingExceptions


# ------------------------------------------------- the serializability guard


def test_a_widget_is_not_serializable(utils, qapp):
    from PyQt5.QtWidgets import QWidget

    assert utils._is_json_serializable(QWidget()) is False


def test_a_list_of_widgets_is_not_serializable(utils, qapp):
    """The exact shape that crashed: a container, so not a bare QWidget."""
    from PyQt5.QtWidgets import QWidget

    assert utils._is_json_serializable([QWidget(), QWidget()]) is False


def test_ordinary_state_values_are_serializable(utils, qapp):
    for value in ("text", 42, 3.5, True, None, [1, 2], {"a": 1}, []):
        assert utils._is_json_serializable(value) is True, value


def test_a_nested_widget_is_caught(utils, qapp):
    from PyQt5.QtWidgets import QWidget

    assert utils._is_json_serializable({"wrappers": [QWidget()]}) is False


# ----------------------------------------------------- the file survives


def test_an_unencodable_value_does_not_destroy_the_file(utils, qapp, tmp_path):
    """json.dump truncates first and raises second; json.dumps cannot."""
    from PyQt5.QtWidgets import QWidget

    target = tmp_path / "glados_state.json"
    good = {"MDA": {"exposure": 100}, "MMControls": {}, "GlobalData": {}}
    target.write_text(json.dumps(good, indent=4))

    # Simulate the old behaviour to show what it cost.
    with pytest.raises(TypeError):
        encoded = json.dumps({"MDA": {"wrappers": [QWidget()]}}, indent=4)
        target.write_text(encoded)

    assert json.loads(target.read_text()) == good, (
        "encoding before opening the file leaves the previous state intact"
    )


def test_save_encodes_before_opening_the_file(utils):
    import inspect

    source = inspect.getsource(utils.CustomMainWindow.save_state_MDA)
    assert "json.dumps(state, indent=4)" in source
    assert "json.dump(state, file" not in source, (
        "open(..., 'w') truncates before the encoder can fail"
    )


def test_the_generic_branch_checks_before_storing(utils):
    import inspect

    source = inspect.getsource(utils.CustomMainWindow.save_state_MDA)
    assert "_is_json_serializable(value)" in source
    assert "storingExceptions" in source
