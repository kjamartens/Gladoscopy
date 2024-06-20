from pycromanager import core
import sys
sys.path.append('GUI\\nodz')

import os
from LaserControlScripts import *
# from AutonomousMicroscopyScripts import *
# from MMcontrols import *
from napariGlados import *
from PyQt5.QtWidgets import QMainWindow,QApplication
# from MDAGlados import MDAGlados

class Shared_data:
    def __init__(self):
        self._liveMode = False
    @property
    def liveMode(self):
        return self._liveMode
    @liveMode.setter
    def liveMode(self, new_value):
        if new_value != self._liveMode:
            self._liveMode = new_value
            self.on_value_change()
    def on_value_change(self):
        # This is the function that will be called when the 'value' changes
        liveModeChanged()


if __name__ == "__main__":
    # Create an instance of the shared_data class
    shared_data = Shared_data()
    try:
        # get object representing MMCore, used throughout
        core = Core()

        #Open JSON file with MM settings
        with open(os.path.join(sys.path[0], 'MM_PycroManager_JSON.json'), 'r') as f:
            MM_JSON = json.load(f)

        #Setup UI
        
        app = QApplication(sys.argv)
        window = MainWindow()
        window.show()

        # Run the laserController UI
        runlaserControllerUI(core,MM_JSON,window,shared_data)

        #Run autonomousMicroscopy UI
        # runAutonomousMicroscopyUI(core,MM_JSON,window)

        #Get a new basic UI in a new tab
        # tab_MMcontrol = window.findChild(QWidget, "tab_MMControls")
        #Create a layout in this
        # main_layout = QVBoxLayout(tab_MMcontrol) #type: ignore
        # microManagerControlsUI(core,MM_JSON,main_layout)

        #Create the napari UI
        # runNapariMicroManager(core,MM_JSON,shared_data)

        #Show window and start app
        #Breakpoint here for useful debugging
        window.show()
        app.exec()
        # z=2
        sys.exit(app.exec_())

    except:
        print('No micromanager, test mode!')

        #Open JSON file with MM settings
        with open(os.path.join(sys.path[0], 'MM_PycroManager_JSON.json'), 'r') as f:
            MM_JSON = json.load(f)

        #Setup UI
        app = QApplication(sys.argv)
        window = MainWindow()
        # window.show()

        #Show window and start app
        window.show()
        app.exec()
        sys.exit(app.exec_())


