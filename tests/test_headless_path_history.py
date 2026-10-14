"""Start dialog: last-20 history of Micro-Manager paths and config files."""

from __future__ import annotations

import os
from types import SimpleNamespace
from unittest import mock

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PyQt5.QtWidgets import QApplication

from glados_pycromanager.GUI.headless_validation import (
    PATH_HISTORY_LIMIT,
    push_path_history,
)
from glados_pycromanager.GUI.sharedFunctions import MicroManagerConfig


@pytest.fixture(scope="module", autouse=True)
def _qapp():
    app = QApplication.instance() or QApplication([])
    yield app


def test_push_puts_newest_first_and_dedupes():
    h = push_path_history([], "C:/a")
    h = push_path_history(h, "C:/b")
    h = push_path_history(h, "C:/a")
    assert h == ["C:/a", "C:/b"]


@pytest.mark.skipif(os.name != "nt", reason="case/separator folding is Windows path semantics")
def test_push_dedupes_case_and_separator_insensitively():
    h = push_path_history(["c:\\MM\\cfg.cfg", "C:/other.cfg"], "C:/mm/cfg.cfg")
    assert h == ["C:/mm/cfg.cfg", "C:/other.cfg"]


def test_push_caps_at_limit():
    h: list[str] = []
    for i in range(PATH_HISTORY_LIMIT + 5):
        h = push_path_history(h, f"C:/p{i}")
    assert len(h) == PATH_HISTORY_LIMIT == 20
    assert h[0] == f"C:/p{PATH_HISTORY_LIMIT + 4}"


def test_push_ignores_empty_and_tolerates_bad_history():
    assert push_path_history(["C:/a"], "  ") == ["C:/a"]
    assert push_path_history("not a list", "C:/a") == ["C:/a"]
    assert push_path_history([None, 3, "C:/b"], "C:/a") == ["C:/a", "C:/b"]


def test_history_fields_are_independent_lists():
    a, b = MicroManagerConfig(), MicroManagerConfig()
    a.path_history.append("x")
    assert b.path_history == []


def _dialog(mm_cfg):
    from glados_pycromanager.GUI import GUI_napari

    shared_data = SimpleNamespace(config=SimpleNamespace(micromanager_config=mm_cfg))
    with mock.patch.object(GUI_napari.headlessGUI, "show"):
        return GUI_napari.headlessGUI(shared_data)


def test_dialog_arrow_fills_line_edit_and_start_records_history(tmp_path):
    mm_cfg = MicroManagerConfig()
    mm_cfg.config_path_history = ["C:/old1.cfg", "C:/old2.cfg"]
    dlg = _dialog(mm_cfg)

    assert not dlg.mm_app_history.isEnabled()  # no history yet
    actions = dlg.config_file_history.menu().actions()
    assert [a.text() for a in actions] == ["C:/old1.cfg", "C:/old2.cfg"]
    actions[1].trigger()
    assert dlg.config_fileLineEdit.text() == "C:/old2.cfg"

    dlg.mm_app_pathLineEdit.setText(str(tmp_path))
    with mock.patch("glados_pycromanager.GUI.utils.storeSharedData_GlobalData"):
        dlg.start()
    assert mm_cfg.path_history == [str(tmp_path)]
    assert mm_cfg.config_path_history == ["C:/old2.cfg", "C:/old1.cfg"]
