"""
The main function to call if running glados-napari from the python interface.
"""

#region imports
import logging
import argparse
import napari
import os
import json
import sys
import utils
from pycromanager import Core
from pycromanager import start_headless
from PyQt5.QtWidgets import (
    QApplication,
    QWidget,
    QLabel, 
    QLineEdit,
    QGridLayout,
    QPushButton,
    QRadioButton, 
    QButtonGroup,
    QFileDialog)
from PyQt5.QtCore import (
    QThread,
    QObject,
    pyqtSignal,
    Qt)
from PyQt5.QtGui import (
    QIcon,
    QPixmap,
)

#Napari optimizations
os.environ['NAPARI_ASYNC'] = '1'
os.environ['NAPARI_OCTREE'] = '1' #this is rather smoother than async

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
        # Run the NapariPycroManager function
        runNapariPycroManager(core, MM_JSON, shared_data,includecustomUI=includeCustomUI)
        self.finished.emit()

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
        
        iconFolder = utils.findIconFolder()
        icon_path = iconFolder+os.sep+'GladosIcon.ico'
        self.setWindowIcon(QIcon(icon_path))
        
        self.setWindowFlags(self.windowFlags() | Qt.WindowStaysOnTopHint) #type:ignore
        
        # Center the window on the screen, fall back to just somewhere
        try:
            screen = QApplication.primaryScreen()
            screen_geometry = screen.availableGeometry() #type: ignore
            window_width = 500
            window_height = 350
            self.setGeometry(
                (screen_geometry.width() - window_width) // 2,
                (screen_geometry.height() - window_height) // 2,
                window_width,
                window_height
            )
        except Exception as e:
            logging.warning(f'Try/exception occured! {e}')
            self.setGeometry(100, 100, 500, 350)
            
        # Add a splash screen at the top
        self.splash_label = QLabel(self)
        splash_png = iconFolder+os.sep+'GladosSplash_inv.png'
        splash_pixmap = QPixmap(splash_png)
        new_width = window_width
        self.splash_label.setPixmap(
            splash_pixmap.scaled(new_width, int(splash_pixmap.height() * new_width / splash_pixmap.width()),
            Qt.KeepAspectRatio, Qt.SmoothTransformation) #type:ignore
        )
        self.splash_label.setAlignment(Qt.AlignCenter) #type:ignore

        self.backendLabel = QLabel('Backend:', self)

        self.pythonRadio = QRadioButton('Python (recommended)', self)
        self.javaRadio = QRadioButton('Java', self)
        if self.shared_data.globalData['MM_HEADLESS_BACKEND']['value'] == 'JAVA':
            self.javaRadio.setChecked(True)
        else:
            self.pythonRadio.setChecked(True)

        self.buttonGroup = QButtonGroup()
        self.buttonGroup.addButton(self.pythonRadio)
        self.buttonGroup.addButton(self.javaRadio)

        self.mm_app_pathLabel = QLabel('MicroManager Path:', self)
        self.mm_app_pathLineEdit = QLineEdit(self.shared_data.globalData['MMPATH']['value'], self)
        self.mm_app_browse = QPushButton('...', self)
        self.mm_app_browse.clicked.connect(self.BrowseMMAppPath)

        self.config_fileLabel = QLabel('Config File:', self)
        self.config_fileLineEdit = QLineEdit(self.shared_data.globalData['MM_CONFIG_PATH']['value'], self)
        self.config_file_browse = QPushButton('...', self)
        self.config_file_browse.clicked.connect(self.BrowseConfigFile)

        self.buffer_size_mbLabel = QLabel('Buffer Size MB:', self)
        self.buffer_size_mbLineEdit = QLineEdit(str(self.shared_data.globalData['MM_HEADLESS_BUFFER_MB']['value']), self)

        self.max_memory_mbLabel = QLabel('Max Memory MB:', self)
        self.max_memory_mbLineEdit = QLineEdit(str(self.shared_data.globalData['MM_HEADLESS_MAX_MEMORY_MB']['value']), self)

        self.startButton = QPushButton('Start', self)
        self.startButton.clicked.connect(self.start)

        layout = QGridLayout()
        layout.addWidget(self.splash_label,1,0,1,4)
        layout.addWidget(self.backendLabel, 3, 0)
        layout.addWidget(self.pythonRadio, 3, 1)
        layout.addWidget(self.javaRadio, 3, 2)
        layout.addWidget(self.mm_app_pathLabel, 4, 0)
        layout.addWidget(self.mm_app_pathLineEdit, 4, 1,1,2)
        layout.addWidget(self.mm_app_browse, 4, 3)
        layout.addWidget(self.config_fileLabel, 5, 0)
        layout.addWidget(self.config_fileLineEdit, 5, 1,1,2)
        layout.addWidget(self.config_file_browse, 5, 3)
        layout.addWidget(self.buffer_size_mbLabel, 6, 0)
        layout.addWidget(self.buffer_size_mbLineEdit, 6, 1)
        layout.addWidget(self.max_memory_mbLabel, 6, 2)
        layout.addWidget(self.max_memory_mbLineEdit, 6, 3)
        layout.addWidget(self.startButton, 7, 0, 1, 4) # Span across two columns

        self.setLayout(layout)
        self.show()

    def BrowseMMAppPath(self):
        options = QFileDialog.Options()
        folder_name = QFileDialog.getExistingDirectory(self, "Select Micro-Manager App Path", self.mm_app_pathLineEdit.text(), options=options)
        if folder_name:
            self.mm_app_pathLineEdit.setText(folder_name)

        
    def BrowseConfigFile(self):
        options = QFileDialog.Options()
        file_name, _ = QFileDialog.getOpenFileName(self, "Select Micro-Manager Config File", self.config_fileLineEdit.text(), "Config Files (*.cfg);;All Files (*)", options=options)
        if file_name:
            self.config_fileLineEdit.setText(file_name)

        
    def start(self):
        self.backend = 'Python' if self.pythonRadio.isChecked() else 'JAVA'
        self.mm_app_path = self.mm_app_pathLineEdit.text()
        self.config_file = self.config_fileLineEdit.text()
        self.buffer_size_mb = self.buffer_size_mbLineEdit.text()
        self.max_memory_mb = self.max_memory_mbLineEdit.text()
        
        #Also store these in the shared_data
        self.shared_data.globalData['MMPATH']['value'] = self.mm_app_path
        self.shared_data.globalData['MM_HEADLESS_BACKEND']['value'] = self.backend
        self.shared_data.globalData['MM_CONFIG_PATH']['value'] = self.config_file
        self.shared_data.globalData['MM_HEADLESS_BUFFER_MB']['value'] = self.buffer_size_mb
        self.shared_data.globalData['MM_HEADLESS_MAX_MEMORY_MB']['value'] = self.max_memory_mb
        #And update the JSON
        utils.storeSharedData_GlobalData(self.shared_data)
        
        self.close()

