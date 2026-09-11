
import dataclasses
import json
import logging
import os
import sys
import tempfile
from dataclasses import dataclass, fields
from typing import Optional

import appdirs
import useq
from PyQt5.QtCore import QObject, QTimer, pyqtSignal

#Sys insert to allow for proper importing from module via debug
if 'glados_pycromanager' not in sys.modules and 'site-packages' not in __file__:
    sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..')))


from glados_pycromanager.Core import microscopeInterfaceLayer as MIL
from glados_pycromanager.Core.microscope_service import MicroscopeService
from glados_pycromanager.GUI.napariGlados import napariHandler
from glados_pycromanager.GUI.subprocess_pool import WarmSubprocessPool
from glados_pycromanager.GUI.utils import updateAutonousErrorWarningInfo

"""Shared data summary

    Shared_data is a class of shared data between the script, threads, napari, and napari plug-ins. It contains info on e.g. the analysis threads, the napari Viewer, and whether micromanager is acquiring data, or in live mode, or etc
"""

# NOTE: there used to be a `LoggingList(list)` here whose remove() override was
# meant to stop/destroy a removed RT-analysis entry. It was never instantiated
# (RTAnalysisQueuesThreads is a plain list), so that teardown never ran -- and it
# would not have worked anyway, since the removed item is a
# {'Queue':..., 'Thread':...} dict with no .stop()/.destroy(). All four
# RTAnalysisQueuesThreads.remove() call sites already tear the thread down
# explicitly (item['Thread'].destroy() or stop_signal.set()+join()) and drain the
# queue immediately before removing, so the class was deleted rather than wired
# up. See claude_decisions.md (T-A5).


def setting(default, display_name="", description="", input_type="lineEdit", options=None, hidden=False):
    return dataclasses.field(
        default=default,
        metadata={
            "display_name": display_name,
            "description": description,
            "input_type": input_type,
            "options": options or [],
            "hidden": hidden,
        }
    )
        
@dataclass
class MDAConfig:
    vis_method:     str = setting("multiDstack", "MDA Visualisation method",
                                "Choose between MDA Visualisation methods - multiDStack will ensure that all frames are visualised after a full MDA, frameByFrame leaves these blank.",
                                input_type="dropdown", options=["multiDstack", "frameByFrame"])
    backend_method: str = setting("process", "Backend transfer method",
                                "Choose between the transfer method in the backend of the JAVA --> Python layer. Either directly grabs images via RAM (Can cause RAM issues), or performs a save-->load routine (limited by Disk write speed). Process is strongly recommended.",
                                input_type="dropdown", options=["process", "saved"])
    live_mode_method: str = setting(
        "sequence",
        "Live mode method",
        "How live mode drives the camera. 'sequence' runs a continuous "
        "sequence acquisition straight into the circular buffer -- no "
        "acquisition engine and no per-frame event validation -- which is "
        "how Micro-Manager's own live window works and is the faster path. "
        "'mda' is the legacy behaviour: a multi-dimensional acquisition of "
        "live_mode_nr_frames frames, restarted in a loop. Switch to 'mda' "
        "to rule the new path out if live mode misbehaves.",
        input_type="dropdown", options=["sequence", "mda"])
    live_pull_policy: str = setting(
        "latest",
        "Live frame pull policy",
        "Which frame live mode takes from the circular buffer. 'latest' "
        "shows the newest frame and consumes nothing, so the buffer cannot "
        "overflow no matter how far behind the display falls -- correct for "
        "a preview. 'sequential' delivers every frame in order and can "
        "overflow the buffer if the consumer is slower than the camera. "
        "Only applies when live_mode_method == 'sequence'.",
        input_type="dropdown", options=["latest", "sequential"])
    live_mode_nr_frames: int = setting(999,"Number of frames taken for live mode","Only applies when live_mode_method == 'mda', where live mode is a MDA with many frames. Set how many frames here.")
    mmcore_save_format: str = setting(
        "ndtiff",
        "MDA save format (pymmcore-plus)",
        "What an MDA writes to your Storage folder when the pymmcore-plus "
        "backend is selected. 'ndtiff' (default) is the format the "
        "pycromanager backends write: two files per acquisition, written by "
        "Glados on its own thread with bounded memory, ~2-7 ms/frame and "
        "fast random frame reads. 'ome-tiff' is a single interoperable file, "
        "similarly fast to write but with a few seconds of setup before the "
        "first frame. 'ome-zarr' is interoperable too, but pymmcore-plus' "
        "writer keeps the whole acquisition in RAM until it ends and writes "
        "one file per frame -- avoid it for long acquisitions. 'none' "
        "acquires without saving anything. Measured with "
        "'make bench-storage' (docs/bench-storage.txt). Ignored by the "
        "pycromanager backends, which always save NDTiff.",
        input_type="dropdown", options=["ndtiff", "ome-tiff", "ome-zarr", "none"])

