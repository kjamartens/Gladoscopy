from PyQt5.QtWidgets import QGridLayout, QPushButton
from AnalysisClass import *
import napariGlados

class analysisDockWidget:
    def __init__(self,napariViewer,sharedData2=None):
        if sharedData2 is not None:
            shared_data = sharedData2
        self.napariViewer = napariViewer
        #Create a Vertical+horizontal layout:
        self.mainLayout = QGridLayout()
        #Create a layout for the configs:
        self.analysisLayout = QGridLayout()
        #Add this to the mainLayout:
        self.mainLayout.addLayout(self.analysisLayout,0,0)
        #Add a button
        self.Button1 = QPushButton('Mean grayscale value')
        self.analysisLayout.addWidget(self.Button1,1,0)
        #add a connection to the button:
        self.Button1.clicked.connect(lambda index: self.startThread('AvgGrayValueText'))
        
        self.Button2 = QPushButton('Random')
        self.analysisLayout.addWidget(self.Button2,2,0)
        #add a connection to the button:
        self.Button2.clicked.connect(lambda index: self.startThread('Random'))
        
        self.Button2 = QPushButton('GrayValOverlay')
        self.analysisLayout.addWidget(self.Button2,3,0)
        #add a connection to the button:
        self.Button2.clicked.connect(lambda index: self.startThread('GrayValueOverlay'))
        
        self.Button2 = QPushButton('Cell Segment Overlay')
        self.analysisLayout.addWidget(self.Button2,4,0)
        #add a connection to the button:
        self.Button2.clicked.connect(lambda index: self.startThread('CellSegmentOverlay'))
        
        #Add a button
        self.Button1 = QPushButton('Testing change of stage')
        self.analysisLayout.addWidget(self.Button1,5,0)
        #add a connection to the button:
        self.Button1.clicked.connect(lambda index: self.startThread('ChangeStageAtFrame'))
        
        self.Button1 = QPushButton('Start live vis')
        self.analysisLayout.addWidget(self.Button1,6,0)
        #add a connection to the button:
        self.Button1.clicked.connect(lambda index, s=shared_data: napariGlados.startLiveModeVisualisation(s))
        
        self.Button1 = QPushButton('Start mda vis')
        self.analysisLayout.addWidget(self.Button1,7,0)
        #add a connection to the button:
        self.Button1.clicked.connect(lambda index, s=shared_data: napariGlados.startMDAVisualisation(s))
    
    def startThread(self,analysisInfo):
        print('Starting analysis ' + analysisInfo)
        create_analysis_thread(shared_data,analysisInfo=analysisInfo)

def analysis_dockWidget_plugin(MM_JSON,main_layout,napariviewer,parent,sharedData2=None):
    global core, livestate, napariViewer, shared_data
    core = parent.core
    livestate = parent.livestate
    shared_data = parent.shared_data
    napariViewer = parent.napariViewer
    
    # napariViewer = napariviewer
    
    #Create the MM config via all config groups
    MMconfig = analysisDockWidget(napariViewer,sharedData2=sharedData2)
    
    return MMconfig.mainLayout


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


from MMcontrols import *

def microManagerControlsUI_plugin(parent):
    """
    Controls the Micro Manager UI.
    
    Args:
        core: The Micro Manager core object.
        MM_JSON: JSON object for Micro Manager.
        main_layout: The main layout of the UI.
        sshared_data: Shared data for the UI.
    
    Returns:
        MMconfig: The Micro Manager configuration UI object.
    """
    global core, livestate, napariViewer, shared_data
    core = parent.core
    livestate = parent.livestate
    shared_data = parent.shared_data
    napariViewer = parent.napariViewer
    shared_data.napariViewer = napariViewer
    # Get all config groups
    allConfigGroups={}
    nrconfiggroups = core.get_available_config_groups().size()
    for config_group_id in range(nrconfiggroups):
        allConfigGroups[config_group_id] = ConfigInfo(core,config_group_id)
    
    #Create the MM config via all config groups
    MMconfig = MMConfigUI(allConfigGroups,autoSaveLoad=True,parent=parent)
    # main_layout.addLayout(MMconfig.mainLayout,0,0)
    
    return MMconfig.mainLayout

