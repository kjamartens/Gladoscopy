"""Generate the demo recipes in this folder for the SMLMDemoCam Micro-Manager install.

The recipes target `C:\\GitHub\\demoCam_SMLM_MM` loaded through `DemoSMLM.cfg`: one
`SMLMDemoCam` camera, one `SMLMDemoZStage` (the focus device), and only these config
groups -- Fluorophore, Simulation, PSF, Interpolation, Density, Camera_noise.

Rather than hand-writing the JSON, this drives the *real* Nodz flowchart offscreen (a
bundled pymmcore-plus core running `DemoSMLM.cfg`, a stub napari viewer) and saves each
graph through the app's own `saveGraph`, so the files are exactly what the GUI writes.

    .venv/Scripts/python.exe glados_pycromanager/AutonomousMicroscopy/ExampleRecipes/_generate_demo_recipes.py

Set `GLADOS_DEMO_MM_PATH` / `GLADOS_DEMO_CFG` if the demo install lives elsewhere (defaults
are the values in `demo_settings.mk`). Regenerating overwrites the recipes.
"""
from __future__ import annotations

import json
import os
import sys
from types import SimpleNamespace
from unittest.mock import MagicMock

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
os.environ.setdefault('QT_QPA_FONTDIR', 'C:/Windows/Fonts')

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.abspath(os.path.join(HERE, '..', '..', '..'))
sys.path.insert(0, REPO)

# WebEngine must be imported before the QApplication exists (utils.py imports it).
from PyQt5.QtWebEngineWidgets import QWebEngineView  # noqa: F401,E402
from PyQt5.QtCore import QPointF  # noqa: E402
from PyQt5.QtWidgets import QApplication, QComboBox, QGridLayout, QLineEdit  # noqa: E402

_PYMMC = os.path.join(os.path.expanduser('~'), 'AppData', 'Local', 'pymmcore-plus', 'pymmcore-plus', 'mm')
MM_PATH = os.environ.get('GLADOS_DEMO_MM_PATH', os.path.join(_PYMMC, 'Micro-Manager_2.0.3_20260724'))
CFG_PATH = os.environ.get('GLADOS_DEMO_CFG', os.path.join(_PYMMC, 'DemoSMLM.cfg'))

ZSTAGE = 'SMLMDemoZStage'
POS_FILE = os.path.join(HERE, 'demo_zstage_3_planes.pos')


# --------------------------------------------------------------------------------------
# Boot: a real flowchart, headless
# --------------------------------------------------------------------------------------
def boot():
    app = QApplication([])
    from glados_pycromanager.GUI.sharedFunctions import Shared_data
    import glados_pycromanager.Core.microscopeInterfaceLayer as MIL
    from pymmcore_plus import CMMCorePlus

    sd = Shared_data()
    sd.MILcore = MIL.MicroscopeInterfaceLayer()
    core = CMMCorePlus(mm_path=MM_PATH)
    sd.MILcore.set_core(core)
    core.loadSystemConfiguration(CFG_PATH)
    viewer = MagicMock()  # napari needs a GL context; the flowchart only stores it
    sd.napariViewer = viewer

    import glados_pycromanager.GUI.MMcontrols as MMC
    MMC.shared_data, MMC.core, MMC.napariViewer = sd, sd.MILcore, viewer
    from glados_pycromanager.GUI import FlowChart_dockWidgets as F

    mm_json = json.load(open(os.path.join(REPO, 'glados_pycromanager', 'GUI', 'MM_PycroManager_JSON.json')))
    fc = F.flowChart_dockWidgets(sd.MILcore, mm_json, QGridLayout(), sd)
    return app, core, F, fc


app, core, F, fc = boot()
from glados_pycromanager.GUI import utils  # noqa: E402


def reset_graph():
    fc.clearGraph()
    fc.nodes = []
    for nodeType in fc.nodeInfo:
        if nodeType[:2] != '__':
            fc.nodeInfo[nodeType]['NodeCounter'] = 0
            fc.nodeInfo[nodeType]['NodeCounterNeverReset'] = 0
    fc.globalVariables = {}


