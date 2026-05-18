
import dataclasses
import json
import logging
import os
import sys
import time
from dataclasses import dataclass, fields
from typing import Optional

import appdirs
import slack
from ndstorage import NDTiffDataset
from PyQt5.QtCore import QObject, QTimer, pyqtSignal

#Sys insert to allow for proper importing from module via debug
if 'glados_pycromanager' not in sys.modules and 'site-packages' not in __file__:
    sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..')))


from glados_pycromanager.Core import microscopeInterfaceLayer as MIL
from glados_pycromanager.GUI.napariGlados import napariHandler
from glados_pycromanager.GUI.utils import updateAutonousErrorWarningInfo

"""Shared data summary

    Shared_data is a class of shared data between the script, threads, napari, and napari plug-ins. It contains info on e.g. the analysis threads, the napari Viewer, and whether micromanager is acquiring data, or in live mode, or etc
"""

class LoggingList(list):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.logger = logging.getLogger(__name__)

    def append(self, item):
        super().append(item)
        self.on_analysisThreads_value_change()

    def extend(self, items):
        super().extend(items)
        self.on_analysisThreads_value_change()

    def insert(self, index, item):
        super().insert(index, item)
        self.on_analysisThreads_value_change()

    def remove(self, item):
        super().remove(item)
        self.on_analysisThreads_value_change(removed_entry=item)

    def pop(self, index=None):
        v = super().pop(index)
        self.on_analysisThreads_value_change()
        return v
    
    
    def on_analysisThreads_value_change(self,removed_entry=None):
        logging.debug('Analysis Threads now: '+str(self))
        # removed_entry = None
        # if len(self) < len(self.prevSelf):
        #     removed_entry = [entry for entry in self if entry not in self.prevSelf][0]
        logging.debug('Analysis Threads now: ' + str(self))
        if removed_entry is not None:
            logging.debug('Removed entry: ' + str(removed_entry))
            try:
                removed_entry.stop()
                removed_entry.destroy()
                logging.debug('succesfully stopped/destroyed Analysis thread '+str(removed_entry))
            except (AttributeError, RuntimeError) as exc:
                logging.warning('Could not stop/destroy Analysis thread %s: %s', removed_entry, exc)
    
    

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
    live_mode_nr_frames: int = setting(999,"Number of frames taken for live mode","The live mode here is basically just a MDA with many frames. Set how many frames here.")

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
class Config:
    mda_config:           MDAConfig           = dataclasses.field(default_factory=MDAConfig)
    visualisation_config: VisualisationConfig = dataclasses.field(default_factory=VisualisationConfig)
    micromanager_config: MicroManagerConfig  = dataclasses.field(default_factory=MicroManagerConfig)
    webhook_config: WebhookConfig  = dataclasses.field(default_factory=WebhookConfig)


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
    liveUpdateEvent = pyqtSignal(object)
    #Initialises the info of shared data
    def __init__(self):
        super().__init__()
        self._liveMode = False
        self._mdaMode = False
        self._mdaModeParams = []
        self._napariViewer = None
        self._headless = False
        self._busy = False
        self._core = []
        self.MILcore: MIL.MicroscopeInterfaceLayer | None = None
        
        self._RTAnalysisQueuesThreads = []#{'Queue': [],'Thread':LoggingList()}
        # self._analysisThreads = LoggingList()
        # self._RTAnalysisQueues = []
        
        self._mdaImageQueues = []
        self._defaultFocusDevice = ''
        self._mdaModeSaveLoc = ['','']
        self._mdaModeNapariViewer = None
        self.mdaDatasets = []
        self.pyMMCdataset: NDTiffDataset = NDTiffDataset('./',summary_metadata={})
        self.activeMDAobject = None
        self.mdaZarrData = {}
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
        
        self.config = Config()
        load_config_from_json(self.config)
        
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
        
        
    def __setattr__(self, name, value):
        logging.debug(f"Setting attribute {name} to {value}")
        super().__setattr__(name, value)
    
    def mdaacqdonefunction(self):
        logging.debug('mda acq done in shared_data')
        self.mda_acq_done_signal.emit(True)
    
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
        time.sleep(0.1)
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
        time.sleep(0.1)
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
            logging.debug('updateAutonousErrorWarningInfo not available yet: %s', exc)
    
class Dict_Specific_WarningErrorInfo(dict):
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
        self.oldValue = self.copy()
        if isinstance(value, dict):
            value = Dict_Specific_WarningErrorInfo(value, parent=self, errorType=key)
        elif isinstance(value, list):
            value = [Dict_Specific_WarningErrorInfo(item, parent=self, errorType=key) if isinstance(item, dict) else item for item in value]
        super().__setitem__(key, value)
        self._notify_change()

    def _notify_change(self):
        if self.parent:
            self.parent.on_warningErrorInfoInfo_changed(oldValue=self.oldValue,errorType=self.errorType)
        else:
            self.on_warningErrorInfoInfo_changed(oldValue=self.oldValue,errorType=self.errorType)
            
    def on_warningErrorInfoInfo_changed(self, oldValue=None,errorType=None):
        # This method will be overridden in the Shared_data class
        if self.parent.loadingOngoing == False:
            updateAutonousErrorWarningInfo(self,updateInfo='All')
        pass

class periodicallyUpdate:
    def __init__(self,updateFunction,timing = 10000):
        logging.debug('Initted periodically update with function %s', updateFunction)
        # Create a QTimer to periodically update MM info
        self.timer = QTimer()
        self.timer.setInterval(timing)
        self.timer.timeout.connect(updateFunction)
        self.timer.start()