
#region imports
from pycromanager import Core
from pycromanager import start_headless
import os
os.environ['NAPARI_ASYNC'] = '1'
import json
import sys
from PyQt5.QtWidgets import QApplication
import shutil
import logging
import argparse

sys.path.append(os.path.dirname(os.path.abspath(__file__))+"\\GUI")
sys.path.append(os.path.dirname(os.path.abspath(__file__))+"\\AutonomousMicroscopy")
sys.path.append(os.path.dirname(os.path.abspath(__file__))+"\\AutonomousMicroscopy\\MainScripts")
sys.path.append(os.path.dirname(os.path.abspath(__file__))+"\\GUI\\nodz")
from napariGlados import *
from sharedFunctions import Shared_data, periodicallyUpdate
from utils import *

from PyQt5.QtCore import QThread, QObject, pyqtSignal
from PyQt5.QtWidgets import QApplication, QMainWindow
import sys
# Add the folder 2 folders up to the system path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
#Import all scripts in the custom script folders
from Analysis_Images import * #type: ignore
from Analysis_Measurements import * #type: ignore
from Analysis_Shapes import * #type: ignore
from CustomFunctions import * #type: ignore
from Scoring_Images import * #type: ignore
from Scoring_Measurements import * #type: ignore
from Scoring_Shapes import * #type: ignore
from Scoring_Images_Measurements import * #type: ignore
from Scoring_Measurements_Shapes import * #type: ignore
from Scoring_Images_Measurements_Shapes import * #type: ignore
from Visualisation_Images import * #type: ignore
from Visualisation_Measurements import * #type: ignore
from Visualisation_Shapes import * #type: ignore
# Obtain the helperfunctions
import HelperFunctions #type: ignore
#endregion


from napari.utils.notifications import show_info

def show_hello_message():
    show_info('Hello, world!')


class Worker(QObject):
    """
    Worker wrapper for the runNapariPycroManager function
    """
    finished = pyqtSignal()

    def runNapariPycroManagerWrap_plugin(self, core, MM_JSON, shared_data,includeCustomUI=False):
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
        
        # Your code for running the NapariPycroManager function goes here
        runNapariPycroManager_plugin(core, MM_JSON, shared_data,includecustomUI=includeCustomUI)
        self.finished.emit()


def run_glados_pycromanager():
    
    print('INIT glados_pycromanager')
    cleanUpTemporaryFiles()
    
    #Set up logging at correct level
    log_file_path = 'logpath.txt'
    logger = logging.getLogger()
    logger.setLevel(logging.INFO)

    # Create the file handler to log to the file
    file_handler = logging.FileHandler(log_file_path)
    file_handler.setLevel(logging.INFO)

    # Create the stream handler to log to the debug terminal
    stream_handler = logging.StreamHandler(sys.stdout)
    stream_handler.setLevel(logging.INFO)

    # Add the handlers to the logger
    logging.basicConfig(handlers=[file_handler, stream_handler], level=logging.INFO,format="%(asctime)s [%(levelname)s] %(filename)s:%(lineno)d - %(message)s")
    
    # Create an instance of the shared_data class
    shared_data = Shared_data()
    
    #For now, no headless option
    core = Core()
    shared_data.core = core
    shared_data._headless = False
    
    runNapariPycroManager_plugin(core, None, shared_data,includecustomUI=False)
    #Open JSON file with MM settings
    # with open(os.path.join(sys.path[0], 'MM_PycroManager_JSON.json'), 'r') as f:
    #     MM_JSON = json.load(f)

    # #Run the UI on a second thread (hopefully robustly)
    # app = QApplication(sys.argv)

    # worker = Worker()
    # thread = QThread()
    # worker.moveToThread(thread)
    # thread.started.connect(lambda: worker.runNapariPycroManagerWrap_plugin(core, None, shared_data))
    # thread.start()
    
    # worker.finished.connect(thread.quit)
    # worker.finished.connect(worker.deleteLater)
    # thread.finished.connect(thread.deleteLater)
    
    print('INIT glados_pycromanager complete')

#Import qwidget:
from PyQt5.QtWidgets import QWidget



import napari
import napari
from qtpy.QtWidgets import QVBoxLayout, QWidget, QLabel
from qtpy.QtCore import Qt

