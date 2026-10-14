"""The Real-time analysis section of the Controls dock.

One method dropdown (full width), the chosen method's parameters in a scroll
area of fixed height, and one row of buttons: a toggle that reads "Activate" or,
highlighted, "Deactivate" while the analysis runs; Reset (end() then init()
with the panel's current settings); and Restore defaults.

The parameter widgets are still built by `utils.layout_init`, the same builder
the Nodz node dialogs use, so the `currentData` dict it fills (keyed by widget
object name, `LineEdit#<Module.Function>#<kwarg>`) is exactly what
`create_real_time_analysis_thread` consumes. Here the per-kwarg
Value/Variable/Advanced switch is left out (`showVariableOptions=False`): there
are no Nodz variables to pick from in the Controls dock, so every kwarg is a
Value.

Settings persist between sessions in the `RTAnalysis` section of
`glados_state.json` (`RT_STATE_SECTION`): the selected method plus every value
that differs from its default. Storing only the differences means a default
changed in a node's code still reaches users who never touched that setting.
"""
from __future__ import annotations

import logging
import os
import sys

import numpy as np
from PyQt5.QtCore import QEvent, QSize, Qt, QTimer
from PyQt5.QtGui import QBrush, QColor, QFont
from PyQt5.QtWidgets import (
    QCheckBox,
    QComboBox,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QStyledItemDelegate,
    QVBoxLayout,
    QWidget,
)

if 'glados_pycromanager' not in sys.modules and 'site-packages' not in __file__:
    sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..')))

import glados_pycromanager.GUI.utils as utils
from glados_pycromanager.ui.layout import ROLE_ACTIVE, ROLE_MODIFIED, compact_spacing, current_theme, set_role

#: Top-level section of glados_state.json holding this panel's settings.
RT_STATE_SECTION = 'RTAnalysis'
#: Parameter rows visible before the parameter area scrolls.
RT_PARAMS_VISIBLE_ROWS = 6
#: Debounce for writing settings: a typed number saves once, not per keystroke.
RT_SETTINGS_SAVE_DELAY_MS = 500
#: How often an active panel checks whether its analysis is still running (the
#: user can end it from elsewhere, e.g. by closing its napari layer).
RT_ACTIVE_POLL_MS = 500

_KWARG_WIDGET_PREFIX = 'LineEdit'


def discover_rt_function_names():
    """`Module.Function` names of every RT-analysis node: package first, then AppData."""
    import appdirs
    builtin = utils.functionNamesFromDir('AutonomousMicroscopy\\Real_Time_Analysis')
    appdata_dir = os.path.join(appdirs.user_data_dir(), 'Glados-PycroManager',
                               'AutonomousMicroscopy', 'Real_Time_Analysis')
    try:
        found = utils.functionNamesFromDir(appdata_dir)
    except OSError as exc:
        logging.debug('No AppData RT-analysis nodes at %s: %s', appdata_dir, exc)
        found = []
    #functionNamesFromDir can report AppData nodes twice; keep the first, in order.
    extra = [name for name in dict.fromkeys(found) if name not in builtin]
    return builtin + extra


def _kwarg_parts(widget):
    """`(function, kwarg)` for a Value-mode kwarg widget, else None."""
    parts = widget.objectName().split('#')
    if len(parts) == 3 and parts[0] == _KWARG_WIDGET_PREFIX:
        return parts[1], parts[2]
    return None


def _as_bool(value) -> bool:
    if isinstance(value, str):
        return value.strip().lower() in ('true', '1')
    return bool(value)


def widget_value(widget) -> str:
    """A kwarg widget's value as the string `currentData` stores for it."""
    if isinstance(widget, QCheckBox):
        return str(widget.isChecked())
    return widget.text()


def set_widget_value(widget, value) -> None:
    if isinstance(widget, QCheckBox):
        widget.setChecked(_as_bool(value))
    else:
        widget.setText('' if value is None else str(value))


def default_widget_value(widget, function, kwarg) -> str:
    """What `widget` shows for the kwarg's declared default, in `widget_value` form."""
    default = utils.defaultValueFromKwarg(function, kwarg)
    if isinstance(widget, QCheckBox):
        return str(_as_bool(default) if default is not None else False)
    return '' if default is None else str(default)


