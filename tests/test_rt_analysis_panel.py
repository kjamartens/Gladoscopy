"""The Controls dock's RT-analysis panel (`GUI/rt_analysis_panel.py`).

Built against a fake node module, never the real node tree: importing that pulls
in TensorFlow and costs ~2 min (see `test_controls_panel_layout.py`).
"""
from __future__ import annotations

import json
import os
import sys
import types
from collections import deque
from unittest.mock import MagicMock

import numpy as np
import pytest

pytest.importorskip("PyQt5.QtWidgets")

MODULE = "FakeRTPanelNode"
NODE = f"{MODULE}.FakeNode"
OTHER = f"{MODULE}.OtherNode"


def _fake_metadata():
    def kw(name, default, typ):
        return {"name": name, "default": default, "type": typ, "description": name, "display_text": name}
    return {
        "FakeNode": {
            "display_name": "Fake node",
            "help_string": "",
            "required_kwargs": [kw("threshold", 5, float)],
            "optional_kwargs": [kw("invert", False, bool), kw("label", "abc", str)],
        },
        "OtherNode": {
            "display_name": "Other node",
            "help_string": "",
            "required_kwargs": [kw("count", 3, int)],
            "optional_kwargs": [],
        },
    }


@pytest.fixture(scope="module")
def qapp():
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from PyQt5.QtCore import QCoreApplication, Qt
    from PyQt5.QtWidgets import QApplication

    QCoreApplication.setAttribute(Qt.AA_ShareOpenGLContexts, True)
    return QApplication.instance() or QApplication([])


@pytest.fixture
def appdata(tmp_path, monkeypatch):
    import appdirs
    monkeypatch.setattr(appdirs, "user_data_dir", lambda *a, **k: str(tmp_path))
    return tmp_path / "Glados-PycroManager" / "glados_state.json"


@pytest.fixture
def fake_node(monkeypatch):
    from glados_pycromanager.autonomous import registry
    module = types.ModuleType(MODULE)
    module.__function_metadata__ = _fake_metadata
    monkeypatch.setitem(sys.modules, MODULE, module)
    registry.clear_metadata_cache()
    yield
    registry.clear_metadata_cache()


@pytest.fixture
def shared():
    shared = MagicMock()
    shared.RTAnalysisQueuesThreads = []
    shared.liveMode = False
    shared.mdaMode = False
    shared.napariViewer = None
    shared.hw_pixel_size_um = 0.1
    return shared


def _panel(shared, persist=False):
    from glados_pycromanager.GUI.rt_analysis_panel import RTAnalysisPanel
    return RTAnalysisPanel(shared, persist=persist, function_names=[NODE, OTHER])


def _widget(panel, kwarg, function=NODE):
    return next(w for w in panel.kwargWidgets(function) if w.objectName().endswith("#" + kwarg))


def _role(widget):
    return widget.property("gladosRole") or ""


def test_value_widgets_only_no_variable_switch(qapp, fake_node, shared, appdata):
    panel = _panel(shared)
    names = [w.objectName() for w in panel.paramsWidget.findChildren(object) if hasattr(w, "objectName")]
    assert not any(n.startswith(("ComboBoxSwitch#", "LineEditVariable#", "LineEditAdv#")) for n in names)
    assert {w.objectName() for w in panel.kwargWidgets(NODE)} == {
        f"LineEdit#{NODE}#threshold", f"LineEdit#{NODE}#invert", f"LineEdit#{NODE}#label"}
    #Every kwarg resolves as a Value: no mode switch to say otherwise.
    from glados_pycromanager.GUI import utils
    _name, kwargs, values, modes = utils._rtAnalysisKwargsFromCurrentData(NODE, panel.currentData)
    assert dict(zip(kwargs, values)) == {"threshold": "5", "invert": "False", "label": "abc"}
    assert set(modes) == {"Value"}


def test_only_the_selected_methods_parameters_are_shown(qapp, fake_node, shared, appdata):
    panel = _panel(shared)
    assert not _widget(panel, "threshold").isHidden()
    assert _widget(panel, "count", OTHER).isHidden()
    panel.methodDropdown.setCurrentText("Other node")
    assert _widget(panel, "threshold").isHidden()
    assert not _widget(panel, "count", OTHER).isHidden()