# --------------------------------------------------------------------------------------
# Building blocks
# --------------------------------------------------------------------------------------
def _type_of(node):
    return fc.nodeLookupName_withoutCounter(node.name)


def add(ntype, x, y):
    node = fc.createNode(name=ntype + '_', preset='node_preset_1', position=QPointF(x, y),
                         displayName=fc.nodeInfo[ntype]['displayName'], nodeInfo=fc.nodeInfo[ntype])
    app.processEvents()
    return node


def link(a, b, src=None, dst=None):
    """Connect `a`'s finished plug to `b`'s start socket (or the named attributes)."""
    if src is None:
        src = fc.nodeInfo[_type_of(a)]['finishedAttributes'][0]
    if dst is None:
        dst = fc.nodeInfo[_type_of(b)]['startAttributes'][0]
    fc.createConnection(a.name, src, b.name, dst, plugSkipSignalEmit=True, socketSkipSignalEmit=False)


def chain(*nodes):
    for a, b in zip(nodes, nodes[1:]):
        link(a, b)


def note(x, y, text):
    n = add('stickyNote', x, y)
    n.stickyNoteInfo = text
    fc.set_readable_text_after_dialogChange(n, None, 'stickyNote')
    return n


def general(node, storeAttr, internal, fields):
    """Fill one of the Value/Variable/Advanced dialogs (timer, if, global vars, ...).

    `fields` maps a variable name to `(mode, text)`, mode being Value | Variable | Advanced.
    """
    info = {}
    for var, (mode, text) in fields.items():
        info[f'ComboBoxSwitch#{internal}#{var}'] = mode
        for prefix, m in (('LineEdit', 'Value'), ('LineEditAdv', 'Advanced'), ('LineEditVariable', 'Variable')):
            info[f'{prefix}#{internal}#{var}'] = text if m == mode else ''
    setattr(node, storeAttr, info)
    return info


def timer(x, y, seconds):
    n = add('timer', x, y)
    general(n, 'timerInfo', 'timerDialog', {'wait_time': ('Value', str(seconds))})
    fc.set_readable_text_after_dialogChange(n, SimpleNamespace(timerInfo=n.timerInfo), 'timer')
    return n


def new_var(x, y, name, value):
    n = add('newGlobalVar', x, y)
    general(n, 'newGlobalVarInfo', 'newVarChange',
            {'globalVarName': ('Value', name), 'globalVarValue': ('Value', str(value))})
    # what newGlobalVarCallAction does at run time; the change/if nodes' preview text needs it now
    fc.globalVariables[name] = {'data': value, 'type': [type(value)], 'importance': 'informative', 'lastUpdateTime': 0}
    fc.set_readable_text_after_dialogChange(n, None, 'newGlobalVar')
    return n


def change_var(x, y, name, expr):
    n = add('changeGlobalVar', x, y)
    general(n, 'changeGlobalVarInfo', 'globalVarChange',
            {'globalVarName': ('Variable', f'{name}@Global'), 'globalVarValue': ('Advanced', expr)})
    fc.set_readable_text_after_dialogChange(n, None, 'changeGlobalVar')
    return n


def if_statement(x, y, variable, comparator, against):
    n = add('ifStatement', x, y)
    general(n, 'ifStatementInfo', 'ifStatementDialog',
            {'valueToCheck': ('Variable', variable), 'comparator': ('Value', comparator),
             'valueCheckAgainst': ('Value', str(against))})
    fc.set_readable_text_after_dialogChange(n, None, 'ifStatement')
    return n


def set_presets(x, y, presets):
    """A "Change Properties" node setting `(group, preset)` config-group presets."""
    n = add('changeProperties', x, y)
    fc.changeConfigStorageInNodz(n, presets)
    fc.set_readable_text_after_dialogChange(
        n, SimpleNamespace(ConfigsToBeChanged=lambda: [list(p) for p in presets]), 'changeProperties')
    return n


