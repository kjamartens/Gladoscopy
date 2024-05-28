import sys
import time
from AnalysisClass import *
from PyQt5.QtWidgets import QLineEdit, QFrame, QGridLayout, QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QLabel, QComboBox, QSpacerItem, QSizePolicy, QSlider, QCheckBox, QGroupBox, QVBoxLayout, QFileDialog, QRadioButton
from PyQt5.QtCore import Qt, pyqtSignal, QObject, QThread, QCoreApplication
from PyQt5.QtGui import QResizeEvent, QIcon, QPixmap, QFont, QDoubleValidator, QIntValidator
from PyQt5 import uic
import os
# import PyQt5.QtWidgets
import json
from pycromanager import Core, multi_d_acquisition_events, Acquisition
import numpy as np
import asyncio
import pyqtgraph as pg
import matplotlib.pyplot as plt
from matplotlib import colormaps # type: ignore
import napariGlados
#For drawing
import matplotlib
import utils
from utils import CustomMainWindow
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


#region List Widgets
class InteractiveListWidget(QTableWidget):
    """
    Creation of an interactive list widget, initially created for a nice XY list (similar to POS list in micromanager)
    """
    def __init__(self,fontsize=6,columnCount=2):
        """
        Initializes an InteractiveListWidget.
        
        Args:
            fontsize (int): The font size to be set for the widget. Default is 6.
            columnCount (int): The number of columns to be displayed in the widget. Default is 2.
        
        Returns:
            None
        """
        
        logging.debug('init InteractiveListWidget')
        super().__init__(rowCount=0, columnCount=columnCount) #type: ignore
        self.horizontalHeader().setStretchLastSection(True)
        
        font = QFont()
        font.setPointSize(fontsize)
        self.setFont(font)
        # Reduce padding within cells
        self.setStyleSheet("QTableWidget::item { padding: 1px; }")
        
        self.parentWidget=None #type:ignore
            
    def setColumNames(self, names):
        """
        Set column names for the interactive list table.
        
        Args:
            names (list): A list of column names to be set.
        
        Returns:
            None
        """
        
        self.setColumnCount(len(names))
        self.setHorizontalHeaderLabels(names)
        
    def deleteSelected(self):
        """
        Deletes selected rows from the table.
        
        Args:
            None
        
        Returns:
            None
        """
        
        selectedRows = sorted(set(index.row() for index in self.selectedIndexes()), reverse=True)
        for row in selectedRows:
            self.removeRow(row)

    def deleteAll(self):
        """
        Deletes all rows in the table.
        
        Args:
            None
        
        Returns:
            None
        """
        for row in range(self.rowCount() - 1, -1, -1):
            self.removeRow(row)

    def moveUp(self):
        """
        Moves the current row up by swapping it with the row above.
        
            Args:
                None
        
            Returns:
                None
        """
        row = self.currentRow()
        if row > 0:
            self.swapRows(row, row - 1)
            
    def moveDown(self):
        """
        Moves the current row down by swapping it with the row below.
        
        Args:
            None
        
        Returns:
            None
        """
        row = self.currentRow()
        if row < self.rowCount() - 1 and row != -1:
            self.swapRows(row, row + 1)

    def getIDValues(self):
        """
        Get the ID values from the second column of the table.
        
        Args:
            None
        
        Returns:
            list: A list of float values extracted from the second column of the table.
        """
        id_values = []
        for row in range(self.rowCount()):
            item_id = self.takeItem(row, 1)
            if item_id:
                id_values.append(float(item_id.text()))
        return id_values

class ChannelList(InteractiveListWidget):
    """
    Creation of an interactive list widget, initially created for a nice channel list
    Extends InteractiveListWidget
    """
    def __init__(self,parent=None):
        """
        Initializes the channellist class within the given parent widget.
        
        Args:
            parent: The parent widget to set for the current instance.
        
        Returns:
            None
        """
        super().__init__(columnCount=3)
        self.channelName = ''
        self.parentWidget=parent #type:ignore
        
    def setChannelName(self, channelName):
        """
        Set the name of the channel.
        
        Args:
            channelName: A string representing the name of the channel.
        
        Returns:
            None
        """
        self.channelName = channelName
        
    def swapRows(self, row1, row2):
        """
        Swap rows in the table.
        
        Args:
            row1 (int): The index of the first row to swap.
            row2 (int): The index of the second row to swap.
        
        Returns:
            None
        """
        for col in range(self.columnCount()):
            if col == 0:
                combobox1 = self.cellWidget(row1, col)
                combobox2 = self.cellWidget(row2, col)
                
                chosenEntry1 = combobox1.currentText()
                chosenEntry2 = combobox2.currentText()
                
                combobox1.setCurrentText(chosenEntry2)
                combobox2.setCurrentText(chosenEntry1)
            else:
                item1 = self.takeItem(row1, col)
                item2 = self.takeItem(row2, col)
                self.setItem(row1, col, item2)
                self.setItem(row2, col, item1)
        self.setCurrentCell(row2, 1)
        
    def addNewEntry(self,channelEntry=None,exposureEntry=None):
        """
        Add a new entry to the table.
        
        Args:
            channelEntry (str): The channel entry to be added to the table.
            exposureEntry (str): The exposure entry to be added to the table.
        
        Returns:
            None
        """
        #Add the current exposure time as text as textentry:
        if 'channelDropdown' in dir(self.parentWidget):
            rowPosition = self.rowCount()
            self.insertRow(rowPosition)
            #Create a dropbox with two options:
            newdropbox = QComboBox()
            #Currently selected channel: self.parentWidget.channelDropdown.currentText()
            #Find the corresponding options:
            currentChannel = self.parentWidget.channelDropdown.currentText()
            nrConfigs = self.parentWidget.core.get_available_configs(currentChannel).size()
            for i in range(nrConfigs):
                newdropbox.addItem(self.parentWidget.core.get_available_configs(currentChannel).get(i))
            if channelEntry is not None:
                try:
                    newdropbox.setCurrentText(channelEntry)
                except:
                    logging.warning('Wrong mix of channel and entries')
                    pass
            self.setCellWidget(rowPosition, 0, newdropbox)
            # self.setItem(rowPosition, 1, QTableWidgetItem(textEntry))
            if exposureEntry == None:
                currentexposure = self.parentWidget.core.get_exposure()
                self.setItem(rowPosition, 1, QTableWidgetItem(str(currentexposure)))
            else:
                self.setItem(rowPosition, 1, QTableWidgetItem(exposureEntry))