@dataclass
class WebhookConfig:
    slack_token:   str = setting("",
                            "Slack Token",   "The token for Slack messaging (Slack-token). Configure via Slack Settings dialog.")
    slack_secret:  str = setting("",
                            "Slack Secret",  "The secret ID for Slack messaging (Slack-secret). Configure via Slack Settings dialog.")
    slack_channel: str = setting("",
                            "Slack Channel", "Channel for the Slack node to send messages to (Slack-channel). Configure via Slack Settings dialog.")
    
@dataclass
class VisualisationConfig:
    fps: int = setting(60, "Visualisation FPS", "Update speed of napari visualisation (in frames per second)")
    contrast_refresh_every_n_frames: int = setting(
        10,
        "Auto-contrast refresh interval (frames)",
        "How often (in displayed live-preview frames) to recompute contrast "
        "limits from the image data. Recomputing every frame is expensive "
        "(a full min/max scan); higher values trade brightness-adjustment "
        "responsiveness for throughput. Set to 1 to recompute every frame.",
    )
    image_scroll_z_modifier: str = setting(
        "Ctrl",
        "Scroll-to-move-Z modifier key (on image)",
        "Modifier key that must be held while scrolling the mouse wheel over "
        "the napari image canvas to move the current Z/focus stage. Choose "
        "'Disabled' to turn this off. Scrolling directly over the Z-stage "
        "buttons always moves the stage, regardless of this setting.",
        input_type="dropdown",
        options=["Ctrl", "Shift", "Disabled"],
        hidden=False,
    )


@dataclass
class MicroManagerConfig:
    path:             str = setting("C:/Program Files/Micro-Manager-2.0",
                                    "Micromanager Path", "Micromanager Path",
                                    hidden=True)
    headless_backend: str = setting("Python",
                                    hidden=True)
    config_path:      str = setting("C:/Program Files/Micro-Manager-2.0/MMConfig_demo.cfg",
                                    "Micromanager config file path", "Micromanager config file path",
                                    hidden=True)
    buffer_mb:        int = setting(4096,  "Buffer size (MB)",  "Buffer size of the headless Micromanager instance",  hidden=True)
    max_memory_mb:    int = setting(12000, "Max memory (MB)",   "Maximum memory footprint of the headless Micromanager instance", hidden=True)


@dataclass
class LoggingConfig:
    log_level: str = setting(
        "INFO",
        "Log level",
        "Console/file log verbosity. DEBUG shows all internal trace messages; INFO is the normal level. Takes effect immediately.",
        input_type="dropdown",
        options=["INFO", "DEBUG", "WARNING", "ERROR"],
        hidden=False,
    )


@dataclass
class RealTimeAnalysisConfig:
    # See https://github.com/kjamartens/Gladoscopy/issues/16: nodes whose
    # __function_metadata__ sets "__runInSubprocess__" (e.g. Real-Time FFT)
    # normally run in a separate OS process (AnalysisProcess_customFunction)
    # to avoid Python GIL contention with the UI thread. This is a global
    # kill switch: set to "False" to force every RT-analysis node back onto
    # the older same-process QThread execution (AnalysisThread_customFunction)
    # regardless of its own opt-in -- useful for troubleshooting (e.g. under
    # an IDE debugger that doesn't like subprocess.spawn) or on a system
    # where multiprocessing itself is problematic.
    subprocess_isolation: str = setting(
        "True",
        "RT-analysis: use a separate CPU core (subprocess)",
        "Nodes that opt into it (e.g. Real-Time FFT) run their compute in a "
        "separate OS process, so a slow/GIL-heavy analysis can't freeze the "
        "UI ('True', recommended). Set to 'False' to force the older "
        "same-process/same-thread execution for every node instead (legacy "
        "behaviour, useful for troubleshooting). Read fresh each time you "
        "(re)activate real-time analysis -- no restart required.",
        input_type="dropdown",
        options=["True", "False"],
        hidden=False,
    )


@dataclass
class PerformanceConfig:
    default_capture_seconds: int = setting(
        5,
        "Performance Mode: default capture window (s)",
        "Default duration for a Performance Mode capture; adjustable per-run "
        "via the spinbox in the Performance panel.",
    )
    hotspot_top_n: int = setting(
        25,
        "Performance Mode: hotspot rows shown",
        "How many top cumulative-time functions to show per cProfile table "
        "(main process and each subprocess-isolated RT-analysis node).",
        hidden=True,
    )


