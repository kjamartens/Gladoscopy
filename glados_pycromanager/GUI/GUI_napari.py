"""
The main function to call if running glados-napari from the python interface.
"""

#region imports

import argparse
import json
import logging
import os
import socket
import sys

# isort: off
# Must be imported before napari/PyQt5: loading Qt first and then constructing
# a pymmcore.CMMCore later (headless Python backend) crashes with an access
# violation on Windows (see docs/perf-runtime-recipe.md "Known gotchas").
# Importing pymmcore here first avoids it.
import pymmcore  # noqa: F401

import napari
# isort: on
from PyQt5.QtCore import QObject, Qt, QThread, pyqtSignal
from PyQt5.QtGui import (
    QIcon,
    QPixmap,
)
from PyQt5.QtWidgets import (
    QApplication,
    QButtonGroup,
    QFileDialog,
    QGridLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QRadioButton,
    QWidget,
)

#Napari optimizations
os.environ['NAPARI_ASYNC'] = '1'
os.environ['NAPARI_OCTREE'] = '1' #this is rather smoother than async

#Sys insert to allow for proper importing from module via debug
if 'glados_pycromanager' not in sys.modules and 'site-packages' not in __file__:
    sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..')))

import glados_pycromanager.Core.microscopeInterfaceLayer as MIL

#Obtain the helperfunctions
import glados_pycromanager.GUI.utils as utils
from glados_pycromanager.GUI.napariGlados import runNapariPycroManager
from glados_pycromanager.GUI.sharedFunctions import Shared_data
from glados_pycromanager.GUI.utils import *

#endregion

def perform_post_closing_actions(shared_data:Shared_data):
    """Performing closing actions

    Args:
        shared_data: shared_data class (Shared_data())
    """
    #Clean up temporary files
    utils.cleanUpTemporaryFiles(shared_data=shared_data)

class Worker(QObject):
    """
    Worker wrapper for the runNapariPycroManager function
    """
    finished = pyqtSignal()

    def runNapariPycroManagerWrap(self, MM_JSON, shared_data:Shared_data,includeCustomUI:bool=False):
        """
        Runs the NapariPycroManagerWrap function.
        
        Args:
            core: The core object.
            MM_JSON: The MM_JSON object.
            shared_data: The shared data object.
            includeCustomUI (bool, optional): Flag to include custom UI. Defaults to False.
        
        Returns:
            None
        """
        import platform
        # Get the computer's hostname
        if 'SMIPC' in platform.node():
            includeCustomUI=True
        else:
            includeCustomUI=False
        # Run the NapariPycroManager function
        runNapariPycroManager(MM_JSON, shared_data,includecustomUI=includeCustomUI)
        self.finished.emit()

