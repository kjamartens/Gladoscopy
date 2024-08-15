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
from napariHelperFunctions import getLayerIdFromName, InitateNapariUI, checkIfLayerExistsOrCreate, addToExistingOrNewLayer, moveLayerToTop
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
            #If there is exactly one option...
            if self.nrConfigs() == 1:
                #And the option is 'NewPreset', it means there are no presets specified
                if self.core.get_available_configs(self.configGroupName()).get(0) == 'NewPreset':
                    return False
                else:
                    return True
        
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
            #If there is exactly one option...
            if self.nrConfigs() == 1:
                #And the option is 'NewPreset', it means there are no presets specified
                if self.core.get_available_configs(self.configGroupName()).get(0) == 'NewPreset':
                    #check if it's not a slider...
                    if self.hasPropertyLimits():
                        return False
                    else:
                        return True
                else:
                    return False

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

    def getStorableValue(self):
        """Get the current MM value of this config group, in a storable manner - i.e. depending on slider, input, dropdown:"""
        if self.isDropDown():
            return self.core.get_current_config(self.configGroupName())
        if self.isSlider():
            #A slider config by definition (?) only has a single property underneath, so get that:
            configGroupName = self.configGroupName()
            underlyingProperty = self.core.get_available_configs(configGroupName).get(0)
            configdata = self.core.get_config_data(configGroupName,underlyingProperty)
            device_label = configdata.get_setting(0).get_device_label()
            property_name = configdata.get_setting(0).get_property_name()
            
            #Finally we get the current value of the slider
            currentSliderValue = float(self.core.get_property(device_label,property_name))
            return currentSliderValue
        if self.isInputField():
            #An input field config by definition (?) only has a single property underneath, so get that:
            configGroupName = self.configGroupName()
            underlyingProperty = self.core.get_available_configs(configGroupName).get(0)
            configdata = self.core.get_config_data(configGroupName,underlyingProperty)
            device_label = configdata.get_setting(0).get_device_label()
            property_name = configdata.get_setting(0).get_property_name()
            
            #Finally we get the current value of the slider
            try:
                currentValue = (self.core.get_property(device_label,property_name))
            except:
                currentValue = 0
            return currentValue
        