@dataclass
class Config:
    mda_config:           MDAConfig           = dataclasses.field(default_factory=MDAConfig)
    visualisation_config: VisualisationConfig = dataclasses.field(default_factory=VisualisationConfig)
    micromanager_config: MicroManagerConfig  = dataclasses.field(default_factory=MicroManagerConfig)
    webhook_config: WebhookConfig  = dataclasses.field(default_factory=WebhookConfig)
    logging_config:       LoggingConfig       = dataclasses.field(default_factory=LoggingConfig)
    rt_analysis_config:   RealTimeAnalysisConfig = dataclasses.field(default_factory=RealTimeAnalysisConfig)
    performance_config:   PerformanceConfig   = dataclasses.field(default_factory=PerformanceConfig)


# Phase 7.1 moved the JSON load/save bodies to
# `glados_pycromanager.io.appdata`. Phase 7.2 adds `DeprecationWarning`
# shims so call sites that still import from `sharedFunctions` (the
# legacy path) see a one-time warning. Phase 18.1 deletes both wrappers
# entirely.
import warnings as _shim_warnings  # noqa: E402

from glados_pycromanager.io import appdata as _appdata  # noqa: E402

_DEPRECATION_MSG = (
    "{name}() has moved to glados_pycromanager.io.appdata.{name}; the "
    "GUI.sharedFunctions re-export is scheduled for removal in Phase 18.1 "
    "of claude_project.md."
)


def load_config_from_json(cfg):
    _shim_warnings.warn(
        _DEPRECATION_MSG.format(name="load_config_from_json"),
        DeprecationWarning,
        stacklevel=2,
    )
    return _appdata.load_config_from_json(cfg)


def save_config_to_json(cfg):
    _shim_warnings.warn(
        _DEPRECATION_MSG.format(name="save_config_to_json"),
        DeprecationWarning,
        stacklevel=2,
    )
    return _appdata.save_config_to_json(cfg)