def main():
    """
    Run the main function to start Glados-PycroManager-Napari interface for autonomous microscopy.
    
    Args:
        None
    
    Returns:
        None
    """
    print('Glados-pycromanager main function called')
    
    #Create parser
    parser = argparse.ArgumentParser(description='Glados-PycroManager-Napari: an interface for autonomous microscopy via PycroManager')
    parser.add_argument('--debug', '-d', action='store_true', help='Enable debug')
    args=parser.parse_args()
    
    
    # Create an instance of the shared_data class
    print('Creating shared data.')
    shared_data = Shared_data()
    print('Cleaning up temporary files.')
    utils.cleanUpTemporaryFiles(shared_data=shared_data)
        
    #Some QT attributes
    print('Setting QT attributes.')
    QApplication.setAttribute(Qt.AA_EnableHighDpiScaling)# type:ignore
    QApplication.setAttribute(Qt.AA_ShareOpenGLContexts)# type:ignore
    QApplication.setAttribute(Qt.AA_UseStyleSheetPropagationInWidgetStyles, True)# type:ignore
    
    napariSettings = napari.settings.get_settings() #type: ignore
    if napariSettings.application.playback_fps < 120:
        napariSettings.application.playback_fps = 120
        print('Set the napari Playback FPS to 120!')
    
    # get object representing MMCore, used throughout
    #try to open a running instance:
    print('Finding or creating micromanager instance.')
    try:
        core = Core()
        shared_data.core = core
        shared_data._headless = False
    except Exception as e:
        logging.warning(f'Try/exception occured! {e}')
        #Create a small GUI for settings
        appSmall = QApplication([])
        headlessGUIv = headlessGUI(shared_data)
        appSmall.exec_()
        
        #Get those settings and use to start headless
        start_headless(mm_app_path=headlessGUIv.mm_app_path, config_file=headlessGUIv.config_file, python_backend=headlessGUIv.backend=='Python', buffer_size_mb=int(headlessGUIv.buffer_size_mb), max_memory_mb=int(headlessGUIv.max_memory_mb))
        core = Core()
        logging.info('Headless MicroManager started')
        
        #Also store some settings in shared_data
        shared_data._headless = True
        shared_data.backend = headlessGUIv.backend
        shared_data.core = core
    
    #Open JSON file with MM settings
    try:
        with open(os.path.join(sys.path[0], 'MM_PycroManager_JSON.json'), 'r') as f:
            MM_JSON = json.load(f)
    except Exception as e:
        logging.warning(f'Try/exception occured! {e}')
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


if __name__ == "__main__":
    main()