def move_z(x, y, um):
    """Relative move of the demo z-stage."""
    n = add('changeStagePos', x, y)
    info = [[ZSTAGE, um], ['__chosenRelStage__', ZSTAGE]]
    fc.changeRelStageStorageInNodz(n, info)
    fc.set_readable_text_after_dialogChange(n, SimpleNamespace(RelStageInfo=lambda: info), 'changeStagePos')
    return n


def visualisation(x, y, layer, colormap='gray'):
    n = add('visualisation', x, y)
    n.visualisation_currentData['layerName'] = layer
    n.visualisation_currentData['colormap'] = colormap
    fc.set_readable_text_after_dialogChange(
        n, SimpleNamespace(layerNameEdit=SimpleNamespace(text=lambda: layer),
                           colormapComboBox=SimpleNamespace(currentText=lambda: colormap)), 'visualisation')
    return n


def acquisition(x, y, *, frames=None, exposure_ms=50, z=None, interval_s=0.0):
    """An MDA node, configured through the real MDA dialog.

    `frames`: number of time points (None -> 1). `z`: `(start_um, end_um, n_steps)` for a
    z-stack on the demo focus device.
    """
    n = add('acquisition', x, y)
    dlg = F.nodz_openMDADialog(parentData=fc, currentNode=n)
    m = dlg.mdaconfig
    m.GUI_show_z_chkbox.setChecked(z is not None)
    m.GUI_show_time_chkbox.setChecked(True)
    m.GUI_show_exposure_chkbox.setChecked(True)
    m.showOptionChanged()
    m.exposureEntry.setText(str(exposure_ms))
    m.timePointEntry.setText(str(frames or 1))
    m.timeIntervalEntry.setText(str(interval_s))
    if z is not None:
        start, end, steps = z
        m.z_oneDstageDropdown.setCurrentText(ZSTAGE)
        m.z_startEntry.setText(str(start))
        m.z_endEntry.setText(str(end))
        m.z_nrsteps_radio.setChecked(True)
        m.z_nrsteps_entry.setText(str(steps))
    m.get_MDA_events_from_GUI()
    fc.set_readable_text_after_dialogChange(n, dlg, 'acquisition')
    skip = ['gui', 'core', 'shared_data', 'has_GUI', 'data', 'staticMetaObject', 'MDA_completed', 'MM_JSON']
    for attr in vars(m):
        if attr not in skip:
            setattr(n.mdaData, attr, getattr(m, attr))
    return n


def _set_kwargs(data, function, kwargs, mode='Value'):
    for kw, val in kwargs.items():
        data[f'LineEdit#{function}#{kw}'] = str(val)
        data[f'ComboBoxSwitch#{function}#{kw}'] = mode


def analysis(x, y, display_name, kwargs=None):
    """An "Analysis [Measurement]" node running the function with this display name."""
    n = add('analysisMeasurement', x, y)
    data = n.scoring_analysis_currentData
    fname = dict(data['__displayNameFunctionNameMap__'])[display_name]
    data['__selectedDropdownEntryAnalysis__'] = display_name
    _set_kwargs(data, fname, kwargs or {})
    utils.analysis_outputs_to_variableNodz(n)
    fc.set_readable_text_after_dialogChange(n, SimpleNamespace(currentData=data), 'analysisMeasurement')
    return n


def custom_function(x, y, display_name, kwargs=None):
    n = add('customFunction', x, y)
    data = n.customFunction_currentData
    fname = dict(data['__displayNameFunctionNameMap__'])[display_name]
    data['__selectedDropdownEntryAnalysis__'] = display_name
    _set_kwargs(data, fname, kwargs or {})
    utils.customFunction_outputs_to_variableNodz(n)
    fc.set_readable_text_after_dialogChange(n, SimpleNamespace(currentData=data), 'customFunction')
    return n