class Shared_data(QObject):
    mda_acq_done_signal = pyqtSignal(bool)
    #Initialises the info of shared data
    def __init__(self):
        super().__init__()
        self._liveMode = False
        self._mdaMode = False
        # Bumped by the _mdaModeParams setter; see it for why. Must exist
        # before the assignment below, which goes through that setter.
        self._mdaModeParamsGeneration = 0
        self._mdaModeParams = []
        self._napariViewer = None
        self._headless = False
        self._busy = False
        self._core = []
        self._MILcore: "MIL.MicroscopeInterfaceLayer | None" = None
        # T-B2: mirrored hardware constants. The display path must never call
        # MIL -- on PYCROMANAGER_JAVA a bridge round trip was measured at
        # ~257 ms, and napariUpdateLive used to make one per candidate frame on
        # the GUI thread. These plain attributes are refreshed from MIL only at
        # the points where the hardware value can actually change (core bind,
        # set_exposure, set_roi/clear_roi, acquisition start) via the mirror
        # callback registered in the `MILcore` setter below. `None` means "not
        # read yet"; readers fall back to MIL once and the refresh fills it in.
        self.hw_exposure_ms: float | None = None
        self.hw_pixel_size_um: float | None = None
        self.hw_image_shape: tuple | None = None
        self.hw_roi: tuple | None = None
        # T-B3: the single owning thread for `MILcore`. Created by
        # `start_microscope_service()` once a backend is bound; until then (and
        # in tests / the napari-plugin path) every caller keeps talking to MIL
        # directly, which T-B1's re-entrant lock still makes safe.
        self.microscope_service = None
        
        self._RTAnalysisQueuesThreads = []#{'Queue': [],'Thread':LoggingList()}
        # self._analysisThreads = LoggingList()
        # self._RTAnalysisQueues = []

        # RT-analysis subprocess startup speedups (see AnalysisClass.py's
        # AnalysisProcess_customFunction and subprocess_pool.py):
        # - _rt_subprocess_cache: still-alive subprocess+queues (+ the
        #   main-process visualisation shadow object) parked on stop(), keyed
        #   by a hash of the node's analysisInfo config, so restarting the
        #   *same* node reclaims its already-warm worker instead of a cold
        #   spawn + reimport + model reload.
        # - _rt_subprocess_pool: one pre-spawned, pre-imported "blank" process
        #   kept ready so the *first* subprocess-isolated node started in a
        #   session isn't a cold spawn either. Started as early as possible
        #   from GUI_napari.py's main().
        self._rt_subprocess_cache = {}
        self._rt_subprocess_pool = WarmSubprocessPool()

        self._mdaImageQueues = []
        self._defaultFocusDevice = ''
        self._mdaModeSaveLoc = ['','']
        self._mdaModeNapariViewer = None
        self.mdaDatasets = []
        #The dataset the current/last MDA acquisition produced, or None if it
        #produced none. mdaDatasets[-1] can be an earlier acquisition's (T-D8).
        self.mdaCurrentDataset = None
        self.pyMMCdataset = None
        self.activeMDAobject = None
        self.mdaZarrData = {}
        # See the "Temporary store directories" methods below. Keyed by napari
        # layer name, one TemporaryDirectory per zarr store; the NDTiff scratch
        # dataset gets its own slot.
        self.mdaZarrTempDirs = {}
        self.pyMMCdatasetTempDir = None
        # The active ZarrFrameWriter, published by napariHandler so the
        # module-level display path can ask how far behind the disk it is and
        # render the newest slice that actually exists rather than a queued one.
        self.zarrFrameWriter = None
        # Where the pymmcore-plus MDA output handler actually wrote this
        # acquisition, so `_acquisition_storage_path()` can report the user's
        # Storage folder rather than the scratch zarr's temp directory.
        self.mdaSavedPath = None
        self.nodzInstance = None
        self.backend='JAVA' #JAVA or Python, if running headlessly
        self.loadingOngoing = False #Set to true if loading of a nodz instance is actively ongoing - halts checking for errors and such.
        self.last_display_update_time = 0
        self.newestLayerName = '' #Updated with whatever the newest layer name is, when called from napariGlados.py
        self._warningErrorInfoInfo = Dict_Specific_WarningErrorInfo({'Errors': [], 'Warnings': [], 'Info': {'LastNodeRan': None, 'Other': None}},parent=self)
        self.liveModeUpdateOngoing = False
        self.liveModeVisualisationThreadRunning=False
        self.debugImageArrivalTimes = []
        self.debugImageDisplayTimes = []

        # Performance Mode (glados_pycromanager/observability/perf_capture.py):
        # native OS thread id -> human label, refreshed as threads come and go
        # (acquisition/visualisation workers, one per active RT-analysis node).
        # Read fresh on every capture window, not cached at app start.
        self.perfThreadLabels: dict = {}
        
        self.config = Config()
        load_config_from_json(self.config)

        # Apply the persisted log level immediately after config is loaded
        try:
            from glados_pycromanager.observability.logger import set_log_level
            set_log_level(self.config.logging_config.log_level)
        except Exception as exc:
            logging.warning("Could not apply saved log level: %s", exc)

        #Overwrite all values that can be found from the .JSON:x
        #load from appdata
        appdata_folder = appdirs.user_data_dir()#os.getenv('APPDATA')
        if appdata_folder is None:
            raise OSError("APPDATA environment variable not found")
        app_specific_folder = os.path.join(appdata_folder, 'Glados-PycroManager')
        os.makedirs(app_specific_folder, exist_ok=True)
        if os.path.exists(os.path.join(app_specific_folder, 'glados_state.json')):
            #Load the mda state
            with open(os.path.join(app_specific_folder, 'glados_state.json')) as file:
                gladosInfo = json.load(file)
                if 'GlobalData' in gladosInfo:
                    globalDataInfo = gladosInfo['GlobalData']
                else:
                    globalDataInfo = {}
        
            for key in globalDataInfo:
                try:
                    self.globalData[key]['value'] = globalDataInfo[key]
                except (KeyError, TypeError, AttributeError) as exc:
                    logging.debug('globalData key %r not present in current schema (%s)', key, exc)
        
        if self.config.webhook_config.slack_token is not None and not len(self.config.webhook_config.slack_token) == 0:
            try:
                import slack
                self.config.webhook_config.slack_client = slack.WebClient(token=self.config.webhook_config.slack_token)
                logging.debug('Slack client initialised')
            except (ValueError, TypeError, AttributeError, OSError) as exc:
                logging.error('Slack client initialisation failed: %s', exc)
    
        # self._mdamodeNapariHandler.mda_acq_done_signal.connect(self.mdaacqdonefunction)
        self._livemodeNapariHandler = napariHandler(self,liveOrMda='live')
        self._mdamodeNapariHandler = napariHandler(self,liveOrMda='mda')
        
        #Store whether we're running via PIP or via a local install
        self._RunningViaPIP = 'site-packages' in __file__ or 'dist-packages' in __file__
        self._RunningLocally = not self._RunningViaPIP
        
        
    # NOTE: Shared_data deliberately does NOT override __setattr__. It used to,
    # purely to log every attribute write at DEBUG -- which called
    # logging.getLogger() 4-6 times per displayed frame on the GUI thread for no
    # diagnostic value that the targeted log lines don't already provide.
    # (The liveMode/mdaMode transitions, which are the writes worth tracing, have
    # their own property setters with their own logging.)

    # --- Mirrored hardware constants (T-B2) -------------------------------

    @property
    def MILcore(self):
        return self._MILcore

    @MILcore.setter
    def MILcore(self, new_value):
        self._MILcore = new_value
        if new_value is not None and hasattr(new_value, "set_hardware_mirror"):
            # MIL calls back on set_core/set_exposure/set_roi/clear_roi.
            new_value.set_hardware_mirror(self._on_hardware_mirror_changed)
            if getattr(new_value, "core", None) is not None:
                self.refresh_hardware_mirror()

    def _on_hardware_mirror_changed(self, reason: str) -> None:
        """MIL mirror callback -- runs on whichever thread changed the hardware."""
        self.refresh_hardware_mirror(reason)

    def refresh_hardware_mirror(self, reason: str = "all") -> None:
        """Re-read the mirrored hardware constants from MIL.

        `reason` is one of ``'core'``, ``'exposure'``, ``'roi'`` or ``'all'``
        (acquisition start / explicit refresh). Never raises: a backend that
        cannot answer leaves the previous mirrored value in place, and the
        readers fall back to MIL themselves.
        """
        mil = self._MILcore
        if mil is None or getattr(mil, "core", None) is None:
            return
        wants_exposure = reason in ("all", "core", "exposure")
        wants_geometry = reason in ("all", "core", "roi")
        if wants_exposure:
            try:
                self.hw_exposure_ms = float(mil.get_exposure())
            except Exception:
                logging.debug("refresh_hardware_mirror: get_exposure failed", exc_info=True)
        if reason in ("all", "core"):
            try:
                self.hw_pixel_size_um = float(mil.get_pixel_size_um())
            except Exception:
                logging.debug("refresh_hardware_mirror: get_pixel_size_um failed", exc_info=True)
        if wants_geometry:
            try:
                roi = mil.get_roi()
                self.hw_roi = tuple(int(v) for v in roi)
                # ROI is (x, y, width, height); image shape is (height, width).
                self.hw_image_shape = (self.hw_roi[3], self.hw_roi[2])
            except Exception:
                logging.debug("refresh_hardware_mirror: get_roi failed", exc_info=True)

    # --- Hardware owner thread (T-B3) -------------------------------------

    def start_microscope_service(self, name: str = "MicroscopeService"):
        """Start the single owner thread for the currently bound `MILcore`.

        Returns the running `MicroscopeService`, or None when no MIL is bound.
        Idempotent: a second call with a service already running is a no-op, and
        a service bound to a *different* MIL (a backend switch) is stopped and
        replaced.
        """
        mil = self._MILcore
        if mil is None:
            logging.warning('start_microscope_service(): no MILcore bound yet')
            return None
        service = self.microscope_service
        if service is not None:
            if service.running and service.mil is mil:
                return service
            service.stop()
        self.microscope_service = MicroscopeService(mil, name=name).start()
        return self.microscope_service

    def stop_microscope_service(self, timeout: float = 5.0) -> None:
        service = self.microscope_service
        if service is None:
            return
        service.stop(timeout)
        self.microscope_service = None

    def microscope_proxy(self, priority=None):
        """A MIL-shaped facade routed through the owner thread.

        Falls back to the raw `MILcore` when no service is running, so callers
        do not have to branch (see `MicroscopeProxy`, which also falls back
        per call if the service stops underneath it).
        """
        service = self.microscope_service
        if service is None:
            return self._MILcore
        if priority is None:
            return service.proxy()
        return service.proxy(priority=priority)

    def mdaacqdonefunction(self):
        logging.debug('mda acq done in shared_data')
        self.mda_acq_done_signal.emit(True)

    def register_perf_thread_label(self, native_id, label: str) -> None:
        """Performance Mode: record a human label for a native OS thread id
        (threading.get_native_id()) so a capture can attribute CPU time to
        e.g. "MDA/acquisition worker" instead of a bare thread number."""
        self.perfThreadLabels[native_id] = label

    def unregister_perf_thread_label(self, native_id) -> None:
        self.perfThreadLabels.pop(native_id, None)

    # --- Temporary store directories (T-D7) ------------------------------
    # Every on-disk scratch store -- the multiDstack zarr arrays, the
    # MMCORE_PLUS NDTiff dataset -- lives in a `tempfile.TemporaryDirectory`
    # whose *object* has to outlive every reader of that directory: its
    # finalizer rmtree()s the directory, so dropping the last reference to it
    # deletes a store a napari layer may still be rendering from.

    @staticmethod
    def _discard_temp_dir(tmpdir) -> None:
        """Delete one temporary store now, tolerating a locked directory."""
        if tmpdir is None:
            return
        try:
            tmpdir.cleanup()
        except OSError as exc:
            # Windows keeps zarr chunk files open until the layer releases them.
            # cleanUpTemporaryFiles and the OS temp sweep are the backstop; a
            # store we could not remove is not worth failing a teardown over.
            logging.debug(
                'Could not remove temporary store %s: %s',
                getattr(tmpdir, 'name', '?'), exc,
            )

    def new_zarr_temp_dir(self, layer_name: str):
        """Create, and take ownership of, `layer_name`'s zarr store directory.

        Per layer, not one shared slot. Both zarr-creation sites in
        `napariGlados` used to assign the same `mdaZarrTempDir` attribute, so
        starting a second MDA dropped the first `TemporaryDirectory` and its
        finalizer rmtree'd a store the first acquisition's napari layer was
        still pointing at.

        Re-creating a store for the *same* layer does replace it: that layer's
        old array is being discarded anyway (see the dimension-mismatch branch
        in `_napariUpdateLive_locked`).
        """
        self._discard_temp_dir(self.mdaZarrTempDirs.pop(layer_name, None))
        tmpdir = tempfile.TemporaryDirectory()
        self.mdaZarrTempDirs[layer_name] = tmpdir
        return tmpdir

    def release_zarr_temp_dir(self, layer_name: str) -> None:
        """Drop `layer_name`'s store. Call when the layer itself goes away."""
        self._discard_temp_dir(self.mdaZarrTempDirs.pop(layer_name, None))

    def new_pyMMC_temp_dir(self):
        """Create, and take ownership of, the NDTiff scratch dataset's directory.

        `PyMMCore_startedAcqCallback` used to write
        `str(tempfile.TemporaryDirectory().name)` -- constructing the object and
        immediately discarding it, so the finalizer deleted the directory and
        the `os.makedirs` right below recreated it with no owner at all.
        """
        self._discard_temp_dir(self.pyMMCdatasetTempDir)
        self.pyMMCdatasetTempDir = tempfile.TemporaryDirectory()
        return self.pyMMCdatasetTempDir

    def release_all_temp_dirs(self) -> None:
        """Remove every scratch store this session created.

        Wired to `aboutToQuit` in `GUI_napari.main()`: the app deliberately
        force-exits via `os._exit(0)`, so no finalizer would otherwise run and
        every store would be left behind in the OS temp directory.
        """
        for layer_name in list(self.mdaZarrTempDirs):
            self.release_zarr_temp_dir(layer_name)
        self._discard_temp_dir(self.pyMMCdatasetTempDir)
        self.pyMMCdatasetTempDir = None
    
    @property
    def _mdaModeParams(self):
        """The current MDA event list, in pycromanager event-dict form.

        Live mode (MMCORE_PLUS backend, `napariGlados.run_MILCoreAcquisition_worker`)
        assigns a raw `useq.MDASequence` here instead of eagerly converting it.
        Converting via `useq.pycromanager.to_pycromanager()` fully iterates and
        pydantic-validates every `MDAEvent` in the sequence (999 events for the
        default `live_mode_nr_frames`) -- wasted work in the common case, since
        `core.run_mda()` iterates+validates the same sequence again, internally,
        to actually drive acquisition (bench_live_display / docs/bench-live-display.md
        traced this to the "~3-4 useq.MDAEvent validations per frame" entry in
        docs/perf-runtime-recipe.md's "Next perf passes"). The conversion here
        only runs -- and is cached -- if something actually reads this property:
        `_get_cached_dimensions` and the RT-analysis dimension bookkeeping in
        pSMLM.py/RT_counter.py, which a plain live-preview session (no RT-analysis
        node, no multiDstack live layer) never triggers.

        MDA mode (`MDAGlados.MDA_acq_from_GUI`) still assigns an already-converted
        list directly here, unaffected -- the getter passes lists through as-is.
        """
        value = self._mdaModeParams_raw
        if isinstance(value, useq.MDASequence):
            from useq.pycromanager import to_pycromanager
            value = to_pycromanager(value)
            self._mdaModeParams_raw = value  # cache the converted list
        return value

    @_mdaModeParams.setter
    def _mdaModeParams(self, value):
        self._mdaModeParams_raw = value
        # Acquisition identity, for caches derived from the event list
        # (napariGlados._get_cached_dimensions). It replaces an `id(params)`
        # cache key, which was unsound: CPython reuses the addresses of freed
        # objects, so the second of two back-to-back acquisitions could get a
        # params list at the first one's old address and silently reuse the
        # first one's dimension map -- and every sliceTuple, the zarr shape and
        # the napari dims stepping derive from that map.
        #
        # Bumped here rather than in the getter's useq->list conversion on
        # purpose: that conversion is the same acquisition, just materialised.
        self._mdaModeParamsGeneration += 1

    #Each shared data property contains of this block of code. This is to ensure that the value of the property is only changed when the setter is called, and that shared_data can communicate between the different parts of the program
    #When adding a new shared_data property, change in __init__ above, and copy/paste this block and change all instances of 'liveMode' to whatever property you create.
    @property
    def liveMode(self):
        return self._liveMode
    @liveMode.setter
    def liveMode(self, new_value):
        if new_value != self._liveMode:
            self._liveMode = new_value
            self.on_liveMode_value_change()
    def on_liveMode_value_change(self):
        logging.info("LIVE mode changed!")
        # T-F10 part 2: the `time.sleep(0.1)` that used to sit here is gone. It
        # blocked whichever thread flipped the flag -- usually the GUI thread --
        # and it did not make anything more synchronous: `acqModeChanged` was
        # (and is) called synchronously either side of it, so the only effect was
        # to *delay* the dispatch by 100 ms. What it papered over was callers
        # that touch hardware immediately after flipping the mode; the one that
        # genuinely did, `MMcontrols.setROI`, now waits on the core explicitly.
        self._livemodeNapariHandler.acqModeChanged(newSharedData=self)
        
        
    @property
    def mdaMode(self):
        return self._mdaMode
    @mdaMode.setter
    def mdaMode(self, new_value):
        if new_value != self._mdaMode:
            logging.debug('new mdamode value: '+str(new_value))
            self._mdaMode = new_value
            self.on_mdaMode_value_change()
    def on_mdaMode_value_change(self):
        logging.debug('shared_data.mdaMode changed to '+str(self._mdaMode))
        # T-F10 part 2: see on_liveMode_value_change above.
        self._mdamodeNapariHandler.acqModeChanged(newSharedData=self)
    
    #NapariViewer property   
    @property
    def napariViewer(self):
        return self._napariViewer
    @napariViewer.setter
    def napariViewer(self, new_value):
        if new_value != self._napariViewer:
            self._napariViewer = new_value
    
    #analysisThreads property        
    @property
    def analysisThreads(self):
        return self._analysisThreads
    
    @analysisThreads.setter
    def analysisThreads(self, new_value):
        logging.info('in analysisthread-setter')
        if new_value != self._analysisThreads:
            self._analysisThreads = new_value
            self.on_analysisThreads_value_change()
    
    def on_analysisThreads_value_change(self):
        logging.debug('Analysis Threads now: '+str(self._analysisThreads))
        removed_entry = None
        if len(self._analysisThreads) < len(self.analysisThreads):
            removed_entry = [entry for entry in self.analysisThreads if entry not in self._analysisThreads][0]
        logging.debug('Analysis Threads now: ' + str(self._analysisThreads))
        if removed_entry is not None:
            logging.debug('Removed entry: ' + str(removed_entry))
        
    #core property        
    @property
    def core(self):
        return self._core
    @core.setter
    def core(self, new_value):
        if new_value != self._core:
            self._core = new_value

    # @property
    # def RTAnalysisQueues(self):
    #     return self._RTAnalysisQueues
    # @RTAnalysisQueues.setter
    # def RTAnalysisQueues(self, new_value):
    #     if new_value != self._RTAnalysisQueues:
    #         self._RTAnalysisQueues = new_value
    #         self.on_RTAnalysisQueues_value_change()
    # def on_RTAnalysisQueues_value_change(self):
    #     logging.debug('RTAnalysisQueues changed')
        
    @property
    def RTAnalysisQueuesThreads(self):
        return self._RTAnalysisQueuesThreads
    @RTAnalysisQueuesThreads.setter
    def RTAnalysisQueuesThreads(self, new_value):
        if new_value != self._RTAnalysisQueuesThreads:
            self._RTAnalysisQueuesThreads = new_value
            self.on_RTAnalysisQueuesThreads_value_change()
    def on_RTAnalysisQueuesThreads_value_change(self):
        logging.debug('_RTAnalysisQueuesThreads changed')
        
        
    @property
    def mdaImageQueues(self):
        return self._mdaImageQueues
    @mdaImageQueues.setter
    def mdaImageQueues(self, new_value):
        if new_value != self._mdaImageQueues:
            self._mdaImageQueues = new_value
            self.on_mdaImageQueues_value_change()
    def on_mdaImageQueues_value_change(self):
        logging.debug('mdaImageQueues changed')
    
    @property
    def busy(self):
        return self._busy
    @busy.setter
    def busy(self, new_value):
        if new_value != self._busy:
            self._busy = new_value
            self.on_busy_value_change()
    def on_busy_value_change(self):
        logging.debug(f"shared_data.busy changed to {self._busy}")
    
    def appendNewMDAdataset(self,mdadataset):
        self.mdaDatasets.append(mdadataset)
        self.mdaCurrentDataset = mdadataset
    
    
    @property
    def warningErrorInfoInfo(self):
        return self._warningErrorInfoInfo

    def on_warningErrorInfoInfo_changed(self,oldValue=None,errorType=None):
        try:
            # logging.debug(f"shared_data.warningErrorInfoInfo changed to {self._warningErrorInfoInfo}")
            if self.loadingOngoing == False:
                from utils import updateAutonousErrorWarningInfo
                updateAutonousErrorWarningInfo(self,updateInfo='All')
        except (AttributeError, ImportError, RuntimeError) as exc:
            pass
            # logging.debug('updateAutonousErrorWarningInfo not available yet: %s', exc)
    
