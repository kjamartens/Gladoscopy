"""The Controls panel (`MMConfigUI`) on the layout toolkit.

Its boxes are `Section`s placed by a `ResponsiveGrid` per dock shape (they used
to sit in one fixed row whatever the dock's shape), config labels share one
column so every control starts at the same x, and a rebuild of the config rows
leaves no stale widget painted over the new ones. Fonts come from the theme:
the per-widget Arial 7 walker is gone.
"""
from __future__ import annotations

import os
from unittest.mock import MagicMock

import pytest

pytest.importorskip("PyQt5.QtWidgets")


@pytest.fixture(scope="module")
def qapp():
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from PyQt5.QtCore import QCoreApplication, Qt
    from PyQt5.QtWidgets import QApplication

    QCoreApplication.setAttribute(Qt.AA_ShareOpenGLContexts, True)
    return QApplication.instance() or QApplication([])


class _Group:
    """Just enough of `ConfigInfo` for the panel to build a row."""

    def __init__(self, index, name, kind):
        self.config_group_id, self.name, self.kind = index, name, kind

    def configGroupName(self): return self.name
    def nrConfigs(self): return 3 if self.kind == "drop" else 1
    def configName(self, i): return ["488", "561", "640"][i]
    def isReadOnly(self): return self.kind == "ro"
    def isDropDown(self): return self.kind == "drop"
    def isSlider(self): return self.kind == "slider"
    def isInputField(self): return self.kind == "input"
    def hasPropertyLimits(self): return self.kind == "slider"
    def lowerLimit(self): return 0.0
    def upperLimit(self): return 100.0
    def getCurrentMMValue(self): return "488"
    def getStorableValue(self): return {"drop": "488", "slider": 50.0, "input": "1", "ro": "25.3"}[self.kind]
    def helpStringInfo(self): return self.name


GROUPS = [("Fluorophore", "drop"), ("Laser power", "slider"), ("Binning", "input"), ("Real_ms", "ro")]


@pytest.fixture(scope="module")
def panel(qapp, tmp_path_factory):
    """Built once, without the RT-analysis section: that one imports every RT
    node module (TensorFlow among them) and adds ~2 min to construction."""
    import glados_pycromanager.GUI.MMcontrols as MMc
    from glados_pycromanager.GUI.sharedFunctions import LayoutConfig, VisualisationConfig

    appdata = tmp_path_factory.mktemp("appdata")
    (appdata / "Glados-PycroManager" / "AutonomousMicroscopy" / "Real_Time_Analysis").mkdir(parents=True)

    mil = MagicMock()
    mil.get_loaded_devices.return_value = ["XY", "Z", "Shutter"]
    mil.get_device_type.side_effect = lambda d: {"XY": 6, "Z": 5, "Shutter": 3}[d]
    mil.get_available_config_groups.return_value = [name for name, _ in GROUPS]
    mil.get_exposure.return_value = 25.0
    mil.get_xy_stage_device.return_value = "XY"
    mil.get_focus_device.return_value = "Z"
    mil.get_shutter_device.return_value = "Shutter"
    mil.get_position.return_value = 12.5
    shared = MagicMock()
    shared.MILcore = shared.core = mil
    shared.config.layout_config = LayoutConfig()
    shared.config.visualisation_config = VisualisationConfig()
    groups = {i: _Group(i, name, kind) for i, (name, kind) in enumerate(GROUPS)}
    for group in groups.values():
        group.core, group.shared_data = mil, shared
    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(MMc, "shared_data", shared, raising=False)
        mp.setattr(MMc, "ConfigInfo", lambda core, sd, i: groups[i])
        mp.setattr(MMc.appdirs, "user_data_dir", lambda *a, **k: str(appdata))
        ui = MMc.MMConfigUI(groups, number_config_columns=7, autoSaveLoad=False, showRealTimeAnalysis=False)
        yield ui
    ui.sectionGrid.deleteLater()


def test_sections_follow_the_dock_shape(panel):
    from PyQt5.QtCore import QSize

    grid = panel.sectionGrid
    panel.handleSizeChange(QSize(1800, 300))
    assert [grid.position_of(k) for k in ("controls.general", "controls.configs", "controls.stages")] == [
        (0, 0, 1, 1), (0, 1, 1, 1), (0, 2, 1, 1)]
    assert grid.position_of("controls.rt") is None           # not built: ranks close around it
    panel.handleSizeChange(QSize(1000, 900))
    assert grid.position_of("controls.stages") == (1, 0, 1, 1)
    panel.handleSizeChange(QSize(400, 1500))
    assert grid.position_of("controls.stages") == (2, 0, 1, 1)