class headlessGUI(QWidget):
    """
    Small GUI for user input on a headless Pycromanager start
    """
    def __init__(self, shared_data: Shared_data):
        super().__init__()
        self.shared_data = shared_data
        self.initUI()
    def initUI(self):
        self.setWindowTitle('Glados-PycroManager-Napari GUI')
        
        iconFolder = utils.findIconFolder()
        icon_path = iconFolder+os.sep+'GladosIcon.ico'
        self.setWindowIcon(QIcon(icon_path))
        
        self.setWindowFlags(self.windowFlags() | Qt.WindowStaysOnTopHint) #type:ignore
        
        # Center the window on the screen, fall back to just somewhere
        #TODO: new config in shared_data
        try:
            screen = QApplication.primaryScreen()
            screen_geometry = screen.availableGeometry() #type: ignore
            self.setGeometry(
                (screen_geometry.width() - 500) // 2,
                (screen_geometry.height() - 350) // 2,
                500,
                350
            )
        except Exception as e:
            logging.warning(f'Try/exception occured! {e}')
            self.setGeometry(100, 100, 500, 350)
            
        # Add a splash screen at the top
        self.splash_label = QLabel(self)
        splash_png = iconFolder+os.sep+'GladosSplash_inv.png'
        splash_pixmap = QPixmap(splash_png)
        new_width = 500
        self.splash_label.setPixmap(
            splash_pixmap.scaled(new_width, int(splash_pixmap.height() * new_width / splash_pixmap.width()),
            Qt.KeepAspectRatio, Qt.SmoothTransformation) #type:ignore
        )
        self.splash_label.setAlignment(Qt.AlignCenter) #type:ignore

        self.backendLabel = QLabel('Backend:', self)

        self.pyMMCorePlusRadio = QRadioButton('PyMMCore+ (testing)', self)
        self.pythonRadio = QRadioButton('Python (recommended)', self)
        self.javaRadio = QRadioButton('Java', self)
        self.pyMMCorePlusRadio.setChecked(False)
        self.pythonRadio.setChecked(False)
        self.javaRadio.setChecked(False)
        if self.shared_data.config.micromanager_config.headless_backend == 'JAVA':
            self.javaRadio.setChecked(True)
        if self.shared_data.config.micromanager_config.headless_backend == 'Python':
            self.pythonRadio.setChecked(True)
        if self.shared_data.config.micromanager_config.headless_backend == 'PyMMCorePlus':
            self.pyMMCorePlusRadio.setChecked(True)

        self.buttonGroup = QButtonGroup()
        self.buttonGroup.addButton(self.pyMMCorePlusRadio)
        self.buttonGroup.addButton(self.pythonRadio)
        self.buttonGroup.addButton(self.javaRadio)

        self.mm_app_pathLabel = QLabel('MicroManager Path:', self)
        self.mm_app_pathLineEdit = QLineEdit(self.shared_data.config.micromanager_config.path, self)
        self.mm_app_browse = QPushButton('...', self)
        self.mm_app_browse.clicked.connect(self.BrowseMMAppPath)

        self.config_fileLabel = QLabel('Config File:', self)
        self.config_fileLineEdit = QLineEdit(self.shared_data.config.micromanager_config.config_path, self)
        self.config_file_browse = QPushButton('...', self)
        self.config_file_browse.clicked.connect(self.BrowseConfigFile)

        self.buffer_size_mbLabel = QLabel('Buffer Size MB:', self)
        self.buffer_size_mbLineEdit = QLineEdit(str(self.shared_data.config.micromanager_config.buffer_mb), self)

        self.max_memory_mbLabel = QLabel('Max Memory MB:', self)
        self.max_memory_mbLineEdit = QLineEdit(str(self.shared_data.config.micromanager_config.max_memory_mb), self)

        self.startButton = QPushButton('Start', self)
        self.startButton.clicked.connect(self.start)
        # Phase 10.9: gate Start on real filesystem state for the MM path
        # and config file. Wire the textChanged signals so the button
        # reflects validity live as the user types or browses.
        self.mm_app_pathLineEdit.textChanged.connect(self._refresh_start_enabled)
        self.config_fileLineEdit.textChanged.connect(self._refresh_start_enabled)
        self._refresh_start_enabled()

        layout = QGridLayout()
        layout.addWidget(self.splash_label,1,0,1,4)
        layout.addWidget(self.backendLabel, 3, 0)
        layout.addWidget(self.pyMMCorePlusRadio, 3, 1)
        layout.addWidget(self.pythonRadio, 3, 2)
        layout.addWidget(self.javaRadio, 3, 3)
        layout.addWidget(self.mm_app_pathLabel, 4, 0)
        layout.addWidget(self.mm_app_pathLineEdit, 4, 1,1,2)
        layout.addWidget(self.mm_app_browse, 4, 3)
        layout.addWidget(self.config_fileLabel, 5, 0)
        layout.addWidget(self.config_fileLineEdit, 5, 1,1,2)
        layout.addWidget(self.config_file_browse, 5, 3)
        layout.addWidget(self.buffer_size_mbLabel, 6, 0)
        layout.addWidget(self.buffer_size_mbLineEdit, 6, 1)
        layout.addWidget(self.max_memory_mbLabel, 6, 2)
        layout.addWidget(self.max_memory_mbLineEdit, 6, 3)
        layout.addWidget(self.startButton, 7, 0, 1, 4) # Span across two columns

        self.setLayout(layout)
        self.show()

    def BrowseMMAppPath(self):
        options = QFileDialog.Options()
        folder_name = QFileDialog.getExistingDirectory(self, "Select Micro-Manager App Path", self.mm_app_pathLineEdit.text(), options=options)
        if folder_name:
            self.mm_app_pathLineEdit.setText(folder_name)

        
    def BrowseConfigFile(self):
        options = QFileDialog.Options()
        file_name, _ = QFileDialog.getOpenFileName(self, "Select Micro-Manager Config File", self.config_fileLineEdit.text(), "Config Files (*.cfg);;All Files (*)", options=options)
        if file_name:
            self.config_fileLineEdit.setText(file_name)

    def _refresh_start_enabled(self) -> None:
        """Enable Start only when the MM path and config file resolve."""
        from glados_pycromanager.GUI.headless_validation import (
            validate_headless_inputs,
        )

        errors = validate_headless_inputs(
            self.mm_app_pathLineEdit.text(),
            self.config_fileLineEdit.text(),
        )
        self.startButton.setEnabled(not errors)
        self.startButton.setToolTip("\n".join(errors) if errors else "")

        
    def start(self):
        self.backend = 'JAVA' if self.javaRadio.isChecked() else 'Python' if self.pythonRadio.isChecked() else 'PyMMCorePlus'
        self.mm_app_path = self.mm_app_pathLineEdit.text()
        self.config_file = self.config_fileLineEdit.text()
        self.buffer_size_mb = int(self.buffer_size_mbLineEdit.text())
        self.max_memory_mb = int(self.max_memory_mbLineEdit.text())
        
        #Also store these in the shared_data
        self.shared_data.config.micromanager_config.path = self.mm_app_path
        self.shared_data.config.micromanager_config.headless_backend = self.backend
        self.shared_data.config.micromanager_config.config_path = self.config_file
        self.shared_data.config.micromanager_config.buffer_mb = self.buffer_size_mb
        self.shared_data.config.micromanager_config.max_memory_mb = self.max_memory_mb
        #And update the JSON
        utils.storeSharedData_GlobalData(self.shared_data)
        
        self.close()


