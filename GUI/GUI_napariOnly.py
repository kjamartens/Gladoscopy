from pycromanager import Core
import os
import json
import sys
from PyQt5.QtWidgets import QApplication

from napariGlados import runNapariPycroManager
from sharedFunctions import Shared_data, periodicallyUpdate

if __name__ == "__main__":
    # Create an instance of the shared_data class
    shared_data = Shared_data()
    # try:
        
    # get object representing MMCore, used throughout
    core = Core()
    
    shared_data.core = core

    #Open JSON file with MM settings
    with open(os.path.join(sys.path[0], 'MM_PycroManager_JSON.json'), 'r') as f:
        MM_JSON = json.load(f)

    #Run the live mode UI
    nPM = runNapariPycroManager(core,MM_JSON,shared_data)

    #Periodically update the MM info of the MMcontrolsWidget
    periodicallyUpdate(updateFunction=nPM['MMcontrolWidget'].updateAllMMinfo)

    #Ensure it stays open?
    app = QApplication([])
    sys.exit(app.exec_())

    # except:
    #     print('Error!')