class MMConfigUI(CustomMainWindow):
    """
        A class to create a MicroManager config UI
    """
    def __init__(self, config_groups,parent=None,showConfigs = True,showStages=True,showROIoptions=True,showShutterOptions=True,showLiveSnapExposureButtons=True,number_config_columns=5,changes_update_MM = True,showCheckboxes = False,checkboxStartInactive=True,showRelativeStages = False,autoSaveLoad=False):
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
            showShutterOptions (bool, optional): Whether to show the Shutter options in the UI. Defaults to True.
            showLiveSnapExposureButtons (bool, optional): Whether to show the live mode in the UI. Defaults to True.
            number_config_columns (int, optional): The number of columns in the layout. Defaults to 5.
            changes_update_MM (bool, optional): Whether to update the configs in MicroManager real-time. Defaults to True.
            showCheckboxes (bool, optional): Whether to show checkboxes for each config group. Defaults to False.
            checkboxStartInactive (bool, optional): Whether the checkboxes should start inactive. Defaults to True.
            showRelativeStages (bool, optional): Whether to show the relative stages in the UI. Defaults to False.
            autoSaveLoad (bool, optional): Whether to automatically save and load the configs to file when the UI is opened and closed. Defaults to False. 
        """
        
        if parent is not None:# from napari plugin run
            global core, livestate, napariViewer, shared_data
            core = parent.core
            livestate = parent.livestate
            shared_data = parent.shared_data
            napariViewer = parent.napariViewer
            shared_data.napariViewer = napariViewer
        else: #assuming shared_data is global - from .py run
            try:
                # global core, napariViewer
                core = shared_data.core
                napariViewer = shared_data.napariViewer
            except:
                logging.error('Line 237 fails')
        super().__init__()
        self.fullyLoaded = False
        self.autoSaveLoad = autoSaveLoad
        self.showConfigs = showConfigs
        self.showStages = showStages
        self.showROIoptions = showROIoptions
        self.showShutterOptions = showShutterOptions
        self.showLiveSnapExposureButtons = showLiveSnapExposureButtons
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
        self.editFields = {}
        self.configCheckboxes = {}
        self.sliderPrecision = 1000
        self.config_string_storage = []
        self.relstage_string_storage = []
        #Create a Vertical+horizontal layout:
        self.mainLayout = QGridLayout()
        self.configEntries = {}
        
        #Find the iconPath folder
        if os.path.exists('./glados_pycromanager/GUI/Icons/General_Start.png'):
            self.iconFolder = './glados_pycromanager/GUI/Icons/'
        elif os.path.exists('./glados-pycromanager/glados_pycromanager/GUI/Icons/General_Start.png'):
            self.iconFolder = './glados-pycromanager/glados_pycromanager/GUI/Icons/'
        else:
            self.iconFolder = ''
        
        
        
        if showLiveSnapExposureButtons:
            self.generalImagingGroupBox = QGroupBox("General")
            
            #Now add the live mode widget
            # self.liveModeGroupBox = QGroupBox("Live Mode")
            self.generalImagingGroupBox.setLayout(self.generalImagingLayout())
            self.mainLayout.addWidget(self.generalImagingGroupBox, 0, 0)
            
            #TODO: add shutter here
            
            
            
        if showConfigs:
            #Create a layout for the configs:
            self.configGroupBox = QGroupBox("Configurations")
            self.configLayout = QGridLayout()
            self.configLayout.setSizeConstraint(QHBoxLayout.SetMinimumSize) #type:ignore
            #Add this to the mainLayout via the groupbox:
            self.configGroupBox.setLayout(self.configLayout)
            self.mainLayout.addWidget(self.configGroupBox,0,2)
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
            self.mainLayout.addWidget(self.stagesGroupBox, 0, 3)
        
        
        if showRelativeStages:
            self.relativeStagesGroupBox = QGroupBox("RelativeStages")
            self.relativeStagesGroupBox.setLayout(self.relativeStagesLayout())
            # self.relativeStagesGroupBox.setLayout(QLayout())
            self.mainLayout.addWidget(self.relativeStagesGroupBox, 0, 4)
        
        #Update everything for good measure at the end of init
        self.updateAllMMinfo()
        self.fullyLoaded = True
        self.LoadAllMMFromJSON()
        
        #Inactivate all configs if this is wanted
        if checkboxStartInactive and showCheckboxes and showConfigs:
            for config_id in range(len(config_groups)):
                self.configCheckboxes[config_id].setChecked(False)
                    
        #Change the font of everything in the layout
        self.set_font_and_margins_recursive(self.mainLayout, font=QFont("Arial", 7))
        #Twice because it relies on dependancies inside qgridlayouts
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
        if self.showShutterOptions:
            self.updateShutterOptions()
        
        #Then store it in JSON for good measure
        if self.autoSaveLoad:
            if self.fullyLoaded:
                #Store in appdata
                appdata_folder = os.getenv('APPDATA')
                if appdata_folder is None:
                    raise EnvironmentError("APPDATA environment variable not found")
                app_specific_folder = os.path.join(appdata_folder, 'Glados-PycroManager')
                os.makedirs(app_specific_folder, exist_ok=True)
                self.save_state_MMControls(os.path.join(app_specific_folder, 'glados_state.json'))
                
        #         #Store in appdata
        #         appdata_folder = os.getenv('APPDATA')
        #         if appdata_folder is None:
        #             raise EnvironmentError("APPDATA environment variable not found")
        #         app_specific_folder = os.path.join(appdata_folder, 'Glados-PycroManager')
        #         os.makedirs(app_specific_folder, exist_ok=True)
                
                
        #         if os.path.exists(os.path.join(app_specific_folder, 'glados_state.json')):
        #             with open(os.path.join(app_specific_folder, 'glados_state.json'), 'r') as file:
        #                 gladosInfo = json.load(file)
        #                 MMControlsInfo = gladosInfo['MMControls']
                
        #             #Hand-set the values that I want:
        #             if 'exposureTimeInputField' in MMControlsInfo:
        #                 self.exposureTimeInputField.setText(MMControlsInfo['exposureTimeInputField']['text'])
        #             for key, object in self.XYMoveEditField.items():
        #                 if key in MMControlsInfo:
        #                     object.setText(MMControlsInfo[key]['text'])
        #             for key,object in self.oneDMoveEditField.items():
        #                 for objectLineEditKey in object:
        #                     objectLineEdit = object[objectLineEditKey]
        #                     if objectLineEditKey in MMControlsInfo:
        #                         objectLineEdit.setText(MMControlsInfo[objectLineEditKey]['text'])

    def LoadAllMMFromJSON(self):
        """
        Update all the info that can be loaded from the JSON file.
        """
        #Load from APPData, if it exists
        appdata_folder = os.getenv('APPDATA')
        if appdata_folder is None:
            raise EnvironmentError("APPDATA environment variable not found")
        app_specific_folder = os.path.join(appdata_folder, 'Glados-PycroManager')
        
        if os.path.exists(os.path.join(app_specific_folder, 'glados_state.json')):
            #Load the file
            with open(os.path.join(app_specific_folder, 'glados_state.json'), 'r') as file:
                gladosInfo = json.load(file)
                MMControlsInfo = gladosInfo['MMControls']
        
            #Hand-set the values that I want:
            if 'exposureTimeInputField' in MMControlsInfo:
                self.exposureTimeInputField.setText(MMControlsInfo['exposureTimeInputField']['text'])
            if 'oneDstageDropdown' in MMControlsInfo:
                self.oneDstageDropdown.setCurrentText(MMControlsInfo['oneDstageDropdown']['text'])
            
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
                logging.debug('Storing glados state.json')
                
                #Store in appdata
                appdata_folder = os.getenv('APPDATA')
                if appdata_folder is None:
                    raise EnvironmentError("APPDATA environment variable not found")
                app_specific_folder = os.path.join(appdata_folder, 'Glados-PycroManager')
                os.makedirs(app_specific_folder, exist_ok=True)
                self.save_state_MMControls(os.path.join(app_specific_folder, 'glados_state.json'))
                pass

    def set_font_and_margins_recursive(self,widget, font=QFont("Arial", 8)):
        """
        Recursively sets the font of all buttons/labels in a layout to the specified font, and sets the contents margins to 0.
        Also sets the size policy of the widget to minimum, so it will only take up as much space as it needs.

        """
        # if widget is None:
        #     return
        #Testing a few things
        # try:
        #     widget.setSizePolicy(
        #         QSizePolicy(QSizePolicy.MinimumExpanding, QSizePolicy.MinimumExpanding)
        #     )
        # except:
        #     pass
        # try:
        #     widget.setMimimumSize(10, 10)
        # except:
        #     pass
        
        # if not isinstance(widget, (QPushButton,QComboBox)):
        #     try:
        #         widget.setSizePolicy(
        #             QSizePolicy(QSizePolicy.MinimumExpanding, QSizePolicy.MinimumExpanding)
        #         )
        #     except:
        #         pass
        
        if isinstance(widget, (QPushButton)):
            widget.setFont(font)
            # widget.setContentsMargins(0, 0, 0, 0)
            # widget.setMinimumSize(20, 20)
        if isinstance(widget, (QLabel, QComboBox)):
            widget.setFont(font)
            # widget.setContentsMargins(0, 0, 0, 0)
            # widget.setMinimumSize(20, 20)

        if isinstance(widget, QGroupBox):
            widget.setSizePolicy(
                QSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
            )
            # Ensure QGroupBox respects the size of its contents
            widget.setMinimumSize(widget.minimumSizeHint())  # Set the minimum size of QGroupBox based on its size hint

        if hasattr(widget, 'layout'):
            layout = widget.layout()
            if layout:
                # layout.setContentsMargins(0, 0, 0, 0)
                # layout.setSpacing(0)  # Optionally, remove spacing between widgets
                for i in range(layout.count()):
                    item = layout.itemAt(i)
                    if hasattr(item, 'widget'):
                        self.set_font_and_margins_recursive(item.widget(), font=font)
                    if hasattr(item, 'layout'):
                        self.set_font_and_margins_recursive(item.layout(), font=font)
    
    #Get all config information as set by the UI:
    def getUIConfigInfo(self,onlyChecked=False):
        """
        Get all config information as set by the UI.

        param onlyChecked: If True, only return information for checked configs.
        """
        configInfo = {}
        for config_id in range(len(self.config_groups)):
            if onlyChecked and not self.configCheckboxes[config_id].isChecked():
                continue
            configInfo[self.config_groups[config_id].configGroupName()] = self.currentConfigUISingleValue(config_id)
        return configInfo

    def currentConfigUISingleValue(self,config_id):
        """
        Get the value of a single config as currently determined by the UI.

        param config_id: The ID of the config_group to get the value for.
        """
        #Get the value of a single config as currently determined by the UI
        if self.config_groups[config_id].isDropDown():
            currentUIvalue = self.dropDownBoxes[config_id].currentText()
        elif self.config_groups[config_id].isSlider():
            #Get the value from the slider:
            sliderValue = self.sliders[config_id].value()
            #Get the true value from the conversion:
            currentUIvalue = sliderValue/self.sliders[config_id].slider_conversion_array[2]*(self.sliders[config_id].slider_conversion_array[1]-self.sliders[config_id].slider_conversion_array[0])+self.sliders[config_id].slider_conversion_array[0]
        elif self.config_groups[config_id].isInputField():
            currentUIvalue = self.editFields[config_id].text()
        else:
            currentUIvalue = None
        return currentUIvalue
    #endregion
    
    #region general imaging mode
    def generalImagingLayout(self):
        """
        Creates the layout for the general imaging mode options.
        This includes an input field for the exposure time in ms.
        Basically, should be exposure time (ms), snap, addToAlbum, live start/stop

        Returns:
            QGridLayout: The layout for the live mode options.
        """
        #Create a Grid layout:
        liveModeLayout = QGridLayout()
        liveModeLayout.setSizeConstraint(QHBoxLayout.SetMinimumSize) #type:ignore
        #Add a 'exposure time' label:
        exposureTimeLabel = QLabel("Exposure time (ms):")
        liveModeLayout.addWidget(exposureTimeLabel,0,0)
        #Add a 'exposure time' input field:
        self.exposureTimeInputField = QLineEdit()
        self.exposureTimeInputField.setText(str(100))
        self.exposureTimeInputField.editingFinished.connect(lambda: self.storeAllControlValues())
        liveModeLayout.addWidget(self.exposureTimeInputField,0,1)
        
        self.LiveModeButton = QPushButton("Start Live Mode")
        icon = QIcon(self.iconFolder+os.sep+'General_Start.png')
        # icon: Flaticon.com
        self.LiveModeButton.setIcon(icon)
        
        #add a connection to the button:
        self.LiveModeButton.clicked.connect(lambda index: self.changeLiveMode())
        #Add the button to the layout:
        liveModeLayout.addWidget(self.LiveModeButton,1,0,1,2)
        
        self.SnapButton = QPushButton("Snap")
        icon = QIcon(self.iconFolder+os.sep+'General_Snap.png')
        # icon: Flaticon.com
        self.SnapButton.setIcon(icon)
        #add a connection to the button:
        self.SnapButton.clicked.connect(lambda index: self.snapImage())
        #Add the button to the layout:
        liveModeLayout.addWidget(self.SnapButton,2,0,1,2)
        
        self.AlbumButton = QPushButton("Add to Album")
        #add a connection to the button:
        self.AlbumButton.clicked.connect(lambda index: self.addImageToAlbum())
        icon = QIcon(self.iconFolder+os.sep+'General_Album.png')
        # icon: Flaticon.com
        self.AlbumButton.setIcon(icon)
        #Add the button to the layout:
        liveModeLayout.addWidget(self.AlbumButton,3,0,1,2)
        
        
        if self.showShutterOptions:
            self.shutterOptionsGroupBox = QGroupBox("Shutter")
            self.shutterOptionsGroupBox.setLayout(self.shutterOptionsLayout(orientation='horizontal'))
            liveModeLayout.addWidget(self.shutterOptionsGroupBox, 4,0,1,2)
            
        
        if self.showROIoptions:
            #Now add the ROI options widget
            self.roiOptionsGroupBox = QGroupBox("ROI Options")
            self.roiOptionsGroupBox.setLayout(self.ROIoptionsLayout(orientation='horizontal'))
            liveModeLayout.addWidget(self.roiOptionsGroupBox, 5,0,1,2)
        
        #Add one of those spacers at the bottom:
        verticalSpacer = QSpacerItem(20, 40, QSizePolicy.Minimum, QSizePolicy.Expanding)
        liveModeLayout.addItem(verticalSpacer)
        
        #Add a button to update all MM info
        self.updateAllMMinfoButton = QPushButton("Update all MM info")
        self.updateAllMMinfoButton.clicked.connect(self.updateAllMMinfo)
        #all the way at the bottom of the layout
        liveModeLayout.addWidget(self.updateAllMMinfoButton,99,0,1,1)
        #Add a button to close all layers
        self.closeAllLayersButton = QPushButton("Close all Layers")
        self.closeAllLayersButton.clicked.connect(lambda index, shared_data=shared_data: utils.closeAllLayers(shared_data))
        #all the way at the bottom of the layout
        liveModeLayout.addWidget(self.closeAllLayersButton,99,1,1,1)
        
        #Return the layout
        return liveModeLayout
    
    def snapImage(self):
        """
        Function that's called when an image is snapped (i.e. get a single image), uses the float(self.exposureTimeInputField.text()) as time in ms
        """
        #Set the correct exposure time
        shared_data.core.set_exposure(float(self.exposureTimeInputField.text()))
        #Snap an image
        shared_data.core.snap_image()
        #Get the just-snapped image
        newImage = shared_data.core.get_tagged_image()
        snapLayer = checkIfLayerExistsOrCreate(napariViewer,'Snap',shared_data_throughput = shared_data, required_size = (newImage.tags["Height"],newImage.tags["Width"]))
        snapLayer.data = np.reshape(newImage.pix, newshape=[newImage.tags["Height"], newImage.tags["Width"]])
        #Move the layer to top
        moveLayerToTop(napariViewer,'Snap')
        return
    
    def addImageToAlbum(self):
        """
        Add an image to the Album layer in napari
        """ 
        #Set the correct exposure time
        shared_data.core.set_exposure(float(self.exposureTimeInputField.text()))
        #Snap an image
        shared_data.core.snap_image()
        #Get the just-snapped image
        newImage = shared_data.core.get_tagged_image()
        
        #And add to the 'Album' layer
        addToExistingOrNewLayer(napariViewer,'Album',np.reshape(newImage.pix, newshape=[newImage.tags["Height"], newImage.tags["Width"]]),shared_data_throughput = shared_data)
        return
    
    def changeLiveMode(self):
        """
        Function that should be called when live mode is changed. Sets the shared_data.liveMode to True or False.
        """
        if shared_data.liveMode == False:
            #update the button text of the live mode:
            self.LiveModeButton.setText("Stop Live Mode")
            icon = QIcon(self.iconFolder+os.sep+'General_Stop.png')
            # icon: Flaticon.com
            self.LiveModeButton.setIcon(icon)
            #set exposure time first:
            shared_data.core.set_exposure(float(self.exposureTimeInputField.text()))
            #Then start live mode:
            shared_data.liveMode = True
        else:
            #update the button text of the live mode:
            self.LiveModeButton.setText("Start Live Mode")
            icon = QIcon(self.iconFolder+os.sep+'General_Start.png')
            # icon: Flaticon.com
            self.LiveModeButton.setIcon(icon)
            #update live mode:
            shared_data.liveMode = False
    #endregion

    #region Shutter
    def shutterOptionsLayout(self,orientation='horizontal'):
        """
        Create a layout with buttons for Shutter options

        Returns
        -------
        ShutterOptionsLayout : QGridLayout
            A layout with buttons for Shutter options
        """
        #Create a Grid layout:
        shutterOptionsLayout = QGridLayout()
        #Add a dropdown:
        self.shutterChoiceDropdown = QComboBox()
        shutterDevices = self.getDevicesOfDeviceType('ShutterDevice')
        for shutterDevice in shutterDevices:
            self.shutterChoiceDropdown.addItem(shutterDevice)
        self.shutterChoiceDropdown.currentIndexChanged.connect(self.on_shutterChoiceChanged)
        
        self.shutterAutoCheckbox = QCheckBox("Auto")
        self.shutterAutoCheckbox.stateChanged.connect(self.on_shutterAutoCheckboxChanged)
        
        self.shutterOpenCloseButton = QPushButton("Open")
        self.shutterOpenCloseButton.setIcon(QIcon(self.iconFolder+os.sep+'ShutterOpen.png'))
        self.shutterOpenCloseButton.clicked.connect(self.on_shutterOpenCloseButtonPressed)
        
        shutterOptionsLayout.addWidget(self.shutterChoiceDropdown,0,0,1,2)
        shutterOptionsLayout.addWidget(self.shutterAutoCheckbox,1,0)
        shutterOptionsLayout.addWidget(self.shutterOpenCloseButton,1,1)
        
        return shutterOptionsLayout

    def on_shutterOpenCloseButtonPressed(self):
        """" 
        Method that's called when the Open/Close shutter button is pressed.
        """
        current_text = self.shutterOpenCloseButton.text()
        if current_text == 'Open':
            self.core.set_shutter_open(True) #type:ignore
            self.shutterOpenCloseButton.setText('Close')
            self.shutterOpenCloseButton.setIcon(QIcon(self.iconFolder+os.sep+'ShutterClosed.png'))
        elif current_text == 'Close':
            self.core.set_shutter_open(False) #type:ignore
            self.shutterOpenCloseButton.setText('Open')
            self.shutterOpenCloseButton.setIcon(QIcon(self.iconFolder+os.sep+'ShutterOpen.png'))

    def on_shutterChoiceChanged(self):
        """
        Set the shutter to the new choice if the dropdown is changed
        """ 
        selected_item = self.shutterChoiceDropdown.currentText()
        self.core.set_shutter_device(selected_item) #type:ignore

    def on_shutterAutoCheckboxChanged(self,state):
        """
        Set the auto-shutter to whether the checkbox is selected or not
        """
        if state == 2:
            self.shutterOpenCloseButton.setEnabled(False)
            self.core.set_auto_shutter(True) #type:ignore
        else:
            self.shutterOpenCloseButton.setEnabled(True)
            self.core.set_auto_shutter(False) #type:ignore
    
    def updateShutterOptions(self):
        """" 
        Update the shutter GUI options based on what's what in MM
        """
        #Set the current shutter device to the one in MM
        currentShutterDevice = self.core.get_shutter_device() #type:ignore
        self.shutterChoiceDropdown.currentText = currentShutterDevice
        #Set the auto-method to the one in MM:
        currentShutterAuto = self.core.get_auto_shutter() #type:ignore
        self.shutterAutoCheckbox.setChecked(currentShutterAuto)
        if currentShutterAuto == False:
            self.shutterOpenCloseButton.setEnabled(True)
        #Set the button text
        currentShutterOpen = self.core.get_shutter_open() #type:ignore
        if currentShutterOpen == True:
            self.shutterOpenCloseButton.setText('Close')
        else:
            self.shutterOpenCloseButton.setText('Open')
        
    #endregion

    #region ROI
    def ROIoptionsLayout(self,orientation='horizontal'):
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
        self.ROIoptionsButtons['Reset'].setIcon(QIcon(self.iconFolder+os.sep+'ROI_reset.png'))
        self.ROIoptionsButtons['Reset'].clicked.connect(lambda index: self.resetROI())
        #Zoom in once to center
        self.ROIoptionsButtons['ZoomIn'] = QPushButton("Zoom In")
        self.ROIoptionsButtons['ZoomIn'].setIcon(QIcon(self.iconFolder+os.sep+'ROI_zoomIn.png'))
        self.ROIoptionsButtons['ZoomIn'].clicked.connect(lambda index: self.zoomROI('ZoomIn'))
        #Zoom out once from center
        self.ROIoptionsButtons['ZoomOut'] = QPushButton("Zoom Out")
        self.ROIoptionsButtons['ZoomOut'].setIcon(QIcon(self.iconFolder+os.sep+'ROI_zoomOut.png'))
        self.ROIoptionsButtons['ZoomOut'].clicked.connect(lambda index: self.zoomROI('ZoomOut'))
        #Draw a ROI
        self.ROIoptionsButtons['drawROI'] = QPushButton("Draw ROI")
        self.ROIoptionsButtons['drawROI'].setIcon(QIcon(self.iconFolder+os.sep+'ROI_select.png'))
        self.ROIoptionsButtons['drawROI'].clicked.connect(lambda index: self.drawROI())
        if orientation == 'vertical':
            ROIoptionsLayout.addWidget(self.ROIoptionsButtons['Reset'],0,0)
            ROIoptionsLayout.addWidget(self.ROIoptionsButtons['ZoomIn'],1,0)
            ROIoptionsLayout.addWidget(self.ROIoptionsButtons['ZoomOut'],2,0)
            ROIoptionsLayout.addWidget(self.ROIoptionsButtons['drawROI'],3,0)
        else:
            ROIoptionsLayout.addWidget(self.ROIoptionsButtons['Reset'],0,0)
            ROIoptionsLayout.addWidget(self.ROIoptionsButtons['ZoomIn'],0,1)
            ROIoptionsLayout.addWidget(self.ROIoptionsButtons['ZoomOut'],0,2)
            ROIoptionsLayout.addWidget(self.ROIoptionsButtons['drawROI'],0,3)
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
    
    def drawROI(self):
        """
        Draw a ROI. Idea is to create a new layer, let the user draw a rectangle, and ask if they like it or not. Then a small popup window with 'OK', 'Let me draw again', 'Stop this futile attempt'
        """
        
        # Create a shapes layer
        self.drawROIlayer = shared_data.napariViewer.add_shapes(name='drawROI')

        # Set the shapes layer mode to 'add_rectangle'
        self.drawROIlayer.mode = 'add_rectangle'
        
        #Changes the button to a different method, which should be pressed once the rectangle is drawn:
        self.ROIoptionsButtons['drawROI'].setText('ROI drawn')
        self.ROIoptionsButtons['drawROI'].clicked.disconnect()
        self.ROIoptionsButtons['drawROI'].clicked.connect(lambda index: self.setROItoDrawn())
    
    def setROItoDrawn(self):
        """
        The setROItoDrawn function is used to set the ROI of the microscope to a drawn shape.
        The function first checks if there are any shapes in self.drawROIlayer, and if so, it gets the vertices of the last added shape (which should be a rectangle). It then sets the ROI using these vertices as top left and bottom right corners.
        It also removes self.drawROIlayer from shared_data.napariViewer
        """
        # Get the type of the last added shape
        if len(self.drawROIlayer.data) > 0:
            shape_type = self.drawROIlayer.shape_type[-1]
            if shape_type == 'rectangle':
                vertices = self.drawROIlayer.data[-1]  # Get the vertices of the last added shape
                #Get the topleft, bottomright position from the drawn rectangle
                topleftxy = np.floor(vertices[0])
                bottomrightxy = np.ceil(vertices[2])
                #Set the boundaries based on the camera
                mintopleft = [0,0]
                maxbottomright = [shared_data.core.get_roi().width, shared_data.core.get_roi().height]
                #Find the bounded positions
                topleftpos = np.maximum(topleftxy,mintopleft)
                bottomrightpos = np.minimum(bottomrightxy,maxbottomright)
                #Set the ROI correclty
                shared_data.core.set_roi(int(topleftpos[0]),int(topleftpos[1]),int(bottomrightpos[0]-topleftpos[0]),int(bottomrightpos[1]-topleftpos[1]))
                logging.info(f"Set ROI to {topleftpos[0]},{topleftpos[1]},{bottomrightpos[0]},{bottomrightpos[1]} px")
        else:
            logging.warning('Attempted to set ROI to drawn, but no shape was added')
        
        #remove the self.drawROIlayer:
        try:
            shared_data.napariViewer.layers.remove(self.drawROIlayer)
        except:
            logging.error('Failed to remove the drawROIlayer')
        
        #Reset the Draw ROI button
        self.ROIoptionsButtons['drawROI'].setText('Draw ROI')
        self.ROIoptionsButtons['drawROI'].clicked.disconnect()
        self.ROIoptionsButtons['drawROI'].clicked.connect(lambda index: self.drawROI())
    #endregion
    
    #region Stages
    def stagesLayout(self):
        """
        Returns the layout with the XY and 1D stage widgets.
        """
        stageLayout = QHBoxLayout()
        # self.XYstageLayout()
        xyStageLayout = self.XYstageLayout()
        oneDstageLayout = self.oneDstageLayout()
        stageLayout.addLayout(xyStageLayout)
        stageLayout.addLayout(oneDstageLayout)
        #Add a horizontal spacer:
        stageLayout.addStretch(1)
        stageLayout.setSizeConstraint(QHBoxLayout.SetMinimumSize) #type:ignore
        # print(stageLayout.children())
        xyLayoutWidth = 0
        for i in range(xyStageLayout.columnCount()):
            xyLayoutWidth += xyStageLayout.columnMinimumWidth(i)
        oneDstageLayoutWidth = 0
        for i in range(oneDstageLayout.columnCount()):
            oneDstageLayoutWidth += oneDstageLayout.columnMinimumWidth(i)
        
        containerWidget = QWidget()
        containerWidget.setLayout(stageLayout)
        containerWidget.setFixedWidth(xyLayoutWidth+oneDstageLayoutWidth)
        
        stageOvercapLayout = QHBoxLayout()
        stageOvercapLayout.addWidget(containerWidget)
        
        return stageLayout
    
    def relativeStagesLayout(self):
        """
        Returns the layout with the XY stage widgets in relative mode.

        This layout is used when the user is in relative mode.
        """
        stageLayout = QHBoxLayout()
        # stageLayout.addLayout(self.XYstageLayout())
        stageLayout.addLayout(self.oneDstageRelLayout())
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
            self.XYMoveEditField[f"X_{m}"].editingFinished.connect(lambda: self.storeAllControlValues())
            self.XYMoveEditField[f"Y_{m}"] = QLineEdit()
            XYStageSetMovementLayout.addWidget(self.XYMoveEditField[f"Y_{m}"],m,2,1,1, alignment=Qt.AlignmentFlag.AlignCenter)
            self.XYMoveEditField[f"Y_{m}"].editingFinished.connect(lambda: self.storeAllControlValues())
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
        #Also store the JSON if changed:
        self.oneDstageDropdown.currentTextChanged.connect(lambda: self.storeAllControlValues())
        #Set default value to default z stage of MM
        try:
            self.oneDstageDropdown.setCurrentText(self.core.get_focus_device()) #type:ignore
        except:
            pass
        #Add the dropdown to the layout:
        self.oneDStageLayout.addWidget(self.oneDstageDropdown,0,0)
        
        #Add left/right buttons and a label for the position
        self.oneDmoveButtons = {}
        for m in range(1,3):
            #Initialize buttons
            self.oneDmoveButtons[f'Left_{m}'] = QPushButton("⮝"*(3-m))
            self.oneDmoveButtons[f'Left_{m}'].clicked.connect(lambda index, m=m: self.moveOneDStage(m))
            self.oneDmoveButtons[f'Right_{m}'] = QPushButton("⮟"*(3-m))
            self.oneDmoveButtons[f'Right_{m}'].clicked.connect(lambda index, m=m: self.moveOneDStage(-m))
            
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
                self.oneDMoveEditField[stage][f'oneDStackedWidget_{stage}_{m}'].editingFinished.connect(lambda: self.storeAllControlValues())
            
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
    
    
    def oneDstageRelLayout(self):
        """
        Creates a UI layout to place all found one-D stages in a QStackedWidget and add the LineEdits etc. Also see oneDstageLayout()
        """
        #Create a layout
        self.oneDStageRelLayout = QGridLayout()
        
        #Creates a UI layout to move all found 1D stages
        #Find all 1D stages
        allStages = self.getDevicesOfDeviceType('StageDevice')
        
        #Create a drop-down menu that has these stages as options
        self.oneDstageRelDropdown = QComboBox()
        for stage in allStages:
            self.oneDstageRelDropdown.addItem(stage)
        #If it changes, call the update routine
        self.oneDstageRelDropdown.currentTextChanged.connect(lambda index: self.updateOneDstageRelLayout())
        #Also store the JSON if changed:
        self.oneDstageRelDropdown.currentTextChanged.connect(lambda: self.storeAllControlValues())
        #Set default value to default z stage of MM
        try:
            self.oneDstageRelDropdown.setCurrentText(self.core.get_focus_device()) #type:ignore
        except:
            pass
        #Add the dropdown to the layout:
        self.oneDStageRelLayout.addWidget(self.oneDstageRelDropdown,0,0)
        
        #Create a QGridBox for the movement sizes for each stage:
        self.oneDMoveRelEditFieldGridLayouts={}
        self.oneDMoveRelEditField={}
        self.oneDRelStackedWidget = QStackedWidget()
        for stage in allStages:
            self.oneDMoveRelEditFieldGridLayouts[stage] = QWidget()
            self.oneDMoveRelEditFieldGridLayouts[stage].setObjectName(stage)
            internalLayout = QGridLayout()
            self.oneDMoveRelEditFieldGridLayouts[stage].setLayout(internalLayout)
            self.oneDMoveRelEditField[stage] = {}
            
            internalLayout.addWidget(QLabel("Move"),0,0)
            self.oneDMoveRelEditField[stage] = QLineEdit()
            internalLayout.addWidget(self.oneDMoveRelEditField[stage],1,0)
            self.oneDMoveRelEditField[stage].setText("10")
            self.oneDMoveRelEditField[stage].editingFinished.connect(lambda: self.storeAllControlValues())
            
            self.oneDRelStackedWidget.addWidget(self.oneDMoveRelEditFieldGridLayouts[stage])
        
        self.oneDStageRelLayout.addWidget(self.oneDRelStackedWidget,1,0)
        
        #Get current info of the widget
        self.oneDinfoRelWidget = QLabel()
        self.oneDStageRelLayout.addWidget(self.oneDinfoRelWidget,2,0)
        #update the text
        # self.updateOneDstageRelLayout()
        
        #Store the values
        # self.storeAllControlValues()
        
        return self.oneDStageRelLayout
    
    def updateOneDstageRelLayout(self):
        """
        Updates the OneD stage layout text with the current values of the stage dropdown and the current position of the stage
        """
        logging.debug("Updating OneD stage layout")
        self.oneDinfoRelWidget.setText(f"{self.oneDstageRelDropdown.currentText()}\r\n {self.core.get_position(self.oneDstageRelDropdown.currentText()):.1f}") #type:ignore
        
        for widget_id in range(0,self.oneDRelStackedWidget.count()):
            widget = self.oneDRelStackedWidget.widget(widget_id)
            if widget.objectName() == self.oneDstageRelDropdown.currentText():
                self.oneDRelStackedWidget.setCurrentIndex(widget_id)
    
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
        
        
        #First add an editfield that has the value numerically:
        self.editFields[config_id] = QLineEdit()
        self.editFields[config_id].setText(str(currentSliderValue))
        #Only allow numbers/float values
        self.editFields[config_id].setValidator(QDoubleValidator())
        rowLayout.addWidget(self.editFields[config_id])
        self.editFields[config_id].editingFinished.connect(lambda config_id = config_id: self.on_sliderChanged(config_id,fromText=True,fromSlider=False))


        #Create the slider:
        self.sliders[config_id] = QSlider(Qt.Horizontal) #type: ignore
        #Give it a minimum size:
        self.sliders[config_id].setMinimumWidth(50)
        self.sliders[config_id].setRange(0,sliderPrecision)
        self.sliders[config_id].setValue(sliderValInSliderPrecision)
        self.sliders[config_id].slider_conversion_array = [lowerLimit,upperLimit,sliderPrecision]
        #Add a callback when it is changed:
        self.sliders[config_id].valueChanged.connect(lambda value, config_id = config_id: self.on_sliderChanged(config_id,fromSlider=True,fromText=False))
        # #Add the slider to the rowLayout:
        rowLayout.addWidget(self.sliders[config_id])
        pass
    
    def on_sliderChanged(self,config_id,fromText=False,fromSlider=True):
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
            
        #Get the new value from the slider:
        if fromSlider:
            newValue = self.sliders[config_id].value()
            #Get the true value from the conversion:
            trueValue = newValue/self.sliders[config_id].slider_conversion_array[2]*(self.sliders[config_id].slider_conversion_array[1]-self.sliders[config_id].slider_conversion_array[0])+self.sliders[config_id].slider_conversion_array[0]
        elif fromText:
            if self.editFields[config_id].text() != "":
                trueValue = float(self.editFields[config_id].text())
            else:
                trueValue = ""
        else:
            trueValue = "" #error out later on purpose
            
        if self.changes_update_MM:
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
                
        if trueValue != "" and trueValue != " ":
            trueValue = round(trueValue,3)
            #Set the slider/text if the other is changed
            if fromSlider:
                self.editFields[config_id].setText(str(trueValue))
            elif fromText:
                newValue = self.sliders[config_id].slider_conversion_array[2] * (trueValue - self.sliders[config_id].slider_conversion_array[0]) / (self.sliders[config_id].slider_conversion_array[1] - self.sliders[config_id].slider_conversion_array[0])
                self.sliders[config_id].setValue(int(newValue))
    
    def addInputField(self,rowLayout,config_id):
        """ 
        Add a editfield to a rowLayout for a given MMConfigItem.

        """
        #Get the config group name
        configGroupName = self.config_groups[config_id].configGroupName()

        self.editFields[config_id] = QLineEdit()
        #Add a callback when it is changed:
        self.editFields[config_id].editingFinished.connect(lambda config_id = config_id: self.onEditFieldChanged(config_id))
        # Add the editFields to the rowLayout:
        rowLayout.addWidget(self.editFields[config_id])
    
    def onEditFieldChanged(self,config_id):
        """
        Changes a micromanager config when an editfield has changed
        Args:
            config_id (int): The ID of the editfield box that triggered the event.
        Returns:
            None
        """

        CurrentText = self.editFields[config_id].text()
        #Get the config group name:
        configGroupName = self.config_groups[config_id].configGroupName()

        #An Editfield config by definition (?) only has a single property underneath, so get that:
        underlyingProperty = self.config_groups[config_id].core.get_available_configs(configGroupName).get(0)
        configdata = self.config_groups[config_id].core.get_config_data(configGroupName,underlyingProperty)
        device_label = configdata.get_setting(0).get_device_label()
        property_name = configdata.get_setting(0).get_property_name()

        #Set this property:
        self.config_groups[config_id].core.set_property(device_label,property_name,CurrentText)
        
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
            #Also update the corresponding editField
            self.editFields[config_id].setText(str(currentSliderValue))
            
        elif self.config_groups[config_id].isInputField():
            #A editfield config by definition (?) only has a single property underneath, so get that:
            configGroupName = self.config_groups[config_id].configGroupName()
            underlyingProperty = self.config_groups[config_id].core.get_available_configs(configGroupName).get(0)
            configdata = self.config_groups[config_id].core.get_config_data(configGroupName,underlyingProperty)
            device_label = configdata.get_setting(0).get_device_label()
            property_name = configdata.get_setting(0).get_property_name()

            #Finally we get the current value of the editfield
            currentValue = (self.config_groups[config_id].core.get_property(device_label,property_name))

            self.editFields[config_id].setText(currentValue)
        
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