class Dict_Specific_WarningErrorInfo(dict):
    # T-F4: `oldValue` is part of the notification signature but nothing reads
    # it -- `on_warningErrorInfoInfo_changed` accepts and ignores it, and a grep
    # of the codebase finds no other reader. It used to be a *full dict copy*
    # taken on every `__setitem__`, on the GUI thread, several times a second.
    oldValue = None

    #: Set while a coalescing drain is already scheduled (see `_notify_change`).
    _notifyPending = False

    def __init__(self, *args, **kwargs):
        self.parent = kwargs.pop('parent', None)
        self.errorType = kwargs.pop('errorType', None)
        super().__init__(*args, **kwargs)
        self._convert_nested()

    def _convert_nested(self):
        for key, value in self.items():
            if isinstance(value, dict):
                self[key] = Dict_Specific_WarningErrorInfo(value, parent=self, errorType=key)
            elif isinstance(value, list):
                self[key] = [Dict_Specific_WarningErrorInfo(item, parent=self, errorType=key) if isinstance(item, dict) else item for item in value]

    def __setitem__(self, key, value):
        if isinstance(value, dict):
            value = Dict_Specific_WarningErrorInfo(value, parent=self, errorType=key)
        elif isinstance(value, list):
            value = [Dict_Specific_WarningErrorInfo(item, parent=self, errorType=key) if isinstance(item, dict) else item for item in value]
        super().__setitem__(key, value)
        self._notify_change()

    def _notify_change(self):
        """Schedule one rebuild per event-loop turn (T-F4).

        A single logical update writes this dict several times -- the nodz timer
        clears `Warnings` and then appends to it -- and each write used to drive
        the full `updateAutonousErrorWarningInfo` chain: icon lookups, pixmap
        builds and a loop over every node. Setting a dirty flag and draining it
        from a zero-delay singleShot collapses those into one rebuild.

        The deferral only happens on the GUI thread with a live application: a
        zero-delay `QTimer` needs an event loop *in the calling thread*, so from
        a worker thread (or in a headless test) the notification is delivered
        synchronously, exactly as it was before.
        """
        if not self._can_defer_notification():
            self._deliver_change()
            return

        if self._notifyPending:
            return
        self._notifyPending = True
        QTimer.singleShot(0, self._drain_pending_notification)

    @staticmethod
    def _can_defer_notification():
        try:
            from PyQt5.QtCore import QThread
            from PyQt5.QtWidgets import QApplication

            app = QApplication.instance()
            return app is not None and QThread.currentThread() == app.thread()
        except (ImportError, RuntimeError):
            return False

    def _drain_pending_notification(self):
        self._notifyPending = False
        self._deliver_change()

    def _deliver_change(self):
        if self.parent:
            self.parent.on_warningErrorInfoInfo_changed(oldValue=self.oldValue,errorType=self.errorType)
        else:
            self.on_warningErrorInfoInfo_changed(oldValue=self.oldValue,errorType=self.errorType)

    
    def on_warningErrorInfoInfo_changed(self, oldValue=None,errorType=None):
        # This method will be overridden in the Shared_data class
        if self.parent.loadingOngoing == False:
            updateAutonousErrorWarningInfo(self,updateInfo='All')
        pass