def test_dropdown_spans_the_label_column(qapp, fake_node, shared, appdata):
    """The method dropdown sits above the parameter grid, not in its field column."""
    panel = _panel(shared)
    assert panel.paramsLayout.indexOf(panel.methodDropdown) == -1
    assert panel.layout().indexOf(panel.methodDropdown) == 0


def test_changed_setting_is_highlighted_and_restored(qapp, fake_node, shared, appdata):
    from glados_pycromanager.ui.layout import ROLE_MODIFIED
    from PyQt5.QtWidgets import QLabel

    panel = _panel(shared)
    threshold = _widget(panel, "threshold")
    label = panel.paramsWidget.findChild(QLabel, f"Label#{NODE}#threshold")
    assert _role(threshold) == "" and not panel.restoreDefaultsButton.isEnabled()

    threshold.setText("7.5")
    _widget(panel, "invert").setChecked(True)
    assert _role(threshold) == ROLE_MODIFIED and _role(label) == ROLE_MODIFIED
    assert _role(_widget(panel, "invert")) == ROLE_MODIFIED
    assert panel.currentData[f"LineEdit#{NODE}#threshold"] == "7.5"
    assert panel.restoreDefaultsButton.isEnabled()

    panel.restoreDefaults()
    assert threshold.text() == "5" and not _widget(panel, "invert").isChecked()
    assert _role(threshold) == "" and _role(label) == ""
    assert panel.currentData[f"LineEdit#{NODE}#threshold"] == "5"
    assert not panel.restoreDefaultsButton.isEnabled()


def test_reload_rebuilds_kwargs_and_keeps_edits(qapp, fake_node, shared, appdata):
    """Plugins > Reload Glados Custom Nodes: a kwarg added to (or removed from) a
    node's metadata shows up without restarting, and the user's edits survive."""
    from glados_pycromanager.autonomous import registry
    from glados_pycromanager.plugins import discovery

    panel = _panel(shared)
    assert any(ref() == panel._onNodesReloaded for ref in discovery._reload_listeners)
    _widget(panel, "count", OTHER).setText("9")
    panel.methodDropdown.setCurrentText("Other node")

    def edited():
        meta = _fake_metadata()
        meta["OtherNode"]["optional_kwargs"] = [
            {"name": "sigma", "default": 1.5, "type": float, "description": "s", "display_text": "s"}]
        meta["FakeNode"]["optional_kwargs"] = meta["FakeNode"]["optional_kwargs"][:1]  # drop `label`
        return meta
    sys.modules[MODULE].__function_metadata__ = edited
    registry.clear_metadata_cache()
    panel.reloadMethods()

    assert {w.objectName() for w in panel.kwargWidgets(OTHER)} == {
        f"LineEdit#{OTHER}#count", f"LineEdit#{OTHER}#sigma"}
    assert {w.objectName() for w in panel.kwargWidgets(NODE)} == {
        f"LineEdit#{NODE}#threshold", f"LineEdit#{NODE}#invert"}
    assert panel.methodDropdown.currentText() == "Other node"
    assert _widget(panel, "count", OTHER).text() == "9"
    assert _widget(panel, "sigma", OTHER).text() == "1.5"
    assert not _widget(panel, "sigma", OTHER).isHidden() and _widget(panel, "threshold").isHidden()
    assert panel.currentData[f"LineEdit#{OTHER}#sigma"] == "1.5"
    assert f"LineEdit#{NODE}#label" not in panel.currentData


def test_restore_defaults_touches_only_the_selected_method(qapp, fake_node, shared, appdata):
    panel = _panel(shared)
    _widget(panel, "count", OTHER).setText("9")
    panel.restoreDefaults()                       #Fake node is selected
    assert _widget(panel, "count", OTHER).text() == "9"


def test_settings_persist_between_sessions(qapp, fake_node, shared, appdata):
    appdata.parent.mkdir(parents=True, exist_ok=True)
    appdata.write_text(json.dumps({"MDA": {"keep": 1}}))
    panel = _panel(shared, persist=True)
    _widget(panel, "label").setText("xyz")
    panel.methodDropdown.setCurrentText("Other node")
    panel.saveSettings()

    state = json.loads(appdata.read_text())
    assert state["MDA"] == {"keep": 1}            #other sections untouched
    #Only non-default values are stored.
    assert state["RTAnalysis"] == {"selected": "Other node",
                                   "values": {f"LineEdit#{NODE}#label": "xyz"}}

    again = _panel(shared, persist=True)
    assert again.methodDropdown.currentText() == "Other node"
    assert _widget(again, "label").text() == "xyz"
    assert again.currentData[f"LineEdit#{NODE}#label"] == "xyz"
    assert _role(_widget(again, "label")) != ""