class XYStageList(InteractiveListWidget):
    """
    Creation of an interactive list widget, initially created for a nice XY list (similar to POS list in micromanager)
    Extends InteractiveListWidget
    """
    def __init__(self):
        """
        Initializes the XY stage, only setting the name to empty
        
        Args:
            None
        
        Returns:
            None
        """
        super().__init__()
        self.XYstageName = ''
        
    def setXYStageName(self, XYstageName):
        """
        Set the name of the XY stage.
        
        Args:
            XYstageName (str): The name of the XY stage to be set.
        
        Returns:
            None
        """
        self.XYstageName = XYstageName
    
    def swapRows(self, row1, row2):
        """
        Swap rows in the table widget.
        
        Args:
            row1 (int): The index of the first row to swap.
            row2 (int): The index of the second row to swap.
        
        Returns:
            None
        """
        for col in range(self.columnCount()):
            item1 = self.takeItem(row1, col)
            item2 = self.takeItem(row2, col)
            self.setItem(row1, col, item2)
            self.setItem(row2, col, item1)
        self.setCurrentCell(row2, 0)
        
    def addNewEntry(self,textEntry="New Entry",id=None):
        """
        Add a new entry to the table.
        
        Args:
            textEntry (str): The text entry to be added. Default is "New Entry".
            id (int): The ID of the new entry. If not provided, it will be automatically generated based on existing IDs.
        
        Returns:
            None
        """
        if id is None:
            if self.rowCount() == 0:
                id = 1
            else:
                try:
                    #add the new ID to be the max existing ID + 1
                    existing_ids = [int(self.item(row, 1).text()) for row in range(self.rowCount())]
                    id = max(existing_ids) + 1
                except:
                    id = self.rowCount() + 1
        rowPosition = self.rowCount()
        self.insertRow(rowPosition)
        self.setItem(rowPosition, 0, QTableWidgetItem(textEntry))
        self.setItem(rowPosition, 1, QTableWidgetItem(str(id)))
#endregion

