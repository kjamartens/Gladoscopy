"""
The main function to call if running glados-napari from the python interface.
"""

#region imports
from pycromanager import Core
from pycromanager import start_headless
import os
os.environ['NAPARI_ASYNC'] = '1'
os.environ['NAPARI_OCTREE'] = '1' #this is rather smoother than async
import json
import sys
from PyQt5.QtWidgets import QApplication
import shutil
import logging
import argparse
from PyQt5.QtCore import QThread, QObject, pyqtSignal
from PyQt5.QtWidgets import QApplication, QMainWindow
import sys


def is_pip_installed():
    return 'site-packages' in __file__ or 'dist-packages' in __file__

if is_pip_installed():
    from glados_pycromanager.GUI.napariGlados import runNapariPycroManager
    from glados_pycromanager.GUI.sharedFunctions import Shared_data, periodicallyUpdate
    from glados_pycromanager.GUI.utils import *
    from glados_pycromanager.AutonomousMicroscopy.Analysis_Measurements import * #type: ignore
    from glados_pycromanager.AutonomousMicroscopy.Real_Time_Analysis import * #type: ignore
    #Obtain the helperfunctions
    import glados_pycromanager.GUI.utils as utils
else:
    from napariGlados import runNapariPycroManager
    from sharedFunctions import Shared_data, periodicallyUpdate
    from utils import *

    # Add the folder 2 folders up to the system path
    sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    #Import all scripts in the custom script folders
    from Analysis_Measurements import * #type: ignore
    from Real_Time_Analysis import * #type: ignore
    #Obtain the helperfunctions
    import utils
#endregion

def perform_post_closing_actions(shared_data):
    """Performing closing actions

    Args:
        shared_data: shared_data class (Shared_data())
    """
    #Clean up temporary files
    utils.cleanUpTemporaryFiles(shared_data=shared_data)
    
    # if shared_data._headless:
    #     stop_headless()

class Worker(QObject):
    """
    Worker wrapper for the runNapariPycroManager function
    """
    finished = pyqtSignal()

    def runNapariPycroManagerWrap(self, core, MM_JSON, shared_data,includeCustomUI=False):
        """
        Runs the NapariPycroManagerWrap function.
        
        Args:
            core: The core object.
            MM_JSON: The MM_JSON object.
            shared_data: The shared data object.
            includeCustomUI (bool, optional): Flag to include custom UI. Defaults to False.
        
        Returns:
            None
        """
        import platform
        # Get the computer's hostname
        if 'SMIPC' in platform.node():
            includeCustomUI=True
        else:
            includeCustomUI=False
        # Your code for running the NapariPycroManager function goes here
        runNapariPycroManager(core, MM_JSON, shared_data,includecustomUI=includeCustomUI)
        self.finished.emit()

from PyQt5.QtWidgets import QApplication, QWidget, QLabel, QLineEdit, QVBoxLayout, QPushButton, QRadioButton, QButtonGroup
class headlessGUI(QWidget):
    """
    Small GUI for user input on a headless Pycromanager start
    """
    def __init__(self, shared_data):
        super().__init__()
        self.shared_data = shared_data
        self.initUI()

    def initUI(self):
        self.setWindowTitle('Glados-PycroManager-Napari GUI')
        self.setGeometry(100, 100, 300, 200)

        self.backendLabel = QLabel('Backend:', self)

        self.pythonRadio = QRadioButton('Python (recommended)', self)
        self.javaRadio = QRadioButton('Java', self)
        self.pythonRadio.setChecked(True)

        self.buttonGroup = QButtonGroup()
        self.buttonGroup.addButton(self.pythonRadio)
        self.buttonGroup.addButton(self.javaRadio)

        self.mm_app_pathLabel = QLabel('MM App Path:', self)
        self.mm_app_pathLineEdit = QLineEdit("C:\\Data\\Software\\Micro-Manager-2.0\\", self)

        self.config_fileLabel = QLabel('Config File:', self)
        self.config_fileLineEdit = QLineEdit("C:\\Data\\Software\\Micro-Manager-2.0\\MMConfig_Demo.cfg", self)

        self.buffer_size_mbLabel = QLabel('Buffer Size MB:', self)
        self.buffer_size_mbLineEdit = QLineEdit("4096", self)

        self.max_memory_mbLabel = QLabel('Max Memory MB:', self)
        self.max_memory_mbLineEdit = QLineEdit("10000", self)

        self.startButton = QPushButton('Start', self)
        self.startButton.clicked.connect(self.start)

        layout = QVBoxLayout()
        layout.addWidget(self.backendLabel)
        layout.addWidget(self.pythonRadio)
        layout.addWidget(self.javaRadio)
        layout.addWidget(self.mm_app_pathLabel)
        layout.addWidget(self.mm_app_pathLineEdit)
        layout.addWidget(self.config_fileLabel)
        layout.addWidget(self.config_fileLineEdit)
        layout.addWidget(self.buffer_size_mbLabel)
        layout.addWidget(self.buffer_size_mbLineEdit)
        layout.addWidget(self.max_memory_mbLabel)
        layout.addWidget(self.max_memory_mbLineEdit)
        layout.addWidget(self.startButton)

        self.setLayout(layout)
        self.show()

    def start(self):
        self.backend = 'Python' if self.pythonRadio.isChecked() else 'JAVA'
        self.mm_app_path = self.mm_app_pathLineEdit.text()
        self.config_file = self.config_fileLineEdit.text()
        self.buffer_size_mb = self.buffer_size_mbLineEdit.text()
        self.max_memory_mb = self.max_memory_mbLineEdit.text()
        self.close()