def rt_analysis(x, y, display_name, kwargs=None, visualise=True):
    """A "Real-Time analysis" node, configured through the real dialog."""
    n = add('realTimeAnalysis', x, y)
    dlg = F.nodz_realTimeAnalysisDialog(currentNode=n, parent=fc)
    dlg.comboBox_RTanalysisFunctions.setCurrentText(display_name)
    fname = dict(dlg.currentData['__displayNameFunctionNameMap__'])[display_name]
    for kw, val in (kwargs or {}).items():
        edit = dlg.findChild(QLineEdit, f'LineEdit#{fname}#{kw}')
        edit.setText(str(val))
    dlg.visualisationBox.setChecked(visualise)
    n.real_time_analysis_currentData = dlg.currentData
    n.real_time_analysis_currentData['__selectedDropdownEntryRTAnalysis__'] = dlg.comboBox_RTanalysisFunctions.currentText()
    n.real_time_analysis_currentData['__realTimeVisualisation__'] = dlg.visualisationBox.isChecked()
    fc.set_readable_text_after_dialogChange(n, dlg, 'RTanalysisMeasurement')
    return n


def case_switch(x, y, variable, cases):
    n = add('caseSwitch', x, y)
    general(n, 'caseSwitchInfo', 'CaseSwitch', {'Var': ('Variable', variable)})
    n.caseSwitchInfo['Plugs'] = list(cases)
    fc.update_plugs_fromDialog(n, list(cases))
    for _ in range(3):
        fc.updateNumberStartFinishedDataAttributes(n, 'caseSwitch')
        fc.update()
    fc.set_readable_text_after_dialogChange(n, None, 'caseSwitch')
    return n


def scoring_end_var(x, y, conditions):
    """The "Scoring end" node. `conditions`: up to five `(variable, operator, value)`.

    An empty list means every scoring passes (the decision has nothing to test).
    """
    n = add('scoringEndVar', x, y)
    dw = fc.decisionWidget
    dw.mode_dropdown.setCurrentText('Direct Decision')
    dw.decisionLayouts['DirectDecision'].mode_dropdown.setCurrentText('All VAR scoring conditions met')
    dw.updateAllDecisions()
    app.processEvents()  # the condition rows are rebuilt (deleteLater) on every update
    layout = dw.decisionLayouts['DirectDecision'].decisiontypes['AND_Score_VAR']
    for i, (var, op, val) in enumerate(conditions):
        row = layout.decisionInfoGUIVAR[i]
        row['varName'].setText(var)
        row['dropdown'].setCurrentText(op)
        row['lineedit'].setText(str(val))
    return n


def _paint_scene():
    """`NodeItem.textbox` only exists once a node has been painted; saveGraph reads it."""
    from PyQt5.QtGui import QImage, QPainter
    rect = fc.scene().itemsBoundingRect()
    img = QImage(max(int(rect.width()), 10), max(int(rect.height()), 10), QImage.Format_ARGB32)
    painter = QPainter(img)
    fc.scene().render(painter)
    # scene.render() can skip an item (seen for a node far above the rest); paint it directly
    for item in fc.scene().nodes.values():
        if not hasattr(item, 'textbox'):
            item.paint(painter, None, None)
    painter.end()
    app.processEvents()


def save(name):
    _paint_scene()
    path = os.path.join(HERE, name)
    fc.saveGraph(path)
    print('saved', path)
    return path


def scan_widget_use_pos_file():
    """Point the (full-run) scanning widget at the bundled 3-plane position list."""
    lay = fc.scanningWidget.scanLayouts['LoadPos']
    lay.lineEdit_posFilename.setText(POS_FILE)
    lay.scanningInfoGUI['LoadPos']['fileName'] = POS_FILE
    fc.scanningWidget.scanMode = 'LoadPos'
    fc.scanningWidget.currentMode = 'LoadPos'


