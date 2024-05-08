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

class ConfigInfo:
    """
    This class contains information about a pycromanager config group
    Contains info such as name, min/max value etc
    """
    def __init__(self,core,config_group_id):
        """
        This class contains information about a pycromanager config group
        Contains info such as name, min/max value etc
        
        Attributes:
            core (Core): The pycromanager core object
            config_group_id (int): The id of the config group
        """
        self.core = core
        self.config_group_id = config_group_id
        pass
    
    def configGroupName(self):
        """
        Returns the config group name
        """
        return self.core.get_available_config_groups().get(self.config_group_id)
    
    def nrConfigs(self):
        """Returns the number of config options for this config group"""
        return self.core.get_available_configs(self.core.get_available_config_groups().get(self.config_group_id)).size()
    
    def configName(self,config_id):
        """Returns the name of the config within the config group"""
        return self.core.get_available_configs(self.core.get_available_config_groups().get(self.config_group_id)).get(config_id)
    
    def deviceNameProperty_fromVerbose(self):
        """Returns the first device name and property from Verbose"""
        verboseInfoCurrentConfigGroup = self.core.get_config_group_state(self.configGroupName()).get_verbose()
        start_index = verboseInfoCurrentConfigGroup.find("<html>") + len("<html>")
        end_index = verboseInfoCurrentConfigGroup.find(":")
        deviceName = verboseInfoCurrentConfigGroup[start_index:end_index]
        start_index = end_index + len(":")
        end_index = verboseInfoCurrentConfigGroup.find("=")
        deviceProperty  = verboseInfoCurrentConfigGroup[start_index:end_index]
        return deviceName,deviceProperty
    
    def hasPropertyLimits(self):
        """Returns whether the config group has property limits"""
        #Get the verbose info from the config group state
        verboseInfoCurrentConfigGroup = self.core.get_config_group_state(self.configGroupName()).get_verbose()
        #Determine the number of devices in the verbose info
        nrDevicesFromVerbose = verboseInfoCurrentConfigGroup.count('<br>')
        if nrDevicesFromVerbose == 1 and self.nrConfigs() == 1:
            [deviceName,deviceProperty] = self.deviceNameProperty_fromVerbose()
            #Determines whether the device name/property has limits:
            if self.core.has_property_limits(deviceName,deviceProperty):
                return True
            else:
                return False
        else:
            return False
    
    def lowerLimit(self):
        """Finds lower limit of the device property"""
        [deviceName,deviceProperty] = self.deviceNameProperty_fromVerbose()
        if self.core.has_property_limits(deviceName,deviceProperty):
            lowerLimit = self.core.get_property_lower_limit(deviceName,deviceProperty)
        else:
            lowerLimit = 0
        return lowerLimit
            
    def upperLimit(self):
        """Finds upper limit of the device property"""
        [deviceName,deviceProperty] = self.deviceNameProperty_fromVerbose()
        if self.core.has_property_limits(deviceName,deviceProperty):
            upperLimit = self.core.get_property_upper_limit(deviceName,deviceProperty)
        else:
            upperLimit = 0
        return upperLimit
            
    def isDropDown(self):
        """Returns Boolean whether the config group should be represented as a drop-down menu"""
        if self.nrConfigs()>1:
            return True
        else:
            return False
        
    def isSlider(self):
        """Returns Boolean whether the config group should be represented as a slider"""
        if self.nrConfigs()>1:
            return False
        else:
            if self.hasPropertyLimits():
                return True
            else:
                return False
    
    def isInputField(self):
        """Returns Boolean whether the config group should be represented as an input field"""
        if self.nrConfigs()>1:
            return False
        else:
            if self.hasPropertyLimits():
                return False
            else:
                return True

    def helpStringInfo(self):
        """Provides some info about the config group, whether it should be a dropdown, slider, input field"""
        infostring='No option for this config'
        if self.isDropDown():
            infostring = "Device {} should be an dropdown with {} options".format(self.configGroupName(),self.nrConfigs())
        if self.isSlider():
            infostring = "Device {} should be an Slider with limits {}-{}".format(self.configGroupName(),self.lowerLimit(),self.upperLimit())
        if self.isInputField():
            infostring = "Device {} should be an input field".format(self.configGroupName())
        return infostring
    
    def getCurrentMMValue(self):
        """Get the current MM value of this config group:"""
        return self.core.get_current_config(self.configGroupName())

