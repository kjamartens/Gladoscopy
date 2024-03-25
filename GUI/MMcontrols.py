from PyQt5.QtWidgets import QLayout, QLineEdit, QFrame, QGridLayout, QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QLabel, QComboBox, QSpacerItem, QSizePolicy, QSlider, QCheckBox, QGroupBox, QVBoxLayout, QFileDialog, QRadioButton
from PyQt5.QtCore import Qt, pyqtSignal, QObject, QThread, QCoreApplication
from PyQt5.QtGui import QResizeEvent, QIcon, QPixmap, QFont, QDoubleValidator, QIntValidator
from PyQt5 import uic
from AnalysisClass import *
import sys
import os
# import PyQt5.QtWidgets
import json
from pycromanager import Core, multi_d_acquisition_events, Acquisition
import numpy as np
import time
import asyncio
import pyqtgraph as pg
import matplotlib.pyplot as plt
from matplotlib import colormaps # type: ignore
#For drawing
import matplotlib
matplotlib.use('Qt5Agg')
# from PyQt5 import QtCore, QtWidgets
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


class ConfigInfo:
    def __init__(self,core,config_group_id):
        self.core = core
        self.config_group_id = config_group_id
        pass
    
    #Returns the config group name
    def configGroupName(self):
        return self.core.get_available_config_groups().get(self.config_group_id)
    
    #Returns the number of config options for this config group
    def nrConfigs(self):
        return self.core.get_available_configs(self.core.get_available_config_groups().get(self.config_group_id)).size()
    
    #Returns the name of the config within the config group
    def configName(self,config_id):
        return self.core.get_available_configs(self.core.get_available_config_groups().get(self.config_group_id)).get(config_id)
    
    #Returns the first device name and property from Verbose
    def deviceNameProperty_fromVerbose(self):
        verboseInfoCurrentConfigGroup = self.core.get_config_group_state(self.configGroupName()).get_verbose()
        start_index = verboseInfoCurrentConfigGroup.find("<html>") + len("<html>")
        end_index = verboseInfoCurrentConfigGroup.find(":")
        deviceName = verboseInfoCurrentConfigGroup[start_index:end_index]
        start_index = end_index + len(":")
        end_index = verboseInfoCurrentConfigGroup.find("=")
        deviceProperty  = verboseInfoCurrentConfigGroup[start_index:end_index]
        return deviceName,deviceProperty
    
    #Returns whether the config group has property limits
    def hasPropertyLimits(self):
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
    
    #Finds lower limit of the device property
    def lowerLimit(self):
        [deviceName,deviceProperty] = self.deviceNameProperty_fromVerbose()
        if self.core.has_property_limits(deviceName,deviceProperty):
            lowerLimit = self.core.get_property_lower_limit(deviceName,deviceProperty)
        else:
            lowerLimit = 0
        return lowerLimit
            
    #Finds upper limit of the device property
    def upperLimit(self):
        [deviceName,deviceProperty] = self.deviceNameProperty_fromVerbose()
        if self.core.has_property_limits(deviceName,deviceProperty):
            upperLimit = self.core.get_property_upper_limit(deviceName,deviceProperty)
        else:
            upperLimit = 0
        return upperLimit
            
    #Returns Boolean whether the config group should be represented as a drop-down menu
    def isDropDown(self):
        if self.nrConfigs()>1:
            return True
        else:
            return False
        
    #Returns Boolean whether the config group should be represented as a slider
    def isSlider(self):
        if self.nrConfigs()>1:
            return False
        else:
            if self.hasPropertyLimits():
                return True
            else:
                return False
        
    #Returns Boolean whether the config group should be represented as an input field
    def isInputField(self):
        if self.nrConfigs()>1:
            return False
        else:
            if self.hasPropertyLimits():
                return False
            else:
                return True

    def helpStringInfo(self):
        infostring='No option for this config'
        if self.isDropDown():
            infostring = "Device {} should be an dropdown with {} options".format(self.configGroupName(),self.nrConfigs())
        if self.isSlider():
            infostring = "Device {} should be an Slider with limits {}-{}".format(self.configGroupName(),self.lowerLimit(),self.upperLimit())
        if self.isInputField():
            infostring = "Device {} should be an input field".format(self.configGroupName())
        return infostring
    
    #Get the current MM value of this config group:
    def getCurrentMMValue(self):
        return self.core.get_current_config(self.configGroupName())

