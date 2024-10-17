from PyQt5.QtWidgets import QGridLayout, QPushButton
from PyQt5.QtWidgets import QLayout, QLineEdit, QFrame, QGridLayout, QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QLabel, QComboBox, QSpacerItem, QSizePolicy, QSlider, QCheckBox, QGroupBox, QVBoxLayout, QFileDialog, QRadioButton, QStackedWidget, QTableWidget, QWidget, QInputDialog, QTableWidgetItem
from PyQt5.QtCore import Qt, pyqtSignal, QObject, QThread, QCoreApplication, QSize, pyqtSignal
from PyQt5.QtGui import QResizeEvent, QIcon, QPixmap, QFont, QDoubleValidator, QIntValidator
from PyQt5 import uic

import sys, appdirs
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

def is_pip_installed():
    return 'site-packages' in __file__ or 'dist-packages' in __file__

if is_pip_installed():
    from glados_pycromanager.GUI.AnalysisClass import *
    import glados_pycromanager.GUI.napariGlados
    from glados_pycromanager.GUI.utils import CustomMainWindow
    from glados_pycromanager.GUI.napariHelperFunctions import getLayerIdFromName, InitateNapariUI
    from glados_pycromanager.GUI.MMcontrols import *
    from glados_pycromanager.GUI.MDAGlados import *
    from glados_pycromanager.GUI.FlowChart_dockWidgets import * 
else:
    from AnalysisClass import *
    import napariGlados
    from utils import CustomMainWindow
    from napariHelperFunctions import getLayerIdFromName, InitateNapariUI
    from MMcontrols import *
    from MDAGlados import *
    from FlowChart_dockWidgets import * 

#For drawing
matplotlib.use('Qt5Agg')


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
    parent.layoutInfo = MMconfig
    
    return MMconfig.mainLayout

def MDAGlados_plugin(parent):
    """
    Initializes and returns a custom dock widget for the GladOS GUI's MDA (Multi-Dimensional Acquisition) functionality.
    
    This function sets up a custom dock widget that includes the full Micro Manager controls UI. It loads the necessary configuration from a JSON file and passes it to the `MDAGlados` class.
    
    The dock widget is returned as the main layout, which can be added to the parent layout.
    
    Args:
        parent (QWidget): The parent widget for the dock widget.
    
    Returns:
        QWidget: The main layout of the custom dock widget.
    """
    appdata_folder = appdirs.user_data_dir()#os.getenv('APPDATA')
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
        
        try:
            #Add the full micro manager controls UI
            dockWidget = MDAGlados(core,None,parent.layout,shared_data,
                        hasGUI=True,
                        num_time_points = mdaInfo['num_time_points'], 
                        time_interval_s = mdaInfo['time_interval_s'], 
                        time_interval_s_or_ms = mdaInfo['time_interval_s_or_ms'],
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
                        exposure_s_or_ms = mdaInfo['exposure_s_or_ms'],
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
                        GUI_xy_pos_fullInfo = mdaInfo['xy_positions_saveInfo'],
                        GUI_acquire_button = True,
                        autoSaveLoad=True).getGui()
        except:
            
            dockWidget = MDAGlados(core,None,parent.layout,shared_data,
                        hasGUI=True,
                        GUI_acquire_button = True,
                        autoSaveLoad=True).getGui()
    else: #If no MDA state is yet saved, open a new MDAGlados from scratch
        #Add the full micro manager controls UI
        dockWidget = MDAGlados(core,None,parent.layout,shared_data,
                    hasGUI=True,
                    GUI_acquire_button = True,
                    autoSaveLoad=True).getGui()
        
    parent.layoutInfo = dockWidget
    
    return dockWidget.mainLayout

def autonomousMicroscopy_plugin(parent):
    """
    Initializes and returns a custom dock widget for the GladOS GUI's autonomous microscopy functionality.
    
    This function sets up a custom dock widget that includes a flowchart testing UI. It loads the necessary configuration from a JSON file and passes it to the `GladosNodzFlowChart_dockWidget` class.
    
    The dock widget is returned as the main layout, which can be added to the parent layout.
    
    Args:
        parent (QWidget): The parent widget for the dock widget.
    
    Returns:
        QWidget: The main layout of the custom dock widget.
    """
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
    """
    Initializes and returns a custom dock widget for the GladOS GUI.
    
    This function sets up a custom dock widget that includes a laser controller UI. It loads the necessary configuration from a JSON file and passes it to the `runlaserControllerUI` function from the `LaserControlScripts` module.
    
    The dock widget is returned as the main layout, which can be added to the parent layout.
    
    Args:
        parent (QWidget): The parent widget for the dock widget.
    
    Returns:
        QWidget: The main layout of the custom dock widget.
    """
    global shared_data, napariViewer
    shared_data = parent.shared_data
    napariViewer = shared_data.napariViewer
    MM_JSON = None
    core = shared_data.core
    
    logging.debug("dockWidget_fullGladosUI started")
    
    #new QWidget:
    tempWidget = QMainWindow()
    
    ui = Ui_CustomDockWidget()
    ui.setupUi(tempWidget)
    #Open JSON file with MM settings
    # with open(os.path.join(sys.path[0], 'MM_PycroManager_JSON.json'), 'r') as f:
    with open("C:/Users/Koen Martens/Documents/GitHub/ScopeGUI/glados-pycromanager/glados_pycromanager/GUI/MM_PycroManager_JSON.json") as f:
        MM_JSON = json.load(f)
    #Run the laserController UI
    logging.debug("dockWidget_fullGladosUI halfway")
    from LaserControlScripts import runlaserControllerUI
    runlaserControllerUI(core,MM_JSON,ui,shared_data)
    
    logging.debug("dockWidget_fullGladosUI initted")
    
    return ui