class _ParamsScrollArea(QScrollArea):
    """Scrolls the parameters, asking for at most `RT_PARAMS_VISIBLE_ROWS` rows.

    A method with few parameters gets just the rows it needs; one with twenty
    scrolls instead of stretching the dock.
    """

    def __init__(self, row_reference, parent=None):
        super().__init__(parent)
        self._row_reference = row_reference
        row_reference.installEventFilter(self)
        self.setWidgetResizable(True)
        self.setFrameShape(QFrame.NoFrame)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Preferred)

    def _cap_height(self):
        row = self._row_reference.sizeHint().height() + compact_spacing()
        return RT_PARAMS_VISIBLE_ROWS * row

    def sizeHint(self):
        content = self.widget().sizeHint() if self.widget() is not None else QSize(0, 0)
        width = content.width() + self.verticalScrollBar().sizeHint().width()
        return QSize(width, min(content.height(), self._cap_height()))

    #Events after which the hint may have changed: the content re-laid out (another
    #method's rows shown) or the row reference restyled (the dock stylesheet landing).
    _RESIZE_EVENTS = (QEvent.LayoutRequest, QEvent.StyleChange, QEvent.FontChange)

    def setWidget(self, widget):
        super().setWidget(widget)
        widget.installEventFilter(self)

    def eventFilter(self, watched, event):
        #Layouts cache a widget's size hint until it calls updateGeometry(), and
        #nothing else would: the hint depends on two *other* widgets.
        if event.type() in self._RESIZE_EVENTS:
            self.updateGeometry()
        return False

    def minimumSizeHint(self):
        return QSize(super().minimumSizeHint().width(), self._row_reference.sizeHint().height())