def main():
    """
    Run the main function to start Glados-PycroManager-Napari interface for autonomous microscopy.
    
    Args:
        None
    
    Returns:
        None
    """
    #cProfiler testing
    
    #Create parser
    parser = argparse.ArgumentParser(description='Glados-PycroManager-Napari: an interface for autonomous microscopy via PycroManager')
    parser.add_argument('--debug', '-d', action='store_true', help='Enable debug')
    args=parser.parse_args()
    
    
    # Create an instance of the shared_data class
    shared_data = Shared_data()
    utils.cleanUpTemporaryFiles(shared_data=shared_data)
        
    #Some QT attributes
    from PyQt5.QtWidgets import QApplication
    from PyQt5.QtCore import Qt
    QApplication.setAttribute(Qt.AA_EnableHighDpiScaling)# type:ignore
    QApplication.setAttribute(Qt.AA_ShareOpenGLContexts)# type:ignore
    QApplication.setAttribute(Qt.AA_UseStyleSheetPropagationInWidgetStyles, True)# type:ignore
    
    # get object representing MMCore, used throughout
    #try to open a running instance:
    try:
        core = Core()
        shared_data.core = core
        shared_data._headless = False
    except:
        #Create a small GUI for settings
        appSmall = QApplication([])
        headlessGUIv = headlessGUI(shared_data)
        appSmall.exec_()
        
        #Get those settings and use to start headless
        start_headless(mm_app_path=headlessGUIv.mm_app_path, config_file=headlessGUIv.config_file, python_backend=headlessGUIv.backend=='Python', buffer_size_mb=int(headlessGUIv.buffer_size_mb), max_memory_mb=int(headlessGUIv.max_memory_mb))
        core = Core()
        print('headless MM started')
        
        #Also store some settings in shared_data
        shared_data._headless = True
        shared_data.backend = headlessGUIv.backend
        shared_data.core = core
    
    #Open JSON file with MM settings
    try:
        with open(os.path.join(sys.path[0], 'MM_PycroManager_JSON.json'), 'r') as f:
            MM_JSON = json.load(f)
    except:
        MM_JSON = None
        
        
    app = QApplication(sys.argv)

    worker = Worker()
    thread = QThread()
    worker.moveToThread(thread)
    thread.started.connect(lambda: worker.runNapariPycroManagerWrap(core, MM_JSON, shared_data))
    thread.start()
    
    worker.finished.connect(thread.quit)
    worker.finished.connect(worker.deleteLater)
    thread.finished.connect(thread.deleteLater)

    #Set up logging to files in appData folder - INFO and DEBUG
    utils.set_up_logger()
    
    #Run the app until closed
    sys.exit(app.exec_())


def show_UserManualNapari():
    try:
        
        quickStartWindow = utils.SmallWindow(None)
        QApplication.processEvents()
        quickStartWindow.setWindowTitle('Quick start / User Manual')
        QApplication.processEvents()
        
        if is_pip_installed():
            package_path = os.path.dirname(glados_pycromanager.__file__)# type:ignore
            quickStartWindow.addMarkdown(os.path.join(package_path, 'Documentation', 'UserManual.md'))
        else:
            quickStartWindow.addMarkdown('glados-pycromanager/glados_pycromanager/Documentation/UserManual.md')
        QApplication.processEvents()
        quickStartWindow.show()
        

    except Exception as e:
        logging.error(f'Could not open quick start window. {e}')
    
    
if __name__ == "__main__":
    # try:
    
    import cProfile
    
# Start the profiler
    # cProfile.run("main()", "profiling_results.prof", sort="cumtime")

    
    main()
    
    # except:
        # print('Error!')