def test_config_labels_share_one_column(panel):
    layout = panel.configLayout
    columns = set()
    for i in range(layout.count()):
        item = layout.itemAt(i)
        _row, col, _rs, _cs = layout.getItemPosition(i)
        inner = item.layout()
        first = inner.itemAt(0).widget() if inner is not None and inner.count() else None
        if first is not None and first.__class__.__name__ == "QLabel" and first.text() in dict(GROUPS):
            columns.add(col)
    assert columns == {0}


def test_rebuild_leaves_no_stale_rows(panel):
    from PyQt5.QtWidgets import QLabel

    for _ in range(3):
        panel.rebuildConfigLayout()
    labels = [w for w in panel.configGroupBox.findChildren(QLabel) if w.text() == "Real_ms"]
    assert len(labels) == 1


def test_fonts_come_from_the_theme(panel):
    assert not hasattr(panel, "set_font_and_margins_recursive")


def test_hidden_sections_setting_is_applied(panel):
    layout_config = panel.shared_data.config.layout_config
    layout_config.hidden_sections = "controls.stages"
    try:
        panel.sectionGrid.set_hidden(panel._configuredHiddenSections())
        assert panel.sectionGrid.position_of("controls.stages") is None
    finally:
        layout_config.hidden_sections = ""
        panel.sectionGrid.set_hidden(())


def test_stages_section_is_compact(panel):
    """XY is a dial with the step table below it, Z a separate block; step
    fields are capped, so the Stages box no longer stretches over the dock."""
    from PyQt5.QtWidgets import QWIDGETSIZE_MAX

    from glados_pycromanager.ui.widgets.stage_dial import StageDial

    from glados_pycromanager.ui.layout import build_stylesheet

    box = panel.stagesGroupBox
    box.setStyleSheet(build_stylesheet())  # as the dock applies it
    box.adjustSize()
    assert isinstance(panel.XYStageInfoWidget, StageDial)
    fields = [f for k, f in panel.XYMoveEditField.items() if not k.startswith("Button")]
    fields += [f for stage in panel.oneDMoveEditField.values() for f in stage.values()]
    assert fields and all(f.maximumWidth() < QWIDGETSIZE_MAX for f in fields)
    # Structure, not pixels: offscreen font fallback makes absolute sizes meaningless.
    box.resize(box.sizeHint())
    box.layout().activate()
    dial, first_field = panel.XYStageInfoWidget, panel.XYMoveEditField["X_1"]
    assert first_field.mapTo(box, first_field.rect().topLeft()).y() >= dial.mapTo(box, dial.rect().bottomLeft()).y()
    assert panel.zStageBlock.mapTo(box, panel.zStageBlock.rect().topLeft()).x() >=         panel.xyStageBlock.mapTo(box, panel.xyStageBlock.rect().topRight()).x()


def test_dial_ring_moves_by_that_rings_step(panel, monkeypatch):
    moves = []
    monkeypatch.setattr(panel, "moveXYStage", lambda dx, dy: moves.append((dx, dy)))
    for m, (x, y) in enumerate([("1", "2"), ("10", "20"), ("100", "200")], start=1):
        panel.XYMoveEditField[f"X_{m}"].setText(x)
        panel.XYMoveEditField[f"Y_{m}"].setText(y)
    dial = panel.XYStageInfoWidget
    dial.stepRequested.emit(0, 1, 1)    # up, inner ring
    dial.stepRequested.emit(-1, 0, 3)   # left, outer ring
    dial.stepRequested.emit(0, -1, 2)   # down, middle ring
    assert moves == [(0.0, 2.0), (-100.0, 0.0), (0.0, -20.0)]


def test_scripts_section_hidden_unless_enabled(panel):
    layout_config = panel.shared_data.config.visualisation_config
    assert layout_config.show_scripts_section is False
    assert panel.scriptsGroupBox.isHidden()
    assert hasattr(panel, "scriptPathLineEdit")  # still built: the saved path round-trips
    for stored in (True, "True"):
        layout_config.show_scripts_section = stored
        try:
            assert panel._showScriptsSection()
        finally:
            layout_config.show_scripts_section = False


def test_setting_is_true_parses_stored_forms():
    from glados_pycromanager.GUI.utils import settingIsTrue

    assert settingIsTrue(True) and settingIsTrue("True") and settingIsTrue("true")
    assert not settingIsTrue(False) and not settingIsTrue("False") and not settingIsTrue("")


def test_field_step_buttons_fill_one_decimal(panel):
    """0.1 field of a 512 px ROI at 0.1 um/px is 5.12 um -- shown as 5.1, not the
    full float (which could print 20 digits)."""
    mil = panel.shared_data.MILcore
    mil.get_pixel_size_um.return_value = 0.1
    mil.get_roi.return_value = (0, 0, 512, 333)
    panel.XYMoveEditField["Button_1"].click()
    assert panel.XYMoveEditField["X_1"].text() == "5.1"
    assert panel.XYMoveEditField["Y_1"].text() == "3.3"