def write_pos_file(z_positions_um):
    """A Micro-Manager .pos list of z-only positions on the demo stage."""
    array = []
    for i, z in enumerate(z_positions_um):
        array.append({
            'DefaultZStage': {'type': 'STRING', 'scalar': ZSTAGE},
            'DevicePositions': {'type': 'PROPERTY_MAP', 'array': [
                {'Device': {'type': 'STRING', 'scalar': ZSTAGE},
                 'Position_um': {'type': 'DOUBLE', 'array': [float(z)]}}]},
            'GridCol': {'type': 'INTEGER', 'scalar': 0},
            'GridRow': {'type': 'INTEGER', 'scalar': 0},
            'Label': {'type': 'STRING', 'scalar': f'Plane{i}_{z:+g}um'},
            'Properties': {'type': 'PROPERTY_MAP', 'scalar': {}},
        })
    doc = {'format': 'Micro-Manager Property Map', 'major_version': 2, 'minor_version': 0,
           'map': {'StagePositions': {'type': 'PROPERTY_MAP', 'array': array}}}
    with open(POS_FILE, 'w') as fh:
        json.dump(doc, fh, indent=2)
    print('wrote', POS_FILE)


# Layout grid: initialisation on top, scoring in the middle, acquisition at the bottom.
COL = 330
ROW_INIT, ROW_SCORE, ROW_ACQ = 0, 380, 800


def x(i):
    return 150 + COL * i


def skeleton():
    """initStart/initEnd, scoringStart, acqStart/acqEnd nodes."""
    return SimpleNamespace(
        i0=add('initStart', x(0), ROW_INIT), i1=add('initEnd', x(5), ROW_INIT),
        s0=add('scoringStart', x(0), ROW_SCORE),
        a0=add('acqStart', x(0), ROW_ACQ), a1=add('acqEnd', x(7), ROW_ACQ))


# --------------------------------------------------------------------------------------
# 01 - simple
# --------------------------------------------------------------------------------------
def recipe_simple():
    reset_graph()
    k = skeleton()
    note(x(3), ROW_INIT, 'SIMPLE: set a sample, always pass scoring, record 100 frames of blinking dyes '
         'and show them in a napari layer.')
    presets = set_presets(x(1), ROW_INIT, [('Simulation', 'Grid'), ('Fluorophore', 'Normal'), ('Density', 'LowDens')])
    chain(k.i0, presets, k.i1)
    end = scoring_end_var(x(2), ROW_SCORE, [])
    chain(k.s0, end)
    scan_widget_use_pos_file()
    acq = acquisition(x(2), ROW_ACQ, frames=100, exposure_ms=50)
    vis = visualisation(x(2), ROW_ACQ + 300, 'Blinking dyes', 'magma')
    chain(k.a0, acq, k.a1)
    link(acq, vis, 'Visual', 'Start')
    save('01_simple_timelapse.json')


# --------------------------------------------------------------------------------------
# 02 - intermediate
# --------------------------------------------------------------------------------------
def recipe_intermediate():
    reset_graph()
    k = skeleton()
    note(x(3), ROW_INIT + 200, 'INTERMEDIATE: 9-spot calibration sample. Scoring records 10 frames and passes '
         'only if the mean gray value is above the camera offset (100) by a bit. The acquisition is a z-stack '
         'with a live sharpness readout - watch it peak at the focal plane.')
    presets = set_presets(x(1), ROW_INIT, [('Simulation', 'Calib'), ('PSF', 'Ext_range'), ('Fluorophore', 'HighInt')])
    settle = timer(x(3), ROW_INIT, 1)
    chain(k.i0, presets, settle, k.i1)
    sacq = acquisition(x(1), ROW_SCORE, frames=10, exposure_ms=50)
    avg = analysis(x(2.5), ROW_SCORE, 'Average gray value', {'ReqKwarg1': 'x', 'ReqKwarg2': 0})
    svis = visualisation(x(2.5), ROW_SCORE + 300, 'Score: mean gray value', 'gray')
    end = scoring_end_var(x(4), ROW_SCORE, [(f'overall_avg_intensity@{avg.name}', '>', 100.4)])
    chain(k.s0, sacq, avg, end)
    link(avg, svis, 'Visual', 'Start')
    acq = acquisition(x(2), ROW_ACQ, frames=3, exposure_ms=50, z=(-2.0, 2.0, 8))
    vis = visualisation(x(2), ROW_ACQ + 300, 'Z-stack', 'gray')
    rt = rt_analysis(x(3.3), ROW_ACQ + 300, 'Sharpness value', {'FilterType': 'Laplacian'})
    back = move_z(x(4), ROW_ACQ, 0)
    chain(k.a0, acq, back, k.a1)
    link(acq, vis, 'Visual', 'Start')
    link(acq, rt, 'Real-time', 'Start')
    scan_widget_use_pos_file()
    save('02_intermediate_scoring_zstack.json')