def test_non_persisting_panel_never_writes(qapp, fake_node, shared, appdata):
    panel = _panel(shared, persist=False)
    _widget(panel, "label").setText("xyz")
    panel.saveSettings()
    assert not appdata.exists()


def test_parameter_area_scrolls_instead_of_growing(qapp, fake_node, shared, appdata):
    from glados_pycromanager.GUI import rt_analysis_panel as rp
    panel = _panel(shared)
    for row in range(40):                         #a node with many parameters
        from PyQt5.QtWidgets import QLineEdit
        panel.paramsLayout.addWidget(QLineEdit(), 100 + row, 1)
    scroll = panel.paramsScroll
    assert scroll.sizeHint().height() == scroll._cap_height()
    assert scroll.sizeHint().height() < panel.paramsWidget.sizeHint().height()
    assert scroll._cap_height() == rp.RT_PARAMS_VISIBLE_ROWS * (
        panel.methodDropdown.sizeHint().height() + rp.compact_spacing())


class _FakeThread:
    def __init__(self):
        self.new_images = 0
        self.destroyed = False
        self.visualisationObject = None

    def new_image(self):
        self.new_images += 1

    def destroy(self):
        self.destroyed = True


@pytest.fixture
def fake_create(monkeypatch, shared):
    import glados_pycromanager.GUI.AnalysisClass as AC
    created = []

    def create(shared_data, analysisInfo=None, delay=None, nodzInfo=None):
        thread = _FakeThread()
        thread.info = dict(analysisInfo)
        shared_data.RTAnalysisQueuesThreads.append({"Queue": deque(maxlen=10), "Thread": thread})
        created.append(thread)
        return thread

    monkeypatch.setattr(AC, "create_real_time_analysis_thread", create)
    return created


def test_toggle_shows_state_and_switches(qapp, fake_node, shared, appdata, fake_create):
    from glados_pycromanager.ui.layout import ROLE_ACTIVE
    panel = _panel(shared)
    assert panel.toggleButton.text() == "Activate" and not panel.resetButton.isEnabled()

    panel.toggleButton.click()
    assert panel.isActive()
    assert panel.toggleButton.text() == "Deactivate"
    assert _role(panel.toggleButton) == ROLE_ACTIVE and panel.resetButton.isEnabled()
    assert fake_create[0].info["__selectedDropdownEntryRTAnalysis__"] == "Fake node"

    panel.toggleButton.click()
    assert not panel.isActive() and fake_create[0].destroyed
    assert shared.RTAnalysisQueuesThreads == []
    assert panel.toggleButton.text() == "Activate" and _role(panel.toggleButton) == ""


def test_two_methods_run_and_stop_independently(qapp, fake_node, shared, appdata, fake_create):
    panel = _panel(shared)
    panel.activate()                              #Fake node
    panel.methodDropdown.setCurrentText("Other node")
    assert panel.toggleButton.text() == "Activate"   #follows the selected method
    panel.toggleButton.click()
    assert len(shared.RTAnalysisQueuesThreads) == 2
    fake, other = fake_create
    #Each run has its own settings: activating the second must not retarget the first.
    assert fake.info["__selectedDropdownEntryRTAnalysis__"] == "Fake node"
    assert other.info["__selectedDropdownEntryRTAnalysis__"] == "Other node"
    assert panel._runs[NODE]["info"]["__selectedDropdownEntryRTAnalysis__"] == "Fake node"

    panel.toggleButton.click()                    #deactivates Other node only
    assert other.destroyed and not fake.destroyed
    assert panel.toggleButton.text() == "Activate"
    panel.methodDropdown.setCurrentText("Fake node")
    assert panel.toggleButton.text() == "Deactivate"


