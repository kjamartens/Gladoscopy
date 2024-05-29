from typing import Callable
from dataclasses import dataclass

import napari
from qtpy.QtWidgets import QVBoxLayout, QWidget, QLabel
from qtpy.QtCore import Qt
from PyQt5.QtWidgets import QLayout, QLineEdit, QFrame, QGridLayout, QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QLabel, QComboBox, QSpacerItem, QSizePolicy, QSlider, QCheckBox, QGroupBox, QVBoxLayout, QFileDialog, QRadioButton, QStackedWidget, QTableWidget, QWidget, QInputDialog, QTableWidgetItem
from PyQt5.QtCore import Qt, pyqtSignal, QObject, QThread, QCoreApplication, QSize, pyqtSignal
from PyQt5.QtGui import QResizeEvent, QIcon, QPixmap, QFont, QDoubleValidator, QIntValidator
from PyQt5 import uic
from AnalysisClass import * #type:ignore
from utils import CustomMainWindow #type:ignore
from napariHelperFunctions import getLayerIdFromName, InitateNapariUI #type:ignore
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
from matplotlib.backends.backend_qt5agg import FigureCanvasQTAgg
from matplotlib.figure import Figure
import tifffile
import time
from PyQt5.QtCore import QTimer,QDateTime
import logging
from typing import List, Iterable
import itertools
import queue
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
from napariGlados import * #type: ignore
from sharedFunctions import Shared_data, periodicallyUpdate #type: ignore
from utils import * #type: ignore

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
from napariHelperFunctions import showScaleBar #type: ignore
#endregion

class GladosWidget(QWidget):
    """
    The main Class of glados-pycromanager widget that gets added to napari.
    """
    def __init__(self, viewer: napari.viewer.Viewer, parent=None): #type: ignore
        """
        Init a glados widget, mostly passing around parent variables to daughter (plugin) variables. Used to be global-specified, but doesn't work with napari plugins for some reason.
        """
        super().__init__()
        self._viewer = viewer
        
        if parent is not None:
            self.core = parent.core
            self.MM_JSON = parent.MM_JSON
            self.livestate = parent.livestate
            self.shared_data = parent.shared_data
            self.napariViewer = parent.napariViewer

class MMConfigWidget(GladosWidget):
    """
    The micromanager-glados-pycromanager configuration plugin.
    Allows users to change all configs specified in MM
    """
    def __init__(self, viewer: napari.viewer.Viewer, parent=None): #type: ignore
        """
        Initialize the micromanager-config plugin
        """
        super().__init__(viewer = viewer, parent=parent)
        
        #Get some info from core to put in shared_data
        self.shared_data._defaultFocusDevice = self.core.get_focus_device()
        logging.info(f"Default focus device set to {self.shared_data._defaultFocusDevice}")
        
        #Start docwidget
        self.dockWidget = microManagerControlsUI_plugin(self) #type:ignore
        self.setLayout(self.dockWidget)
        logging.info("dockWidget_MMConfig started")


class MDAWidget(GladosWidget):
    """
    The micromanager-glados-pycromanager multi-dimensional acquisition plugin
    """
    def __init__(self, viewer: napari.viewer.Viewer, parent=None): #type:ignore
        """
        Initialize the Multi-D acquisition plugin
        """
        super().__init__(viewer = viewer, parent=parent)
        
        self.dockWidget = MDAGlados_plugin(self) #type:ignore
        self.setLayout(self.dockWidget)
        logging.info("dockwidget_MDA started")


class AutonomousMicroscopyWidget(GladosWidget):
    """
    The micromanager-glados-pycromanager autonomous microscopy widget plugin
    """
    def __init__(self, viewer: napari.viewer.Viewer, parent=None): #type:ignore
        """
        Initialize the AutonomousMicroscopyWidget plugin
        """
        super().__init__(viewer = viewer, parent=parent)
        
        #Add the full micro manager controls UI
        self.dockWidget = autonomousMicroscopy_plugin(self) #type:ignore
        
        self.setLayout(self.dockWidget)
        logging.info("dockWidget_AutonomousMicroscopy started")

class MainWidget(QWidget):
    """
    The main call when napari-glados is started
    Basically starts-up all the initialization and starts all widgets
    """
    def __init__(self, viewer: napari.viewer.Viewer): #type:ignore
        """
        Initialize the GladosPycroManager plugin call
        """
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
        
        self.core = core
        self.shared_data = shared_data
        self.napariViewer = viewer
        self.MM_JSON = MM_JSON
        self.livestate = livestate
    
        includecustomUI = False
        include_flowChart_automatedMicroscopy = True
        
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
        logging.info("Main napari Glados-pycromanager plugin started")
        
        #Initialise napari-scalebar
        napariViewer = viewer
        showScaleBar(viewer)
        
        #Add the individual widgets
        
        #Full MM control
        MMconfigWidget = MMConfigWidget(viewer, parent=self)
        self._viewer.window.add_dock_widget(MMconfigWidget, area='top',tabify=True,name='Config')
        
        #Multi-D acquisition window
        custom_widget_MDA = MDAWidget(viewer, parent=self)
        napariViewer.window.add_dock_widget(custom_widget_MDA, area="top", name="Multi-D acquisition",tabify=True)

        #Autonomous microscopy
        autonomousMicroscopyWidget = AutonomousMicroscopyWidget(viewer, parent=self)
        napariViewer.window.add_dock_widget(autonomousMicroscopyWidget, area="top", name="Glados",tabify=True)

        logging.info('Napari-glados-pycromanager plugin fully loaded')