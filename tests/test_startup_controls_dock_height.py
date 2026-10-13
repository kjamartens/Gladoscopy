"""The top dock area is sized at startup to fit the Controls and MDA tabs.

It used to ask for the Controls content's `sizeHint()` height, which (1) misses
rows a wrapping FlowRow adds when narrow, and (2) loses the tabified docks' tab
bar, which Qt takes out of the requested height -- the bottom row was clipped.
"""
from __future__ import annotations

import os

import pytest

pytest.importorskip("PyQt5.QtWidgets")


@pytest.fixture(scope="module")
def qapp():
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from PyQt5.QtCore import QCoreApplication, Qt
    from PyQt5.QtWidgets import QApplication

    QCoreApplication.setAttribute(Qt.AA_ShareOpenGLContexts, True)
    import PyQt5.QtWebEngineWidgets  # noqa: F401  (before the QApplication)
    return QApplication.instance() or QApplication([])


def _dock_with(qapp, widget, width):
    from glados_pycromanager.GUI import napariGlados

    dock = napariGlados.dockWidgets()
    dock.layout.addWidget(widget, 0, 0)
    dock.resize(width, 600)
    dock.show()
    qapp.processEvents()
    return dock


def test_content_height_includes_wrapped_rows(qapp):
    from PyQt5.QtWidgets import QPushButton

    from glados_pycromanager.GUI import napariGlados
    from glados_pycromanager.ui.layout import FlowRow

    row = FlowRow([QPushButton(f"A rather long button label {i}") for i in range(8)])
    dock = _dock_with(qapp, row, 300)
    one_line = dock.content_widget.sizeHint().height()
    assert napariGlados._dockContentHeight(dock) > one_line
    dock.close()


def test_tallest_tab_sets_the_height(qapp):
    from PyQt5.QtWidgets import QLabel

    from glados_pycromanager.GUI import napariGlados

    short_label, tall_label = QLabel("short"), QLabel("tall")
    tall_label.setMinimumHeight(400)
    short = _dock_with(qapp, short_label, 800)
    tall = _dock_with(qapp, tall_label, 800)
    assert napariGlados._tallestDockContent(short, (tall,)) == napariGlados._dockContentHeight(tall, 800)
    assert napariGlados._tallestDockContent(short, ()) < 400
    short.close(); tall.close()