class MDAGlados(CustomMainWindow):
    """ 
    Class that handles the multi-Dimensional acquisition of Pycromanager
    """
    #Pysignal should be outside the functions for proper init
    MDA_completed = pyqtSignal(bool)
    def __init__(self,core,MM_JSON,layout,
                shared_data,
                hasGUI=False,
                num_time_points: int | None = 10, 
                time_interval_s: float | List[float] = 0, 
                z_start: float | None = None, 
                z_end: float | None = None, 
                z_step: float | None = None, 
                z_stage_sel : str | None = None,
                z_nr_steps: float | None = None,
                z_step_distance: float | None = None,
                z_nrsteps_radio_sel: bool | None = None,
                z_stepdistance_radio_sel: bool | None = None,
                channel_group: str | None = None, 
                channels: list | None = None, 
                channel_exposures_ms: list | None = None, 
                xy_positions: Iterable | None = None, 
                xyz_positions: Iterable | None = None, 
                position_labels: List[str] | None = None, 
                order: str = 'tpcz', 
                exposure_ms: float | None = 90, 
                storage_folder: str | None = None,
                storage_file_name: str | None = None,
                GUI_show_exposure = True, 
                GUI_show_xy = True, 
                GUI_show_z = True, 
                GUI_show_channel = True, 
                GUI_show_time = True, 
                GUI_show_order = True, 
                GUI_show_storage = True, 
                GUI_acquire_button = True,
                autoSaveLoad = False,
                parent=None):
        """
        Initializes the MDAGlados class with the provided parameters.
        
        Args:
            core: Core object for communication with the microscope.
            MM_JSON: JSON object containing metadata.
            layout: Layout object for GUI layout.
            shared_data: Shared data object for communication between modules.
            hasGUI: Boolean indicating whether GUI should be displayed (default is False).
            num_time_points: Number of time points (default is 10).
            time_interval_s: Time interval in seconds between acquisitions (default is 0).
            z_start: Starting position of the Z-stack (default is None).
            z_end: Ending position of the Z-stack (default is None).
            z_step: Step size for Z-stack acquisition (default is None).
            z_stage_sel: Selected Z-stage for acquisition (default is None).
            z_nr_steps: Number of steps in the Z-stack (default is None).
            z_step_distance: Distance between Z-stack steps (default is None).
            z_nrsteps_radio_sel: Boolean indicating whether number of steps is selected (default is None).
            z_stepdistance_radio_sel: Boolean indicating whether step distance is selected (default is None).
            channel_group: Group of channels to acquire (default is None).
            channels: List of channels to acquire (default is None).
            channel_exposures_ms: List of exposure times for each channel in milliseconds (default is None).
            xy_positions: Iterable of XY positions to acquire (default is None).
            xyz_positions: Iterable of XYZ positions to acquire (default is None).
            position_labels: List of labels for positions (default is None).
            order: Order of acquisition (default is 'tpcz').
            exposure_ms: Exposure time in milliseconds (default is 90).
            storage_folder: Folder path for storing data (default is None).
            storage_file_name: Name of the storage file (default is None).
            GUI_show_exposure: Boolean indicating whether to show exposure settings in GUI (default is True).
            GUI_show_xy: Boolean indicating whether to show XY settings in GUI (default is True).
            GUI_show_z: Boolean indicating whether to show Z settings in GUI (default is True).
            GUI_show_channel: Boolean indicating whether to show channel settings in GUI (default is True).
            GUI_show_time: Boolean indicating whether to show time settings in GUI (default is True).
            GUI_show_order: Boolean indicating whether to show order settings in GUI (default is True).
            GUI_show_storage: Boolean indicating whether to show storage settings in GUI (default is True).
            GUI_acquire_button: Boolean indicating whether to show the acquisition button in GUI (default is True).
            autoSaveLoad: Boolean indicating whether to automatically save and load settings (default is False).
        
        Returns:
            None
        """
        
        super().__init__()
        
        #If run as plugin, we need to specify the globals like this:
        if parent is not None:
            global livestate, napariViewer
            livestate = parent.livestate
            napariViewer = parent.napariViewer
            
        self.num_time_points = num_time_points
        self.time_interval_s = time_interval_s
        self.z_start = z_start
        self.z_end = z_end
        self.z_step = z_step
        self.z_stage_sel = z_stage_sel
        self.z_nr_steps = z_nr_steps
        self.z_step_distance = z_step_distance
        self.z_nrsteps_radio_sel = z_nrsteps_radio_sel
        self.z_stepdistance_radio_sel = z_stepdistance_radio_sel
        self.channel_group = channel_group
        self.channels = channels
        self.channel_exposures_ms = channel_exposures_ms
        self.storage_folder = storage_folder
        self.storage_file_name = storage_file_name
        self.xy_positions = xy_positions
        self.xyz_positions = xyz_positions
        self.position_labels = position_labels
        self.order = order
        self.exposure_ms = exposure_ms
        self.GUI_show_exposure = GUI_show_exposure
        self.GUI_show_xy = GUI_show_xy
        self.GUI_show_z = GUI_show_z
        self.GUI_show_channel = GUI_show_channel
        self.GUI_show_time = GUI_show_time
        self.GUI_show_order = GUI_show_order
        self.GUI_show_storage = GUI_show_storage
        self.autoSaveLoad = autoSaveLoad

        
        self.GUI_exposure_enabled = GUI_show_exposure
        self.GUI_xy_enabled = GUI_show_xy
        self.GUI_z_enabled = GUI_show_z
        self.GUI_channel_enabled = GUI_show_channel
        self.GUI_time_enabled = GUI_show_time
        self.GUI_order_enabled = GUI_show_order
        self.GUI_storage_enabled = GUI_show_storage
        
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
        
        #Initiate GUI if wanted
        if hasGUI:
            self.initGUI(GUI_show_exposure=self.GUI_show_exposure,GUI_show_xy=self.GUI_show_xy, GUI_show_z=self.GUI_show_z, GUI_show_channel=self.GUI_show_channel, GUI_show_time=self.GUI_show_time, GUI_show_order=self.GUI_show_order, GUI_show_storage=self.GUI_show_storage, GUI_acquire_button=self.GUI_acquire_button)
            self.has_GUI = True
        
        #initiate with an empty mda, or mda based on GUI:
        self.mda = multi_d_acquisition_events(num_time_points=self.num_time_points, time_interval_s=self.time_interval_s,z_start=self.z_start,z_end=self.z_end,z_step=self.z_step,channel_group=self.channel_group,channels=self.channels,channel_exposures_ms=self.channel_exposures_ms,xy_positions=self.xy_positions,xyz_positions=self.xyz_positions,position_labels=self.position_labels,order=self.order) #type:ignore
        
        self.fully_started = True
        #check if mda_state.json exists:
        # if os.path.isfile('mda_state.json'):
        #     if self.autoSaveLoad:
        #         self.load_state('mda_state.json')
    
    #region properties
    @property
    def GUI_grid_width(self):
        """
        Get the width of the GUI grid.
        
        Returns:
            int: The width of the GUI grid.
        """
        
        return self._GUI_grid_width
    
    @GUI_grid_width.setter
    def GUI_grid_width(self, value):
        """
        Updates the width of the GUI grid.
        
        Args:
            value: An integer representing the new width of the GUI grid.
        
        Returns:
            None
        """
        
        if value != self._GUI_grid_width:
            self._GUI_grid_width = value
            if self.has_GUI and self.fully_started:
                try:
                    logging.debug(f"updating gui with nr of columns: {self._GUI_grid_width}")
                    self.showOptionChanged()
                except:
                    pass
    #endregion
    
    #region GUI
    def initGUI(self, GUI_show_exposure=True, GUI_show_xy = True, GUI_show_z=True, GUI_show_channel=True, GUI_show_time=True, GUI_show_order=True, GUI_show_storage=True, GUI_showOptions=True,GUI_acquire_button=True):
        """
        Initiate the GUI.
        
        Args:
            GUI_show_exposure (bool): Whether to show the exposure widget. Default is True.
            GUI_show_xy (bool): Whether to show the XY widget. Default is True.
            GUI_show_z (bool): Whether to show the Z widget. Default is True.
            GUI_show_channel (bool): Whether to show the Channel widget. Default is True.
            GUI_show_time (bool): Whether to show the Time widget. Default is True.
            GUI_show_order (bool): Whether to show the Order widget. Default is True.
            GUI_show_storage (bool): Whether to show the Storage widget. Default is True.
            GUI_showOptions (bool): Whether to show the Options widget. Default is True.
            GUI_acquire_button (bool): Whether to show the Acquire button. Default is True.
        
        Returns:
            None
        """
        
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
        channelLayout = QGridLayout()
        timeLayout = QGridLayout()
        orderLayout = QVBoxLayout()
        storageLayout = QGridLayout()
        showOptionsLayout = QGridLayout()

        # Add widgets to each layout
        # --------------- Exposure widget -----------------------------------------------
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
        if self.num_time_points is not None:
            self.timePointEntry.setText(str(self.num_time_points))
        self.timePointEntry.setValidator(QIntValidator())
        self.timeIntervalLabel = QLabel("Time interval:")
        self.timeIntervalEntry = QLineEdit()
        if self.time_interval_s is not None:
            self.timeIntervalEntry.setText(str(self.time_interval_s))
        self.timeIntervalEntry.setValidator(QDoubleValidator())
        self.timeIntervalDropdown = QComboBox()
        self.timeIntervalDropdown.addItem("ms")
        self.timeIntervalDropdown.addItem("s")
        #Adding widgets to layout
        timeLayout.addWidget(self.timePointLabel,0,0)
        timeLayout.addWidget(self.timePointEntry,0,1)
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
        if self.storage_folder is not None:
            self.storageFolderEntry.setText(self.storage_folder)
        self.storageFolderButton = QPushButton('...')
        #add a lambda function when this is pressed to search for a folder:
        self.storageFolderButton.clicked.connect(lambda: self.storageFolderEntry.setText(QFileDialog.getExistingDirectory()))
        #Then add a label and entry field for the file name:
        self.storageFileNameLabel = QLabel("File name:")
        self.storageFileNameEntry = QLineEdit()
        if self.storage_file_name is not None:
            self.storageFileNameEntry.setText(self.storage_file_name)
        #Adding widgets to layout
        storageLayout.addWidget(self.storageFolderLabel,0,0)
        storageLayout.addWidget(self.storageFolderEntry,0,1)
        storageLayout.addWidget(self.storageFolderButton,0,2)
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
        
        #Initisalise the XY position list
        self.xypositionListWidget.setXYStageName(self.xy_stagesDropdown.currentText)
        #Buttons for the xy position list
        self.xypositionListWidget_deleteButton = QPushButton('Delete Selected')
        self.xypositionListWidget_moveUpButton = QPushButton('Move Up')
        self.xypositionListWidget_moveDownButton = QPushButton('Move Down')
        self.xypositionListWidget_addButton = QPushButton('Add New Entry')
        #Adding callbacks to the xy position list buttons
        self.xypositionListWidget_deleteButton.clicked.connect(self.xypositionListWidget.deleteSelected)
        self.xypositionListWidget_moveUpButton.clicked.connect(self.xypositionListWidget.moveUp)
        self.xypositionListWidget_moveDownButton.clicked.connect(self.xypositionListWidget.moveDown)
        self.xypositionListWidget_addButton.clicked.connect(lambda: self.xypositionListWidget.addNewEntry(textEntry="Your Text Entry"))

        #Adding widgets to layout
        xyLayout.addWidget(self.xy_stagesDropdownLabel,0,0)
        xyLayout.addWidget(self.xy_stagesDropdown,0,1)
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
        if self.z_stage_sel is not None:
            if self.z_stage_sel in oneDstages:
                self.z_oneDstageDropdown.setCurrentText(self.z_stage_sel)
        #Create all other buttons/lineedits
        self.z_startLabel = QLabel("Start:")
        self.z_startEntry = QLineEdit()
        if self.z_start is not None:
            self.z_startEntry.setText(str(self.z_start))
        self.z_startEntry.setValidator(QDoubleValidator())
        self.z_startSetButton = QPushButton('Set')
        self.z_startSetButton.clicked.connect(lambda: self.setZStart())
        self.z_endLabel = QLabel("End:")
        self.z_endEntry = QLineEdit()
        if self.z_end is not None:
            self.z_endEntry.setText(str(self.z_end))
        self.z_endEntry.setValidator(QDoubleValidator())
        self.z_endSetButton = QPushButton('Set')
        self.z_endSetButton.clicked.connect(lambda: self.setZEnd())
        
        #add radio buttons:
        self.z_nrsteps_radio= QRadioButton("Number of steps: ")
        self.z_stepdistance_radio= QRadioButton("Step distance: ")
        #preselect the nr of steps one:
        if self.z_nrsteps_radio_sel == True:
            self.z_nrsteps_radio.setChecked(True)
        elif self.z_stepdistance_radio_sel == True:
            self.z_stepdistance_radio.setChecked(True)
        else:
            self.z_nrsteps_radio.setChecked(True)
        #add edit boxes for number of steps and step distance:
        self.z_nrsteps_entry = QLineEdit()
        if self.z_nr_steps is not None:
            self.z_nrsteps_entry.setText(str(self.z_nr_steps))
        self.z_nrsteps_entry.setValidator(QIntValidator())
        self.z_stepdistance_entry = QLineEdit()
        if self.z_step_distance is not None:
            self.z_stepdistance_entry.setText(str(self.z_step_distance))
        self.z_stepdistance_entry.setValidator(QDoubleValidator())
        
        #Add all widgets to layout
        zLayout.addWidget(self.z_oneDstageDropdownLabel,0,0)
        zLayout.addWidget(self.z_oneDstageDropdown,0,1)
        zLayout.addWidget(self.z_startLabel,1,0)
        zLayout.addWidget(self.z_startEntry,1,1)
        zLayout.addWidget(self.z_startSetButton,1,2)
        zLayout.addWidget(self.z_endLabel,2,0)
        zLayout.addWidget(self.z_endEntry,2,1)
        zLayout.addWidget(self.z_endSetButton,2,2)
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

        # --- Ordering widget ---
        #Note: only used in updateGUIwidgets
        
        #--------------- Channel widget -----------------------------------------------
        #Adding a list widget to add a list of channels
        self.channelListWidget = ChannelList(parent=self)
        self.channelListWidget.setColumNames(["Channel Setting", "Exposure"])
        
        #Add possible channels
        self.channelDropdownLabel = QLabel("Channel:")
        self.channelDropdown = QComboBox()
        
        #Figure out from all config groups which ones are "dropdown"
        nrconfiggroups = self.core.get_available_config_groups().size()
        allConfigGroups={}
        from MMcontrols import ConfigInfo
        for config_group_id in range(nrconfiggroups):
            allConfigGroups[config_group_id] = ConfigInfo(self.core,config_group_id)
        comboboxindexes = []
        for config_group_id in range(nrconfiggroups):
            if allConfigGroups[config_group_id].isDropDown():
                comboboxindexes.append(config_group_id)
        ComboBoxes = {key: allConfigGroups[key] for key in comboboxindexes}
        ComboBoxNames = {allConfigGroups[key].configGroupName() for key in comboboxindexes}
        
        #add the options to the dropdown:
        for combobox in ComboBoxes:
            self.channelDropdown.addItem(allConfigGroups[combobox].configGroupName())
        #Add a callback if we change this dropdown:
        self.channelDropdown.currentIndexChanged.connect(lambda: self.channelListWidget.setChannelName(self.channelDropdown.currentText()))
        #Also delete all the current entries
        self.channelDropdown.currentIndexChanged.connect(lambda: self.channelListWidget.deleteAll())
        
        #Initisalise the channel  list
        self.channelListWidget.setChannelName(self.channelDropdown.currentText)
        
        
        #Buttons for the channel position list
        self.channelListWidget_deleteButton = QPushButton('Delete Selected')
        self.channelListWidget_moveUpButton = QPushButton('Move Up')
        self.channelListWidget_moveDownButton = QPushButton('Move Down')
        self.channelListWidget_addButton = QPushButton('Add New Entry')
        self.channelListWidget_deleteAllButton = QPushButton('Delete All')
        #Adding callbacks to the channel list buttons
        self.channelListWidget_deleteButton.clicked.connect(self.channelListWidget.deleteSelected)
        self.channelListWidget_deleteAllButton.clicked.connect(self.channelListWidget.deleteAll)
        self.channelListWidget_moveUpButton.clicked.connect(self.channelListWidget.moveUp)
        self.channelListWidget_moveDownButton.clicked.connect(self.channelListWidget.moveDown)
        self.channelListWidget_addButton.clicked.connect(lambda: self.channelListWidget.addNewEntry())

        #Adding widgets to layout
        channelLayout.addWidget(self.channelDropdownLabel,0,0)
        channelLayout.addWidget(self.channelDropdown,0,1)
        channelLayout.addWidget(self.channelListWidget,1,0,6,1)
        channelLayout.addWidget(self.channelListWidget_deleteButton,2,1)
        channelLayout.addWidget(self.channelListWidget_moveUpButton,3,1)
        channelLayout.addWidget(self.channelListWidget_moveDownButton,4,1)
        channelLayout.addWidget(self.channelListWidget_addButton,5,1)
        channelLayout.addWidget(self.channelListWidget_deleteAllButton,6,1)

        #Add the pre-set channels:
        if self.channel_group in ComboBoxNames:
            if self.channel_group is not None:
                self.channelDropdown.setCurrentText(self.channel_group)
        if self.channels is not None and self.channel_exposures_ms is not None:
            for entry in range(len(self.channels)):
                self.channelListWidget.addNewEntry(channelEntry=self.channels[entry],exposureEntry=str(self.channel_exposures_ms[entry]))
        #--------------- Show options widget -----------------------------------------------
        #This should have checkboxes for exposure, xy, z, channel, time, order, storage. If these checkboxes are clicked, the GUI should be updated accordingly:
        self.GUI_show_exposure_chkbox = QCheckBox("Exposure")
        self.GUI_show_xy_chkbox = QCheckBox("XY")
        self.GUI_show_z_chkbox = QCheckBox("Z")
        self.GUI_show_channel_chkbox = QCheckBox("Channel")
        self.GUI_show_time_chkbox = QCheckBox("Time")
        self.GUI_show_storage_chkbox = QCheckBox("Storage")
        #initialise the checkboxes based on the values in this GUI:
        self.GUI_show_exposure_chkbox.setChecked(self.GUI_show_exposure)
        self.GUI_show_xy_chkbox.setChecked(self.GUI_show_xy)
        self.GUI_show_z_chkbox.setChecked(self.GUI_show_z)
        self.GUI_show_channel_chkbox.setChecked(self.GUI_show_channel)
        self.GUI_show_time_chkbox.setChecked(self.GUI_show_time)
        self.GUI_show_storage_chkbox.setChecked(self.GUI_show_storage)
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

        #Add all checkboxes to the options-layout
        showOptionsLayout.addWidget(self.GUI_show_exposure_chkbox,0,0)
        showOptionsLayout.addWidget(self.GUI_show_xy_chkbox,0,1)
        showOptionsLayout.addWidget(self.GUI_show_z_chkbox,0,2)
        showOptionsLayout.addWidget(self.GUI_show_channel_chkbox,1,0)
        showOptionsLayout.addWidget(self.GUI_show_time_chkbox,1,1)
        showOptionsLayout.addWidget(self.GUI_show_storage_chkbox,1,2)
        
        # ---------- Combining all to the main layout -----------------------------------------
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
            try:
                self.layout.addLayout(self.gui,0,0)
            except:
                self.setLayout(self.gui)
                self.mainLayout = self.gui
            
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
    
    def handleSizeChange(self, size):
        """
        Handle a change in size by adjusting the number of columns in the GUI grid.
        
        Args:
            size: The new size of the GUI window.
        
        Returns:
            None
        """
        
        newNrColumns = max(1,min(10, size.width() // 150))
        self.GUI_grid_width = newNrColumns
    
    def getDevicesOfDeviceType(self,devicetype):
        """
        Find all devices that have a specific devicetype.
        
        Args:
            devicetype (str): The type of device to search for. Refer to https://javadoc.scijava.org/Micro-Manager-Core/mmcorej/DeviceType.html for all devicetypes.
        
        Returns:
            list: A list of devices that match the specified devicetype.
        """
        
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
    
    def createOrderLayout(self,GUI_show_channel, GUI_show_time, GUI_show_xy, GUI_show_z, orderChoice = None):
        """
        Create an order ('t','tc', etc) layout based on the provided parameters.
        
        Args:
            GUI_show_channel (bool): Whether to include channel in the layout.
            GUI_show_time (bool): Whether to include time in the layout.
            GUI_show_xy (bool): Whether to include xy in the layout.
            GUI_show_z (bool): Whether to include z in the layout.
            orderChoice (str, optional): The default order choice. Defaults to None.
        
        Returns:
            QVBoxLayout: The layout containing the order dropdown and label.
        """
        
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
        
        if orderChoice in permuatations:
            if orderChoice is not None:
                self.orderDropdown.setCurrentText(orderChoice)
        
        return orderLayout
        
    def showOptionChanged(self):
        """
        Updates the GUI widgets based on the checkbox values.
        
        This function will be called when the checkboxes are clicked. It will update the GUI accordingly.
        
        Args:
            None
        
        Returns:
            None
        """
        
        self.setAllCheckBoxEnableValues()
        #This function will be called when the checkboxes are clicked. It will update the GUI accordingly:
        self.updateGUIwidgets(GUI_show_exposure=self.GUI_show_exposure_chkbox.isChecked(), GUI_show_xy = self.GUI_show_xy_chkbox.isChecked(), GUI_show_z=self.GUI_show_z_chkbox.isChecked(), GUI_show_channel=self.GUI_show_channel_chkbox.isChecked(), GUI_show_time=self.GUI_show_time_chkbox.isChecked(), GUI_show_storage=self.GUI_show_storage_chkbox.isChecked(),GUI_showOptions=True,GUI_acquire_button=self.GUI_acquire_button)
        self.get_MDA_events_from_GUI()
    
    def setAllCheckBoxEnableValues(self):
        """
        Set the enable values for all the checkboxes.
        
        Args:
            None
        
        Returns:
            None
        """
        
        self.GUI_exposure_enabled = self.GUI_show_exposure_chkbox.isChecked()
        self.GUI_xy_enabled = self.GUI_show_xy_chkbox.isChecked()
        self.GUI_z_enabled = self.GUI_show_z_chkbox.isChecked()
        self.GUI_channel_enabled = self.GUI_show_channel_chkbox.isChecked()
        self.GUI_time_enabled = self.GUI_show_time_chkbox.isChecked()
        self.GUI_storage_enabled = self.GUI_show_storage_chkbox.isChecked()
        self.GUI_show_exposure = self.GUI_show_exposure_chkbox.isChecked()
        self.GUI_show_xy = self.GUI_show_xy_chkbox.isChecked()
        self.GUI_show_z = self.GUI_show_z_chkbox.isChecked()
        self.GUI_show_channel = self.GUI_show_channel_chkbox.isChecked()
        self.GUI_show_time = self.GUI_show_time_chkbox.isChecked()
        self.GUI_show_storage = self.GUI_show_storage_chkbox.isChecked()
    
    def updateGUIwidgets(self,GUI_show_exposure=True, GUI_show_xy = False, GUI_show_z=True, GUI_show_channel=False, GUI_show_time=True, GUI_show_storage=True,GUI_showOptions=True,gridWidth=4,GUI_acquire_button=True):
        """
        Updates the GUI widgets based on the specified parameters.
        
        Args:
            GUI_show_exposure (bool): Whether to show the exposure widget. Default is True.
            GUI_show_xy (bool): Whether to show the XY widget. Default is False.
            GUI_show_z (bool): Whether to show the Z widget. Default is True.
            GUI_show_channel (bool): Whether to show the channel widget. Default is False.
            GUI_show_time (bool): Whether to show the time widget. Default is True.
            GUI_show_storage (bool): Whether to show the storage widget. Default is True.
            GUI_showOptions (bool): Whether to show the options widget. Default is True.
            gridWidth (int): The width of the grid. Default is 4.
            GUI_acquire_button (bool): Whether to show the acquire button. Default is True.
        
        Returns:
            None
        """
        
        gridWidth = self.GUI_grid_width
        # Remove the widgets from their parent
        self.exposureGroupBox.setParent(None) # type: ignore
        self.xyGroupBox.setParent(None) # type: ignore
        self.zGroupBox.setParent(None) # type: ignore
        self.channelGroupBox.setParent(None) # type: ignore
        self.timeGroupBox.setParent(None) # type: ignore
        # # self.orderGroupBox.setParent(None) # type: ignore
        self.storageGroupBox.setParent(None) # type: ignore
        self.showOptionsGroupBox.setParent(None)  # type: ignore


        # Clear the layout - this is required
        while self.gui.count(): # type: ignore
            item = self.gui.takeAt(0) # type: ignore
            widget = item.widget()
            if widget:
                widget.deleteLater()
        #redraw the self.gui:
        self.gui.update()
        QCoreApplication.processEvents()
        
        # At the beginning add an options groupbox, which has all the checkboxes and storage/acquire
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
        self.GUI_acquire_button.clicked.connect(lambda index: self.MDA_acq_from_GUI(mdaLayerName='MDA'))
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
        
        if GUI_show_exposure:
            self.exposureGroupBox.setEnabled(True)
        else:
            self.exposureGroupBox.setEnabled(False)
            
        self.orderGroupBox = QGroupBox("Order")
        orderlayout = self.createOrderLayout(GUI_show_channel, GUI_show_time, GUI_show_xy, GUI_show_z, orderChoice=self.order)
        self.orderGroupBox.setLayout(orderlayout)
        
        orderexposuretimelayout.addWidget(self.orderGroupBox) # type: ignore
        orderexposuretimelayout.addWidget(self.exposureGroupBox) # type: ignore
        orderexposuretimelayout.addWidget(self.timeGroupBox) # type: ignore
        if GUI_show_time:
            self.timeGroupBox.setEnabled(True)
        else:
            self.timeGroupBox.setEnabled(False)
        #     # QCoreApplication.processEvents()
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
    
    def printText(self):
        """
        Prints the events obtained from the getEvents method.
        
        Args:
            self: The object instance.
        
        Returns:
            None
        """
        print(self.getEvents())
    
    def getEvents(self):
        """
        Get the MDA events from the object.
        
        Returns:
            The MDA events stored in the object.
        """
        return self.mda
    
    def getGui(self):
        """
        Returns the GUI object.
        
        Args:
            None
        
        Returns:
            The GUI object.
        """
        return self
    #endregion
    
    #region Multi-D acquisition logic
    def MDA_acq_finished(self):
        """
        Signal that MDA acquisition has finished.
        
        Disconnects the signal, stores the acquired data, and updates the status of connected nodes in the nodz-coupled visualization and real-time analysis.
        
        Args:
            self: The object instance.
        
        Returns:
            None
        """
        
        self.shared_data.mda_acq_done_signal.disconnect(self.MDA_acq_finished)
        self.data = self.shared_data.mdaDatasets[-1]
        logging.info('MDA acq data finished and data stored!')
        
        #Remove any existing nodz-coupled real-time analyses:
        if 'nodz_analysis_threads' in vars(self):
            for analysis_thread in self.nodz_analysis_threads:
                analysis_thread.stop()
        
        #Set the status of the nodz-coupled vis and real-time to finished:
        if 'nodeInfo' in vars(self):
        #Look at the 'Visual' bottom attribute:
            visualAttr = self.nodeInfo.bottomAttrs['Visual']
            if len(visualAttr.connections) > 0:
                visual_connected_node_name = visualAttr.connections[0].socketNode
                for node in self.nodeInfo.flowChart.nodes:
                    if node.name == visual_connected_node_name:
                        visual_connected_node = node
                        visual_connected_node.status = 'finished'
            
            #Look at the 'Real-time' bottom attribute:
            RealTimeAttr = self.nodeInfo.bottomAttrs['Real-time']
            if len(RealTimeAttr.connections) > 0:
                self.nodz_analysis_threads = []
                rt_analysis_connected_node_name = RealTimeAttr.connections[0].socketNode
                for node in self.nodeInfo.flowChart.nodes:
                    if node.name == rt_analysis_connected_node_name:
                        rt_analysis_connected_node = node
                        rt_analysis_connected_node.status = 'finished'
        
        self.MDA_completed.emit(True)
    
    def MDA_acq_from_Node(self, nodeInfo):
        """MDA_acq_from_Node(self, nodeInfo)
        
        Basically the same as MDA_from_GUI, but with the NodeInfo.
        
        Args:
            self: The object itself.
            nodeInfo: Information about the node.
        
        Returns:
            None
        
        Raises:
            None
        
        This function acquires data from a node and performs various operations based on the node information provided.
        """
        logging.debug('At MDA_acq_from_node')
        nodeName = nodeInfo.name
        
        self.nodeInfo = nodeInfo
        
        #Look at the 'Visual' bottom attribute:
        visualAttr = nodeInfo.bottomAttrs['Visual']
        if len(visualAttr.connections) > 0:
            for connection in visualAttr.connections:
                if connection.plugAttr is not None and connection.socketAttr is not None and connection.plugItem is not None and connection.socketItem is not None and connection.plugNode is not None and connection.socketNode is not None:
                    visual_connected_node_name = connection.socketNode
                    for node in nodeInfo.flowChart.nodes:
                        if node.name == visual_connected_node_name:
                            visual_connected_node = node
                            if 'layerName' in visual_connected_node.visualisation_currentData and visual_connected_node.visualisation_currentData['layerName'] is not None:
                                layerName = visual_connected_node.visualisation_currentData['layerName']
                            else:
                                visual_connected_node.visualisation_currentData['layerName'] = nodeName
                                layerName = nodeName
                                
                            if 'colormap' in visual_connected_node.visualisation_currentData and visual_connected_node.visualisation_currentData['colormap'] is not None:
                                colormap = visual_connected_node.visualisation_currentData['colormap']
                            else:
                                visual_connected_node.visualisation_currentData['colormap'] = 'gray'
                                colormap = 'gray'
                            
                            visual_connected_node.status = 'running'
                            break
                
                    napariGlados.startMDAVisualisation(self.shared_data,layerName=layerName,layerColorMap=colormap)
        
        #And try to get real-time analysis attributes at bottom:
        
        #Look at the 'Real-time' bottom attribute:
        RealTimeAttr = nodeInfo.bottomAttrs['Real-time']
        if len(RealTimeAttr.connections) > 0:
            self.nodz_analysis_threads = []
            rt_analysis_connected_node_name = RealTimeAttr.connections[0].socketNode
            for node in nodeInfo.flowChart.nodes:
                if node.name == rt_analysis_connected_node_name:
                    rt_analysis_connected_node = node
                    rt_analysis_info = rt_analysis_connected_node.real_time_analysis_currentData
                    
                    new_analysis_thread = create_real_time_analysis_thread(self.shared_data,analysisInfo = rt_analysis_info,delay=None)
                    self.nodz_analysis_threads.append(new_analysis_thread)
                    rt_analysis_connected_node.status = 'running'
                    
                    
        self.shared_data._mdaMode = False
        
        #Set the exposure time:
        self.core.set_exposure(self.exposure_ms)
        
        #Set the location where to save the mda
        self.shared_data._mdaModeSaveLoc = [self.storage_folder,self.storage_file_name]
        #Set whether the napariviewer should (also) try to connect to the mda
        # self.shared_data._mdaModeNapariViewer = self.shared_data.napariViewer
        #Set the mda parameters
        self.shared_data._mdaModeParams = self.mda
        #Set this MDA object as the active MDA object in the shared_data
        self.shared_data.activeMDAobject = self
        self.shared_data.mda_acq_done_signal.connect(self.MDA_acq_finished)
        #And set the mdamode to be true
        self.shared_data.mdaMode = True
        logging.debug('ended setting mdamode params')
        
        pass
    
    def MDA_acq_from_GUI(self, mdaLayerName=None):
        """
        The MDA_acq_from_GUI function is called when the user presses the 'Start MDA' button in the GUI.
        It sets all of the parameters for an MDA acquisition, and then starts it by calling startMDAacq()
        
        Args:
            self: Refer to the instance of the class
            mdaLayerName: Set the name of the napari layer that will be created for this mda
        
        Returns:
            Nothing
        
        Doc Author:
            Trelent
        """
        logging.debug('At MDA_acq_from_GUI')
        self.shared_data._mdaMode = False
        
        #Set the exposure time:
        self.core.set_exposure(self.exposure_ms)
        
        #Set the location where to save the mda
        self.shared_data._mdaModeSaveLoc = [self.storage_folder,self.storage_file_name]
        #Set whether the napariviewer should (also) try to connect to the mda
        # self.shared_data._mdaModeNapariViewer = self.shared_data.napariViewer
        #Set the mda parameters
        self.shared_data._mdaModeParams = self.mda
        #Set this MDA object as the active MDA object in the shared_data
        self.shared_data.activeMDAobject = self
        self.shared_data.mda_acq_done_signal.connect(self.MDA_acq_finished)
        #And set the mdamode to be true
        self.shared_data.mdaMode = True
        #And start visualization
        if mdaLayerName is not None:
            napariGlados.startMDAVisualisation(self.shared_data,layerName=mdaLayerName)
        logging.debug('ended setting mdamode params')
        
        pass
    
    def get_MDA_events_from_GUI(self):
        """
        The get_MDA_events_from_GUI function is called every time the user changes any option in the GUI.
        It will then update all variables that are used to create an MDA object, which can be used to run a multi-dimensional acquisition.
        
        
        Args:
            self: Refer to the object itself
        """
        logging.debug('starting get_MDA_events_from_GUI')
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
            self.storage_folder = self.storageFolderEntry.text()
            self.storage_file_name = self.storageFileNameEntry.text()
        
        if self.zGroupBox.isEnabled():
            try:
                #We also need to set the shared_data focus device for proper z-functioning
                self.shared_data.core.set_focus_device(self.z_oneDstageDropdown.currentText())
            except:
                self.shared_data.core.set_focus_device(self.shared_data._defaultFocusDevice)
                
            self.z_stage_sel = self.z_oneDstageDropdown.currentText()
            
            if self.z_startEntry.text() != '':
                self.z_start = (float(self.z_startEntry.text()))
            else:
                self.z_start = None
                
            if self.z_endEntry.text() != '':
                self.z_end = (float(self.z_endEntry.text()))
            else:
                self.z_end = None
                
            if self.z_nrsteps_radio.isChecked():
                if (self.z_nrsteps_entry.text() != '') and self.z_start is not None and self.z_end is not None:
                    self.z_step = float((self.z_end-self.z_start)/int(self.z_nrsteps_entry.text()))
                    self.z_step_distance = None
                    self.z_nr_steps = int(self.z_nrsteps_entry.text())
                else:
                    self.z_step = None
                    self.z_step_distance = None
                    self.z_nr_steps = None
            elif self.z_stepdistance_radio.isChecked():
                if self.z_stepdistance_entry.text() != '' and self.z_start is not None and self.z_end is not None:
                    self.z_step = float(self.z_stepdistance_entry.text())
                    self.z_step_distance = float(self.z_stepdistance_entry.text())
                    self.z_nr_steps = None
                    if self.z_start < self.z_end:
                        if self.z_step < 0:
                            self.z_step*=-1
                    elif self.z_start > self.z_end:
                        if self.z_step > 0:
                            self.z_step*=-1
                else:
                    self.z_step = None
                    self.z_step_distance = None
                    self.z_nr_steps = None
            self.z_nrsteps_radio_sel = self.z_nrsteps_radio.isChecked()
            self.z_stepdistance_radio_sel = self.z_stepdistance_radio.isChecked()
        else:
            self.shared_data.core.set_focus_device(self.shared_data._defaultFocusDevice)
        
        if self.channelGroupBox.isEnabled():
            try:
                
                self.channel_group = self.channelDropdown.currentText()
                
                self.channels = []
                self.channel_exposures_ms = []
                for row in range(self.channelListWidget.rowCount()):
                    for column in range(self.channelListWidget.columnCount()):
                        if column == 0:
                            self.channels.append(self.channelListWidget.cellWidget(row,0).currentText())
                        elif column == 1:
                            item = self.channelListWidget.item(row, column)
                            try: #Check if it will be float-value:
                                if item is not None:
                                    self.channel_exposures_ms.append(float(item.text()))
                                else:
                                    self.channel_exposures_ms.append("")  # Add an empty string for empty cells
                            except ValueError:  # Add an empty string for non-float
                                self.channel_exposures_ms.append("")

            except:
                self.channel_group = None
                self.channels = None
                self.channel_exposures_ms = None
        
        #Do a small catch in case z_start, z_step or z_end is None:
        if self.z_start is None or self.z_step is None or self.z_end is None:
            logging.warning("z_start, z_step or z_end is None. MDA will not be created.")
            self.z_start = 0
            self.z_step = 1
            self.z_end = 1
        
        #initiate with an empty mda:
        self.mda = multi_d_acquisition_events(num_time_points=self.num_time_points, time_interval_s=self.time_interval_s,z_start=self.z_start,z_end=self.z_end,z_step=self.z_step,channel_group=self.channel_group,channels=self.channels,channel_exposures_ms=self.channel_exposures_ms,xy_positions=self.xy_positions,xyz_positions=self.xyz_positions,position_labels=self.position_labels,order=self.order) #type:ignore
        
        logging.debug(f"mda: {self.mda}")
        if self.fully_started:
            if self.autoSaveLoad:
                self.save_state_MDA('glados_state.json')
        logging.debug('ended get_MDA_events_from_GUI')
        
        pass
    
    def setZStart(self):
        """
        Set the starting Z position based on the selected zstage.
        
        Args:
            None
        
        Returns:
            None
        """
        
        zstage = self.z_oneDstageDropdown.currentText()
        #zstage value limited to 2 decimal places:
        zstagePos = round(float(self.core.get_position(zstage)),2)
        self.z_startEntry.setText(str(zstagePos))
    
    def setZEnd(self):
        """
        Set the end position of the Z stage.
        
        Args:
            None
        
        Returns:
            None
        """
        
        zstage = self.z_oneDstageDropdown.currentText()
        #zstage value limited to 2 decimal places:
        zstagePos = round(float(self.core.get_position(zstage)),2)
        self.z_endEntry.setText(str(zstagePos))
        
    def setMDAparams(self,mdaparams):
        """
        Set the MDA parameters.
        
        Args:
            mdaparams: The MDA parameters to be set.
        
        Returns:
            None
        """
        self.mda = mdaparams
    #endregion
