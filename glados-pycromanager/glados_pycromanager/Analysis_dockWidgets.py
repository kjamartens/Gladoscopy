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
from MDAGlados import *

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


def MDAGlados_plugin(parent):
    
    appdata_folder = os.getenv('APPDATA')
    if appdata_folder is None:
        raise EnvironmentError("APPDATA environment variable not found")
    app_specific_folder = os.path.join(appdata_folder, 'Glados-PycroManager')
    os.makedirs(app_specific_folder, exist_ok=True)
    
    if os.path.exists(os.path.join(app_specific_folder, 'glados_state.json')):
        #Load the mda state
        with open(os.path.join(app_specific_folder, 'glados_state.json'), 'r') as file:
            gladosInfo = json.load(file)
            mdaInfo = gladosInfo['MDA']
        
        
        global core, livestate, napariViewer, shared_data, MM_JSON
        core = parent.core
        livestate = parent.livestate
        shared_data = parent.shared_data
        napariViewer = parent.napariViewer
        shared_data.napariViewer = napariViewer
        MM_JSON = None
        
        #Add the full micro manager controls UI
        dockWidget = MDAGlados(core,None,parent.layout,shared_data,
                    hasGUI=True,
                    num_time_points = mdaInfo['num_time_points'], 
                    time_interval_s = mdaInfo['time_interval_s'], 
                    z_start = mdaInfo['z_start'],
                    z_end = mdaInfo['z_end'],
                    z_step = mdaInfo['z_step'],
                    z_stage_sel = mdaInfo['z_stage_sel'],
                    z_nr_steps = mdaInfo['z_nr_steps'],
                    z_step_distance = mdaInfo['z_step_distance'],
                    z_nrsteps_radio_sel = mdaInfo['z_nrsteps_radio_sel'],
                    z_stepdistance_radio_sel = mdaInfo['z_stepdistance_radio_sel'],
                    channel_group = mdaInfo['channel_group'],
                    channels = mdaInfo['channels'],
                    channel_exposures_ms = mdaInfo['channel_exposures_ms'],
                    xy_positions = mdaInfo['xy_positions'],
                    xyz_positions = mdaInfo['xyz_positions'],
                    position_labels = mdaInfo['position_labels'],
                    exposure_ms = mdaInfo['exposure_ms'],
                    storage_folder = mdaInfo['storage_folder'],
                    storage_file_name = mdaInfo['storage_file_name'],
                    order = mdaInfo['order'],
                    GUI_show_exposure = mdaInfo['GUI_show_exposure'], 
                    GUI_show_xy = mdaInfo['GUI_show_xy'], 
                    GUI_show_z = mdaInfo['GUI_show_z'], 
                    GUI_show_channel = mdaInfo['GUI_show_channel'], 
                    GUI_show_time = mdaInfo['GUI_show_time'], 
                    GUI_show_order = mdaInfo['GUI_show_order'], 
                    GUI_show_storage = mdaInfo['GUI_show_storage'], 
                    GUI_acquire_button = True,
                    autoSaveLoad=True).getGui()
    else: #If no MDA state is yet saved, open a new MDAGlados from scratch
        #Add the full micro manager controls UI
        dockWidget = MDAGlados(core,None,parent.layout,shared_data,
                    hasGUI=True,
                    GUI_acquire_button = True,
                    autoSaveLoad=True).getGui()
        
    # self.sizeChanged.connect(self.dockWidget.handleSizeChange)
    
    # #Create the MM config via all config groups
    # MMconfig = MDAGlados(allConfigGroups,autoSaveLoad=True,parent=parent)
    # # main_layout.addLayout(MMconfig.mainLayout,0,0)
    
    return dockWidget.mainLayout


from FlowChart_dockWidgets import * 

def autonomousMicroscopy_plugin(parent):
    global shared_data, napariViewer
    shared_data = parent.shared_data
    napariViewer = shared_data.napariViewer
    MM_JSON = None
    core = shared_data.core
    
    #Create the a flowchart testing
    flowChart_dockWidget = GladosNodzFlowChart_dockWidget(core=core,shared_data=shared_data,MM_JSON=MM_JSON,parent=parent)
    # main_layout.addLayout(flowChart_dockWidget.mainLayout,0,0)
    
    flowChart_dockWidget.getNodz() #not sure if needed
    
    return flowChart_dockWidget.mainLayout


def gladosSliders_plugin(parent):
    global shared_data, napariViewer
    shared_data = parent.shared_data
    napariViewer = shared_data.napariViewer
    MM_JSON = None
    core = shared_data.core
    
    print("dockWidget_fullGladosUI started")
    super().__init__()
    ui = Ui_CustomDockWidget()
    ui.setupUi(self)
    #Open JSON file with MM settings
    with open(os.path.join(sys.path[0], 'MM_PycroManager_JSON.json'), 'r') as f:
        MM_JSON = json.load(f)
    #Run the laserController UI
    print("dockWidget_fullGladosUI halfway")
    from LaserControlScripts import runlaserControllerUI
    runlaserControllerUI(core,MM_JSON,ui,shared_data)
    
    print("dockWidget_fullGladosUI initted")
    
    return ui