# --------------------------------------------------------------------------------------
# 03 - complex
# --------------------------------------------------------------------------------------
def recipe_complex():
    reset_graph()
    k = skeleton()
    note(x(0), ROW_INIT - 250, 'COMPLEX: a random "sample" is picked by a dice roll (case/switch -> Simulation preset). '
         'Scoring gates on brightness. Acquisition: z-scan -> mean gray value -> if dim, boost the fluorophore '
         '(VeryHigh), else keep it -> SMLM movie with live pSMLM -> counter bump + wait -> done. '
         'Thresholds are guesses (Normal ~100.5, HighInt ~101, VeryHigh ~103) - adjust to taste.')
    counter = new_var(x(1), ROW_INIT, 'runs_done', 0)
    dice = custom_function(x(2), ROW_INIT, 'Example custom function - Roll a dice', {'MaxDiceValue': 4})
    cs = case_switch(x(3), ROW_INIT, f'DiceResult@{dice.name}', ['1', '2', '3', 'Error'])
    p1 = set_presets(x(4), ROW_INIT - 200, [('Simulation', 'Grid')])
    p2 = set_presets(x(4), ROW_INIT, [('Simulation', 'NUP')])
    p3 = set_presets(x(4), ROW_INIT + 200, [('Simulation', 'Calib')])
    common = set_presets(x(3), ROW_INIT + 300, [('Fluorophore', 'Normal'), ('Density', 'LowDens'),
                                                ('PSF', 'Ext_range'), ('Camera_noise', 'sCMOS_normal')])
    chain(k.i0, counter, dice, cs)
    link(cs, p1, '1', 'Start'); link(cs, p2, '2', 'Start'); link(cs, p3, '3', 'Start')
    link(cs, common, 'Error', 'Start')
    for p in (p1, p2, p3):
        link(p, common, 'Done', 'Start')
    link(common, k.i1, 'Done', 'End')
    sacq = acquisition(x(1), ROW_SCORE, frames=10, exposure_ms=50)
    savg = analysis(x(2.5), ROW_SCORE, 'Average gray value', {'ReqKwarg1': 'x', 'ReqKwarg2': 0})
    end = scoring_end_var(x(4), ROW_SCORE, [(f'overall_avg_intensity@{savg.name}', '>', 100.2)])
    chain(k.s0, sacq, savg, end)
    zacq = acquisition(x(1), ROW_ACQ, frames=1, exposure_ms=50, z=(-2.0, 2.0, 8))
    zvis = visualisation(x(1), ROW_ACQ + 300, 'Z-scan', 'gray')
    zrt = rt_analysis(x(2), ROW_ACQ + 300, 'Sharpness value', {'FilterType': 'Laplacian'})
    zavg = analysis(x(2), ROW_ACQ, 'Average gray value', {'ReqKwarg1': 'x', 'ReqKwarg2': 0})
    chain(k.a0, zacq, zavg)
    link(zacq, zvis, 'Visual', 'Start'); link(zacq, zrt, 'Real-time', 'Start')
    branch = if_statement(x(3), ROW_ACQ, f'overall_avg_intensity@{zavg.name}', '>', 102.0)
    link(zavg, branch)
    keep = set_presets(x(4), ROW_ACQ - 130, [('Fluorophore', 'Normal')])
    boost = set_presets(x(4), ROW_ACQ + 130, [('Fluorophore', 'VeryHigh')])
    link(branch, keep, 'Succeed', 'Start'); link(branch, boost, 'Fail', 'Start')
    movie = acquisition(x(5), ROW_ACQ, frames=300, exposure_ms=30)
    link(keep, movie, 'Done', 'Acquisition start'); link(boost, movie, 'Done', 'Acquisition start')
    psmlm = rt_analysis(x(5), ROW_ACQ + 300, 'pSMLM live + SR', {'ROIradius': 3, 'stdmult': 2, 'srSigma': 1.0})
    link(movie, psmlm, 'Real-time', 'Start')
    bump = change_var(x(6), ROW_ACQ - 150, 'runs_done', '{runs_done@Global}+1')
    wait = timer(x(6), ROW_ACQ + 130, 2)
    link(movie, bump); link(movie, wait)
    link(wait, k.a1, 'Finished', 'End')
    scan_widget_use_pos_file()
    save('03_complex_adaptive_branching.json')