class UserManualWidget(QWidget):
    """Napari dock widget that renders the Glados user manual as HTML."""

    def __init__(self, viewer=None):
        super().__init__()
        import glados_pycromanager
        from PyQt5.QtCore import QUrl
        from PyQt5.QtWebEngineWidgets import QWebEngineView
        from PyQt5.QtWidgets import QVBoxLayout
        from glados_pycromanager.ui.markdown_view import markdown_to_html

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        view = QWebEngineView()
        view.setMinimumSize(680, 800)

        pkg_root = os.path.dirname(glados_pycromanager.__file__)
        md_path = os.path.join(pkg_root, "Documentation", "UserManual.md")
        base_dir = os.path.dirname(os.path.abspath(md_path))
        try:
            view.setHtml(markdown_to_html(md_path), QUrl.fromLocalFile(base_dir + "/"))
        except Exception as exc:
            view.setHtml(f"<p>Could not load user manual: {exc}</p>")
        layout.addWidget(view)


# napari.yaml widget contribution points here
show_UserManualNapari = UserManualWidget


def main():
    """
    Run the main function to start Glados-PycroManager-Napari interface for autonomous microscopy.
    
    Args:
        None
    
    Returns:
        None
    """
    print('Glados-pycromanager main function called')
    
    #Create parser
    parser = argparse.ArgumentParser(description='Glados-PycroManager-Napari: an interface for autonomous microscopy via PycroManager')
    parser.add_argument('--debug', '-d', action='store_true', help='Enable debug')
    parser.add_argument('--backend', choices=['JAVA', 'Python', 'PyMMCorePlus'],
                        help='MM backend to start headlessly. Combined with --config, '
                             'bypasses the startup popup (useful for testing/profiling).')
    parser.add_argument('--config', help='Path to the Micro-Manager .cfg file (skips popup when set with --backend).')
    parser.add_argument('--mm-path', help='Path to the Micro-Manager install directory (defaults to the config in Shared_data).')
    parser.add_argument('--buffer-mb', type=int, help='Circular buffer size in MB (overrides Shared_data default).')
    parser.add_argument('--max-memory-mb', type=int, help='Max Java memory in MB (overrides Shared_data default; ignored by PyMMCorePlus).')
    parser.add_argument('--auto-demo', action='store_true',
                        help='Use the pymmcore-plus bundled demo install + MMConfig_demo.cfg. '
                             'Equivalent to --backend PyMMCorePlus with the bundled paths resolved at runtime.')
    parser.add_argument('--profile-runtime', type=float, metavar='SECS', default=None,
                        help='Dev only: after the GUI is up, auto-enable cProfile, toggle live mode '
                             'on for SECS seconds, then dump top-25 cumulative stats to '
                             'docs/perf-runtime.txt and quit. Requires a working backend (use '
                             '--auto-demo for a hardware-free run).')
    args = parser.parse_args()

    # Validate CLI override combos before any heavy work.
    if args.backend and not (args.config or args.auto_demo):
        parser.error('--backend requires --config (or use --auto-demo)')
    if args.config and not (args.backend or args.auto_demo):
        parser.error('--config requires --backend (or use --auto-demo)')

    #Set up logging to files in appData folder - INFO and DEBUG
    from glados_pycromanager.observability.logger import set_up_logger
    set_up_logger()

    # Create an instance of the shared_data class
    print('Creating shared data.')
    shared_data = Shared_data()
    # Start pre-warming a blank RT-analysis subprocess as early as possible so
    # its spawn + package-tree (+ diplib) import cost is hidden behind however
    # long the user takes to reach the microscope/acquisition setup, instead of
    # being paid on the critical path of the first subprocess-isolated node's
    # start (see AnalysisClass.py's AnalysisProcess_customFunction and
    # subprocess_pool.py).
    shared_data._rt_subprocess_pool.start()
    print('Cleaning up temporary files.')
    utils.cleanUpTemporaryFiles(shared_data=shared_data)

    # --- CLI overrides for the headless popup --------------------------------
    # If the user passed --auto-demo or (--backend AND --config), we resolve
    # the MM install path and config now and skip the popup entirely. Anything
    # not overridden falls back to Shared_data defaults.
    cli_backend = args.backend
    cli_config = args.config
    cli_mm_path = args.mm_path
    if args.auto_demo:
        from pymmcore_plus import find_micromanager
        mm_paths = find_micromanager(return_first=False) or []
        if not mm_paths:
            parser.error('--auto-demo: no Micro-Manager install found by pymmcore_plus.find_micromanager(). '
                         'Run `python -m pymmcore_plus install` first.')
        cli_mm_path = cli_mm_path or str(mm_paths[0])
        cli_backend = cli_backend or 'PyMMCorePlus'
        if not cli_config:
            cli_config = os.path.join(cli_mm_path, 'MMConfig_demo.cfg')
    cli_override = bool(cli_backend and cli_config)
    if cli_override:
        # Push overrides into shared_data so downstream code sees a consistent view.
        shared_data.config.micromanager_config.headless_backend = cli_backend
        shared_data.config.micromanager_config.config_path = cli_config
        if cli_mm_path:
            shared_data.config.micromanager_config.path = cli_mm_path
        if args.buffer_mb is not None:
            shared_data.config.micromanager_config.buffer_mb = args.buffer_mb
        if args.max_memory_mb is not None:
            shared_data.config.micromanager_config.max_memory_mb = args.max_memory_mb
    # -------------------------------------------------------------------------

    #Some QT attributes
    print('Setting QT attributes.')
    QApplication.setAttribute(Qt.AA_EnableHighDpiScaling)# type:ignore
    QApplication.setAttribute(Qt.AA_ShareOpenGLContexts)# type:ignore
    QApplication.setAttribute(Qt.AA_UseStyleSheetPropagationInWidgetStyles, True)# type:ignore

    napariSettings = napari.settings.get_settings() #type: ignore
    if napariSettings.application.playback_fps < shared_data.config.visualisation_config.fps:
        napariSettings.application.playback_fps = shared_data.config.visualisation_config.fps
        print(f'Set the napari Playback FPS to {shared_data.config.visualisation_config.fps}!')

    # get object representing MMCore, used throughout
    #try to open a running instance:
    print('Finding or creating micromanager instance.')
    if cli_override:
        # CLI override: go straight to the requested headless backend, no popup,
        # no Core() probe — the override is explicit intent to run headless.
        mm_cfg = shared_data.config.micromanager_config
        if cli_backend in ('JAVA', 'Python'):
            from pycromanager import Core, start_headless
            logging.info('Headless PycroManager started (CLI override, backend=%s)', cli_backend)
            start_headless(mm_app_path=mm_cfg.path, config_file=mm_cfg.config_path,
                           python_backend=cli_backend == 'Python',
                           buffer_size_mb=int(mm_cfg.buffer_mb), max_memory_mb=int(mm_cfg.max_memory_mb))
            shared_data._headless = True
            shared_data.backend = cli_backend
            shared_data.MILcore = MIL.MicroscopeInterfaceLayer()
            shared_data.MILcore.set_core(Core())
        else:  # PyMMCorePlus
            from pymmcore_plus import CMMCorePlus
            logging.info('Headless PyMMCorePlus started (CLI override)')
            shared_data.MILcore = MIL.MicroscopeInterfaceLayer()
            shared_data.MILcore.set_core(CMMCorePlus(mm_path=mm_cfg.path))
            shared_data.MILcore.get_core().loadSystemConfiguration(mm_cfg.config_path)
            shared_data.MILcore.get_core().setCircularBufferMemoryFootprint(int(mm_cfg.buffer_mb))
            # Max memory MB is not settable in PyMMCorePlus; only buffer_mb (the
            # circular buffer footprint) applies to this backend. Warn instead of
            # silently no-op'ing the setting, since an unbounded acquisition could
            # otherwise grow memory usage further than the user expects.
            logging.warning('max_memory_mb (%s MB) has no effect on the MMCORE_PLUS backend; '
                             'only buffer_mb (%s MB, circular buffer) is applied.',
                             mm_cfg.max_memory_mb, mm_cfg.buffer_mb)
    else:
        # Fast socket probe: avoids spawning a pyjavaz bridge thread (and the
        # resulting 1-second timeout + thread-exception traceback) when MM isn't up.
        _java_mm_up = False
        try:
            with socket.create_connection(("127.0.0.1", 4827), timeout=0.2):
                _java_mm_up = True
        except OSError:
            pass

        if _java_mm_up:
            try:
                from pycromanager import Core
                core = Core()
                shared_data._headless = False
                shared_data.MILcore = MIL.MicroscopeInterfaceLayer()
                shared_data.MILcore.set_core(core)
            except Exception as e:
                logging.warning(f'Java MM detected but Core() failed: {e}')
                _java_mm_up = False  # fall through to dialog

        if not _java_mm_up:
            logging.info('No Java MM server on port 4827 — opening headless dialog')
            appSmall = QApplication([])
            headlessGUIv = headlessGUI(shared_data)
            appSmall.exec_()

            if headlessGUIv.javaRadio.isChecked() or headlessGUIv.pythonRadio.isChecked():
                from pycromanager import Core, start_headless
                logging.info('Headless PycroManager started')

                #Get those settings and use to start headless
                try:
                    start_headless(mm_app_path=headlessGUIv.mm_app_path, config_file=headlessGUIv.config_file, python_backend=headlessGUIv.backend=='Python', buffer_size_mb=int(headlessGUIv.buffer_size_mb), max_memory_mb=int(headlessGUIv.max_memory_mb))
                except Exception as e:
                    print("Error!")
                    print(e)
                    
                #Also store some settings in shared_data
                shared_data._headless = True
                shared_data.backend = headlessGUIv.backend
                # shared_data.core = core
                shared_data.MILcore = MIL.MicroscopeInterfaceLayer()
                shared_data.MILcore.set_core(Core())
            elif headlessGUIv.pyMMCorePlusRadio.isChecked():
                from pymmcore_plus import CMMCorePlus
                logging.info('Headless PyMMCorePlus started')

                shared_data.MILcore = MIL.MicroscopeInterfaceLayer()
                shared_data.MILcore.set_core(CMMCorePlus(mm_path=headlessGUIv.mm_app_path))
                shared_data.MILcore.get_core().loadSystemConfiguration(headlessGUIv.config_file)
                shared_data.MILcore.get_core().setCircularBufferMemoryFootprint(int(headlessGUIv.buffer_size_mb))
                #Max memory MB is not settable in PyMMCorePlus, so we don't set it
                logging.warning('max_memory_mb (%s MB) has no effect on the MMCORE_PLUS backend; '
                                 'only buffer_mb (%s MB, circular buffer) is applied.',
                                 headlessGUIv.max_memory_mb, headlessGUIv.buffer_size_mb)
    
    # T-B3: one owner thread for the bound backend, started as soon as the
    # backend selection above has settled and before any worker exists. Every
    # branch above ends with a MILcore bound, so this is the single place that
    # needs to know. Callers that do not use the service keep talking to MIL
    # directly -- T-B1's re-entrant lock still makes that safe.
    try:
        shared_data.start_microscope_service()
    except Exception:
        logging.exception('Could not start the MicroscopeService; '
                          'falling back to direct MIL access')

    #Open JSON file with MM settings
    try:
        with open(os.path.join(os.path.dirname(os.path.abspath(__file__)), 'MM_PycroManager_JSON.json')) as f:
            MM_JSON = json.load(f)
    except Exception as e:
        logging.warning(f'Try/exception occured! {e}')
        MM_JSON = None
        
        
    app = QApplication(sys.argv)

    shared_data.mainApp = app

    worker = Worker()
    thread = QThread()
    worker.moveToThread(thread)
    thread.started.connect(lambda: worker.runNapariPycroManagerWrap(MM_JSON, shared_data))
    thread.start()

    worker.finished.connect(thread.quit)
    worker.finished.connect(worker.deleteLater)
    thread.finished.connect(thread.deleteLater)

    # --- Optional auto-profile (Phase 13.1) ----------------------------------
    # When --profile-runtime SECS is set, we wait for the napari live-mode
    # handler to be initialised by the worker thread, then enable cProfile,
    # toggle live mode on for SECS seconds, dump top-25 cumulative stats to
    # docs/perf-runtime.txt, and quit. Designed for unattended profiling
    # against `--auto-demo`; not used in normal operation.
    if args.profile_runtime is not None and args.profile_runtime > 0:
        import time as _time

        from PyQt5.QtCore import QTimer  # safe: QApplication already exists

        from glados_pycromanager.observability.perf_capture import PerformanceCapture

        _capture = PerformanceCapture(get_thread_registry=lambda: dict(shared_data.perfThreadLabels))
        _state = {'started': False}
        _secs = float(args.profile_runtime)

        def _dump_profile(reason: str) -> None:
            if _state.get('dumped'):
                return
            _state['dumped'] = True
            if not _state.get('started'):
                print(f'[profile_runtime] quit before capture started (reason={reason}), nothing to dump')
                return
            report = _capture.stop()
            from pathlib import Path as _Path
            out_file = _Path(__file__).resolve().parents[2] / 'docs' / 'perf-runtime.txt'
            out_file.parent.mkdir(parents=True, exist_ok=True)
            header = (
                f"\n=== Runtime profile {_time.strftime('%Y-%m-%d %H:%M:%S')} "
                f"({report.duration_s:.2f}s sample, ended via {reason}, --auto-demo) ===\n"
                f"napariUpdateLive calls observed: {report.frames_rendered}\n\n"
            )
            with out_file.open('a', encoding='utf-8') as f:
                f.write(header)
                f.write(report.hotspots_text)
            print(f'[profile_runtime] wrote {out_file} ({report.frames_rendered} frames, {report.duration_s:.2f}s, reason={reason})')

        def _profile_stop_and_dump():
            # Best-effort: turn live mode off so the worker shuts cleanly. If
            # it's already off (crash), the setter is a no-op.
            try:
                shared_data.liveMode = False
            except Exception as exc:
                logging.warning('profile_runtime: stop liveMode failed: %r', exc)
            _dump_profile('timer')
            QTimer.singleShot(0, app.quit)

        def _profile_poll_livemode():
            """Watchdog: if live mode self-terminates (crash, MDA exhaustion),
            dump immediately and quit — we keep whatever frames we captured."""
            if _state.get('dumped'):
                return
            if not getattr(shared_data, 'liveMode', False):
                _dump_profile('liveMode-auto-stop')
                QTimer.singleShot(0, app.quit)
                return
            QTimer.singleShot(250, _profile_poll_livemode)

        def _profile_try_start():
            handler = getattr(shared_data, '_livemodeNapariHandler', None)
            milcore = getattr(shared_data, 'MILcore', None)
            viewer = getattr(shared_data, 'napariViewer', None)
            if handler is None or milcore is None or viewer is None:
                QTimer.singleShot(250, _profile_try_start)
                return
            if _state['started']:
                return
            _state['started'] = True
            _state['t_started'] = _time.time()
            _capture.start()
            print(f'[profile_runtime] handler ready; profiling live mode for up to {_secs:.1f}s')
            # Mirror the LiveModeButton click path (MMcontrols.changeLiveMode):
            # exposure must be applied to the core BEFORE liveMode flips, else
            # the demo cam races and the MDA can crash. 50 ms is a benign default.
            try:
                milcore.set_exposure(50.0)
            except Exception as exc:
                logging.warning('profile_runtime: set_exposure(50) failed: %r', exc)
            if getattr(shared_data, 'mdaMode', False):
                logging.warning('profile_runtime: mdaMode is True at start — cannot start live mode safely; aborting')
                _dump_profile('mdaMode-conflict')
                QTimer.singleShot(0, app.quit)
                return
            try:
                shared_data.liveMode = True
            except Exception as exc:
                logging.warning('profile_runtime: start liveMode failed: %r', exc)
                _dump_profile('start-failed')
                QTimer.singleShot(0, app.quit)
                return
            QTimer.singleShot(int(_secs * 1000), _profile_stop_and_dump)
            # Watchdog: dump as soon as live mode self-terminates so we don't
            # lose frames if the worker dies before the timer fires. Give the
            # worker 1500 ms to flip liveMode on first (was 500 ms — increased
            # to reduce false-positive dumps when the demo cam completes its
            # first 999-frame batch and the worker briefly has acqstate=True
            # while the next batch restarts).
            QTimer.singleShot(1500, _profile_poll_livemode)

        # 5 s grace lets the worker construct napariHandler, MILcore, the
        # napari viewer, and wire up the dock widgets — flipping liveMode
        # earlier can race the GUI setup and crash the demo cam thread.
        QTimer.singleShot(5000, _profile_try_start)
        # Final safety net: dump on app teardown, in case neither path fired.
        app.aboutToQuit.connect(lambda: _dump_profile('aboutToQuit'))
    # -------------------------------------------------------------------------

    # Terminate any parked/warm RT-analysis subprocesses before the forced exit
    # below -- they now outlive a single node's stop() call (that's the whole
    # point of the warm-restart cache in AnalysisClass.py), so without this
    # they'd otherwise be orphaned rather than dying with their daemon-process
    # parent. Non-blocking (.terminate(), no .join()) to match the no-hang
    # intent of the os._exit(0) below.
    def _terminate_rt_subprocesses():
        try:
            from glados_pycromanager.GUI.AnalysisClass import terminate_all_rt_subprocesses
            terminate_all_rt_subprocesses(shared_data)
        except Exception:
            logging.exception('Failed to terminate RT-analysis subprocesses on quit')
    app.aboutToQuit.connect(_terminate_rt_subprocesses)

    # Same reason, for scratch stores: every multiDstack zarr array and the
    # NDTiff scratch dataset live in a tempfile.TemporaryDirectory, and the
    # os._exit(0) below runs no finalizers -- so without this each session
    # leaves its stores behind in the OS temp directory (T-D7).
    def _remove_temp_stores():
        try:
            shared_data.release_all_temp_dirs()
        except Exception:
            logging.exception('Failed to remove temporary stores on quit')
    app.aboutToQuit.connect(_remove_temp_stores)

    # Same reason again, for the hardware owner thread (T-B3): it is a daemon
    # thread, so os._exit(0) would take it down mid-call. Stopping it first
    # lets an in-flight request finish and fails every queued one, rather than
    # leaving a caller blocked on a reply that can never arrive.
    def _stop_microscope_service():
        try:
            shared_data.stop_microscope_service()
        except Exception:
            logging.exception('Error stopping the MicroscopeService')

    app.aboutToQuit.connect(_stop_microscope_service)

    # Force-exit to avoid the ~10-20 s hang + STATUS_ACCESS_VIOLATION that
    # happens when pyjavaz bridge threads or the CMMCorePlus destructor try
    # to clean up after the Qt event loop ends.  The OS reclaims all resources,
    # so skipping Python's atexit / C-extension destructors is safe here.
    app.aboutToQuit.connect(lambda: os._exit(0))

    #Run the app until closed
    app.exec_()


if __name__ == "__main__":
    main()
