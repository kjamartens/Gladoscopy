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
from PyQt5.QtCore import QTimer,QDateTime, pyqtSignal
import logging
from typing import List, Iterable
import itertools
import queue
from napariHelperFunctions import getLayerIdFromName, InitateNapariUI
from PyQt5.QtWidgets import QTableWidget, QWidget, QInputDialog, QTableWidgetItem


class InteractiveListWidget(QTableWidget):
    """Creation of an interactive list widget, initially created for a nice XY list (similar to POS list in micromanager)
    """
    def __init__(self,fontsize=6):
        print('init InteractiveListWidget')
        super().__init__(rowCount=0, columnCount=2) #type: ignore
        self.horizontalHeader().setStretchLastSection(True)
        self.addDummyEntries()
        
        font = QFont()
        font.setPointSize(fontsize)
        self.setFont(font)
        # Reduce padding within cells
        self.setStyleSheet("QTableWidget::item { padding: 1px; }")
        
    def addDummyEntries(self):
        data = ["Entry 1","Entry 2","Entry 3"]
        for entry in data:
            self.addNewEntry(textEntry=entry)
            
    def setColumNames(self, names):
        self.setColumnCount(len(names))
        self.setHorizontalHeaderLabels(names)
        
    def deleteSelected(self):
        selectedRows = sorted(set(index.row() for index in self.selectedIndexes()), reverse=True)
        for row in selectedRows:
            self.removeRow(row)

    def moveUp(self):
        row = self.currentRow()
        if row > 0:
            self.swapRows(row, row - 1)
            
    def moveDown(self):
        row = self.currentRow()
        if row < self.rowCount() - 1 and row != -1:
            self.swapRows(row, row + 1)

    def swapRows(self, row1, row2):
        for col in range(self.columnCount()):
            item1 = self.takeItem(row1, col)
            item2 = self.takeItem(row2, col)
            self.setItem(row1, col, item2)
            self.setItem(row2, col, item1)
        self.setCurrentCell(row2, 0)

    def getIDValues(self):
        id_values = []
        for row in range(self.rowCount()):
            item_id = self.takeItem(row, 1)
            if item_id:
                id_values.append(float(item_id.text()))
        return id_values
    
    def addNewEntry(self,textEntry="New Entry",id=None):
        if id is None:
            if self.rowCount() == 0:
                id = 1
            else:
                try:
                    existing_ids = [int(self.item(row, 1).text()) for row in range(self.rowCount())]
                    id = max(existing_ids) + 1
                except:
                    id = self.rowCount() + 1
        print('added new entry')
        rowPosition = self.rowCount()
        self.insertRow(rowPosition)
        self.setItem(rowPosition, 0, QTableWidgetItem(textEntry))
        self.setItem(rowPosition, 1, QTableWidgetItem(str(id)))

class XYStageList(InteractiveListWidget):
    """Creation of an interactive list widget, initially created for a nice XY list (similar to POS list in micromanager)
    """
    def __init__(self):
        super().__init__()
        self.XYstageName = ''
        
    def setXYStageName(self, XYstageName):
        self.XYstageName = XYstageName


class CustomMainWindow(QWidget):
    def __init__(self):
        super().__init__()
        self.storingExceptions = ['core','layout','shared_data','gui','mda']

    def save_state(self, filename):
        print('SAVING STATE')
        state = {}
        for key, value in vars(self).items():
            if isinstance(value, QWidget):
                state[key] = {
                    'text': value.text() if hasattr(value, 'text') else None,
                    'checked': value.isChecked() if hasattr(value, 'isChecked') else None,
                    # Add more properties as needed
                }
            else:
                if key not in self.storingExceptions:
                    state[key] = value

        with open(filename, 'w') as file:
            json.dump(state, file, indent=4)

    def load_state(self, filename):
        print('LOADING STATE')
        with open(filename, 'r') as file:
            state = json.load(file)
            
        for key, value in state.items():
            try:
                if eval('isinstance(self.'+key+',QWidget)'):
                    isWidget = True
                    isVar = False
                elif eval('hasattr(self,\"'+key+'\")'):
                    isVar = True
                    isWidget = False
                else:
                    isVar = False
                    isWidget = False
                if isWidget:
                    widget = eval('self.'+key)
                    if value['text'] is not None:
                        widget.setText(value['text'])
                    if value['checked'] is not None:
                        widget.setChecked(value['checked'])
                elif isVar:
                    setattr(self, key, value)
            except:
                pass
            
            # if isinstance(value, dict):
            #     for widget_name, properties in value.items():
            #         widget = getattr(self, widget_name, None)
            #         if widget is not None:
            #             if hasattr(widget, 'setText') and 'text' in properties:
            #                 widget.setText(properties['text'])
            #             if hasattr(widget, 'setChecked') and 'checked' in properties:
            #                 widget.setChecked(properties['checked'])
            #             # Add more properties as needed
            # else:


