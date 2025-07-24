
import logging
import slack
import time
import appdirs
import os
import json 
from PyQt5.QtCore import QTimer, QObject, pyqtSignal

def is_pip_installed():
    return 'site-packages' in __file__ or 'dist-packages' in __file__

if is_pip_installed():
    from glados_pycromanager.GUI import microscopeInterfaceLayer as MIL
    from glados_pycromanager.GUI.napariGlados import napariHandler
    from glados_pycromanager.GUI.utils import updateAutonousErrorWarningInfo
else:
    import microscopeInterfaceLayer as MIL
    from napariGlados import napariHandler
    from utils import updateAutonousErrorWarningInfo

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
            except:
                logging.debug('UNsuccesfully stopped/destroyed Analysis thread '+str(removed_entry))
                pass
    
"""Shared data summary

    Shared_data is a class of shared data between the script, threads, napari, and napari plug-ins. It contains info on e.g. the analysis threads, the napari Viewer, and whether micromanager is acquiring data, or in live mode, or etc
"""
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
        
        self.globalData = {}
        self.globalData['SLACK-TOKEN']={}
        self.globalData['SLACK-TOKEN']['value'] = "xoxb-134470729732-5930969383473-bmD1xnNmlKPRlnNPbKrcSiQf"
        self.globalData['SLACK-TOKEN']['displayName'] = "Slack Token"
        self.globalData['SLACK-TOKEN']['description'] = "The token for Slack messaging (Slack-token)"
        self.globalData['SLACK-TOKEN']['inputType'] = "lineEdit"
        self.globalData['SLACK-SECRET']={}
        self.globalData['SLACK-SECRET']['value'] = "e8cd04aa4cc9ec7c51729ec6ecf98c1c"
        self.globalData['SLACK-SECRET']['displayName'] = "Slack Secret"
        self.globalData['SLACK-SECRET']['description'] = "The secret ID for Slack messaging (Slack-secret)"
        self.globalData['SLACK-SECRET']['inputType'] = "lineEdit"
        self.globalData['SLACK-CHANNEL']={}
        self.globalData['SLACK-CHANNEL']['value'] = "glados-bot"
        self.globalData['SLACK-CHANNEL']['displayName'] = "Slack Channel"
        self.globalData['SLACK-CHANNEL']['description'] = "Channel for the Slack node to send messages to (Slack-channel)"
        self.globalData['SLACK-CHANNEL']['inputType'] = "lineEdit"
        self.globalData['MDAVISMETHOD']={}
        self.globalData['MDAVISMETHOD']['value'] = 'multiDstack' #'multiDstack' or 'frameByFrame'
        self.globalData['MDAVISMETHOD']['displayName'] = 'MDA Visualisation method' #'multiDstack' or 'frameByFrame'
        self.globalData['MDAVISMETHOD']['description'] = 'Choose between MDA Visualisation methods - multiDStack will ensure that all frames are visualised after a full MDA, frameByFrame leaves these blank.' #'multiDstack' or 'frameByFrame'
        self.globalData['MDAVISMETHOD']['inputType'] = 'dropdown' #'multiDstack' or 'frameByFrame'
        self.globalData['MDAVISMETHOD']['dropDownOptions'] = ['multiDstack','frameByFrame'] #'multiDstack' or 'frameByFrame'
        self.globalData['MDABACKENDMETHOD']={}
        self.globalData['MDABACKENDMETHOD']['value'] = 'process' #'process' or 'saved'
        self.globalData['MDABACKENDMETHOD']['displayName'] = 'Backend transfer method'
        self.globalData['MDABACKENDMETHOD']['description'] = 'Choose between the transfer method in the backend of the JAVA --> Python layer. Either directly grabs images via RAM (Can cause RAM issues), or performs a save-->load routine (limited by Disk write speed). Process is strongly recommended.'
        self.globalData['MDABACKENDMETHOD']['inputType'] = 'dropdown'
        self.globalData['MDABACKENDMETHOD']['dropDownOptions'] = ['process','saved']
        self.globalData['VISUALISATION-FPS'] = {}
        self.globalData['VISUALISATION-FPS']['value'] = 60
        self.globalData['VISUALISATION-FPS']['displayName'] = 'Visualisation FPS'
        self.globalData['VISUALISATION-FPS']['description'] = 'Update speed of napari visualisation (in frames per second)'
        self.globalData['VISUALISATION-FPS']['inputType'] = 'lineEdit'
        
        self.globalData['MMPATH'] = {}
        self.globalData['MMPATH']['value'] = "C:/Program Files/Micro-Manager-2.0"
        self.globalData['MMPATH']['displayName'] = 'Micromanager Path'
        self.globalData['MMPATH']['description'] = 'Micromanager Path'
        self.globalData['MMPATH']['inputType'] = 'lineEdit'
        self.globalData['MMPATH']['hidden'] = True
        self.globalData['MM_HEADLESS_BACKEND'] = {}
        self.globalData['MM_HEADLESS_BACKEND']['value'] = "Python"
        self.globalData['MM_HEADLESS_BACKEND']['inputType'] = 'lineEdit'
        self.globalData['MM_HEADLESS_BACKEND']['hidden'] = True
        self.globalData['MM_CONFIG_PATH'] = {}
        self.globalData['MM_CONFIG_PATH']['value'] = "C:/Program Files/Micro-Manager-2.0/MMConfig_demo.cfg"
        self.globalData['MM_CONFIG_PATH']['displayName'] = 'Micromanager config file path'
        self.globalData['MM_CONFIG_PATH']['description'] = 'Micromanager config file path'
        self.globalData['MM_CONFIG_PATH']['inputType'] = 'lineEdit'
        self.globalData['MM_CONFIG_PATH']['hidden'] = True
        self.globalData['MM_HEADLESS_BUFFER_MB'] = {}
        self.globalData['MM_HEADLESS_BUFFER_MB']['value'] = 4096
        self.globalData['MM_HEADLESS_BUFFER_MB']['displayName'] = 'Buffer size (MB)'
        self.globalData['MM_HEADLESS_BUFFER_MB']['description'] = 'Buffer size of the headless Micromanager instance'
        self.globalData['MM_HEADLESS_BUFFER_MB']['inputType'] = 'lineEdit'
        self.globalData['MM_HEADLESS_BUFFER_MB']['hidden'] = True
        self.globalData['MM_HEADLESS_MAX_MEMORY_MB'] = {}
        self.globalData['MM_HEADLESS_MAX_MEMORY_MB']['value'] = 12000
        self.globalData['MM_HEADLESS_MAX_MEMORY_MB']['displayName'] = 'Max memory (MB)'
        self.globalData['MM_HEADLESS_MAX_MEMORY_MB']['description'] = 'Maximum memory footprint of the headless Micromanager instance'
        self.globalData['MM_HEADLESS_MAX_MEMORY_MB']['inputType'] = 'lineEdit'
        self.globalData['MM_HEADLESS_MAX_MEMORY_MB']['hidden'] = True
        
        #Overwrite all values that can be found from the .JSON:x
        #load from appdata
        appdata_folder = appdirs.user_data_dir()#os.getenv('APPDATA')
        if appdata_folder is None:
            raise EnvironmentError("APPDATA environment variable not found")
        app_specific_folder = os.path.join(appdata_folder, 'Glados-PycroManager')
        os.makedirs(app_specific_folder, exist_ok=True)
        if os.path.exists(os.path.join(app_specific_folder, 'glados_state.json')):
            #Load the mda state
            with open(os.path.join(app_specific_folder, 'glados_state.json'), 'r') as file:
                gladosInfo = json.load(file)
                if 'GlobalData' in gladosInfo:
                    globalDataInfo = gladosInfo['GlobalData']
                else:
                    globalDataInfo = {}
        
            for key in globalDataInfo:
                try:
                    self.globalData[key]['value'] = globalDataInfo[key]
                except:
                    pass
        
        if self.globalData['SLACK-TOKEN']['value'] is not None and not len(self.globalData['SLACK-TOKEN']['value']) == 0:
            try:
                self.globalData['SLACK-CLIENT'] = {}
                self.globalData['SLACK-CLIENT']['value'] = slack.WebClient(token=self.globalData['SLACK-TOKEN']['value' ])
                self.globalData['SLACK-CLIENT']['hidden'] = True
                logging.debug('Slack client initialised')
            except:
                logging.error('Error with Slack!')
        
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
        print('LIVE mode changed!')
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
        except:
            pass
    

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