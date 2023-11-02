from PyQt5.QtWidgets import QLayout, QLineEdit, QFrame, QGridLayout, QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QLabel, QComboBox, QSpacerItem, QSizePolicy
from PyQt5.QtCore import Qt, pyqtSignal, QObject, QThread
from PyQt5.QtGui import QResizeEvent, QIcon, QPixmap, QFont
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
    def __init__(self, config_groups,showStages=True,showROIoptions=True,number_config_columns=5):
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
        
        if showROIoptions:
            self.mainLayout.addWidget(self.Vseparator_line(),0,3)
            #Now add the ROI options widget
            self.mainLayout.addLayout(self.ROIoptionsLayout(),0,4)
            
        
        #Update everything for good measure at the end of init
        self.updateAllMMinfo()
        
        #Change the font of everything in the layout
        self.set_font_and_margins_recursive(self.mainLayout, font=QFont("Arial", 5))
    
    #Set the font of all buttons/labels in the layout recursively
    def set_font_and_margins_recursive(self,widget, font=QFont("Arial", 8)):
        if widget is None:
            return
        
        if isinstance(widget, (QLabel, QPushButton, QComboBox)):
            widget.setFont(font)
            widget.setContentsMargins(0, 0, 0, 0)
            widget.setMinimumSize(0, 0)
            widget.setSizePolicy(
                QSizePolicy(QSizePolicy.Minimum, QSizePolicy.Minimum)
            )

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
            print('Device: '+device)
            names = core.get_device_property_names(device)
            props = [names.get(i) for i in range(names.size())]
            property_items = []
            for prop in props:
                print('Property',prop)
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
                    print('===>', device, prop, value, allowed)
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
        print('roiv'+str(roiv))
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
                print('ZOOMING IN DIDN\'T WORK!')
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
                print('ZOOMING IN DIDN\'T WORK!')
    
    def setROI(self,ROIpos):
        #ROIpos should be a list of [x,y,width,height]
        print('Zooming ROI to ' + str(ROIpos))
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
            print('ZOOMING DIDN\'T WORK!')
    
    def stagesLayout(self):
        stageLayout = QVBoxLayout()
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
        self.XYStageInfoWidget = QLabel(f"{XYStageName}: {XYStagePos.x:.0f}/{XYStagePos.y:.0f}")
        XYStageLayout.addWidget(self.XYStageInfoWidget,4,4)
        
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
                print(device)
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
            self.oneDmoveButtons[f'Left_{m}'] = QPushButton("⮜"*(4-m))
            self.oneDmoveButtons[f'Left_{m}'].clicked.connect(lambda index, m=m: self.moveOneDStage(-m))
            self.oneDmoveButtons[f'Right_{m}'] = QPushButton("⮞"*(4-m))
            self.oneDmoveButtons[f'Right_{m}'].clicked.connect(lambda index, m=m: self.moveOneDStage(m))
            
            #Add buttons to layout
            self.oneDStageLayout.addWidget(self.oneDmoveButtons[f'Left_{m}'],1,m-1,1,1, alignment=Qt.AlignmentFlag.AlignCenter)
            self.oneDStageLayout.addWidget(self.oneDmoveButtons[f'Right_{m}'],1,6-m,1,1, alignment=Qt.AlignmentFlag.AlignCenter)
        
        #Get current info of the widget
        self.oneDinfoWidget = QLabel(f"{self.oneDstageDropdown.currentText()}: {self.core.get_position(self.oneDstageDropdown.currentText()):.1f}")
        self.oneDStageLayout.addWidget(self.oneDinfoWidget,1,3)
        
        return self.oneDStageLayout
    
    def updateOneDstageLayout(self):
        self.oneDinfoWidget.setText(f"{self.oneDstageDropdown.currentText()}: {self.core.get_position(self.oneDstageDropdown.currentText()):.1f}")
    
    def moveOneDStage(self,amount):
        #Get the currently selected one-D stage:
        selectedStage = self.oneDstageDropdown.currentText()
        
        self.moveoneDstagesmallAmount = 10
        self.moveoneDstagelargeAmount = 100
        
        print(amount)
        print(np.sign(amount))
        print((np.sign(amount)*self.moveoneDstagesmallAmount).astype(float))
        
        #Move the stage relatively
        if abs(amount) == 1:
            self.core.set_relative_position(selectedStage,(np.sign(amount)*self.moveoneDstagesmallAmount).astype(float))
        elif abs(amount) == 2:
            self.core.set_relative_position(selectedStage,(np.sign(amount)*self.moveoneDstagelargeAmount).astype(float))
        self.updateOneDstageLayout()
        
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
        self.updateOneDstageLayout()

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
    main_layout.addLayout(MMconfig.mainLayout)
    
    return MMconfig
    
    #Test line:
    # breakpoint
    
    