class MDAGlados(CustomMainWindow):
    MDA_completed = pyqtSignal(bool)
    def handleSizeChange(self, size):
        newNrColumns = max(1,min(10, size.width() // 150))
        self.GUI_grid_width = newNrColumns
        
    def __init__(self,core,MM_JSON,layout,shared_data,hasGUI=False,num_time_points: int | None = 10, time_interval_s: float | List[float] = 0, z_start: float | None = None, z_end: float | None = None, z_step: float | None = None, channel_group: str | None = None, channels: list | None = None, channel_exposures_ms: list | None = None, xy_positions: Iterable | None = None, xyz_positions: Iterable | None = None, position_labels: List[str] | None = None, order: str = 'tpcz', exposure_ms: float | None = 90, GUI_show_exposure = True, GUI_show_xy = True, GUI_show_z=True, GUI_show_channel=False, GUI_show_time=True, GUI_show_order=True, GUI_show_storage=True, GUI_acquire_button=True):
        super().__init__()
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
        self.has_GUI = False
        self.core = core
        self.mda_analysis_thread = None
        self.MM_JSON = MM_JSON
        self.layout = layout
        self.shared_data = shared_data
        self.gui = {}
        self.lastTimeUpdateSize = time.time()
        self._GUI_grid_width = None
        self.data = None
        
        self.fully_started = False
        
        #initiate with an empty mda:
        self.mda = multi_d_acquisition_events(num_time_points=self.num_time_points, time_interval_s=self.time_interval_s,z_start=self.z_start,z_end=self.z_end,z_step=self.z_step,channel_group=self.channel_group,channels=self.channels,channel_exposures_ms=self.channel_exposures_ms,xy_positions=self.xy_positions,xyz_positions=self.xyz_positions,position_labels=self.position_labels,order=self.order) #type:ignore
        
        #Initiate GUI if wanted
        if hasGUI:
            self.initGUI(GUI_show_exposure=self.GUI_show_exposure,GUI_show_xy=self.GUI_show_xy, GUI_show_z=self.GUI_show_z, GUI_show_channel=self.GUI_show_channel, GUI_show_time=self.GUI_show_time, GUI_show_order=self.GUI_show_order, GUI_show_storage=self.GUI_show_storage, GUI_acquire_button=self.GUI_acquire_button)
            self.has_GUI = True
        
        self.fully_started = True
        #check if mda_state.json exists:
        if os.path.isfile('mda_state.json'):
            self.load_state('mda_state.json')
    
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
    
    @property
    def GUI_grid_width(self):
        return self._GUI_grid_width
    
    @GUI_grid_width.setter
    def GUI_grid_width(self, value):
        if value != self._GUI_grid_width:
            self._GUI_grid_width = value
            if self.has_GUI and self.fully_started:
                try:
                    print(f"updating gui with nr of columns: {self._GUI_grid_width}")
                    self.showOptionChanged()
                except:
                    pass
                
    def initGUI(self, GUI_show_exposure=True, GUI_show_xy = True, GUI_show_z=True, GUI_show_channel=True, GUI_show_time=True, GUI_show_order=True, GUI_show_storage=True, GUI_showOptions=True,GUI_acquire_button=True):
        #initiate the GUI
        #Create a Vertical+horizontal layout:
        self.gui = QGridLayout()
        self.GUI_grid_width = 7
        
        # Add groupboxes for xy, z, channel, time, order, storage
        self.exposureGroupBox = QGroupBox("Exposure")
        self.xyGroupBox = QGroupBox("XY")
        self.zGroupBox = QGroupBox("Z")
        self.channelGroupBox = QGroupBox("Channel")
        self.timeGroupBox = QGroupBox("Time")
        self.storageGroupBox = QGroupBox("Storage")
        self.showOptionsGroupBox = QGroupBox("Options")

        # Create layouts for each groupbox
        exposureLayout=QHBoxLayout()
        xyLayout = QGridLayout()
        zLayout = QGridLayout()
        channelLayout = QVBoxLayout()
        timeLayout = QGridLayout()
        orderLayout = QVBoxLayout()
        storageLayout = QGridLayout()
        showOptionsLayout = QGridLayout()

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
        
        #--------------- XY widget widget -----------------------------------------------
        #First a dropdown to select the xy stage:
        
        #Adding a list widget to add a list of xy positions
        self.xypositionListWidget = XYStageList()
        self.xypositionListWidget.setColumNames(["Name", "ID"])
        
        self.xy_stagesDropdownLabel = QLabel("XY Stage:")
        self.xy_stagesDropdown = QComboBox()
        XYstages = self.getDevicesOfDeviceType('XYStageDevice')
        #add the options to the dropdown:
        for stage in XYstages:
            self.xy_stagesDropdown.addItem(stage)
        #Add a callback if we change this dropdown:
        self.xy_stagesDropdown.currentIndexChanged.connect(lambda: self.xypositionListWidget.setXYStageName(self.xy_stagesDropdown.currentText()))
        
        #Add them to the layout
        xyLayout.addWidget(self.xy_stagesDropdownLabel,0,0)
        xyLayout.addWidget(self.xy_stagesDropdown,0,1)
        
        self.xypositionListWidget.setXYStageName(self.xy_stagesDropdown.currentText)

        self.xypositionListWidget_deleteButton = QPushButton('Delete Selected')
        self.xypositionListWidget_moveUpButton = QPushButton('Move Up')
        self.xypositionListWidget_moveDownButton = QPushButton('Move Down')
        self.xypositionListWidget_addButton = QPushButton('Add New Entry')
        
        self.xypositionListWidget_deleteButton.clicked.connect(self.xypositionListWidget.deleteSelected)
        self.xypositionListWidget_moveUpButton.clicked.connect(self.xypositionListWidget.moveUp)
        self.xypositionListWidget_moveDownButton.clicked.connect(self.xypositionListWidget.moveDown)
        self.xypositionListWidget_addButton.clicked.connect(lambda: self.xypositionListWidget.addNewEntry(textEntry="Your Text Entry"))

        
        xyLayout.addWidget(self.xypositionListWidget,1,0,6,1)
        xyLayout.addWidget(self.xypositionListWidget_deleteButton,2,1)
        xyLayout.addWidget(self.xypositionListWidget_moveUpButton,3,1)
        xyLayout.addWidget(self.xypositionListWidget_moveDownButton,4,1)
        xyLayout.addWidget(self.xypositionListWidget_addButton,5,1)
        
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

        #--------------- Show options widget -----------------------------------------------
        #This should have checkboxes for exposure, xy, z, channel, time, order, storage. If these checkboxes are clicked, the GUI should be updated accordingly:
        self.GUI_show_exposure_chkbox = QCheckBox("Exposure")
        self.GUI_show_xy_chkbox = QCheckBox("XY")
        self.GUI_show_z_chkbox = QCheckBox("Z")
        self.GUI_show_channel_chkbox = QCheckBox("Channel")
        self.GUI_show_time_chkbox = QCheckBox("Time")
        self.GUI_show_storage_chkbox = QCheckBox("Storage")
        #initialise the checkboxes based on the values in this GUI:
        self.GUI_show_exposure_chkbox.setChecked(GUI_show_exposure)
        self.GUI_show_xy_chkbox.setChecked(GUI_show_xy)
        self.GUI_show_z_chkbox.setChecked(GUI_show_z)
        self.GUI_show_channel_chkbox.setChecked(GUI_show_channel)
        self.GUI_show_time_chkbox.setChecked(GUI_show_time)
        self.GUI_show_storage_chkbox.setChecked(GUI_show_storage)
        #Add lambda functions to all of them that all run the same function: showOptionChanged():
        self.GUI_show_exposure_chkbox.stateChanged.connect(lambda: self.showOptionChanged())
        self.GUI_show_xy_chkbox.stateChanged.connect(lambda: self.showOptionChanged())
        self.GUI_show_z_chkbox.stateChanged.connect(lambda: self.showOptionChanged())
        self.GUI_show_channel_chkbox.stateChanged.connect(lambda: self.showOptionChanged())
        self.GUI_show_time_chkbox.stateChanged.connect(lambda: self.showOptionChanged())
        self.GUI_show_storage_chkbox.stateChanged.connect(lambda: self.showOptionChanged())
        
        
        font = QFont()
        font.setPointSize(7)  # Set the desired font size

        [checkbox.setFont(font) for checkbox in [self.GUI_show_exposure_chkbox, self.GUI_show_xy_chkbox, self.GUI_show_z_chkbox, self.GUI_show_channel_chkbox, self.GUI_show_time_chkbox, self.GUI_show_storage_chkbox]]

        showOptionsLayout.addWidget(self.GUI_show_exposure_chkbox,0,0)
        showOptionsLayout.addWidget(self.GUI_show_xy_chkbox,0,1)
        showOptionsLayout.addWidget(self.GUI_show_z_chkbox,0,2)
        showOptionsLayout.addWidget(self.GUI_show_channel_chkbox,1,0)
        showOptionsLayout.addWidget(self.GUI_show_time_chkbox,1,1)
        showOptionsLayout.addWidget(self.GUI_show_storage_chkbox,1,2)
        
        # Set layouts for each groupbox
        self.exposureGroupBox.setLayout(exposureLayout)
        self.xyGroupBox.setLayout(xyLayout)
        self.zGroupBox.setLayout(zLayout)
        self.channelGroupBox.setLayout(channelLayout)
        self.timeGroupBox.setLayout(timeLayout)
        self.storageGroupBox.setLayout(storageLayout)
        self.showOptionsGroupBox.setLayout(showOptionsLayout)

        # Add groupboxes to the main layout, only if they should be shown. The position of the gridbox is based on whether the previous ones are added or not:
        self.updateGUIwidgets(GUI_show_exposure=GUI_show_exposure,GUI_show_xy=GUI_show_xy, GUI_show_z=GUI_show_z, GUI_show_channel=GUI_show_channel, GUI_show_time=GUI_show_time, GUI_show_storage=GUI_show_storage,GUI_showOptions=GUI_showOptions,GUI_acquire_button=GUI_acquire_button)
        
        if self.layout is not None:
            #Add the layout to the main layout
            self.layout.addLayout(self.gui,0,0)
            
            # Changing font and padding of all widgets
            font = QFont("Arial", 7)
            for i in range(self.gui.count()):
                try:
                    item = self.gui.itemAt(i)
                    if item.widget():
                        item.widget().setFont(font)
                        item.widget().setStyleSheet("padding: 2px; margin: 1px; spacing: 1px;")  # Change padding as needed
                except:
                    pass
        
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
        self.orderDropdown.currentTextChanged.connect(lambda: self.get_MDA_events_from_GUI())
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
        self.updateGUIwidgets(GUI_show_exposure=self.GUI_show_exposure_chkbox.isChecked(), GUI_show_xy = self.GUI_show_xy_chkbox.isChecked(), GUI_show_z=self.GUI_show_z_chkbox.isChecked(), GUI_show_channel=self.GUI_show_channel_chkbox.isChecked(), GUI_show_time=self.GUI_show_time_chkbox.isChecked(), GUI_show_storage=self.GUI_show_storage_chkbox.isChecked(),GUI_showOptions=True,GUI_acquire_button=self.GUI_acquire_button)
        self.get_MDA_events_from_GUI()
    
    def updateGUIwidgets(self,GUI_show_exposure=True, GUI_show_xy = False, GUI_show_z=True, GUI_show_channel=False, GUI_show_time=True, GUI_show_storage=True,GUI_showOptions=True,gridWidth=4,GUI_acquire_button=True):
        gridWidth = self.GUI_grid_width
        # Remove the widgets from their parent
        # self.exposureGroupBox.setParent(None) # type: ignore
        # self.xyGroupBox.setParent(None) # type: ignore
        # self.zGroupBox.setParent(None) # type: ignore
        # self.channelGroupBox.setParent(None) # type: ignore
        # self.timeGroupBox.setParent(None) # type: ignore
        # self.orderGroupBox.setParent(None) # type: ignore
        # self.storageGroupBox.setParent(None) # type: ignore
        # self.showOptionsGroupBox.setParent(None)  # type: ignore

        # # Clear the layout
        # while self.gui.count(): # type: ignore
        #     item = self.gui.takeAt(0) # type: ignore
        #     widget = item.widget()
        #     if widget:
        #         widget.deleteLater()
        #redraw the self.gui:
        self.gui.update()
        QCoreApplication.processEvents()
        
        #At the beginning add an options groupbox, which has all the checkboxes and storage/acquire
        optionsBGroupBox = QWidget()
        optionsBLayout = QVBoxLayout()
        optionsBGroupBox.setLayout(optionsBLayout)
        optionsBLayout.addWidget(self.showOptionsGroupBox) # type: ignore
        self.showOptionsGroupBox.setEnabled(True)
        optionsBLayout.addWidget(self.storageGroupBox) # type: ignore
        if GUI_show_storage: 
            self.storageGroupBox.setEnabled(True)
        else:
            self.storageGroupBox.setEnabled(False)
        self.GUI_acquire_button = QPushButton("Acquire")
        self.GUI_acquire_button.clicked.connect(lambda index: self.MDA_acq_from_GUI())
        optionsBLayout.addWidget(self.GUI_acquire_button) # type: ignore
        if GUI_acquire_button:
            self.GUI_acquire_button.setEnabled(True)
        else:
            self.GUI_acquire_button.setEnabled(False)
        
        self.gui.addWidget(optionsBGroupBox, 0, 0) # type: ignore
        
        #Add order/exposure/time as single groupbox
        orderexposuretimegroupbox = QWidget()
        orderexposuretimelayout = QVBoxLayout()
        orderexposuretimegroupbox.setLayout(orderexposuretimelayout)
        
        self.orderGroupBox = QGroupBox("Order")
        orderlayout = self.createOrderLayout(GUI_show_channel, GUI_show_time, GUI_show_xy, GUI_show_z)
        
        self.orderGroupBox.setLayout(orderlayout)
        orderexposuretimelayout.addWidget(self.orderGroupBox) # type: ignore
        orderexposuretimelayout.addWidget(self.exposureGroupBox) # type: ignore
        if GUI_show_exposure:
            self.exposureGroupBox.setEnabled(True)
        else:
            self.exposureGroupBox.setEnabled(False)
        orderexposuretimelayout.addWidget(self.timeGroupBox) # type: ignore
        if GUI_show_time:
            self.timeGroupBox.setEnabled(True)
        else:
            self.timeGroupBox.setEnabled(False)
            # QCoreApplication.processEvents()
        self.gui.addWidget(orderexposuretimegroupbox, 1//gridWidth, 1%gridWidth) # type: ignore
        
        #Add XY, Z, Channel, groupboxes as individual groupboxes
        curindex = 2
        self.gui.addWidget(self.xyGroupBox, curindex//gridWidth, curindex%gridWidth) # type: ignore
        curindex+=1
        if GUI_show_xy:
            self.xyGroupBox.setEnabled(True)
        else:
            self.xyGroupBox.setEnabled(False)
            # QCoreApplication.processEvents()
        self.gui.addWidget(self.zGroupBox, curindex//gridWidth, curindex%gridWidth) # type: ignore
        curindex+=1
        if GUI_show_z:
            self.zGroupBox.setEnabled(True)
        else:
            self.zGroupBox.setEnabled(False)
            # QCoreApplication.processEvents()
        self.gui.addWidget(self.channelGroupBox, curindex//gridWidth, curindex%gridWidth) # type: ignore
        curindex+=1
        if GUI_show_channel:
            self.channelGroupBox.setEnabled(True)
        else:
            self.channelGroupBox.setEnabled(False)
            # QCoreApplication.processEvents()
        
        
        self.gui.setColumnStretch(99,gridWidth+1) # type: ignore
        self.gui.setRowStretch(99,gridWidth+1) # type: ignore
        
        QCoreApplication.processEvents()
        
        #redraw the self.gui:
        self.gui.update()
    
    def MDA_acq_finished(self):
        self.shared_data.mda_acq_done_signal.disconnect(self.MDA_acq_finished)
        self.data = self.shared_data.mdaDatasets[-1]
        print('MDA acq data finished and data stored!')
        self.MDA_completed.emit(True)
    
    def MDA_acq_from_GUI(self):
        print('At MDA_acq_from_GUI')
        self.shared_data._mdaMode = False
        
        #Set the exposure time:
        self.core.set_exposure(self.exposure_ms)
        
        print('starting mda mode')
        #Set the location where to save the mda
        self.shared_data._mdaModeSaveLoc = [self.storageFolder,self.storageFileName]
        #Set whether the napariviewer should (also) try to connect to the mda
        # self.shared_data._mdaModeNapariViewer = self.shared_data.napariViewer
        #Set the mda parameters
        self.shared_data._mdaModeParams = self.mda
        #Set this MDA object as the active MDA object in the shared_data
        self.shared_data.activeMDAobject = self
        self.shared_data.mda_acq_done_signal.connect(self.MDA_acq_finished)
        #And set the mdamode to be true
        self.shared_data.mdaMode = True
        print('ended setting mdamode params')
        
        pass
    
    def get_MDA_events_from_GUI(self):
        #This function will be run every time any option in the GUI is changed.
        print('starting get_MDA_events_from_GUI')
        #Make this somewhat readable:
        if self.exposureGroupBox.isEnabled():
            try:
                self.exposure_ms = float(self.exposureEntry.text())
                if self.exposureDropdown.currentText() == 's':
                    self.exposure_ms *= 1000
            except:
                self.exposure_ms = None
        
        if self.timeGroupBox.isEnabled():
            try:
                self.num_time_points = int(self.timePointEntry.text())
                self.time_interval_s = float(self.timeIntervalEntry.text())
                if self.timeIntervalDropdown.currentText() == 'ms':
                    self.time_interval_s /= 1000
            except:
                self.num_time_points = None
                self.time_interval_s = None
                
        if self.orderGroupBox.isEnabled():
            self.order = self.orderDropdown.currentText()
        
        if self.storageGroupBox.isEnabled():
            self.storageFolder = self.storageFolderEntry.text()
            self.storageFileName = self.storageFileNameEntry.text()
        
        if self.zGroupBox.isEnabled():
            try:
                #We also need to set the shared_data focus device for proper z-functioning
                self.shared_data.core.set_focus_device(self.z_oneDstageDropdown.currentText())
                
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
                self.shared_data.core.set_focus_device(self.shared_data._defaultFocusDevice)
        else:
            self.shared_data.core.set_focus_device(self.shared_data._defaultFocusDevice)
        
        #initiate with an empty mda:
        self.mda = multi_d_acquisition_events(num_time_points=self.num_time_points, time_interval_s=self.time_interval_s,z_start=self.z_start,z_end=self.z_end,z_step=self.z_step,channel_group=self.channel_group,channels=self.channels,channel_exposures_ms=self.channel_exposures_ms,xy_positions=self.xy_positions,xyz_positions=self.xyz_positions,position_labels=self.position_labels,order=self.order) #type:ignore
        
        print(self.mda)
        if self.fully_started:
            self.save_state('mda_state.json')
        print('ended get_MDA_events_from_GUI')
        
        pass
    
    def printText(self):
        print(self.getEvents())
    
    def getEvents(self):
        return self.mda
    
    def getGui(self):
        return self
    
    def setMDAparams(self,mdaparams):
        self.mda = mdaparams