class RTAnalysisPanel(QWidget):
    """The Controls dock's RT-analysis section; see the module docstring."""

    def __init__(self, shared_data, persist=False, function_names=None, parent=None):
        super().__init__(parent)
        self.shared_data = shared_data
        self.persist = persist
        self._runs = {}
        self._loading = False

        if function_names is None:
            function_names = discover_rt_function_names()
        _display_names, self.displayNameMap = utils.displayNamesFromFunctionNames(function_names, '')

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(compact_spacing())

        #Full width, over the parameter labels too: method names are long.
        self.methodDropdown = QComboBox()
        self.methodDropdown.setObjectName('comboBox_RTanalysisFunctions_KEEP')
        self.methodDropdown.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        for display_name, _function in self.displayNameMap:
            self.methodDropdown.addItem(display_name)
        #The default (menu-style) popup delegate ignores per-item background and
        #font, which is how running methods are marked in the list.
        self.methodDropdown.setItemDelegate(QStyledItemDelegate(self.methodDropdown))
        layout.addWidget(self.methodDropdown)

        #layout_init's widgets find `currentData` through their parent widget
        #(`changeDataVarUponKwargChange`) and through `layout.parent().parent()`
        #(`layout_changedDropdown`), so the grid sits one layout deep inside the
        #widget that carries it.
        self.paramsWidget = QWidget()
        paramsOuter = QVBoxLayout(self.paramsWidget)
        paramsOuter.setContentsMargins(0, 0, 0, 0)
        self.paramsLayout = QGridLayout()
        self.paramsLayout.setSpacing(compact_spacing())
        self.paramsLayout.setColumnStretch(1, 1)
        paramsOuter.addLayout(self.paramsLayout)
        paramsOuter.addStretch(1)
        self.currentData = {'__displayNameFunctionNameMap__': self.displayNameMap}
        self.paramsWidget.currentData = self.currentData

        self.paramsScroll = _ParamsScrollArea(self.methodDropdown)
        self.paramsScroll.setWidget(self.paramsWidget)
        layout.addWidget(self.paramsScroll, 1)

        buttons = QHBoxLayout()
        buttons.setSpacing(compact_spacing())
        self.toggleButton = QPushButton('Activate')
        self.toggleButton.clicked.connect(self.toggle)
        self.resetButton = QPushButton('Reset')
        self.resetButton.setToolTip("Restart the running analysis (end, then init) with the settings shown here.")
        self.resetButton.clicked.connect(self.reset)
        self.restoreDefaultsButton = QPushButton('Restore defaults')
        self.restoreDefaultsButton.setToolTip("Set this method's parameters back to their defaults.")
        self.restoreDefaultsButton.clicked.connect(self.restoreDefaults)
        buttons.addWidget(self.toggleButton, 1)
        buttons.addWidget(self.resetButton)
        buttons.addWidget(self.restoreDefaultsButton)
        layout.addLayout(buttons)

        self._saveTimer = QTimer(self)
        self._saveTimer.setSingleShot(True)
        self._saveTimer.setInterval(RT_SETTINGS_SAVE_DELAY_MS)
        self._saveTimer.timeout.connect(self.saveSettings)
        self._activePollTimer = QTimer(self)
        self._activePollTimer.setInterval(RT_ACTIVE_POLL_MS)
        self._activePollTimer.timeout.connect(self.refreshActiveState)

        utils.layout_init(self.paramsLayout, '', self.displayNameMap,
                          current_dropdown=self.methodDropdown, nodzInfo=None, skipInput=True,
                          maxNrRows=10_000, showVariableOptions=False)
        for widget in self.kwargWidgets():
            if isinstance(widget, QCheckBox):
                widget.stateChanged.connect(lambda _state, w=widget: self._onParamEdited(w))
            elif isinstance(widget, QLineEdit):
                widget.textChanged.connect(lambda _text, w=widget: self._onParamEdited(w))
        #Show only the selected method's parameters (layout_init built them all).
        self.methodDropdown.currentIndexChanged.connect(
            lambda _index: utils.layout_changedDropdown(self.paramsLayout, self.methodDropdown,
                                                        self.displayNameMap))
        self.methodDropdown.currentIndexChanged.connect(self._onMethodChanged)

        if self.persist:
            self.loadSettings()
        self._onMethodChanged()
        self.refreshActiveState()

    # ------------------------------------------------------------------ params
    def currentFunction(self):
        return utils.functionNameFromDisplayName(self.methodDropdown.currentText(), self.displayNameMap)

    def kwargWidgets(self, function=None):
        """Value-mode kwarg widgets, of every method or only `function`'s."""
        found = []
        for widget in self.paramsWidget.findChildren(QWidget):
            parts = _kwarg_parts(widget)
            if parts is not None and (function is None or parts[0] == function):
                found.append(widget)
        return found

    def isModified(self, widget):
        function, kwarg = _kwarg_parts(widget)
        return widget_value(widget) != default_widget_value(widget, function, kwarg)

    def _refreshHighlight(self, widget):
        function, kwarg = _kwarg_parts(widget)
        role = ROLE_MODIFIED if self.isModified(widget) else ''
        label = self.paramsWidget.findChild(QLabel, f'Label#{function}#{kwarg}')
        if label is not None:
            set_role(label, role)
        set_role(widget, role)

    def _refreshRestoreButton(self):
        function = self.currentFunction()
        modified = any(self.isModified(w) for w in self.kwargWidgets(function)) if function else False
        self.restoreDefaultsButton.setEnabled(modified)

    def _onParamEdited(self, widget):
        #A running analysis of this method picks the edit up on its next frame,
        #as it did when it read the panel's dict directly. Existing keys only:
        #the analysis thread iterates this dict concurrently.
        run = self._runs.get(_kwarg_parts(widget)[0])
        if run is not None and widget.objectName() in run['info']:
            run['info'][widget.objectName()] = widget_value(widget)
        self._refreshHighlight(widget)
        self._refreshRestoreButton()
        self._scheduleSave()

    def _onMethodChanged(self, *_args):
        for widget in self.kwargWidgets(self.currentFunction()):
            self._refreshHighlight(widget)
        self._refreshRestoreButton()
        self.refreshActiveState()
        self._scheduleSave()

    def restoreDefaults(self):
        """Set the selected method's parameters back to their declared defaults."""
        for widget in self.kwargWidgets(self.currentFunction()):
            function, kwarg = _kwarg_parts(widget)
            set_widget_value(widget, default_widget_value(widget, function, kwarg))

    # ------------------------------------------------------------- persistence
    def settingsState(self):
        """What is persisted: the method and every non-default value."""
        return {
            'selected': self.methodDropdown.currentText(),
            'values': {w.objectName(): widget_value(w)
                       for w in self.kwargWidgets() if self.isModified(w)},
        }

    def _scheduleSave(self):
        if self.persist and not self._loading:
            self._saveTimer.start()

    def saveSettings(self):
        self._saveTimer.stop()
        if not self.persist:
            return
        from glados_pycromanager.io.appdata import save_state_section
        save_state_section(RT_STATE_SECTION, self.settingsState())

    def loadSettings(self):
        from glados_pycromanager.io.appdata import load_glados_state
        state = load_glados_state().get(RT_STATE_SECTION, {})
        if not isinstance(state, dict):
            return
        self._loading = True
        try:
            values = state.get('values', {})
            if isinstance(values, dict):
                for widget in self.kwargWidgets():
                    if widget.objectName() in values:
                        set_widget_value(widget, values[widget.objectName()])
            selected = state.get('selected')
            if selected and self.methodDropdown.findText(selected) >= 0:
                self.methodDropdown.setCurrentText(selected)
        finally:
            self._loading = False

    # -------------------------------------------------------------- activation
    #Every method runs independently: `_runs` maps a method's `Module.Function`
    #name to its thread and its *own* copy of the settings. A shared dict would
    #not do -- the thread reads its method from `__selectedDropdownEntryRTAnalysis__`
    #on every frame, so activating a second method switched the first one over.
    #The buttons always act on the method selected in the dropdown.

    def _displayName(self, function):
        return next((d for d, f in self.displayNameMap if f == function), None)

    def runningFunctions(self):
        """Methods with a running analysis; drops the ones ended elsewhere."""
        live = {id(entry.get('Thread')) for entry in self.shared_data.RTAnalysisQueuesThreads}
        for function in [f for f, run in self._runs.items() if id(run['thread']) not in live]:
            del self._runs[function]
        return list(self._runs)

    def isActive(self, function=None):
        function = function or self.currentFunction()
        return function in self.runningFunctions()

    def refreshActiveState(self):
        running = self.runningFunctions()
        if not running:
            self._activePollTimer.stop()
        active = self.currentFunction() in running
        self.toggleButton.setText('Deactivate' if active else 'Activate')
        self.toggleButton.setToolTip(
            'This analysis is running. Click to stop it and remove its layers.' if active else
            'Start this analysis. With no acquisition running, it also runs once on the '
            'image shown in napari.')
        set_role(self.toggleButton, ROLE_ACTIVE if active else '')
        self.resetButton.setEnabled(active)
        self._refreshDropdownHighlights(running)

    def _refreshDropdownHighlights(self, running):
        """Mark running methods in the dropdown list, and the closed dropdown
        itself while the selected method runs. The item text stays the bare
        display name: methods are looked up by it."""
        theme = current_theme()
        bold = QFont(self.methodDropdown.font())
        bold.setBold(True)
        for index, (_display, function) in enumerate(self.displayNameMap):
            on = function in running
            self.methodDropdown.setItemData(index, QBrush(QColor(theme.active)) if on else None, Qt.BackgroundRole)
            self.methodDropdown.setItemData(index, QBrush(QColor(theme.accent_text)) if on else None, Qt.ForegroundRole)
            self.methodDropdown.setItemData(index, bold if on else None, Qt.FontRole)
            self.methodDropdown.setItemData(index, 'Running' if on else None, Qt.ToolTipRole)
        set_role(self.methodDropdown, ROLE_ACTIVE if self.currentFunction() in running else '')

    def toggle(self):
        if self.isActive():
            self.deactivate()
        else:
            self.activate()

    def acquisitionOngoing(self):
        return bool(getattr(self.shared_data, 'liveMode', False) is True
                    or getattr(self.shared_data, 'mdaMode', False) is True)

    def activate(self, function=None):
        """Start a method's analysis (default: the selected one); with no
        acquisition running, run it once on the image shown in napari."""
        function = function or self.currentFunction()
        if function is None or self.isActive(function):
            return
        #Read the frame before the node adds its own layers on top of the stack.
        frame = None if self.acquisitionOngoing() else self.currentNapariFrame()
        from glados_pycromanager.GUI.AnalysisClass import create_real_time_analysis_thread
        #This method's keys only (kwarg keys are scoped by function name anyway).
        info = {key: value for key, value in self.currentData.items()
                if key.startswith('__') or f'#{function}#' in key}
        info['__selectedDropdownEntryRTAnalysis__'] = self._displayName(function)
        info['__selectedDropdownEntryAnalysis__'] = self._displayName(function)
        info['__realTimeVisualisation__'] = True
        thread = None
        try:
            thread = create_real_time_analysis_thread(
                self.shared_data, analysisInfo=info, delay=None, nodzInfo=None)
        except Exception as exc:  # noqa: BLE001 -- a node's init() can raise anything
            logging.exception('Could not start RT analysis %s', function)
            QMessageBox.warning(self, 'Real-time analysis', f'Could not start the analysis:\n{exc}')
        if thread is not None:
            self._runs[function] = {'thread': thread, 'info': info}
            if frame is not None:
                self._feedFrame(thread, *frame)
            self._activePollTimer.start()
        self.refreshActiveState()

    def deactivate(self, function=None):
        """Stop a method's analysis (default: the selected one) and remove its layers."""
        function = function or self.currentFunction()
        run = self._runs.pop(function, None)
        if run is not None:
            thread = run['thread']
            entries = self.shared_data.RTAnalysisQueuesThreads
            for item in list(entries):
                if item.get('Thread') is not thread:
                    continue
                #A node may own several layers; remove_all tolerates ones already closed.
                visualisation = getattr(thread, 'visualisationObject', None)
                group = getattr(getattr(visualisation, 'napariOverlay', None), 'group', None)
                if group is not None:
                    group.remove_all(self.shared_data.napariViewer)
                #Removing a layer fires layer_removed_event_callback, which already tears
                #the node down; doing it again here would run end() twice.
                if item in entries:
                    thread.destroy()
                    queue = item.get('Queue')
                    if queue is not None:
                        queue.clear()
                    try:
                        entries.remove(item)
                    except ValueError:
                        logging.debug('RT analysis entry already removed')
                logging.debug('Removed analysis thread for %s', function)
                break
        self.refreshActiveState()

    def reset(self):
        """end() then init() again for the selected method, with its current settings."""
        function = self.currentFunction()
        if not self.isActive(function):
            return
        self.deactivate(function)
        #After the layer-removal callback's own deferred cleanup (also a 0 ms timer).
        QTimer.singleShot(0, lambda: self.activate(function))

    # ------------------------------------------------------------ napari frame
    def _ownedLayerNames(self):
        names = set()
        for entry in self.shared_data.RTAnalysisQueuesThreads:
            visualisation = getattr(entry.get('Thread'), 'visualisationObject', None)
            group = getattr(getattr(visualisation, 'napariOverlay', None), 'group', None)
            if group is not None:
                names.update(group.names)
        return names

    def currentNapariFrame(self):
        """`(image, metadata)` of the image napari shows, or None.

        The selected layer when it is an image, else the topmost visible image;
        never a layer an RT node draws into. A layer with more than two
        dimensions is sliced at the viewer's current position.
        """
        viewer = getattr(self.shared_data, 'napariViewer', None)
        if viewer is None:
            return None
        try:
            from napari.layers import Image
        except ImportError:
            return None
        owned = self._ownedLayerNames()

        def usable(layer):
            return isinstance(layer, Image) and layer.name not in owned and not layer.rgb

        layer = viewer.layers.selection.active
        if layer is None or not usable(layer):
            layer = next((l for l in reversed(list(viewer.layers)) if usable(l) and l.visible), None)
        if layer is None:
            logging.info('RT analysis: no image layer in napari to run on')
            return None

        data = layer.data[0] if layer.multiscale else layer.data
        index = ()
        if data.ndim > 2:
            #A layer's dims align with the viewer's trailing dims.
            steps = list(viewer.dims.current_step)[len(viewer.dims.current_step) - data.ndim:][:data.ndim - 2]
            index = tuple(min(max(int(s), 0), n - 1) for s, n in zip(steps, data.shape))
        image = np.asarray(data[index])
        if image.ndim != 2:
            logging.info('RT analysis: layer %r does not give a 2-D image (%s)', layer.name, image.shape)
            return None

        pixel_size = getattr(self.shared_data, 'hw_pixel_size_um', None)
        if not isinstance(pixel_size, (int, float)):
            pixel_size = float(layer.scale[-1])
        metadata = {
            'ImageNumber': 0,
            'Axes': {'time': 0},
            'PixelSize_um': pixel_size,
            'Height': int(image.shape[0]),
            'Width': int(image.shape[1]),
            'SourceLayer': layer.name,
        }
        logging.info('RT analysis: running once on layer %r at %s', layer.name, index)
        return image, metadata

    def _feedFrame(self, thread, image, metadata):
        for entry in self.shared_data.RTAnalysisQueuesThreads:
            if entry.get('Thread') is thread:
                entry['Queue'].append([image, metadata])
                thread.new_image()
                return
