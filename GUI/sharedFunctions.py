from napariGlados import liveModeChanged
from PyQt5.QtCore import QTimer

"""_summary_

    Shared_data is a class of shared data between the script, threads, napari, and napari plug-ins. It contains info on e.g. the analysis threads, the napari Viewer, and whether micromanager is acquiring data, or in live mode, or etc
"""
class Shared_data:
    #Initialises the info of shared data
    def __init__(self):
        self._liveMode = False
        self._napariViewer = None
        self._analysisThreads = []
        self._core = []
        
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
        liveModeChanged()
         
    
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
        print('Analysis Threads now: '+str(self._analysisThreads))
        removed_entry = None
        if len(self._analysisThreads) < len(self.analysisThreads):
            removed_entry = [entry for entry in self.analysisThreads if entry not in self._analysisThreads][0]
        print('Analysis Threads now: ' + str(self._analysisThreads))
        if removed_entry is not None:
            print('Removed entry: ' + str(removed_entry))
        
    #core property        
    @property
    def core(self):
        return self._core
    @core.setter
    def core(self, new_value):
        if new_value != self._core:
            self._core = new_value

class periodicallyUpdate:
    def __init__(self,updateFunction,timing = 5000):
        # Create a QTimer to periodically update MM info
        self.timer = QTimer()
        self.timer.setInterval(timing)
        self.timer.timeout.connect(updateFunction)
        self.timer.start()
