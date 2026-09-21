"""T-F7: rebuilding the MDA GUI must not pump the event loop or leak widgets.

`updateGUIwidgets` tore down and rebuilt seven group boxes, then **synthesised a
QEvent.Resize and sent it**, then called `QCoreApplication.processEvents()`.
Pumping the event loop from inside a widget-tree rebuild allows re-entrant
delivery of `showOptionChanged` / `currentTextChanged` straight back into
`updateGUIwidgets`, and can run `napariUpdateLive` slots mid-rebuild. It also
constructed a **new QPushButton("Acquire") on every call**, leaking the previous
one's connections.

These tests pin the replacements: a zero-delay singleShot relayout request and
one Acquire button for the life of the object.

Since the layout-toolkit rebuild the sections are built once in `initGUI` and
placed by a `ui.layout.ResponsiveGrid`; `updateGUIwidgets` only enables,
refills and re-places. The second half builds a real panel (mocked MIL) and
pins that behaviourally: no widget is ever created by a rebuild or a resize.
"""
from __future__ import annotations

import inspect
import os

import pytest

pytest.importorskip("PyQt5.QtWidgets")


def _address(widget):
    """The C++ object's address: `id()` of a PyQt wrapper is not stable across calls."""
    from PyQt5 import sip

    return sip.unwrapinstance(widget)


@pytest.fixture(scope="module")
def qapp():
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from PyQt5.QtCore import QCoreApplication, Qt
    from PyQt5.QtWidgets import QApplication

    QCoreApplication.setAttribute(Qt.AA_ShareOpenGLContexts, True)
    return QApplication.instance() or QApplication([])


@pytest.fixture(scope="module")
def mda_mod(qapp):
    import glados_pycromanager.Core.MDAGlados as MDAGlados

    return MDAGlados


@pytest.fixture(scope="module")
def mda_cls(mda_mod):
    return mda_mod.MDAGlados


@pytest.fixture(scope="module")
def dock_cls(qapp):
    import glados_pycromanager._dock_widget as dock_widget

    return dock_widget.GladosWidget


# ------------------------------------------------ no re-entrant event pumping


def test_no_synthetic_resize_and_no_process_events(mda_cls):
    source = inspect.getsource(mda_cls.updateGUIwidgets)
    body = "\n".join(
        line for line in source.splitlines() if not line.strip().startswith("#")
    )
    assert "processEvents()" not in body, (
        "pumping the event loop mid-rebuild allows re-entrant updateGUIwidgets"
    )
    assert "sendEvent" not in body, "the synthetic QEvent.Resize must be gone"
    assert "QEvent(QEvent.Resize)" not in body


def test_relayout_is_deferred_not_immediate(mda_cls):
    source = inspect.getsource(mda_cls.updateGUIwidgets)
    assert "QTimer.singleShot(0," in source, (
        "a deferred relayout replaces the synthetic resize"
    )
    assert "requestRelayout" in source


def test_the_gui_update_call_is_kept(mda_cls):
    """The task's Don't: keep self.gui.update()."""
    assert "self.gui.update()" in inspect.getsource(mda_cls.updateGUIwidgets)


def test_dead_qt_imports_were_dropped(mda_mod):
    """`QApplication`, `QCoreApplication` and `QEvent` had no other user here."""
    for name in ("QApplication", "QCoreApplication", "QEvent"):
        assert not hasattr(mda_mod, name), "%s is no longer used" % name


# --------------------------------------------------------- the parent's seam


def test_dock_exposes_request_relayout(dock_cls):
    assert callable(dock_cls.requestRelayout)


def test_request_relayout_forces_a_rebuild_at_an_unchanged_size(dock_cls, qapp):
    """The whole point: same geometry, changed widget tree."""
    from PyQt5.QtCore import QTimer

    obj = type("FakeDock", (), {})()
    obj.type = "MDA"
    obj.RELAYOUT_DEBOUNCE_MS = dock_cls.RELAYOUT_DEBOUNCE_MS
    obj._pendingLayout = None
    obj._appliedLayout = ("rows", 1)
    obj._relayoutTimer = QTimer()
    obj._relayoutTimer.setSingleShot(True)
    obj._layoutForCurrentSize = lambda: ("rows", 1)
    obj.set_groupBoxLayout = lambda **kw: None
    for name in ("_scheduleGroupBoxLayout", "requestRelayout"):
        setattr(obj, name, getattr(dock_cls, name).__get__(obj))

    # A plain resize at the same size is dropped ...
    obj._scheduleGroupBoxLayout(("rows", 1))
    assert not obj._relayoutTimer.isActive()

    # ... but an explicit request is not.
    obj.requestRelayout()
    assert obj._relayoutTimer.isActive()
    assert obj._pendingLayout == ("rows", 1)
    obj._relayoutTimer.stop()


def test_request_relayout_is_a_no_op_for_autonomous_microscopy(dock_cls):
    """resizeEvent excludes those two types; the explicit request must too."""
    for widget_type in (None, "AutonomousMicroscopy"):
        obj = type("FakeDock", (), {})()
        obj.type = widget_type
        obj._appliedLayout = ("rows", 1)
        obj.requestRelayout = dock_cls.requestRelayout.__get__(obj)
        obj.requestRelayout()
        assert obj._appliedLayout == ("rows", 1), "must not touch the layout"


# ------------------------------------------------------- the Acquire button