#Create a big MM config ui and add all config groups with options
class MMConfigUI:
    def __init__(self, config_groups,showConfigs = True,showStages=True,showROIoptions=True,showLiveMode=True,number_config_columns=5,changes_update_MM = True,showCheckboxes = False):
        """
        Initializes the class with the given configuration groups.

        Parameters:
            config_groups (list): A list of configuration groups.
            showConfigs (bool): Whether to show the configurations in the UI.
            showStages (bool): Whether to show the stages in the UI.
            showROIoptions (bool): Whether to show the ROI options in the UI.
            showLiveMode (bool): Whether to show the live mode in the UI.
            number_config_columns (int): The number of columns for the configuration.
            changes_update_MM (bool): Whether to update the MM changes when configs are changed.

        Returns:
            None
        """
        self.showConfigs = showConfigs
        self.showStages = showStages
        self.showROIoptions = showROIoptions
        self.showLiveMode = showLiveMode
        self.showCheckboxes = showCheckboxes
        self.config_groups = config_groups
        self.number_columns = number_config_columns
        self.changes_update_MM = changes_update_MM
        self.core = self.config_groups[0].core
        self.dropDownBoxes = {}
        self.sliders = {}
        self.configCheckboxes = {}
        self.sliderPrecision = 100
        #Create a Vertical+horizontal layout:
        self.mainLayout = QGridLayout()
        if showConfigs:
            #Create a layout for the configs:
            self.configGroupBox = QGroupBox("Configurations")
            self.configLayout = QGridLayout()
            #Add this to the mainLayout via the groupbox:
            self.configGroupBox.setLayout(self.configLayout)
            self.mainLayout.addWidget(self.configGroupBox,0,0)
            #Fill the configLayout
            for config_id in range(len(config_groups)):
                self.addRow(config_id)
            pass
        
            #Add a button to refresh from MM:
            self.refreshButton = QPushButton("Refresh configs from MM")
            totalRowsAdded = int(np.ceil(len(config_groups)/self.number_columns))
            #Add a button spanning the total columns at the bottom
            self.configLayout.addWidget(self.refreshButton,totalRowsAdded+1,0,1,self.number_columns)
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
        
        #Update everything for good measure at the end of init
        self.updateAllMMinfo()
        
        #Change the font of everything in the layout
        self.set_font_and_margins_recursive(self.mainLayout, font=QFont("Arial", 7))
    
    #Get all config information as set by the UI:
    def getUIConfigInfo(self,onlyChecked=False):
        configInfo = {}
        for config_id in range(len(self.config_groups)):
            if onlyChecked and not self.configCheckboxes[config_id].isChecked():
                continue
            configInfo[self.config_groups[config_id].configGroupName()] = self.currentConfigUISingleValue(config_id)
        return configInfo
    
    def currentConfigUISingleValue(self,config_id):
        #Get the value of a single config as currently determined by the UI
        if self.config_groups[config_id].isDropDown():
            currentUIvalue = self.dropDownBoxes[config_id].currentText()
        elif self.config_groups[config_id].isSlider():
            #Get the value from the slider:
            sliderValue = self.sliders[config_id].value()
            #Get the true value from the conversion:
            currentUIvalue = sliderValue/self.sliders[config_id].slider_conversion_array[2]*(self.sliders[config_id].slider_conversion_array[1]-self.sliders[config_id].slider_conversion_array[0])+self.sliders[config_id].slider_conversion_array[0]
        elif self.config_groups[config_id].isInputField():
            currentUIvalue = None
        else:
            currentUIvalue = None
        return currentUIvalue
    
    #Live mode UI
    def liveModeLayout(self):
        #Create a Grid layout:
        liveModeLayout = QGridLayout()
        self.LiveModeButton = QPushButton("Start/Stop Live Mode")
        #add a connection to the button:
        self.LiveModeButton.clicked.connect(lambda index: self.changeLiveMode())
        #Add the button to the layout:
        liveModeLayout.addWidget(self.LiveModeButton,0,0)
        #Return the layout
        return liveModeLayout
    
    #Changes live mode
    def changeLiveMode(self):
        if shared_data.liveMode == False:
            shared_data.liveMode = True
        else:
            shared_data.liveMode = False
                
    #Set the font of all buttons/labels in the layout recursively
    def set_font_and_margins_recursive(self,widget, font=QFont("Arial", 8)):
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
    
    #Unused, but helpfull piece of code
    def get_device_properties(self):
        core = self.core
        devices = core.get_loaded_devices()
        devices = [devices.get(i) for i in range(devices.size())]
        device_items = []
        for device in devices:
            logging.debug('Device: '+device)
            names = core.get_device_property_names(device)
            props = [names.get(i) for i in range(names.size())]
            property_items = []
            for prop in props:
                logging.debug('Property',prop)
                value = core.get_property(device, prop)
                is_read_only = core.is_property_read_only(device, prop)
                if core.has_property_limits(device, prop):
                    lower = core.get_property_lower_limit(device, prop)
                    upper = core.get_property_upper_limit(device, prop)
                    allowed = {
                    "type": "range",
                    "min": lower,
                    "max": upper,
                    "readOnly": is_read_only,
                    }
                else:
                    allowed = core.get_allowed_property_values(device, prop)
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
        separator_line = QFrame()
        separator_line.setFrameShape(QFrame.VLine)
        separator_line.setFrameShadow(QFrame.Sunken)
        separator_line.setStyleSheet("background-color: #FFFFFF; min-width: 1px;")
        return separator_line
    
    def ROIoptionsLayout(self):
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
    
    #Reset the ROI to full frame
    def resetROI(self):
        self.core.clear_roi()
    
    def zoomROI(self,option):
        #Get the current ROI info
        #[x,y,width,height]
        roiv = [self.core.get_roi().x,self.core.get_roi().y,self.core.get_roi().width,self.core.get_roi().height]
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
        #ROIpos should be a list of [x,y,width,height]
        logging.debug('Zooming ROI to ' + str(ROIpos))
        try:
            if shared_data.liveMode == False:
                self.core.set_roi(ROIpos[0],ROIpos[1],ROIpos[2],ROIpos[3])
                self.core.wait_for_system()
            else:
                shared_data.liveMode = False
                self.core.set_roi(ROIpos[0],ROIpos[1],ROIpos[2],ROIpos[3])
                time.sleep(0.5)
                shared_data.liveMode = True
        except:
            logging.error('ZOOMING DIDN\'T WORK!')
    
    def stagesLayout(self):
        stageLayout = QHBoxLayout()
        stageLayout.addLayout(self.XYstageLayout())
        stageLayout.addLayout(self.oneDstageLayout())
        return stageLayout
    
    def XYstageLayout(self):
        #Obtain the stage info from MM:
        XYStageName = self.core.get_xy_stage_device()
        #Get the stage position
        XYStagePos = self.core.get_xy_stage_position(XYStageName)
        
        #Get current pixel size via self.core.get_pixel_size_um()
        #Then move 0.1, 0.5, or 1 field with the arrows
        field_size_um = [self.core.get_pixel_size_um()*self.core.get_roi().width,self.core.get_pixel_size_um()*self.core.get_roi().height]
        field_move_fraction = [1,.5,.1]
        
        #Widget itself is a grid layout with 7x7 entries
        XYStageLayout = QGridLayout()
        XYStageLayout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        
        #XY move buttons
        self.XYmoveButtons = {}
        for m in range(1,4):
            #Initialize buttons
            self.XYmoveButtons[f'Up_{m}'] = QPushButton("⮝"*(4-m))
            self.XYmoveButtons[f'Up_{m}'].clicked.connect(lambda index, m=m: self.moveXYStage(0,field_size_um[1]*field_move_fraction[m-1]))
            self.XYmoveButtons[f'Down_{m}'] = QPushButton("⮟"*(4-m))
            self.XYmoveButtons[f'Down_{m}'].clicked.connect(lambda index, m=m: self.moveXYStage(0,-field_size_um[1]*field_move_fraction[m-1]))
            self.XYmoveButtons[f'Left_{m}'] = QPushButton("⮜"*(4-m))
            self.XYmoveButtons[f'Left_{m}'].clicked.connect(lambda index, m=m: self.moveXYStage(-field_size_um[0]*field_move_fraction[m-1],0))
            self.XYmoveButtons[f'Right_{m}'] = QPushButton("⮞"*(4-m))
            self.XYmoveButtons[f'Right_{m}'].clicked.connect(lambda index, m=m: self.moveXYStage(field_size_um[0]*field_move_fraction[m-1],0))
            
            #Add buttons to layout
            XYStageLayout.addWidget(self.XYmoveButtons[f'Up_{m}'],m-1,4,1,1, alignment=Qt.AlignmentFlag.AlignCenter)
            XYStageLayout.addWidget(self.XYmoveButtons[f'Down_{m}'],8-m,4,1,1, alignment=Qt.AlignmentFlag.AlignCenter)
            XYStageLayout.addWidget(self.XYmoveButtons[f'Left_{m}'],4,m-1,1,1, alignment=Qt.AlignmentFlag.AlignCenter)
            XYStageLayout.addWidget(self.XYmoveButtons[f'Right_{m}'],4,8-m,1,1, alignment=Qt.AlignmentFlag.AlignCenter)
                        
        #Add a central label for info
        #this label contains the XY stage name, then an enter, then the current position:
        self.XYStageInfoWidget = QLabel()
        XYStageLayout.addWidget(self.XYStageInfoWidget,4,4)
        #Update the text of it
        self.updateXYStageInfoWidget()
        
        return XYStageLayout
    
    def getDevicesOfDeviceType(self,devicetype):
        #Find all devices that have a specific devicetype
        #Look at https://javadoc.scijava.org/Micro-Manager-Core/mmcorej/DeviceType.html 
        #for all devicetypes
        #Get devices
        devices = self.core.get_loaded_devices()
        devices = [devices.get(i) for i in range(devices.size())]
        devicesOfType = []
        #Loop over devices
        for device in devices:
            if self.core.get_device_type(device).to_string() == devicetype:
                logging.debug("found " + device + " of type " + devicetype)
                devicesOfType.append(device)
        return devicesOfType
    
    def oneDstageLayout(self):
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
        
        #Get current info of the widget
        self.oneDinfoWidget = QLabel()
        self.oneDStageLayout.addWidget(self.oneDinfoWidget,1,0)
        #update the text
        self.updateOneDstageLayout()
        
        return self.oneDStageLayout
    
    def updateOneDstageLayout(self):
        self.oneDinfoWidget.setText(f"{self.oneDstageDropdown.currentText()}\r\n {self.core.get_position(self.oneDstageDropdown.currentText()):.1f}")
    
    def moveOneDStage(self,amount):
        #Get the currently selected one-D stage:
        selectedStage = self.oneDstageDropdown.currentText()
        
        self.moveoneDstagesmallAmount = 10
        self.moveoneDstagelargeAmount = 100
        
        logging.debug("moving " + selectedStage + " by " + str(amount))
        
        #Move the stage relatively
        if abs(amount) == 2:
            self.core.set_relative_position(selectedStage,(np.sign(amount)*self.moveoneDstagesmallAmount).astype(float))
        elif abs(amount) == 1:
            self.core.set_relative_position(selectedStage,(np.sign(amount)*self.moveoneDstagelargeAmount).astype(float))
        self.updateOneDstageLayout()
        
    def updateXYStageInfoWidget(self):#Obtain the stage info from MM:
        XYStageName = self.core.get_xy_stage_device()
        #Get the stage position
        XYStagePos = self.core.get_xy_stage_position(XYStageName)
        self.XYStageInfoWidget.setText(f"{XYStageName}\r\n {XYStagePos.x:.0f}/{XYStagePos.y:.0f}")
        
    def moveXYStage(self,relX,relY):
        #Move XY stage with um positions in relx, rely:
        self.core.set_relative_xy_position(relX,relY)
        #Update the XYStageInfoWidget (if it exists)
        self.updateXYStageInfoWidget()
    
    def addRow(self,config_id):
        #Add a new row in the configLayout which will be populated with a label-dropdown/slider/inputField combination
        rowLayout = QHBoxLayout()
        #Add the label to it
        self.addLabel(rowLayout,config_id)
        #Add the widget to the QVBoxlayout
        self.configLayout.addLayout(rowLayout,divmod(config_id,self.number_columns)[1],divmod(config_id,self.number_columns)[0])
    
    def addLabel(self,rowLayout,config_id):
        if self.showCheckboxes:
            #Add a checkbox
            self.configCheckboxes[config_id] = QCheckBox()
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
        #Create a drop-down menu:
        self.dropDownBoxes[config_id] = QComboBox()
        #Add an empty option:
        self.dropDownBoxes[config_id].addItem('')
        #Populate with the options:
        for i in range(self.config_groups[config_id].nrConfigs()):
            self.dropDownBoxes[config_id].addItem(self.config_groups[config_id].configName(i))
        #Update the value to the current MM value:
        self.updateValuefromMM(config_id)
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
        pass
    
    #Update a single config based on current value in MM
    def updateValuefromMM(self,config_id):
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
        pass
    
    #Update all configs based on current value in MM
    def updateConfigsFromMM(self):
        #Update all values from MM:
        for config_id in range(len(self.config_groups)):
            self.updateValuefromMM(config_id)
        pass
    
    #Update everything there is update-able
    def updateAllMMinfo(self):
        logging.debug('Updating all MM info')
        if self.showConfigs:
            self.updateConfigsFromMM()
        if self.showStages:
            self.updateXYStageInfoWidget()
            self.updateOneDstageLayout()