class TestWIdget(QWidget):
    """
    Main Widget for napari-bleach-correct.
    """
    def __init__(self, viewer: napari.viewer.Viewer):
        super().__init__()
        self._viewer = viewer
        layout = QVBoxLayout()

        widget = QLabel("Choose a bleaching correction method:")
        # font = widget.font()
        # font.setPointSize(10)
        # widget.setFont(font)
        layout.addWidget(widget)

        self.setLayout(layout)
        self.setWindowTitle("Bleaching Correction")



class AllNapariPycroManagerWidgets():
    # global core, MM_JSON, livestate, napariViewer, shared_data
    
    def __init__(self,napariViewer2: "napari.viewer.Viewer",includecustomUI = False,include_flowChart_automatedMicroscopy = True, parent=None):
        #Go from self to global variables
        
        TestWIdget(napariViewer2)
        
        # self._viewer = napariViewer2
        # global core, MM_JSON, livestate, napariViewer, shared_data
        # core = None
        # MM_JSON = None
        # livestate = None
        # napariViewer = None
        # shared_data = None
        # print('RUN NAPARI PYCROMANAGER PLUGIN')
        # logging.info("p1")
            
        # #Set up logging at correct level
        # log_file_path = 'logpath.txt'
        # logger = logging.getLogger()
        # logger.setLevel(logging.INFO)

        # # Create the file handler to log to the file
        # file_handler = logging.FileHandler(log_file_path)
        # file_handler.setLevel(logging.INFO)

        # # Create the stream handler to log to the debug terminal
        # stream_handler = logging.StreamHandler(sys.stdout)
        # stream_handler.setLevel(logging.INFO)

        # # Add the handlers to the logger
        # logging.basicConfig(handlers=[file_handler, stream_handler], level=logging.INFO,format="%(asctime)s [%(levelname)s] %(filename)s:%(lineno)d - %(message)s")
        
        # # Create an instance of the shared_data class
        # shared_data = Shared_data()
        
        # core = Core()
        # shared_data.core = core
        # shared_data._headless = False
    
        # MM_JSON = None
        # livestate = False
        
        # napariViewer = napariViewer2
                
        # #Get some info from core to put in shared_data
        # shared_data._defaultFocusDevice = core.get_focus_device()
        # logging.info(f"Default focus device set to {shared_data._defaultFocusDevice}")

        # logging.info(MM_JSON)
        # #Add a connect event if a layer is removed - to stop background processes
        # # napariViewer.layers.events.removing.connect(lambda event: layer_removed_event_callback(event,shared_data))
        # # shared_data.napariViewer = napariViewer
        
        # # create_analysis_thread(shared_data,analysisInfo='LiveModeVisualisation',createNewThread=False,throughputThread=shared_data._livemodeNapariHandler.image_queue_analysis)
        # # create_analysis_thread(shared_data,analysisInfo='mdaVisualisation',createNewThread=False,throughputThread=shared_data._mdamodeNapariHandler.image_queue_analysis)
        # # logging.debug("Live mode pseudo-analysis thread created")
        
        # #Set some common things for the UI (scale bar on and such)
        # InitateNapariUI(napariViewer)
        
        # self.dockWidget = analysis_dockWidget_plugin(MM_JSON,self.layout,shared_data)
        
        #Add widgets as wanted
        # custom_widget_analysisThreads = dockWidget_analysisThreads()
        # napariViewer.window.add_dock_widget(custom_widget_analysisThreads, area="top", name="Real-time analysis",tabify=True)
        
        # custom_widget_MMcontrols = dockWidget_MMcontrol()
        # napariViewer.window.add_dock_widget(custom_widget_MMcontrols, area="top", name="Controls",tabify=True)
        
        # custom_widget_MDA = dockWidget_MDA()
        # napariViewer.window.add_dock_widget(custom_widget_MDA, area="top", name="Multi-D acquisition",tabify=True)
        
        # if include_flowChart_automatedMicroscopy:
        #     custom_widget_flowChart = dockWidget_flowChart()
        #     napariViewer.window.add_dock_widget(custom_widget_flowChart, area="top", name="Autonomous microscopy",tabify=True)
        #     custom_widget_flowChart.dockWidget.focus()
        
        # if includecustomUI:
        #     custom_widget_gladosUI = dockWidget_fullGladosUI()
        #     napariViewer.window.add_dock_widget(custom_widget_gladosUI, area="right", name="GladosUI")

        # returnInfo = {}
        # returnInfo['napariViewer'] = napariViewer
        # returnInfo['MMcontrolWidget'] = custom_widget_MMcontrols.getDockWidget()
        
        # # breakpoint
        # return returnInfo
        print('END NAPARI PYCROMANAGER PLUGIN')