def test_running_methods_are_highlighted_in_the_dropdown(qapp, fake_node, shared, appdata, fake_create):
    from PyQt5.QtCore import Qt
    from glados_pycromanager.ui.layout import ROLE_ACTIVE
    panel = _panel(shared)
    combo = panel.methodDropdown

    def marked(index):
        return combo.itemData(index, Qt.BackgroundRole) is not None

    assert not marked(0) and not marked(1) and _role(combo) == ""
    panel.activate()                              #Fake node, index 0
    assert marked(0) and not marked(1) and _role(combo) == ROLE_ACTIVE
    assert combo.itemText(0) == "Fake node"       #text untouched: methods are looked up by it
    combo.setCurrentText("Other node")
    assert marked(0) and _role(combo) == ""       #the selected one is not running
    shared.RTAnalysisQueuesThreads.clear()        #ended elsewhere
    panel.refreshActiveState()
    assert not marked(0)


def test_editing_a_running_method_reaches_only_its_run(qapp, fake_node, shared, appdata, fake_create):
    panel = _panel(shared)
    panel.activate()
    panel.methodDropdown.setCurrentText("Other node")
    panel.activate()
    _widget(panel, "threshold").setText("8")
    _widget(panel, "count", OTHER).setText("4")
    assert panel._runs[NODE]["info"][f"LineEdit#{NODE}#threshold"] == "8"
    assert panel._runs[OTHER]["info"][f"LineEdit#{OTHER}#count"] == "4"
    assert f"LineEdit#{NODE}#threshold" not in panel._runs[OTHER]["info"]


def test_toggle_follows_a_teardown_from_elsewhere(qapp, fake_node, shared, appdata, fake_create):
    """Closing the node's napari layer drops its entry; the button must follow."""
    panel = _panel(shared)
    panel.activate()
    shared.RTAnalysisQueuesThreads.clear()
    panel.refreshActiveState()                    #what the poll timer runs
    assert panel.toggleButton.text() == "Activate"


def test_reset_ends_and_restarts_with_new_settings(qapp, fake_node, shared, appdata, fake_create):
    panel = _panel(shared)
    panel.activate()
    _widget(panel, "threshold").setText("9")
    panel.reset()
    qapp.processEvents()                          #the deferred re-activation
    assert len(fake_create) == 2 and fake_create[0].destroyed
    assert fake_create[1].info[f"LineEdit#{NODE}#threshold"] == "9"
    assert panel.isActive()


def test_activate_runs_once_on_the_napari_image_without_acquisition(qapp, fake_node, shared, appdata, fake_create, monkeypatch):
    panel = _panel(shared)
    frame = np.arange(12, dtype=np.uint16).reshape(3, 4)
    monkeypatch.setattr(panel, "currentNapariFrame", lambda: (frame, {"ImageNumber": 0}))
    panel.activate()
    entry = shared.RTAnalysisQueuesThreads[0]
    assert fake_create[0].new_images == 1
    image, metadata = entry["Queue"][0]
    assert image is frame and metadata == {"ImageNumber": 0}


def test_activate_during_acquisition_does_not_feed_a_frame(qapp, fake_node, shared, appdata, fake_create, monkeypatch):
    panel = _panel(shared)
    shared.liveMode = True
    monkeypatch.setattr(panel, "currentNapariFrame", lambda: pytest.fail("must not read napari"))
    panel.activate()
    assert len(shared.RTAnalysisQueuesThreads[0]["Queue"]) == 0


def test_current_napari_frame_slices_the_selected_image(qapp, fake_node, shared, appdata):
    napari_layers = pytest.importorskip("napari.layers")
    stack = np.arange(3 * 4 * 5, dtype=np.uint16).reshape(3, 4, 5)
    layer = napari_layers.Image(stack, name="MDA")
    overlay = napari_layers.Image(np.zeros((4, 5)), name="Fake node")

    class _Layers(list):
        selection = types.SimpleNamespace(active=overlay)

    viewer = types.SimpleNamespace(layers=_Layers([layer, overlay]),
                                   dims=types.SimpleNamespace(current_step=(2, 0, 0)))
    shared.napariViewer = viewer
    #The overlay belongs to a running node, so it is never analysed.
    group = MagicMock()
    group.names = ["Fake node"]
    thread = MagicMock()
    thread.visualisationObject.napariOverlay.group = group
    shared.RTAnalysisQueuesThreads = [{"Queue": deque(), "Thread": thread}]

    panel = _panel(shared)
    image, metadata = panel.currentNapariFrame()
    np.testing.assert_array_equal(image, stack[2])
    assert metadata["PixelSize_um"] == 0.1 and metadata["SourceLayer"] == "MDA"
