from napariGlados import napariHandler
from PyQt5.QtCore import QTimer
import logging
from PyQt5.QtCore import QObject, pyqtSignal

import slack
from flask import Flask
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
        self._analysisThreads = []
        self._core = []
        self._liveImageQueues = []
        self._mdaImageQueues = []
        self._defaultFocusDevice = ''
        self._mdaModeSaveLoc = ['','']
        self._mdaModeNapariViewer = None
        self.mdaDatasets = []
        self.activeMDAobject = None
        
        self._livemodeNapariHandler = napariHandler(self,liveOrMda='live')
        self._mdamodeNapariHandler = napariHandler(self,liveOrMda='mda')
        
        self.globalData = {}
        self.globalData['SLACK'] = {}
        self.globalData['SLACK']['TOKEN'] = "xoxb-134470729732-5930969383473-bmD1xnNmlKPRlnNPbKrcSiQf"
        self.globalData['SLACK']['SECRET'] = "e8cd04aa4cc9ec7c51729ec6ecf98c1c"
        self.globalData['SLACK']['CHANNEL'] = "glados-bot"
        if self.globalData['SLACK']['TOKEN'] is not None and not len(self.globalData['SLACK']['TOKEN']) == 0:
            self.globalData['SLACK']['CLIENT'] = slack.WebClient(token=self.globalData['SLACK']['TOKEN'])
            logging.info('Slack client initialised')
        
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
            logging.info('Removed entry: ' + str(removed_entry))
        
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
    
    def appendNewMDAdataset(self,mdadataset):
        self.mdaDatasets.append(mdadataset)
    

class periodicallyUpdate:
    def __init__(self,updateFunction,timing = 10000):
        logging.debug('Initted periodically update with function %s', updateFunction)
        # Create a QTimer to periodically update MM info
        self.timer = QTimer()
        self.timer.setInterval(timing)
        self.timer.timeout.connect(updateFunction)
        self.timer.start()
