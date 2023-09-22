from pycromanager import *

from LaserControlScripts import *
from LiveModeControlScripts import *
from AutonomousMicroscopyScripts import *

if __name__ == "__main__":
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

        #Run the laserController UI
        runlaserControllerUI(core,MM_JSON,window,app)

        #Run autonomousMicroscopy UI
        runAutonomousMicroscopyUI(core,MM_JSON,window,app)

        #Run the live mode UI
        runLiveModeUI(core,MM_JSON,window,app)

        #Show window and start app
        #Breakpoint here for useful debugging
        window.show()
        app.exec()
        z=2
        # sys.exit(app.exec_())

    except:
        print('No micromanager, test mode!')

        #Open JSON file with MM settings
        with open(os.path.join(sys.path[0], 'MM_PycroManager_JSON.json'), 'r') as f:
            MM_JSON = json.load(f)

        #Setup UI
        app = QApplication(sys.argv)
        window = MainWindow()
        window.show()

        #Show window and start app
        window.show()
        # app.exec()
        sys.exit(app.exec_())


