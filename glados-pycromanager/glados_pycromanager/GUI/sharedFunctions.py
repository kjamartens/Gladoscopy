from napariGlados import napariHandler
from PyQt5.QtCore import QTimer
import logging
from PyQt5.QtCore import QObject, pyqtSignal

import slack
from flask import Flask
import time
from slackeventsapi import SlackEventAdapter

"""Shared data summary

    Shared_data is a class of shared data between the script, threads, napari, and napari plug-ins. It contains info on e.g. the analysis threads, the napari Viewer, and whether micromanager is acquiring data, or in live mode, or etc
"""
class Shared_data(QObject):
    mda_acq_done_signal = pyqtSignal(bool)
    
    #Initialises the info of shared data
    def __init__(self):
        super().__init__()
        self._liveMode = False
        self._mdaMode = False
        self._mdaModeParams = []
        self._napariViewer = None
        self._headless = False
        self._busy = False
        self._analysisThreads = []
        self._core = []
        self._liveImageQueues = []
        self._mdaImageQueues = []
        self._defaultFocusDevice = ''
        self._mdaModeSaveLoc = ['','']
        self._mdaModeNapariViewer = None
        self.mdaDatasets = []
        self.activeMDAobject = None
        self.mdaZarrData = {}
        self.nodzInstance = None
        self.loadingOngoing = False #Set to true if loading of a nodz instance is actively ongoing - halts checking for errors and such.
        self.last_display_update_time = 0
        self.newestLayerName = '' #Updated with whatever the newest layer name is, when called from napariGlados.py
        self._warningErrorInfoInfo = Dict_Specific_WarningErrorInfo({'Errors': [], 'Warnings': [], 'Info': {'LastNodeRan': None, 'Other': None}},parent=self)
        
        self._livemodeNapariHandler = napariHandler(self,liveOrMda='live')
        self._mdamodeNapariHandler = napariHandler(self,liveOrMda='mda')
        
        self.globalData = {}
        self.globalData['SLACK'] = {}
        self.globalData['SLACK']['TOKEN'] = "xoxb-134470729732-5930969383473-bmD1xnNmlKPRlnNPbKrcSiQf"
        self.globalData['SLACK']['SECRET'] = "e8cd04aa4cc9ec7c51729ec6ecf98c1c"
        self.globalData['SLACK']['CHANNEL'] = "glados-bot"
        if self.globalData['SLACK']['TOKEN'] is not None and not len(self.globalData['SLACK']['TOKEN']) == 0:
            try:
                self.globalData['SLACK']['CLIENT'] = slack.WebClient(token=self.globalData['SLACK']['TOKEN'])
                logging.debug('Slack client initialised')
            except:
                logging.error('Error with Slack!')
        self.globalData['MDAVISMETHOD'] = 'multiDstack' #'multiDstack' or 'frameByFrame'
        
        # self._mdamodeNapariHandler.mda_acq_done_signal.connect(self.mdaacqdonefunction)
    
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

    @property
    def liveImageQueues(self):
        return self._liveImageQueues
    @liveImageQueues.setter
    def liveImageQueues(self, new_value):
        if new_value != self._liveImageQueues:
            self._liveImageQueues = new_value
            self.on_liveImageQueues_value_change()
    def on_liveImageQueues_value_change(self):
        logging.debug('liveImageQueues changed')
        
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
            logging.debug(f"shared_data.warningErrorInfoInfo changed to {self._warningErrorInfoInfo}")
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
            from utils import updateAutonousErrorWarningInfo
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