def test_gui_acquire_button_flag_is_not_used_as_the_built_test(mda_cls):
    """It holds a bool from __init__ before it ever holds the widget."""
    init_source = inspect.getsource(mda_cls.__init__)
    assert "self.GUI_acquire_button = GUI_acquire_button" in init_source, (
        "the attribute really does start out as the boolean flag"
    )


# ------------------------------------------------------------- a real panel


@pytest.fixture
def panel(mda_mod, qapp, monkeypatch):
    from unittest.mock import MagicMock

    class _Group:
        def __init__(self, core, shared_data, index):
            self.index = index

        def isDropDown(self):
            return True

        def configGroupName(self):
            return ["Fluorophore", "Channel"][self.index]

    monkeypatch.setattr(mda_mod, "ConfigInfo", _Group)
    mil = MagicMock()
    mil.get_loaded_devices.return_value = ["XY", "Z"]
    mil.get_device_type.side_effect = lambda d: {"XY": 6, "Z": 5}[d]
    mil.get_available_config_groups.return_value = ["Fluorophore", "Channel"]
    mil.get_available_configs.side_effect = lambda g: ["488", "561"]
    mil.get_exposure.return_value = 25.0
    shared = MagicMock()
    shared.MILcore = mil
    from glados_pycromanager.GUI.sharedFunctions import LayoutConfig

    shared.config.layout_config = LayoutConfig()
    widget = mda_mod.MDAGlados(mil, None, None, shared, hasGUI=True, GUI_acquire_button=True,
                               order="tpcz", channels=["488"], channel_exposures_ms=[25])
    yield widget
    widget.deleteLater()


def _toggle_all_options(panel, times):
    boxes = (panel.GUI_show_xy_chkbox, panel.GUI_show_z_chkbox, panel.GUI_show_channel_chkbox,
             panel.GUI_show_time_chkbox, panel.GUI_show_storage_chkbox)
    for _ in range(times):
        for box in boxes:
            box.setChecked(not box.isChecked())


def test_rebuilds_and_resizes_create_no_widgets(panel):
    from PyQt5.QtCore import QSize
    from PyQt5.QtWidgets import QWidget

    before = set(map(_address, panel.sectionGrid.findChildren(QWidget)))
    assert len(before) > 50
    _toggle_all_options(panel, 4)
    for size in (QSize(1800, 300), QSize(400, 1300), QSize(900, 800)) * 3:
        panel.handleSizeChange(size)
    assert set(map(_address, panel.sectionGrid.findChildren(QWidget))) == before


def test_one_acquire_button_with_one_connection(panel):
    from PyQt5.QtWidgets import QPushButton

    calls = []
    panel.MDA_acq_from_GUI = lambda **kw: calls.append(kw)
    _toggle_all_options(panel, 4)
    acquire = [b for b in panel.sectionGrid.findChildren(QPushButton) if b.text() == "Acquire"]
    assert acquire == [panel._acquireButton]
    acquire[0].click()
    assert calls == [{"mdaLayerName": "MDA"}]


def test_unchecked_option_disables_but_keeps_its_section(panel):
    panel.GUI_show_xy_chkbox.setChecked(False)
    assert not panel.xyGroupBox.isEnabled()
    assert panel.sectionGrid.position_of("mda.xy") is not None
    panel.GUI_show_xy_chkbox.setChecked(True)
    assert panel.xyGroupBox.isEnabled()


def test_order_choice_survives_a_dimension_toggle(panel):
    panel.orderDropdown.setCurrentText("ztpc")
    panel.GUI_show_z_chkbox.setChecked(False)
    assert panel.orderDropdown.currentText() == "tpc"
    panel.GUI_show_z_chkbox.setChecked(True)
    assert panel.orderDropdown.currentText() == "tpcz"
    assert panel.orderDropdown.count() == 24


def test_sections_follow_the_dock_shape(panel):
    from PyQt5.QtCore import QSize

    grid = panel.storageGroupBox.body
    panel.handleSizeChange(QSize(1800, 300))                    # wide
    assert panel.sectionGrid.position_of("mda.storagebar") == (0, 0, 1, 4)
    assert panel.sectionGrid.position_of("mda.channel") == (1, 3, 1, 1)
    assert grid.getItemPosition(grid.indexOf(panel.storageFileNameEntry))[:2] == (0, 4)
    panel.handleSizeChange(QSize(400, 1300))                    # tall: stacked storage
    assert panel.sectionGrid.position_of("mda.channel") == (4, 0, 1, 1)
    assert grid.getItemPosition(grid.indexOf(panel.storageFileNameEntry))[:2] == (1, 1)


def test_legacy_column_count_maps_to_a_bucket(panel, mda_mod):
    panel.GUI_grid_width = 10
    assert panel.GUI_grid_width == mda_mod.WIDE
    panel.GUI_grid_width = 1
    assert panel.GUI_grid_width == mda_mod.TALL
    panel.GUI_grid_width = ["rows", 2]                           # as read back from JSON
    assert panel.GUI_grid_width == mda_mod.LANDSCAPE


def test_hidden_sections_setting_is_applied(panel):
    panel.shared_data.config.layout_config.hidden_sections = "mda.xy"
    panel.showOptionChanged()
    assert panel.sectionGrid.position_of("mda.xy") is None
    assert panel.xyGroupBox.isHidden()


def test_channel_header_is_not_clipped(panel, qapp):
    panel.sectionGrid.resize(1800, 300)
    panel.sectionGrid.show()
    qapp.processEvents()
    header = panel.channelListWidget.horizontalHeader()
    assert header.sectionSize(0) >= header.fontMetrics().horizontalAdvance("Channel Setting")
    panel.sectionGrid.hide()