# --------------------------------------------------------------------------------------
# 04 - fun / biology-adjacent
# --------------------------------------------------------------------------------------
def recipe_fun():
    reset_graph()
    k = skeleton()
    note(x(2), ROW_INIT - 250, 'NUCLEAR PORE HUNT: nuclear pore complexes (Nup96-style labelling) are 8-fold symmetric '
         'rings ~107 nm wide - far below the ~250 nm diffraction limit. Blinking dyes + localisation microscopy '
         'let us see them. Watch the live SR panel (right of the raw frames) turn blobs into rings. '
         'The last analysis averages the raw movie: what a plain wide-field microscope would show.')
    presets = set_presets(x(1), ROW_INIT, [('Simulation', 'NUP'), ('PSF', 'Ext_range'), ('Fluorophore', 'HighInt'),
                                           ('Density', 'LowDens'), ('Camera_noise', 'sCMOS_normal'),
                                           ('Interpolation', 'Cubic')])
    settle = timer(x(3), ROW_INIT, 1)
    chain(k.i0, presets, settle, k.i1)
    sacq = acquisition(x(1), ROW_SCORE, frames=10, exposure_ms=50)
    savg = analysis(x(2.5), ROW_SCORE, 'Average gray value', {'ReqKwarg1': 'x', 'ReqKwarg2': 0})
    end = scoring_end_var(x(4), ROW_SCORE, [(f'overall_avg_intensity@{savg.name}', '>', 100.5)])
    chain(k.s0, sacq, savg, end)
    movie = acquisition(x(1.5), ROW_ACQ, frames=1500, exposure_ms=30)
    rt = rt_analysis(x(1.5), ROW_ACQ + 300, 'pSMLM live + SR', {'ROIradius': 3, 'stdmult': 2, 'srSigma': 1.0})
    counter = rt_analysis(x(3), ROW_ACQ + 300, 'RT counter', {'Color': 'yellow'})
    widefield = analysis(x(3), ROW_ACQ, 'Average image (time)')
    wvis = visualisation(x(4.3), ROW_ACQ + 300, 'Wide-field (average of raw movie)', 'gray')
    chain(k.a0, movie, widefield, k.a1)
    link(movie, rt, 'Real-time', 'Start'); link(movie, counter, 'Real-time', 'Start')
    link(widefield, wvis, 'Visual', 'Start')
    scan_widget_use_pos_file()
    save('04_fun_nuclear_pore_hunt.json')


if __name__ == '__main__':
    write_pos_file([-1.0, 0.0, 1.0])
    for fn in (recipe_simple, recipe_intermediate, recipe_complex, recipe_fun):
        try:
            fn()
        except Exception:
            import traceback
            traceback.print_exc()
            print('FAILED', fn.__name__)
    sys.stdout.flush(); sys.stderr.flush()
    os._exit(0)