class MDAGlados():
    def __init__(self,core,MM_JSON,layout,shared_data,hasGUI=False,num_time_points: int | None = 10, time_interval_s: float | List[float] = 0, z_start: float | None = None, z_end: float | None = None, z_step: float | None = None, channel_group: str | None = None, channels: list | None = None, channel_exposures_ms: list | None = None, xy_positions: Iterable | None = None, xyz_positions: Iterable | None = None, position_labels: List[str] | None = None, order: str = 'tpcz', exposure_ms: float | None = 90, GUI_show_exposure = True, GUI_show_xy = False, GUI_show_z=True, GUI_show_channel=False, GUI_show_time=True, GUI_show_order=True, GUI_show_storage=True, GUI_acquire_button=True):
        self.num_time_points = num_time_points
        self.time_interval_s = time_interval_s
        self.z_start = z_start
        self.z_end = z_end
        self.z_step = z_step
        self.channel_group = channel_group
        self.channels = channels
        self.channel_exposures_ms = channel_exposures_ms
        self.xy_positions = xy_positions
        self.xyz_positions = xyz_positions
        self.position_labels = position_labels
        self.order = order
        self.exposure_ms = exposure_ms
        self.storageFolder = None
        self.storageFileName = None
        self.GUI_show_exposure = GUI_show_exposure
        self.GUI_show_xy = GUI_show_xy
        self.GUI_show_z = GUI_show_z
        self.GUI_show_channel = GUI_show_channel
        self.GUI_show_time = GUI_show_time
        self.GUI_show_order = GUI_show_order
        self.GUI_show_storage = GUI_show_storage
        self.GUI_acquire_button = GUI_acquire_button
        self.core = core
        self.mda_analysis_thread = None
        self.MM_JSON = MM_JSON
        self.layout = layout
        self.shared_data = shared_data
        self.gui = {}
        
        #initiate with an empty mda:
        self.mda = multi_d_acquisition_events(num_time_points=self.num_time_points, time_interval_s=self.time_interval_s,z_start=self.z_start,z_end=self.z_end,z_step=self.z_step,channel_group=self.channel_group,channels=self.channels,channel_exposures_ms=self.channel_exposures_ms,xy_positions=self.xy_positions,xyz_positions=self.xyz_positions,position_labels=self.position_labels,order=self.order) #type:ignore
        
        #Initiate GUI if wanted
        if hasGUI:
            self.initGUI(GUI_show_exposure=self.GUI_show_exposure,GUI_show_xy=self.GUI_show_xy, GUI_show_z=self.GUI_show_z, GUI_show_channel=self.GUI_show_channel, GUI_show_time=self.GUI_show_time, GUI_show_order=self.GUI_show_order, GUI_show_storage=self.GUI_show_storage, GUI_acquire_button=self.GUI_acquire_button)
    
    def getDevicesOfDeviceType(self,devicetype):
        #Find all devices that have a specific devicetype
        #Look at https://javadoc.scijava.org/Micro-Manager-Core/mmcorej/DeviceType.html 
        #for all devicetypes
        #Get devices
        devices = self.core.get_loaded_devices()
        devices = [devices.get(i) for i in range(devices.size())]
        devicesOfType = []
        #Loop over devices
        for device in devices:
            if self.core.get_device_type(device).to_string() == devicetype:
                logging.debug("found " + device + " of type " + devicetype)
                devicesOfType.append(device)
        return devicesOfType
    
    def initGUI(self, GUI_show_exposure=True, GUI_show_xy = False, GUI_show_z=True, GUI_show_channel=False, GUI_show_time=True, GUI_show_order=True, GUI_show_storage=True, GUI_showOptions=True,GUI_acquire_button=True):
        #initiate the GUI
        #Create a Vertical+horizontal layout:
        self.gui = QGridLayout()
        self.GUI_grid_width = 4
    
        # Add groupboxes for xy, z, channel, time, order, storage
        self.exposureGroupBox = QGroupBox("Exposure")
        self.xyGroupBox = QGroupBox("XY")
        self.zGroupBox = QGroupBox("Z")
        self.channelGroupBox = QGroupBox("Channel")
        self.timeGroupBox = QGroupBox("Time")
        self.orderGroupBox = QGroupBox("Order")
        self.storageGroupBox = QGroupBox("Storage")
        self.showOptionsGroupBox = QGroupBox("Options")

        # Create layouts for each groupbox
        exposureLayout=QHBoxLayout()
        xyLayout = QVBoxLayout()
        zLayout = QGridLayout()
        channelLayout = QVBoxLayout()
        timeLayout = QGridLayout()
        orderLayout = QVBoxLayout()
        storageLayout = QGridLayout()
        showOptionsLayout = QHBoxLayout()

        # Add widgets to each layout
        #--------------- Exposure widget -----------------------------------------------
        #Exposure: add a label, an entry field, and a dropdown between 'ms' and 's':
        self.exposureLabel = QLabel("Exposure:")
        self.exposureEntry = QLineEdit()
        self.exposureEntry.setText(str(self.exposure_ms))
        #ensure thatexposureEntry can only be a float:
        self.exposureEntry.setValidator(QDoubleValidator())
        self.exposureDropdown = QComboBox()
        self.exposureDropdown.addItem("ms")
        self.exposureDropdown.addItem("s")
        exposureLayout.addWidget(self.exposureLabel)
        exposureLayout.addWidget(self.exposureEntry)
        exposureLayout.addWidget(self.exposureDropdown)
        #run get_MDA_events_from_GUI when the text or dropdown is changed:
        self.exposureEntry.textChanged.connect(lambda: self.get_MDA_events_from_GUI())
        self.exposureDropdown.currentIndexChanged.connect(lambda: self.get_MDA_events_from_GUI())
        
        #--------------- Time widget -----------------------------------------------
        #Time: add labels for time points and time intervals, and integer-based entry fields:
        self.timePointLabel = QLabel("Number time points:")
        self.timePointEntry = QLineEdit()
        self.timePointEntry.setValidator(QIntValidator())
        timeLayout.addWidget(self.timePointLabel,0,0)
        timeLayout.addWidget(self.timePointEntry,0,1)
        self.timeIntervalLabel = QLabel("Time interval:")
        self.timeIntervalEntry = QLineEdit()
        self.timeIntervalEntry.setValidator(QDoubleValidator())
        self.timeIntervalDropdown = QComboBox()
        self.timeIntervalDropdown.addItem("ms")
        self.timeIntervalDropdown.addItem("s")
        timeLayout.addWidget(self.timeIntervalLabel,1,0)
        timeLayout.addWidget(self.timeIntervalEntry,1,1)
        timeLayout.addWidget(self.timeIntervalDropdown,1,2)
        #run get_MDA_events_from_GUI when the text or dropdown is changed:
        self.timePointEntry.textChanged.connect(lambda: self.get_MDA_events_from_GUI())
        self.timeIntervalEntry.textChanged.connect(lambda: self.get_MDA_events_from_GUI())
        self.timeIntervalDropdown.currentIndexChanged.connect(lambda: self.get_MDA_events_from_GUI())
        
        #--------------- storage widget -----------------------------------------------
        #storage: first, add a label, entry field, and button with '...' to select a folder of choice:
        self.storageFolderLabel = QLabel("Storage:")
        self.storageFolderEntry = QLineEdit()
        storageLayout.addWidget(self.storageFolderLabel,0,0)
        storageLayout.addWidget(self.storageFolderEntry,0,1)
        self.storageFolderButton = QPushButton('...')
        #add a lambda function when this is pressed to search for a folder:
        self.storageFolderButton.clicked.connect(lambda: self.storageFolderEntry.setText(QFileDialog.getExistingDirectory()))
        storageLayout.addWidget(self.storageFolderButton,0,2)
        #Then add a label and entry field for the file name:
        self.storageFileNameLabel = QLabel("File name:")
        self.storageFileNameEntry = QLineEdit()
        storageLayout.addWidget(self.storageFileNameLabel,1,0)
        storageLayout.addWidget(self.storageFileNameEntry,1,1)
        self.storageFolderEntry.textChanged.connect(lambda: self.get_MDA_events_from_GUI())
        self.storageFileNameEntry.textChanged.connect(lambda: self.get_MDA_events_from_GUI())
        
        
        #--------------- Z widget widget -----------------------------------------------
        #First a dropdown to select the 1d stage:
        self.z_oneDstageDropdownLabel = QLabel("Z Stage:")
        self.z_oneDstageDropdown = QComboBox()
        oneDstages = self.getDevicesOfDeviceType('StageDevice')
        #add the options to the dropdown:
        for stage in oneDstages:
            self.z_oneDstageDropdown.addItem(stage)
        zLayout.addWidget(self.z_oneDstageDropdownLabel,0,0)
        zLayout.addWidget(self.z_oneDstageDropdown,0,1)
        
        self.z_startLabel = QLabel("Start:")
        self.z_startEntry = QLineEdit()
        self.z_startEntry.setValidator(QDoubleValidator())
        self.z_startSetButton = QPushButton('Set')
        self.z_startSetButton.clicked.connect(lambda: self.setZStart())
        self.z_endLabel = QLabel("End:")
        self.z_endEntry = QLineEdit()
        self.z_endEntry.setValidator(QDoubleValidator())
        self.z_endSetButton = QPushButton('Set')
        self.z_endSetButton.clicked.connect(lambda: self.setZEnd())
        
        zLayout.addWidget(self.z_startLabel,1,0)
        zLayout.addWidget(self.z_startEntry,1,1)
        zLayout.addWidget(self.z_startSetButton,1,2)
        zLayout.addWidget(self.z_endLabel,2,0)
        zLayout.addWidget(self.z_endEntry,2,1)
        zLayout.addWidget(self.z_endSetButton,2,2)
        
        #add radio buttons:
        self.z_nrsteps_radio= QRadioButton("Number of steps: ")
        self.z_stepdistance_radio= QRadioButton("Step distance: ")
        #preselect the nr of steps one:
        self.z_nrsteps_radio.setChecked(True)
        #add edit boxes for number of steps and step distance:
        self.z_nrsteps_entry = QLineEdit()
        self.z_nrsteps_entry.setValidator(QIntValidator())
        self.z_stepdistance_entry = QLineEdit()
        self.z_stepdistance_entry.setValidator(QDoubleValidator())
        
        zLayout.addWidget(self.z_nrsteps_radio,3,0)
        zLayout.addWidget(self.z_nrsteps_entry,3,1)
        zLayout.addWidget(self.z_stepdistance_radio,4,0)
        zLayout.addWidget(self.z_stepdistance_entry,4,1)
        
        #run get_MDA_events_from_GUI when the text or dropdown is changed:
        self.z_oneDstageDropdown.currentIndexChanged.connect(lambda: self.get_MDA_events_from_GUI())
        self.z_startEntry.textChanged.connect(lambda: self.get_MDA_events_from_GUI())
        self.z_endEntry.textChanged.connect(lambda: self.get_MDA_events_from_GUI())
        self.z_nrsteps_radio.toggled.connect(lambda: self.get_MDA_events_from_GUI())
        self.z_stepdistance_radio.toggled.connect(lambda: self.get_MDA_events_from_GUI())
        self.z_nrsteps_entry.textChanged.connect(lambda: self.get_MDA_events_from_GUI())
        self.z_stepdistance_entry.textChanged.connect(lambda: self.get_MDA_events_from_GUI())
        
        
        #--------------- XY widget widget -----------------------------------------------
        #First a dropdown to select the 1d stage:
        self.xy_oneDstageDropdownLabel = QLabel("XY Stage:")
        self.xy_oneDstageDropdown = QComboBox()
        oneDstages = self.getDevicesOfDeviceType('StageDevice')
        
        
        #--------------- Order widget -----------------------------------------------
        #order should be a dropdown that has all possible options of c,t,p,z (channel, time, position, z), but only if these are actually turned on in the settings:
        orderLayout = self.createOrderLayout(GUI_show_channel, GUI_show_time, GUI_show_xy, GUI_show_z)
        
        #--------------- Show options widget -----------------------------------------------
        #This should have checkboxes for exposure, xy, z, channel, time, order, storage. If these checkboxes are clicked, the GUI should be updated accordingly:
        self.GUI_show_exposure_chkbox = QCheckBox("Exposure")
        self.GUI_show_xy_chkbox = QCheckBox("XY")
        self.GUI_show_z_chkbox = QCheckBox("Z")
        self.GUI_show_channel_chkbox = QCheckBox("Channel")
        self.GUI_show_time_chkbox = QCheckBox("Time")
        self.GUI_show_order_chkbox = QCheckBox("Order")
        self.GUI_show_storage_chkbox = QCheckBox("Storage")
        #initialise the checkboxes based on the values in this GUI:
        self.GUI_show_exposure_chkbox.setChecked(GUI_show_exposure)
        self.GUI_show_xy_chkbox.setChecked(GUI_show_xy)
        self.GUI_show_z_chkbox.setChecked(GUI_show_z)
        self.GUI_show_channel_chkbox.setChecked(GUI_show_channel)
        self.GUI_show_time_chkbox.setChecked(GUI_show_time)
        self.GUI_show_order_chkbox.setChecked(GUI_show_order)
        self.GUI_show_storage_chkbox.setChecked(GUI_show_storage)
        #Add lambda functions to all of them that all run the same function: showOptionChanged():
        self.GUI_show_exposure_chkbox.stateChanged.connect(lambda: self.showOptionChanged())
        self.GUI_show_xy_chkbox.stateChanged.connect(lambda: self.showOptionChanged())
        self.GUI_show_z_chkbox.stateChanged.connect(lambda: self.showOptionChanged())
        self.GUI_show_channel_chkbox.stateChanged.connect(lambda: self.showOptionChanged())
        self.GUI_show_time_chkbox.stateChanged.connect(lambda: self.showOptionChanged())
        self.GUI_show_order_chkbox.stateChanged.connect(lambda: self.showOptionChanged())
        self.GUI_show_storage_chkbox.stateChanged.connect(lambda: self.showOptionChanged())
        
        
        font = QFont()
        font.setPointSize(7)  # Set the desired font size

        [checkbox.setFont(font) for checkbox in [self.GUI_show_exposure_chkbox, self.GUI_show_xy_chkbox, self.GUI_show_z_chkbox, self.GUI_show_channel_chkbox, self.GUI_show_time_chkbox, self.GUI_show_order_chkbox, self.GUI_show_storage_chkbox]]

        showOptionsLayout.addWidget(self.GUI_show_exposure_chkbox)
        showOptionsLayout.addWidget(self.GUI_show_xy_chkbox)
        showOptionsLayout.addWidget(self.GUI_show_z_chkbox)
        showOptionsLayout.addWidget(self.GUI_show_channel_chkbox)
        showOptionsLayout.addWidget(self.GUI_show_time_chkbox)
        showOptionsLayout.addWidget(self.GUI_show_order_chkbox)
        showOptionsLayout.addWidget(self.GUI_show_storage_chkbox)
        

        # Set layouts for each groupbox
        self.exposureGroupBox.setLayout(exposureLayout)
        self.xyGroupBox.setLayout(xyLayout)
        self.zGroupBox.setLayout(zLayout)
        self.channelGroupBox.setLayout(channelLayout)
        self.timeGroupBox.setLayout(timeLayout)
        self.orderGroupBox.setLayout(orderLayout)
        self.storageGroupBox.setLayout(storageLayout)
        self.showOptionsGroupBox.setLayout(showOptionsLayout)

        # Add groupboxes to the main layout, only if they should be shown. The position of the gridbox is based on whether the previous ones are added or not:
        self.updateGUIwidgets(GUI_show_exposure=GUI_show_exposure,GUI_show_xy=GUI_show_xy, GUI_show_z=GUI_show_z, GUI_show_channel=GUI_show_channel, GUI_show_time=GUI_show_time, GUI_show_order=GUI_show_order, GUI_show_storage=GUI_show_storage,GUI_showOptions=GUI_showOptions,GUI_acquire_button=GUI_acquire_button)
        
        #Add the layout to the main layout
        self.layout.addLayout(self.gui,0,0)
    
    def setZStart(self):
        zstage = self.z_oneDstageDropdown.currentText()
        #zstage value limited to 2 decimal places:
        zstagePos = round(float(self.core.get_position(zstage)),2)
        self.z_startEntry.setText(str(zstagePos))
    
    def setZEnd(self):
        zstage = self.z_oneDstageDropdown.currentText()
        #zstage value limited to 2 decimal places:
        zstagePos = round(float(self.core.get_position(zstage)),2)
        self.z_endEntry.setText(str(zstagePos))
    
    def createOrderLayout(self,GUI_show_channel, GUI_show_time, GUI_show_xy, GUI_show_z):
        orderLayout = QVBoxLayout()
        letters_to_include = ''
        if GUI_show_channel:
            letters_to_include += 'c'
        if GUI_show_time:
            letters_to_include += 't'
        if GUI_show_xy:
            letters_to_include += 'p'
        if GUI_show_z:
            letters_to_include += 'z'
        #Now we create an array with all possible combinations of these letters:
        permuatations = [''.join(comb) for comb in itertools.permutations(letters_to_include, len(letters_to_include))]
        self.orderDropdown = QComboBox()
        #add the options to the dropdown:
        for option in permuatations:
            self.orderDropdown.addItem(option)
        #Create a label:
        self.orderLabel = QLabel("Order:")
        
        #Show the widgets.
        orderLayout.addWidget(self.orderLabel)
        orderLayout.addWidget(self.orderDropdown)
        
        return orderLayout
        
    def showOptionChanged(self):
        #This function will be called when the checkboxes are clicked. It will update the GUI accordingly:
        self.updateGUIwidgets(GUI_show_exposure=self.GUI_show_exposure_chkbox.isChecked(), GUI_show_xy = self.GUI_show_xy_chkbox.isChecked(), GUI_show_z=self.GUI_show_z_chkbox.isChecked(), GUI_show_channel=self.GUI_show_channel_chkbox.isChecked(), GUI_show_time=self.GUI_show_time_chkbox.isChecked(), GUI_show_order=self.GUI_show_order_chkbox.isChecked(), GUI_show_storage=self.GUI_show_storage_chkbox.isChecked(),GUI_showOptions=True,GUI_acquire_button=self.GUI_acquire_button)
        self.get_MDA_events_from_GUI()
    
    def updateGUIwidgets(self,GUI_show_exposure=True, GUI_show_xy = False, GUI_show_z=True, GUI_show_channel=False, GUI_show_time=True, GUI_show_order=True, GUI_show_storage=True,GUI_showOptions=True,gridWidth=4,GUI_acquire_button=True):
        gridWidth = self.GUI_grid_width
        # Remove the widgets from their parent
        self.exposureGroupBox.setParent(None)
        self.xyGroupBox.setParent(None)
        self.zGroupBox.setParent(None)
        self.channelGroupBox.setParent(None)
        self.timeGroupBox.setParent(None)
        self.orderGroupBox.setParent(None)
        self.storageGroupBox.setParent(None)
        self.showOptionsGroupBox.setParent(None) 

        # Clear the layout
        while self.gui.count():
            item = self.gui.takeAt(0)
            widget = item.widget()
            if widget:
                widget.deleteLater()
        #redraw the self.gui:
        self.gui.update()
        QCoreApplication.processEvents()
        
        curindex = 0
        if GUI_show_exposure:
            self.gui.addWidget(self.exposureGroupBox, curindex//gridWidth, curindex%gridWidth)
            curindex+=1
            QCoreApplication.processEvents()
        if GUI_show_xy:
            self.gui.addWidget(self.xyGroupBox, curindex//gridWidth, curindex%gridWidth)
            curindex+=1
            QCoreApplication.processEvents()
        if GUI_show_z:
            self.gui.addWidget(self.zGroupBox, curindex//gridWidth, curindex%gridWidth)
            curindex+=1
            QCoreApplication.processEvents()
        if GUI_show_channel:
            self.gui.addWidget(self.channelGroupBox, curindex//gridWidth, curindex%gridWidth)
            curindex+=1
            QCoreApplication.processEvents()
        if GUI_show_time:
            self.gui.addWidget(self.timeGroupBox, curindex//gridWidth, curindex%gridWidth)
            curindex+=1
            QCoreApplication.processEvents()
        if GUI_show_order:    
            #New groupbox
            self.orderGroupBox = QGroupBox("Order")
            QCoreApplication.processEvents()
            orderlayout = self.createOrderLayout(GUI_show_channel, GUI_show_time, GUI_show_xy, GUI_show_z)
            self.orderGroupBox.setLayout(orderlayout)
            self.gui.addWidget(self.orderGroupBox, curindex//gridWidth, curindex%gridWidth)
            curindex+=1
            QCoreApplication.processEvents()
        if GUI_show_storage: 
            self.gui.addWidget(self.storageGroupBox, curindex//gridWidth, curindex%gridWidth)
            curindex+=1
            QCoreApplication.processEvents()
        
        #To the full buttom:
        if GUI_showOptions:
            self.gui.addWidget(self.showOptionsGroupBox, 10,0)
            QCoreApplication.processEvents()
        
        if GUI_acquire_button:
            self.GUI_acquire_button = QPushButton("Acquire")
            self.GUI_acquire_button.clicked.connect(lambda index: self.MDA_acq_from_GUI())
            self.gui.addWidget(self.GUI_acquire_button, 11,0)
            QCoreApplication.processEvents()
        
        self.gui.setColumnStretch(99,gridWidth+1)
        self.gui.setRowStretch(99,gridWidth+1)
        
        QCoreApplication.processEvents()
        
        #redraw the self.gui:
        self.gui.update()
    
    def MDA_acq_from_GUI(self):
        #ensure that live mode is stopped:
        self.shared_data.core.stop_sequence_acquisition()
        
        if self.mda_analysis_thread == None:
            #Create a thread to do some dummy real-time analysis:
            self.mda_analysis_thread = create_analysis_thread(shared_data,analysisInfo='AvgGrayValueText')
        
        #Create a napari layer:
        mdaImageLayer = getLayerIdFromName('pycromanager acquisition',self.shared_data.napariViewer)
        #If it's the first mdaImageLayer
        if not mdaImageLayer:
            nrLayersBefore = len(self.shared_data.napariViewer.layers)
            layer = self.shared_data.napariViewer.add_image(np.zeros((self.shared_data.core.get_roi().width,self.shared_data.core.get_roi().height)), rendering='attenuated_mip', name="pycromanager acquisition")
            #Set correct scale - in nm
            layer.scale = [self.shared_data.core.get_pixel_size_um(),self.shared_data.core.get_pixel_size_um()] #type:ignore
            layer._keep_auto_contrast = True #type:ignore
            self.shared_data.napariViewer.layers.move_multiple([nrLayersBefore,0])
            self.shared_data.napariViewer.reset_view()
        #Else if the layer already exists, replace it!
        else:
            # layer is present, replace its data
            layer = self.shared_data.napariViewer.layers[mdaImageLayer[0]]
            
        layer.events.data.connect(lambda: self.update_mda_visualisation(layer, self.mda_analysis_thread ))

        #First, we get the events:
        self.get_MDA_events_from_GUI()
        
        #Set the exposure time:
        self.core.set_exposure(self.exposure_ms)
        
        # connect napari viewer to Acquisition class and start data acquisition
        acq = Acquisition(directory=self.storageFolder, name=self.storageFileName, napari_viewer=self.shared_data.napariViewer)
        acq.acquire(self.mda)
        acq.mark_finished()
        # acq.await_completion()

        #old method that freezes napari:
        # with Acquisition(directory=self.storageFolder, name=self.storageFileName, show_display=False) as acq:
        #     acq.acquire(self.mda)
        # with Acquisition(directory=self.storageFolder, name=self.storageFileName, napari_viewer=self.shared_data.napariViewer) as acq:
        #     acq.acquire(self.mda)
        pass
    
    def update_mda_visualisation(self, layer, analysis_thread=None):
        # Assuming your new data is added to the first layer
        print('updateMDAvis')
        current_slice = len(self.shared_data.napariViewer.layers[0].data) - 1
        self.shared_data.napariViewer.dims.set_point(0, current_slice)
        layer.reset_contrast_limits() #unsure why this is not working
        
        #Start accompanied analysis thread
        if analysis_thread is not None:
            analysis_thread.image_queue_analysis.put(layer.data[-1,:,:].compute())
            if not analysis_thread.isRunning():
                print('start')
                analysis_thread.start()
        
    def get_MDA_events_from_GUI(self):
        #This function will be run every time any option in the GUI is changed.
        
        #Make this somewhat readable:
        if self.exposureGroupBox.isVisible():
            try:
                self.exposure_ms = float(self.exposureEntry.text())
                if self.exposureDropdown.currentText() == 's':
                    self.exposure_ms *= 1000
            except:
                self.exposure_ms = None
        
        if self.timeGroupBox.isVisible():
            try:
                self.num_time_points = int(self.timePointEntry.text())
                self.time_interval_s = float(self.timeIntervalEntry.text())
                if self.timeIntervalDropdown.currentText() == 'ms':
                    self.time_interval_s /= 1000
            except:
                self.num_time_points = None
                self.time_interval_s = None
                
        if self.orderGroupBox.isVisible():
            self.order = self.orderDropdown.currentText()
        
        if self.storageGroupBox.isVisible():
            self.storageFolder = self.storageFolderEntry.text()
            self.storageFileName = self.storageFileNameEntry.text()
        
        if self.zGroupBox.isVisible():
            try:
                self.z_start = (float(self.z_startEntry.text()))
                self.z_end = (float(self.z_endEntry.text()))
                if self.z_nrsteps_radio.isChecked():
                    self.z_step = float((self.z_end-self.z_start)/int(self.z_nrsteps_entry.text()))
                elif self.z_stepdistance_radio.isChecked():
                    self.z_step = float(self.z_stepdistance_entry.text())
                    if self.z_start < self.z_end:
                        if self.z_step > 0:
                            self.z_step*=-1
                    elif self.z_start > self.z_end:
                        if self.z_step < 0:
                            self.z_step*=-1
            except:
                self.z_start = None
                self.z_end = None
                self.z_step = None
        
        #initiate with an empty mda:
        self.mda = multi_d_acquisition_events(num_time_points=self.num_time_points, time_interval_s=self.time_interval_s,z_start=self.z_start,z_end=self.z_end,z_step=self.z_step,channel_group=self.channel_group,channels=self.channels,channel_exposures_ms=self.channel_exposures_ms,xy_positions=self.xy_positions,xyz_positions=self.xyz_positions,position_labels=self.position_labels,order=self.order) #type:ignore
        
        print(self.mda)
        
        pass
    def printText(self):
        print(self.getEvents())
    
    def getEvents(self):
        return self.mda
    
    def getGui(self):
        return self.gui

def microManagerControlsUI(core,MM_JSON,main_layout,sshared_data):
    global shared_data
    shared_data = sshared_data
    # Get all config groups
    allConfigGroups={}
    nrconfiggroups = core.get_available_config_groups().size()
    for config_group_id in range(nrconfiggroups):
        allConfigGroups[config_group_id] = ConfigInfo(core,config_group_id)
    
    #Create the MM config via all config groups
    MMconfig = MMConfigUI(allConfigGroups)
    main_layout.addLayout(MMconfig.mainLayout,0,0)
    
    return MMconfig
    
    #Test line:
    # breakpoint
    
    