class MMConfigUI(CustomMainWindow):
    """
        A class to create a MicroManager config UI
    """
    def __init__(self, config_groups,showConfigs = True,showStages=True,showROIoptions=True,showLiveMode=True,number_config_columns=5,changes_update_MM = True,showCheckboxes = False,checkboxStartInactive=True,showRelativeStages = False,autoSaveLoad=False):
        """
        A class to create a MicroManager config UI with the given configuration groups.
        
        This class will create a UI with a layout of checkboxes, sliders, input fields, dropdowns, etc
        The user can select which config groups to show and which configs to show for each config group. The user can also change the configs real-time. 
        
        Parameters:
            config_groups (list): A list of configuration groups. Get this as follows:
                nrconfiggroups = core.get_available_config_groups().size()
                for config_group_id in range(nrconfiggroups):
                    allConfigGroups[config_group_id] = ConfigInfo(core,config_group_id)
            showConfigs (bool, optional): Whether to show the configurations in the UI. Defaults to True.
            showStages (bool, optional): Whether to show the stages in the UI. Defaults to True.
            showROIoptions (bool, optional): Whether to show the ROI options in the UI. Defaults to True.
            showLiveMode (bool, optional): Whether to show the live mode in the UI. Defaults to True.
            number_config_columns (int, optional): The number of columns in the layout. Defaults to 5.
            changes_update_MM (bool, optional): Whether to update the configs in MicroManager real-time. Defaults to True.
            showCheckboxes (bool, optional): Whether to show checkboxes for each config group. Defaults to False.
            checkboxStartInactive (bool, optional): Whether the checkboxes should start inactive. Defaults to True.
            showRelativeStages (bool, optional): Whether to show the relative stages in the UI. Defaults to False.
            autoSaveLoad (bool, optional): Whether to automatically save and load the configs to file when the UI is opened and closed. Defaults to False.
        """
        
        super().__init__()
        self.fullyLoaded = False
        self.autoSaveLoad = autoSaveLoad
        self.showConfigs = showConfigs
        self.showStages = showStages
        self.showROIoptions = showROIoptions
        self.showLiveMode = showLiveMode
        self.showCheckboxes = showCheckboxes
        self.showRelativeStages = showRelativeStages
        self.config_groups = config_groups
        self.number_columns = number_config_columns
        self.changes_update_MM = changes_update_MM
        if self.config_groups is not None:
            self.core = self.config_groups[0].core
        else:
            self.core = None
        self.dropDownBoxes = {}
        self.sliders = {}
        self.configCheckboxes = {}
        self.sliderPrecision = 100
        self.config_string_storage = []
        #Create a Vertical+horizontal layout:
        self.mainLayout = QGridLayout()
        self.configEntries = {}
        if showConfigs:
            #Create a layout for the configs:
            self.configGroupBox = QGroupBox("Configurations")
            self.configLayout = QGridLayout()
            #Add this to the mainLayout via the groupbox:
            self.configGroupBox.setLayout(self.configLayout)
            self.mainLayout.addWidget(self.configGroupBox,0,0)
            #Fill the configLayout
            for config_id in range(len(config_groups)):
                self.configEntries[config_id] = self.addRow(config_id)
            pass
        
            #Add a button to refresh from MM:
            self.refreshButton = QPushButton("Refresh configs from MM")
            totalRowsAdded = int(np.ceil(len(config_groups)/self.number_columns))
            #Add a button spanning the total columns at the bottom
            self.configLayout.addWidget(self.refreshButton,totalRowsAdded+99,0,1,self.number_columns)
            #Connect the button:
            self.refreshButton.clicked.connect(lambda index: self.updateConfigsFromMM())
            
        
        #Add the stages widget to the right of this if wanted
        if showStages:
            #Now add the stages widget
            # self.stagesWidget()
            self.stagesGroupBox = QGroupBox("Stages")
            self.stagesGroupBox.setLayout(self.stagesLayout())
            self.mainLayout.addWidget(self.stagesGroupBox, 0, 2)
        
        if showROIoptions:
            #Now add the ROI options widget
            self.roiOptionsGroupBox = QGroupBox("ROI Options")
            self.roiOptionsGroupBox.setLayout(self.ROIoptionsLayout())
            self.mainLayout.addWidget(self.roiOptionsGroupBox, 0, 4)
        
        if showLiveMode:
            #Now add the live mode widget
            self.liveModeGroupBox = QGroupBox("Live Mode")
            self.liveModeGroupBox.setLayout(self.liveModeLayout())
            self.mainLayout.addWidget(self.liveModeGroupBox, 0, 6)
        
        if showRelativeStages:
            self.relativeStagesGroupBox = QGroupBox("RelativeStages")
            self.relativeStagesGroupBox.setLayout(self.relativeStagesLayout())
            self.mainLayout.addWidget(self.relativeStagesGroupBox, 0, 7)
        
        #Update everything for good measure at the end of init
        self.fullyLoaded = True
        self.updateAllMMinfo()
        
        #Inactivate all configs if this is wanted
        if checkboxStartInactive and showCheckboxes and showConfigs:
            for config_id in range(len(config_groups)):
                self.configCheckboxes[config_id].setChecked(False)
                    
        #Change the font of everything in the layout
        self.set_font_and_margins_recursive(self.mainLayout, font=QFont("Arial", 7))
    
    #region General
    def updateAllMMinfo(self):
        """
        Update all the info that can be updated from the microscope.
        """
        logging.debug('Updating all MM info')
        if self.showConfigs:
            self.updateConfigsFromMM()
        if self.showStages:
            self.updateXYStageInfoWidget()
            self.updateOneDstageLayout()
        
        if self.autoSaveLoad:
            if self.fullyLoaded:
                if os.path.exists('glados_state.json'):
                    with open('glados_state.json', 'r') as file:
                        gladosInfo = json.load(file)
                        MMControlsInfo = gladosInfo['MMControls']
                
                    #Hand-set the values that I want:
                    self.exposureTimeInputField.setText(MMControlsInfo['exposureTimeInputField']['text'])
                    for key, object in self.XYMoveEditField.items():
                        if key in MMControlsInfo:
                            object.setText(MMControlsInfo[key]['text'])
                    for key,object in self.oneDMoveEditField.items():
                        for objectLineEditKey in object:
                            objectLineEdit = object[objectLineEditKey]
                            if objectLineEditKey in MMControlsInfo:
                                objectLineEdit.setText(MMControlsInfo[objectLineEditKey]['text'])

    def storeAllControlValues(self):
        """
        Store all the control values in a dictionary, which can be used to save state.
        """
        if self.autoSaveLoad:
            if self.fullyLoaded:
                self.save_state_MMControls('glados_state.json')
                pass

    def set_font_and_margins_recursive(self,widget, font=QFont("Arial", 8)):
        """
        Recursively sets the font of all buttons/labels in a layout to the specified font, and sets the contents margins to 0.
        Also sets the size policy of the widget to minimum, so it will only take up as much space as it needs.

        """
        if widget is None:
            return
        
        if isinstance(widget, (QLabel, QPushButton, QComboBox)):
            widget.setFont(font)
            widget.setContentsMargins(0, 0, 0, 0)
            widget.setMinimumSize(0, 0)
            # widget.setSizePolicy(
            #     QSizePolicy(QSizePolicy.Minimum, QSizePolicy.Minimum)
            # )

        if hasattr(widget, 'layout'):
            layout = widget.layout()
            if layout:
                layout.setContentsMargins(0, 0, 0, 0)
                # layout.setSpacing(0)  # Optionally, remove spacing between widgets
                for i in range(layout.count()):
                    item = layout.itemAt(i)
                    if hasattr(item, 'widget'):
                        self.set_font_and_margins_recursive(item.widget(), font=font)
                    if hasattr(item, 'layout'):
                        self.set_font_and_margins_recursive(item.layout(), font=font)
    #endregion
    
    #region live mode
    def liveModeLayout(self):
        """
        Creates the layout for the live mode options.
        This includes an input field for the exposure time in ms.

        Returns:
            QGridLayout: The layout for the live mode options.
        """
        #Create a Grid layout:
        liveModeLayout = QGridLayout()
        #Add a 'exposure time' label:
        exposureTimeLabel = QLabel("Exposure time (ms):")
        liveModeLayout.addWidget(exposureTimeLabel,1,0)
        #Add a 'exposure time' input field:
        self.exposureTimeInputField = QLineEdit()
        self.exposureTimeInputField.setText(str(100))
        self.exposureTimeInputField.textChanged.connect(lambda: self.storeAllControlValues())
        liveModeLayout.addWidget(self.exposureTimeInputField,1,1)
        
        self.LiveModeButton = QPushButton("Start Live Mode")
        #add a connection to the button:
        self.LiveModeButton.clicked.connect(lambda index: self.changeLiveMode())
        #Add the button to the layout:
        liveModeLayout.addWidget(self.LiveModeButton,0,0,1,2)
        #Return the layout
        return liveModeLayout
    
    def changeLiveMode(self):
        """
        Function that should be called when live mode is changed. Sets the shared_data.liveMode to True or False.
        """
        if shared_data.liveMode == False:
            #update the button text of the live mode:
            self.LiveModeButton.setText("Stop Live Mode")
            #set exposure time first:
            shared_data.core.set_exposure(float(self.exposureTimeInputField.text()))
            #Then start live mode:
            shared_data.liveMode = True
        else:
            #update the button text of the live mode:
            self.LiveModeButton.setText("Start Live Mode")
            #update live mode:
            shared_data.liveMode = False
    #endregion

    #region ROI
    def ROIoptionsLayout(self):
        """
        Create a layout with buttons for ROI options

        Returns
        -------
        ROIoptionsLayout : QGridLayout
            A layout with buttons for ROI options
        """
        #Create a Grid layout:
        ROIoptionsLayout = QGridLayout()
        self.ROIoptionsButtons = {}
        #Following options should be added:
        #Reset ROI to max size
        self.ROIoptionsButtons['Reset'] = QPushButton("Reset ROI")
        self.ROIoptionsButtons['Reset'].clicked.connect(lambda index: self.resetROI())
        ROIoptionsLayout.addWidget(self.ROIoptionsButtons['Reset'],0,0)
        #Zoom in once to center
        self.ROIoptionsButtons['ZoomIn'] = QPushButton("Zoom In")
        self.ROIoptionsButtons['ZoomIn'].clicked.connect(lambda index: self.zoomROI('ZoomIn'))
        ROIoptionsLayout.addWidget(self.ROIoptionsButtons['ZoomIn'],1,0)
        #Zoom out once from center
        self.ROIoptionsButtons['ZoomOut'] = QPushButton("Zoom Out")
        self.ROIoptionsButtons['ZoomOut'].clicked.connect(lambda index: self.zoomROI('ZoomOut'))
        ROIoptionsLayout.addWidget(self.ROIoptionsButtons['ZoomOut'],2,0)
        return ROIoptionsLayout
    
    def resetROI(self):
        """
        Reset the ROI to its maximum size

        This function resets the ROI to its maximum size, which is the size of the image
        """
        self.core.clear_roi() #type:ignore
    
    def zoomROI(self,option):
        """
        Zoom the ROI in or out from the center
        
        This function zooms the ROI in or out from the center.
        It zooms the ROI by a factor of 2.
        If the option is "ZoomIn", the ROI is zoomed in twice.
        If the option is "ZoomOut", the ROI is zoomed out twice
        """
        #Get the current ROI info
        #[x,y,width,height]
        roiv = [self.core.get_roi().x,self.core.get_roi().y,self.core.get_roi().width,self.core.get_roi().height] #type:ignore
        logging.debug('ROI zoom requested, current size: '+str(roiv))
        if option == 'ZoomIn':
            #zoom in twice
            try:
                #Get current widht/height and new width/height
                curTotWidth = roiv[2]
                curTotHeight = roiv[3]
                newTotWidth = int(curTotWidth/2)
                newTotHeight = int(curTotHeight/2)
                newX = int(roiv[0]+(curTotWidth-newTotWidth)/2)
                newY = int(roiv[1]+(curTotHeight-newTotHeight)/2)
                #Set the new ROI size
                self.setROI([newX,newY,newTotWidth,newTotHeight])
            except:
                logging.error('ZOOMING IN DIDN\'T WORK!')
        elif option == 'ZoomOut':
            #zoom in twice
            try:
                #Get current widht/height and new width/height
                curTotWidth = roiv[2]
                curTotHeight = roiv[3]
                newTotWidth = int(curTotWidth*2)
                newTotHeight = int(curTotHeight*2)
                newX = int(roiv[0]-(newTotWidth-curTotWidth)/2)
                newY = int(roiv[1]-(newTotHeight-curTotHeight)/2)
                #Set the new ROI size
                self.setROI([newX,newY,newTotWidth,newTotHeight])
            except:
                logging.error('ZOOMING IN DIDN\'T WORK!')
    
    def setROI(self,ROIpos):
        """
        Set the ROI to the specified position and size.
        
        The ROIpos should be a list of [x,y,width,height]
        """
        #ROIpos should be a list of [x,y,width,height]
        logging.debug('Zooming ROI to ' + str(ROIpos))
        try:
            if shared_data.liveMode == False:
                self.core.set_roi(ROIpos[0],ROIpos[1],ROIpos[2],ROIpos[3]) #type:ignore
                self.core.wait_for_system() #type:ignore
            else:
                shared_data.liveMode = False
                self.core.set_roi(ROIpos[0],ROIpos[1],ROIpos[2],ROIpos[3]) #type:ignore
                time.sleep(0.5)
                shared_data.liveMode = True
        except:
            logging.error('ZOOMING DIDN\'T WORK!')
    #endregion
    
    #region Stages
    def stagesLayout(self):
        """
        Returns the layout with the XY and 1D stage widgets.

        This layout is used when the user is not in relative mode.
        """
        stageLayout = QHBoxLayout()
        stageLayout.addLayout(self.XYstageLayout())
        stageLayout.addLayout(self.oneDstageLayout())
        return stageLayout
    
    def relativeStagesLayout(self):
        """
        Returns the layout with the XY stage widgets in relative mode.

        This layout is used when the user is in relative mode.
        """
        stageLayout = QHBoxLayout()
        stageLayout.addLayout(self.XYstageLayout())
        stageLayout.addLayout(self.oneDstageLayout())
        return stageLayout
    
    def XYstageLayout(self):
        """
        Returns a layout with the XY stage widgets.

        This layout includes a label with the current position,
        three arrow buttons to move in the XY stage relative to the current position,
        and text fields to set the size of the arrow buttons movement
        """
        #Obtain the stage info from MM:
        XYStageName = self.core.get_xy_stage_device() #type: ignore
        #Get the stage position
        XYStagePos = self.core.get_xy_stage_position(XYStageName)#type: ignore
        
        #Get current pixel size via self.core.get_pixel_size_um()
        #Then move 0.1, 0.5, or 1 field with the arrows
        field_size_um = [self.core.get_pixel_size_um()*self.core.get_roi().width,self.core.get_pixel_size_um()*self.core.get_roi().height]#type: ignore
        field_move_fraction = [1,.5,.1]
        
        #Widget itself is a grid layout with 7x7 entries
        XYStageLayout = QGridLayout()
        XYStageLayout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        
        #XY move buttons
        self.XYmoveButtons = {}
        for m in range(1,4):
            #Initialize buttons
            self.XYmoveButtons[f'Up_{m}'] = QPushButton("⮝"*(4-m))
            self.XYmoveButtons[f'Up_{m}'].clicked.connect(lambda index, m=m: self.moveXYStage(0,float(self.XYMoveEditField[f"Y_{4-m}"].text())))
            self.XYmoveButtons[f'Down_{m}'] = QPushButton("⮟"*(4-m))
            self.XYmoveButtons[f'Down_{m}'].clicked.connect(lambda index, m=m: self.moveXYStage(0,float(self.XYMoveEditField[f"Y_{4-m}"].text())*-1))
            self.XYmoveButtons[f'Left_{m}'] = QPushButton("⮜"*(4-m))
            self.XYmoveButtons[f'Left_{m}'].clicked.connect(lambda index, m=m: self.moveXYStage(float(self.XYMoveEditField[f"X_{4-m}"].text())*-1,0))
            self.XYmoveButtons[f'Right_{m}'] = QPushButton("⮞"*(4-m))
            self.XYmoveButtons[f'Right_{m}'].clicked.connect(lambda index, m=m: self.moveXYStage(float(self.XYMoveEditField[f"X_{4-m}"].text()),0))
            
            #Add buttons to layout
            XYStageLayout.addWidget(self.XYmoveButtons[f'Up_{m}'],m-1,4,1,1, alignment=Qt.AlignmentFlag.AlignCenter)
            XYStageLayout.addWidget(self.XYmoveButtons[f'Down_{m}'],8-m,4,1,1, alignment=Qt.AlignmentFlag.AlignCenter)
            XYStageLayout.addWidget(self.XYmoveButtons[f'Left_{m}'],4,m-1,1,1, alignment=Qt.AlignmentFlag.AlignCenter)
            XYStageLayout.addWidget(self.XYmoveButtons[f'Right_{m}'],4,8-m,1,1, alignment=Qt.AlignmentFlag.AlignCenter)
        
        XYStageSetMovementLayout = QGridLayout()
        XYStageSetMovementLayout.addWidget(QLabel('X'),0,1,1,1, alignment=Qt.AlignmentFlag.AlignCenter)
        XYStageSetMovementLayout.addWidget(QLabel('Y'),0,2,1,1, alignment=Qt.AlignmentFlag.AlignCenter)
        self.XYMoveEditField = {}
        pushButtonLabelArr = ["0.1 field","1 field","3 fields"]
        for m in range(1,4):
            XYStageSetMovementLayout.addWidget(QLabel("⮞"*(m)),m,0,1,1, alignment=Qt.AlignmentFlag.AlignRight)
            self.XYMoveEditField[f"X_{m}"] = QLineEdit()
            XYStageSetMovementLayout.addWidget(self.XYMoveEditField[f"X_{m}"],m,1,1,1, alignment=Qt.AlignmentFlag.AlignCenter)
            self.XYMoveEditField[f"X_{m}"].textChanged.connect(lambda: self.storeAllControlValues())
            self.XYMoveEditField[f"Y_{m}"] = QLineEdit()
            XYStageSetMovementLayout.addWidget(self.XYMoveEditField[f"Y_{m}"],m,2,1,1, alignment=Qt.AlignmentFlag.AlignCenter)
            self.XYMoveEditField[f"Y_{m}"].textChanged.connect(lambda: self.storeAllControlValues())
            XYStageSetMovementLayout.addWidget(QLabel("μm"),m,3,1,1, alignment=Qt.AlignmentFlag.AlignLeft)
            self.XYMoveEditField[f"Button_{m}"] = QPushButton(pushButtonLabelArr[m-1])
            
            self.XYMoveEditField[f"Button_{m}"].clicked.connect(lambda index, m=m: self.setXYStageMovementValue(m-1,self.XYMoveEditField[f"X_{m}"],self.XYMoveEditField[f"Y_{m}"]))
            
            XYStageSetMovementLayout.addWidget(self.XYMoveEditField[f"Button_{m}"],m,4,1,1, alignment=Qt.AlignmentFlag.AlignLeft)
            
        #Add the setmovementlayout to the XY stage layout
        XYStageLayout.addLayout(XYStageSetMovementLayout,8,0,1,8, alignment=Qt.AlignmentFlag.AlignCenter)
                
        #Add a central label for info
        #this label contains the XY stage name, then an enter, then the current position:
        self.XYStageInfoWidget = QLabel()
        XYStageLayout.addWidget(self.XYStageInfoWidget,4,4)
        #Update the text of it
        self.updateXYStageInfoWidget()
        
        return XYStageLayout
    
    def setXYStageMovementValue(self,m,xEditField,yEditField):
        """
        Set the XY stageLineEdits to specific values based on the Buttons next to the fields.
        This function is called when the user presses the "Set" buttons next to the XY EditFields
        """
        #Set the values in the XY EditFields based on the buttons
        fieldUnits = [0.1,1,3]
        fieldUnit = fieldUnits[m]
        field_size_um = [self.core.get_pixel_size_um()*self.core.get_roi().width,self.core.get_pixel_size_um()*self.core.get_roi().height]#type: ignore
        
        x_value_um = field_size_um[0]*fieldUnit
        y_value_um = field_size_um[1]*fieldUnit
        xEditField.setText(str(x_value_um))
        yEditField.setText(str(y_value_um))
        self.storeAllControlValues()
    
    def getDevicesOfDeviceType(self,devicetype):
        """
        #Find all devices that have a specific devicetype
        #Look at https://javadoc.scijava.org/Micro-Manager-Core/mmcorej/DeviceType.html 
        #for all devicetypes
        """
        #Get devices
        devices = self.core.get_loaded_devices() #type:ignore
        devices = [devices.get(i) for i in range(devices.size())]
        devicesOfType = []
        #Loop over devices
        for device in devices:
            if self.core.get_device_type(device).to_string() == devicetype: #type:ignore
                logging.debug("found " + device + " of type " + devicetype)
                devicesOfType.append(device)
        return devicesOfType
    
    def oneDstageLayout(self):
        """
        Creates a UI layout to place all found one-D stages in a QStackedWidget and add the LineEdits etc. Also see XYstageLayout()
        """
        #Create a layout
        self.oneDStageLayout = QGridLayout()
        
        #Creates a UI layout to move all found 1D stages
        #Find all 1D stages
        allStages = self.getDevicesOfDeviceType('StageDevice')
        
        #Create a drop-down menu that has these stages as options
        self.oneDstageDropdown = QComboBox()
        for stage in allStages:
            self.oneDstageDropdown.addItem(stage)
        #If it changes, call the update routine
        self.oneDstageDropdown.currentTextChanged.connect(lambda index: self.updateOneDstageLayout())
        #Add the dropdown to the layout:
        self.oneDStageLayout.addWidget(self.oneDstageDropdown,0,0)
        
        #Add left/right buttons and a label for the position
        self.oneDmoveButtons = {}
        for m in range(1,3):
            #Initialize buttons
            self.oneDmoveButtons[f'Left_{m}'] = QPushButton("⮝"*(3-m))
            self.oneDmoveButtons[f'Left_{m}'].clicked.connect(lambda index, m=m: self.moveOneDStage(-m))
            self.oneDmoveButtons[f'Right_{m}'] = QPushButton("⮟"*(3-m))
            self.oneDmoveButtons[f'Right_{m}'].clicked.connect(lambda index, m=m: self.moveOneDStage(m))
            
            #Add buttons to layout
            self.oneDStageLayout.addWidget(self.oneDmoveButtons[f'Left_{m}'],m-1+2,0,1,1, alignment=Qt.AlignmentFlag.AlignCenter)
            self.oneDStageLayout.addWidget(self.oneDmoveButtons[f'Right_{m}'],5-m+2,0,1,1, alignment=Qt.AlignmentFlag.AlignCenter)
        
        #Create a QGridBox for the movement sizes for each stage:
        self.oneDMoveEditFieldGridLayouts={}
        self.oneDMoveEditField={}
        self.oneDStackedWidget = QStackedWidget()
        for stage in allStages:
            self.oneDMoveEditFieldGridLayouts[stage] = QWidget()
            self.oneDMoveEditFieldGridLayouts[stage].setObjectName(stage)
            internalLayout = QGridLayout()
            self.oneDMoveEditFieldGridLayouts[stage].setLayout(internalLayout)
            self.oneDMoveEditField[stage] = {}
            for m in range(1,3):
                internalLayout.addWidget(QLabel("⮞"*(m)),m,0)
                self.oneDMoveEditField[stage][f'oneDStackedWidget_{stage}_{m}'] = QLineEdit()
                internalLayout.addWidget(self.oneDMoveEditField[stage][f'oneDStackedWidget_{stage}_{m}'],m,1)
                self.oneDMoveEditField[stage][f'oneDStackedWidget_{stage}_{m}'].setText("10")
                self.oneDMoveEditField[stage][f'oneDStackedWidget_{stage}_{m}'].textChanged.connect(lambda: self.storeAllControlValues())
            
            self.oneDStackedWidget.addWidget(self.oneDMoveEditFieldGridLayouts[stage])
        
        self.oneDStageLayout.addWidget(self.oneDStackedWidget,8,0)
        
        #Get current info of the widget
        self.oneDinfoWidget = QLabel()
        self.oneDStageLayout.addWidget(self.oneDinfoWidget,1,0)
        #update the text
        self.updateOneDstageLayout()
        
        #Store the values
        self.storeAllControlValues()
        
        return self.oneDStageLayout
    
    def updateOneDstageLayout(self):
        """
        Updates the OneD stage layout text with the current values of the stage dropdown and the current position of the stage
        """
        self.oneDinfoWidget.setText(f"{self.oneDstageDropdown.currentText()}\r\n {self.core.get_position(self.oneDstageDropdown.currentText()):.1f}") #type:ignore
        
        for widget_id in range(0,self.oneDStackedWidget.count()):
            widget = self.oneDStackedWidget.widget(widget_id)
            if widget.objectName() == self.oneDstageDropdown.currentText():
                self.oneDStackedWidget.setCurrentIndex(widget_id)
    
    def moveOneDStage(self,amount):
        """
        Moves the selected one-D stage by the specified amount

        Parameters
        ----------
        amount: int: 1 or 2, 'small step' or 'big step'
        """
        #Get the currently selected one-D stage:
        selectedStage = self.oneDstageDropdown.currentText()
        
        #Get the value currently in the LineEdit
        self.moveoneDstagesmallAmount = float(self.oneDMoveEditField[selectedStage][f'oneDStackedWidget_{selectedStage}_1'].text())
        self.moveoneDstagelargeAmount = float(self.oneDMoveEditField[selectedStage][f'oneDStackedWidget_{selectedStage}_2'].text())
        
        logging.debug("moving " + selectedStage + " by " + str(amount))
        
        #Move the stage relatively
        if abs(amount) == 2:
            self.core.set_relative_position(selectedStage,(np.sign(amount)*self.moveoneDstagesmallAmount).astype(float)) #type:ignore
        elif abs(amount) == 1:
            self.core.set_relative_position(selectedStage,(np.sign(amount)*self.moveoneDstagelargeAmount).astype(float)) #type:ignore
        self.updateOneDstageLayout()
        
    def updateXYStageInfoWidget(self):
        """
        Updates the XY stage info widget with the current position of the stage

        """
        #Obtain the stage info from MM:
        XYStageName = self.core.get_xy_stage_device() #type:ignore
        #Get the stage position
        XYStagePos = self.core.get_xy_stage_position(XYStageName) #type:ignore
        self.XYStageInfoWidget.setText(f"{XYStageName}\r\n {XYStagePos.x:.0f}/{XYStagePos.y:.0f}")
        
    def moveXYStage(self,relX,relY):
        """
        Move XY stage with um positions in relx, rely:
        """
        self.core.set_relative_xy_position(relX,relY) #type:ignore
        #Update the XYStageInfoWidget (if it exists)
        self.updateXYStageInfoWidget()
    #endregion
    
    #region MM-configs
    def addRow(self,config_id):
        """
        Add a new row in the configLayout which will be populated with a label-dropdown/slider/inputField combination
        """
        rowLayout = QHBoxLayout()
        #Add the label to it
        self.addLabel(rowLayout,config_id)
        #Add the widget to the QVBoxlayout
        self.configLayout.addLayout(rowLayout,divmod(config_id,self.number_columns)[1],divmod(config_id,self.number_columns)[0])
        
        return rowLayout
    
    def addLabel(self,rowLayout,config_id):
        """
        Add a label to the given rowLayout with the label text provided in the MM config.

        """
        if self.showCheckboxes:
            #Add a checkbox
            self.configCheckboxes[config_id] = QCheckBox()
            self.configCheckboxes[config_id].setChecked(False)
            #Add callback:
            self.configCheckboxes[config_id].stateChanged.connect(lambda _, self=self, config_id = config_id: self.configLayoutEnableChange(config_id))
            rowLayout.addWidget(self.configCheckboxes[config_id])
        #add a label to the row:
        label = QLabel()
        label.setText(self.config_groups[config_id].configGroupName())
        rowLayout.addWidget(label)
        #Add the dropdown/slider/inputfield:
        if self.config_groups[config_id].isDropDown():
            self.addDropDown(rowLayout,config_id)
        if self.config_groups[config_id].isSlider():
            self.addSlider(rowLayout,config_id)
        if self.config_groups[config_id].isInputField():
            self.addInputField(rowLayout,config_id)
        return rowLayout
        # pass
    
    def addDropDown(self,rowLayout,config_id):
        """
        Add a drop-down menu to the given rowLayout
        with the options provided in the MM config.

        """
        #Create a drop-down menu:
        self.dropDownBoxes[config_id] = QComboBox()
        #Add an empty option:
        self.dropDownBoxes[config_id].addItem('')
        #Populate with the options:
        for i in range(self.config_groups[config_id].nrConfigs()):
            self.dropDownBoxes[config_id].addItem(self.config_groups[config_id].configName(i))
        #Update the value to the current MM value:
        # self.updateValuefromMM(config_id)
        #Add a callback when it is changed:
        self.dropDownBoxes[config_id].currentIndexChanged.connect(lambda index, config_id = config_id: self.on_dropDownChanged(config_id))
        
        #Add dropdown to rowLayout:
        rowLayout.addWidget(self.dropDownBoxes[config_id])
    
    def on_dropDownChanged(self,config_id):
        """
        Changes a micromanager config when a dropdown has changed

        Args:
            config_id (int): The ID of the dropdown box that triggered the event.

        Returns:
            None
        """
        if self.showCheckboxes:
            #Check the corresponding checkbox
            self.configCheckboxes[config_id].setChecked(True)
        if self.changes_update_MM:
            #Get the new value from the dropdown:
            newValue = self.dropDownBoxes[config_id].currentText()
            #Change the value if it's a true value
            if newValue != "" and newValue != " ":
                #Get the config group name:
                configGroupName = self.config_groups[config_id].configGroupName()
                #Set in MM:
                self.config_groups[config_id].core.set_config(configGroupName,newValue)
    
    def addSlider(self,rowLayout,config_id):
        """
        Add a slider to a rowLayout for a given MMConfigItem.

        Args:
            rowLayout (QHBoxLayout): The rowLayout to add the slider to.
            config_id (int): The ID of the MMConfigItem to add a slider for.

        Returns:
            None
        """
        #Get the config group name
        configGroupName = self.config_groups[config_id].configGroupName()
        
        #Get the min and max value of the slider:
        lowerLimit = self.config_groups[config_id].lowerLimit()
        upperLimit = self.config_groups[config_id].upperLimit()
        
        #A slider config by definition (?) only has a single property underneath, so get that:
        underlyingProperty = self.config_groups[config_id].core.get_available_configs(configGroupName).get(0)
        configdata = self.config_groups[config_id].core.get_config_data(configGroupName,underlyingProperty)
        device_label = configdata.get_setting(0).get_device_label()
        property_name = configdata.get_setting(0).get_property_name()
        
        #Finally we get the current value of the slider
        currentSliderValue = float(self.config_groups[config_id].core.get_property(device_label,property_name))
        
        #Sliders only work in integers, so we need to set some artificial precision and translate to this precision
        sliderPrecision = self.sliderPrecision
        sliderValInSliderPrecision = int(((currentSliderValue-lowerLimit)/(upperLimit-lowerLimit))*sliderPrecision)
        # #Create the slider:
        self.sliders[config_id] = QSlider(Qt.Horizontal) #type: ignore
        self.sliders[config_id].setRange(0,sliderPrecision)
        self.sliders[config_id].setValue(sliderValInSliderPrecision)
        self.sliders[config_id].slider_conversion_array = [lowerLimit,upperLimit,sliderPrecision]
        #Add a callback when it is changed:
        self.sliders[config_id].valueChanged.connect(lambda value, config_id = config_id: self.on_sliderChanged(config_id))
        # #Add the slider to the rowLayout:
        rowLayout.addWidget(self.sliders[config_id])
        pass
    
    def on_sliderChanged(self,config_id):
        """
        Changes a micromanager config when a slider has changed

        Args:
            config_id (int): The ID of the slider box that triggered the event.
            slider_conversion_array (array): [lowerLimit,upperLimit,sliderPrecision]

        Returns:
            None
        """
        if self.showCheckboxes:
            #Check the corresponding checkbox:
            self.configCheckboxes[config_id].setChecked(True)
        if self.changes_update_MM:
            #Get the new value from the slider:
            newValue = self.sliders[config_id].value()
            #Get the true value from the conversion:
            trueValue = newValue/self.sliders[config_id].slider_conversion_array[2]*(self.sliders[config_id].slider_conversion_array[1]-self.sliders[config_id].slider_conversion_array[0])+self.sliders[config_id].slider_conversion_array[0]
            #Change the value if it's a true value
            if trueValue != "" and trueValue != " ":
                #Get the config group name:
                configGroupName = self.config_groups[config_id].configGroupName()
                #Set in MM:
                #A slider config by definition (?) only has a single property underneath, so get that:
                underlyingProperty = self.config_groups[config_id].core.get_available_configs(configGroupName).get(0)
                configdata = self.config_groups[config_id].core.get_config_data(configGroupName,underlyingProperty)
                device_label = configdata.get_setting(0).get_device_label()
                property_name = configdata.get_setting(0).get_property_name()

                #Set this property:
                self.config_groups[config_id].core.set_property(device_label,property_name,trueValue)
    
    def addInputField(self,rowLayout,config_id):
        """ 
        TODO
        """
        #TODO: implement
        pass
    
    def updateValuefromMM(self,config_id):
        """
        Updates the value in the GUI for a single config_id based on the current value in MM

        Args:
            config_id (int): The ID of the config_group to update

        Returns:
            None
        """
        logging.debug("Updating value from " + self.config_groups[config_id].configGroupName())
        #Get the value of the config_id from micromanager:
        currentValue = self.config_groups[config_id].getCurrentMMValue()
        
        #Set the value of the dropdown to the current MM value
        if self.config_groups[config_id].isDropDown():
            self.dropDownBoxes[config_id].setCurrentText(currentValue)
        elif self.config_groups[config_id].isSlider():
            #A slider config by definition (?) only has a single property underneath, so get that:
            configGroupName = self.config_groups[config_id].configGroupName()
            underlyingProperty = self.config_groups[config_id].core.get_available_configs(configGroupName).get(0)
            configdata = self.config_groups[config_id].core.get_config_data(configGroupName,underlyingProperty)
            device_label = configdata.get_setting(0).get_device_label()
            property_name = configdata.get_setting(0).get_property_name()
            
            #Finally we get the current value of the slider
            currentSliderValue = float(self.config_groups[config_id].core.get_property(device_label,property_name))
                
            #Sliders only work in integers, so we need to set some artificial precision and translate to this precision
            sliderPrecision = self.sliderPrecision
            #Get the min and max value of the slider:
            lowerLimit = self.config_groups[config_id].lowerLimit()
            upperLimit = self.config_groups[config_id].upperLimit()
            sliderValInSliderPrecision = int(((currentSliderValue-lowerLimit)/(upperLimit-lowerLimit))*sliderPrecision)
            # #Update the slider:
            self.sliders[config_id].setRange(0,sliderPrecision)
            self.sliders[config_id].setValue(sliderValInSliderPrecision)
            
        elif self.config_groups[config_id].isInputField():
            pass
        
        #Make inactive if the checkbox is inactive
        self.configLayoutEnableChange(config_id)
        pass
    
    def updateValueInGUI(self,config_id, newValue):
        """
        I THINK DEPRECATED, BUT KEEPING FOR KEEPING SAKE
        Updates the GUI to reflect a change in the Micromanager config
        Set the value of the dropdown to the current MM value

        Args:
            config_id (int): The ID of the config box to change
            newValue (str): The new value of the config property

        Returns:
            None
        """
        if self.config_groups[config_id].isDropDown():
            self.dropDownBoxes[config_id].setCurrentText(newValue)
        elif self.config_groups[config_id].isSlider():
            #Finally we get the current value of the slider
            currentSliderValue = float(newValue)
                
            #Sliders only work in integers, so we need to set some artificial precision and translate to this precision
            sliderPrecision = self.sliderPrecision
            #Get the min and max value of the slider:
            lowerLimit = self.config_groups[config_id].lowerLimit()
            upperLimit = self.config_groups[config_id].upperLimit()
            sliderValInSliderPrecision = int(((currentSliderValue-lowerLimit)/(upperLimit-lowerLimit))*sliderPrecision)
            
            self.sliders[config_id].setValue(sliderValInSliderPrecision)
            
        elif self.config_groups[config_id].isInputField():
            pass
    
    def configLayoutEnableChange(self,config_id):
        """
        Enables or disables the GUI elements in the layout of the given config box

        Args:
            config_id (int): The ID of the config box to change
        """
        if self.showCheckboxes:
            #Disable all children recursively
            def enableDisableLayout(self, layout,config_id,trueFalse):
                """
                Enables or disables widgets in a layout based on the provided configuration ID.
                
                Args:
                    layout: The layout containing the widgets to be enabled or disabled.
                    config_id: The configuration ID used to identify the checkbox that should not be disabled.
                    trueFalse: A boolean value indicating whether the widgets should be enabled (True) or disabled (False).
                
                Returns:
                    None
                """
                for i in range(layout.count()):
                    item = layout.itemAt(i)

                    if item.widget():
                        #Don't disable if it's the checkbox itself
                        if not item.widget() == self.configCheckboxes[config_id]:
                            item.widget().setEnabled(trueFalse)
                    elif item.layout():
                        self.disableLayout(item.layout())
                        
            if self.configCheckboxes[config_id].isChecked():
                enableDisableLayout(self, self.configEntries[config_id],config_id,True)
            else:
                enableDisableLayout(self, self.configEntries[config_id],config_id,False)
        return
    
    def updateConfigsFromMM(self):
        """
        Updates all configs from the Micro-Manager backend.
        
        This function iterates over all configs and updates their values in the GUI
        based on the current values in the Micro-Manager backend.
        """
        #Update all values from MM:
        for config_id in range(len(self.config_groups)):
            self.updateValuefromMM(config_id)
        pass
    #endregion

    #region deprecated
    def get_device_properties(self):
        """
        Get device properties.
        
        Args:
            self: The object itself.
            
        Returns:
            List: A list of dictionaries containing device properties.
        """
        
        core = self.core
        devices = core.get_loaded_devices() #type:ignore
        devices = [devices.get(i) for i in range(devices.size())]
        device_items = []
        for device in devices:
            logging.debug('Device: '+device)
            names = core.get_device_property_names(device) #type:ignore
            props = [names.get(i) for i in range(names.size())]
            property_items = []
            for prop in props:
                logging.debug('Property',prop)
                value = core.get_property(device, prop) #type:ignore
                is_read_only = core.is_property_read_only(device, prop) #type:ignore
                if core.has_property_limits(device, prop): #type:ignore
                    lower = core.get_property_lower_limit(device, prop) #type:ignore
                    upper = core.get_property_upper_limit(device, prop) #type:ignore
                    allowed = {
                    "type": "range",
                    "min": lower,
                    "max": upper,
                    "readOnly": is_read_only,
                    }
                else:
                    allowed = core.get_allowed_property_values(device, prop) #type:ignore
                    allowed = {
                    "type": "enum",
                    "options": [allowed.get(i) for i in range(allowed.size())],"readOnly": is_read_only,
                    }
                    property_items.append(
                    {"device": device, "name": prop, "value": value, "allowed": allowed}
                    )
                    logging.debug('===>', device, prop, value, allowed)
            if len(property_items) > 0:
                device_items.append(
                {
                "name": device,
                "value": "{} properties".format(len(props)),
                "items": property_items,
                }
                )
        return device_items

    def Vseparator_line(self):
        """
        Creates a vertical separator line widget.
        
        Args:
            None
        
        Returns:
            QFrame: A vertical separator line widget with frame shape set to QFrame.VLine, frame shadow set to QFrame.Sunken, and background color set to #FFFFFF with a minimum width of 1px.
        """
        
        separator_line = QFrame()
        separator_line.setFrameShape(QFrame.VLine)
        separator_line.setFrameShadow(QFrame.Sunken)
        separator_line.setStyleSheet("background-color: #FFFFFF; min-width: 1px;")
        return separator_line
    #endregion
    
def microManagerControlsUI(core,MM_JSON,main_layout,sshared_data):
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
    global shared_data
    shared_data = sshared_data
    # Get all config groups
    allConfigGroups={}
    nrconfiggroups = core.get_available_config_groups().size()
    for config_group_id in range(nrconfiggroups):
        allConfigGroups[config_group_id] = ConfigInfo(core,config_group_id)
    
    #Create the MM config via all config groups
    MMconfig = MMConfigUI(allConfigGroups,autoSaveLoad=True)
    main_layout.addLayout(MMconfig.mainLayout,0,0)
    
    return MMconfig
    
    #Test line:
    # breakpoint
