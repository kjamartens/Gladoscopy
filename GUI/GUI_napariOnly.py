from pycromanager import core

from LaserControlScripts import *
from AutonomousMicroscopyScripts import *
from MMcontrols import *
from napariGlados import *

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

def periodicallyUpdate(updateFunction,timing = 5000):
    # Create a QTimer to periodically update MM info
    timer = QTimer()
    timer.setInterval(timing)
    timer.timeout.connect(updateFunction)
    timer.start()
    return timer

if __name__ == "__main__":
    # Create an instance of the shared_data class
    shared_data = Shared_data()
    # try:
        
    # get object representing MMCore, used throughout
    core = Core()

    #Open JSON file with MM settings
    with open(os.path.join(sys.path[0], 'MM_PycroManager_JSON.json'), 'r') as f:
        MM_JSON = json.load(f)

    #Run the live mode UI
    napariViewer, MMcontrolsWidget = runNapariMicroManager(core,MM_JSON,shared_data)

    #Periodically update the MM info of the MMcontrolsWidget
    timer = periodicallyUpdate(MMcontrolsWidget.updateAllMMinfo)

    #Ensure it stays open?
    app = QApplication([])
    sys.exit(app.exec_())

    # except:
    #     print('Error!')


