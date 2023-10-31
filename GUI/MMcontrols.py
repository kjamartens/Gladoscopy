from PyQt5.QtWidgets import QLayout, QLineEdit, QFrame, QGridLayout, QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QLabel, QComboBox, QSpacerItem, QSizePolicy
from PyQt5.QtCore import Qt, pyqtSignal, QObject, QThread
from PyQt5.QtGui import QResizeEvent, QIcon, QPixmap
from PyQt5 import uic
import sys
import os
# import PyQt5.QtWidgets
import json
from pycromanager import core
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
    def __init__(self, config_groups,showStages=True,number_config_columns=5):
        self.config_groups = config_groups
        self.number_columns = number_config_columns
        self.core = self.config_groups[0].core
        self.dropDownBoxes = {}
        #Create a Vertical+horizontal layout:
        self.mainLayout = QGridLayout()
        #Create a layout for the configs:
        self.configLayout = QGridLayout()
        #Add this to the mainLayout:
        self.mainLayout.addLayout(self.configLayout,0,0)
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
            self.mainLayout.addWidget(self.Vseparator_line(), 0, 1)
            #Now add the stages widget
            # self.stagesWidget()
            self.mainLayout.addLayout(self.stagesLayout(), 0, 2)
            
        #Update everything for good measure at the end of init
        self.updateAllMMinfo()
            
    def Vseparator_line(self):
        separator_line = QFrame()
        separator_line.setFrameShape(QFrame.VLine)
        separator_line.setFrameShadow(QFrame.Sunken)
        return separator_line
    
    def stagesLayout(self):
        stageLayout = QHBoxLayout()
        stageLayout.addLayout(self.XYstageLayout())
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
        
        #Widget itself is a vertical layout with 7 vertical entries: up+3,+2,+1,-1,-2,-3, and a center for horizontal movement+info
        XYStageLayout = QGridLayout()
        XYStageLayout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        horizontalMoverLayout = QGridLayout()
        horizontalMoverLayout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        
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
            XYStageLayout.addWidget(self.XYmoveButtons[f'Up_{m}'],m-1,0,1,8, alignment=Qt.AlignmentFlag.AlignCenter)
            XYStageLayout.addWidget(self.XYmoveButtons[f'Down_{m}'],8-m,0,1,8, alignment=Qt.AlignmentFlag.AlignCenter)
            horizontalMoverLayout.addWidget(self.XYmoveButtons[f'Left_{m}'],0,m-1)
            horizontalMoverLayout.addWidget(self.XYmoveButtons[f'Right_{m}'],0,8-m)
            XYStageLayout.addLayout(horizontalMoverLayout,4,0,1,8, alignment=Qt.AlignmentFlag.AlignCenter)
            
        #Add a central label for info
        #this label contains the XY stage name, then an enter, then the current position:
        self.XYStageInfoWidget = QLabel(f"{XYStageName}: {XYStagePos.x:.0f}/{XYStagePos.y:.0f}")
        horizontalMoverLayout.addWidget(self.XYStageInfoWidget,0,4)
        
        return XYStageLayout
    
    def updateXYStageInfoWidget(self):#Obtain the stage info from MM:
        XYStageName = self.core.get_xy_stage_device()
        #Get the stage position
        XYStagePos = self.core.get_xy_stage_position(XYStageName)
        self.XYStageInfoWidget.setText(f"{XYStageName}: {XYStagePos.x:.0f}/{XYStagePos.y:.0f}")
        
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
        #Get the new value from the dropdown:
        newValue = self.dropDownBoxes[config_id].currentText()
        #Get the config group name:
        configGroupName = self.config_groups[config_id].configGroupName()
        #Set in MM:
        self.config_groups[config_id].core.set_config(configGroupName,newValue)
    
    def addSlider(self,rowLayout,config_id):
        pass
    
    def addInputField(self,rowLayout,config_id):
        pass
    
    #Update a single config based on current value in MM
    def updateValuefromMM(self,config_id):
        #Get the value of the config_id from micromanager:
        currentValue = self.config_groups[config_id].getCurrentMMValue()
        #Set the value of the dropdown to the current MM value
        if self.config_groups[config_id].isDropDown():
            self.dropDownBoxes[config_id].setCurrentText(currentValue)
        pass
    
    #Update all configs based on current value in MM
    def updateConfigsFromMM(self):
        #Update all values from MM:
        for config_id in range(len(self.config_groups)):
            self.updateValuefromMM(config_id)
        pass
    
    #Update everything there is update-able
    def updateAllMMinfo(self):
        print('Updating all MM info')
        self.updateConfigsFromMM()
        self.updateXYStageInfoWidget()

def microManagerControlsUI(core,MM_JSON,main_layout):
    # Get all config groups
    allConfigGroups={}
    nrconfiggroups = core.get_available_config_groups().size()
    for config_group_id in range(nrconfiggroups):
        allConfigGroups[config_group_id] = ConfigInfo(core,config_group_id)
    
    #Create the MM config via all config groups
    MMconfig = MMConfigUI(allConfigGroups)
    main_layout.addLayout(MMconfig.mainLayout)
    
    return MMconfig
    
    #Test line:
    # breakpoint
    
    