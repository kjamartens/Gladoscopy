from typing import Callable
from dataclasses import dataclass

import napari
from qtpy.QtWidgets import QVBoxLayout, QWidget, QLabel
from qtpy.QtCore import Qt
from PyQt5.QtWidgets import QLayout, QLineEdit, QFrame, QGridLayout, QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QLabel, QComboBox, QSpacerItem, QSizePolicy, QSlider, QCheckBox, QGroupBox, QVBoxLayout, QFileDialog, QRadioButton, QStackedWidget, QTableWidget, QWidget, QInputDialog, QTableWidgetItem
from PyQt5.QtCore import Qt, pyqtSignal, QObject, QThread, QCoreApplication, QSize, pyqtSignal
from PyQt5.QtGui import QResizeEvent, QIcon, QPixmap, QFont, QDoubleValidator, QIntValidator
from PyQt5 import uic
from AnalysisClass import *
import sys
import os
import json
from pycromanager import Core, multi_d_acquisition_events, Acquisition
import numpy as np
import time
import asyncio
import pyqtgraph as pg
import matplotlib.pyplot as plt
from matplotlib import colormaps # type: ignore
import matplotlib
import pickle
from utils import CustomMainWindow
from matplotlib.backends.backend_qt5agg import FigureCanvasQTAgg
from matplotlib.figure import Figure
import tifffile
import time
from PyQt5.QtCore import QTimer,QDateTime
import logging
from typing import List, Iterable
import itertools
import queue
from napariHelperFunctions import getLayerIdFromName, InitateNapariUI
#For drawing
matplotlib.use('Qt5Agg')

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



class MMConfigWidget(QWidget):
    """
    The main glados-pycromanager widget that gets added to napari.
    """
    def __init__(self, viewer: napari.viewer.Viewer):
        super().__init__()
        self._viewer = viewer
        global shared_data
        
        
        includecustomUI = False
        include_flowChart_automatedMicroscopy = True
        
        
        core = None
        MM_JSON = None
        livestate = None
        napariViewer = None
        shared_data = None
        print('2RUN NAPARI PYCROMANAGER PLUGIN')
            
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
        
        core = Core()
        shared_data.core = core
        shared_data._headless = False
    
        MM_JSON = None
        livestate = False
        
        napariViewer = viewer
                
        #Get some info from core to put in shared_data
        shared_data._defaultFocusDevice = core.get_focus_device()
        logging.info(f"Default focus device set to {shared_data._defaultFocusDevice}")
        
        self.core = core
        self.MM_JSON = MM_JSON
        self.livestate = livestate
        self.shared_data = shared_data
        self.napariViewer = napariViewer

        # self.dockWidget = analysis_dockWidget_plugin(MM_JSON,self.layout,napariViewer,self,sharedData2=shared_data)

        self.dockWidget = microManagerControlsUI_plugin(self)
        self.setLayout(self.dockWidget)
        print('2Finalise NAPARI PYCROMANAGER PLUGIN')


class MDAWidget(QWidget):
    def __init__(self, viewer: napari.viewer.Viewer):
        logging.debug("dockWidget_MDA started")
        super().__init__()
        self._viewer = viewer
        global shared_data 
        
        #TODO: shared_data, core, outside of MDAwidget but
        # Create an instance of the shared_data class
        shared_data = Shared_data()
        
        core = Core()
        shared_data.core = core
        shared_data._headless = False
    
        MM_JSON = None
        livestate = False
        
        napariViewer = viewer
                
        self.core = core
        self.MM_JSON = MM_JSON
        self.livestate = livestate
        self.shared_data = shared_data
        self.napariViewer = napariViewer
        
        self.dockWidget = MDAGlados_plugin(self)
        self.setLayout(self.dockWidget)


class AutonomousMicroscopyWidget(QWidget):
    def __init__(self, viewer: napari.viewer.Viewer):
        
        
        logging.debug("dockWidget_autonomousMicroscopy started")
        super().__init__()
        self._viewer = viewer
        global shared_data 
        # Create an instance of the shared_data class
        shared_data = Shared_data()
        
        core = Core()
        shared_data.core = core
        shared_data._headless = False
    
        MM_JSON = None
        livestate = False
        
        napariViewer = viewer
        
        self.core = core
        self.MM_JSON = MM_JSON
        self.livestate = livestate
        self.shared_data = shared_data
        self.napariViewer = napariViewer
        
        #Add the full micro manager controls UI
        self.dockWidget = autonomousMicroscopy_plugin(self)
        
        self.setLayout(self.dockWidget)
        



class MainWidget(QWidget):
    """
    The main glados-pycromanager widget that gets added to napari.
    """
    def __init__(self, viewer: napari.viewer.Viewer):
        super().__init__()
        self._viewer = viewer
        global shared_data
        
        
        includecustomUI = False
        include_flowChart_automatedMicroscopy = True
        
        
        core = None
        MM_JSON = None
        livestate = None
        napariViewer = None
        shared_data = None
        print('RUN NAPARI PYCROMANAGER PLUGIN')
        logging.info("p1")
            
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
        
        core = Core()
        shared_data.core = core
        shared_data._headless = False
    
        MM_JSON = None
        livestate = False
        
        napariViewer = viewer
        
        MMconfigWidget = MMConfigWidget(viewer)
        self._viewer.window.add_dock_widget(MMconfigWidget, area='top',tabify=True,name='Config')
        
        custom_widget_MDA = MDAWidget(viewer)
        napariViewer.window.add_dock_widget(custom_widget_MDA, area="top", name="Multi-D acquisition",tabify=True)

        autonomousMicroscopyWidget = AutonomousMicroscopyWidget(viewer)
        napariViewer.window.add_dock_widget(autonomousMicroscopyWidget, area="top", name="Glados",tabify=True)

        print('Finalise NAPARI PYCROMANAGER PLUGIN')