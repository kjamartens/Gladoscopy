
#region imports
import napari
from qtpy.QtWidgets import QWidget
from PyQt5.QtWidgets import QWidget
from AnalysisClass import * #type:ignore
from utils import CustomMainWindow #type:ignore
from napariHelperFunctions import getLayerIdFromName, InitateNapariUI #type:ignore
import sys
import os
from pycromanager import Core
import logging
from PyQt5.QtWidgets import QApplication, QWidget, QGridLayout, QGroupBox, QLabel, QVBoxLayout, QPushButton, QSizePolicy

from typing import List
os.environ['NAPARI_ASYNC'] = '1'
sys.path.append(os.path.dirname(os.path.abspath(__file__))+"\\GUI")
sys.path.append(os.path.dirname(os.path.abspath(__file__))+"\\AutonomousMicroscopy")
sys.path.append(os.path.dirname(os.path.abspath(__file__))+"\\AutonomousMicroscopy\\MainScripts")
sys.path.append(os.path.dirname(os.path.abspath(__file__))+"\\GUI\\nodz")
from napariGlados import * #type: ignore
from sharedFunctions import Shared_data, periodicallyUpdate #type: ignore
from utils import * #type: ignore
# Add the folder 2 folders up to the system path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
#Import all scripts in the custom script folders
										
											   
																				  
from Analysis_Images import * #type: ignore
from Analysis_Measurements import * #type: ignore
from Analysis_Shapes import * #type: ignore
from Scoring_Images import * #type: ignore
from Scoring_Measurements import * #type: ignore
from Scoring_Shapes import * #type: ignore
from Scoring_Images_Measurements import * #type: ignore
from Scoring_Measurements_Shapes import * #type: ignore
from Scoring_Images_Measurements_Shapes import * #type: ignore
from Visualisation_Images import * #type: ignore
from Visualisation_Measurements import * #type: ignore
from Visualisation_Shapes import * #type: ignore
# Obtain the helperfunctions
import HelperFunctions #type: ignore
from napariHelperFunctions import showScaleBar #type: ignore
#endregion

#region Widget Definition
class GladosWidget(QWidget):
    """
    The main Class of glados-pycromanager widget that gets added to napari.
    """
    def __init__(self, viewer: napari.viewer.Viewer, parent=None): #type: ignore
        """
        Init a glados widget, mostly passing around parent variables to daughter (plugin) variables. Used to be global-specified, but doesn't work with napari plugins for some reason.
        """
        super().__init__()
        
        self.setMinimumSize(0, 0)  # Force-set the minimum size to (0, 0)

        self.setBaseSize(200,200)
        
        self._viewer = viewer
        self.type = None
        
        if parent is not None:
            self.core = parent.core
            self.MM_JSON = parent.MM_JSON
            self.livestate = parent.livestate
            self.shared_data = parent.shared_data
            self.napariViewer = parent.napariViewer
    
    def getFirstOrderWidgets(self):
        firstOrderWidgets = []
        for i in range(self.dockWidget.count()):
            item = self.dockWidget.itemAt(i)
            widget = item.widget()
            if widget is not None:
                firstOrderWidgets.append(widget)
                widget.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Preferred)
                logging.debug(f"Widget {i}: {widget.objectName() if widget.objectName() else widget}")
        
        print(firstOrderWidgets)
        return firstOrderWidgets
    
    def getMainWindowSize(self):
        width = self.size().width()
        height = self.size().height()
        print(f"width: {width}, height: {height}")
        
    def resizeEvent(self, event):
        if self.type == None or self.type == "AutonomousMicroscopy":
            super().resizeEvent(event)
            return
        else:
            width = self.size().width()
            height = self.size().height()
            print(f"resize event caleld with type: {self.type}")
            
            # Determine the layout based on the window size
            if width > height * 2:  # Wide window
                self.set_groupBoxLayout(rowsOrColumns='rows', n_items=1)
            elif height > width * 2:  # Tall window
                self.set_groupBoxLayout(rowsOrColumns='columns', n_items=1)
            elif width > height:  # Landscape
                self.set_groupBoxLayout(rowsOrColumns='rows', n_items=2)
            else:  # Portrait
                self.set_groupBoxLayout(rowsOrColumns='columns', n_items=2)
                
            # self.getMainWindowSize()
            super().resizeEvent(event)
        
    def set_groupBoxLayout(self, rowsOrColumns='rows', n_items=1):
        
        allWidgets = self.getFirstOrderWidgets()
        n_widgets = len(allWidgets)
        if rowsOrColumns == 'rows':
            rows = n_items
            columns = n_widgets // rows
        elif rowsOrColumns == 'columns':
            columns = n_items
            rows = n_widgets // columns
            
            
        # print(f"Minimum width dockwidget: {self.dockWidget.minimumWidth()} px")
        # print(f"Minimum height dockwidget: {self.dockWidget.minimumHeight()} px")
        
        # self.dockWidget.setSizeConstraint(QGridLayout.SetMinAndMaxSize)
        # # Clear the layout first
        # for i in reversed(range(n_widgets)):
        #     widget = allWidgets[i]
        #     if widget is not None:
        #         print(f"removing {widget}")
        #         self.dockWidget.removeWidget(widget)
        #         widget.setParent(None)
        
        # # Add group boxes to the layout
        # for index, group_box in enumerate(allWidgets):
        #     row = index // columns
        #     column = index % columns
        #     print(f"adding {group_box} to row {row}, column {column}")
        #     # print(f"Minimum width widget: {group_box.minimumWidth()} px")
        #     # print(f"Minimum height wiget: {group_box.minimumHeight()} px")
        #     self.dockWidget.addWidget(group_box, row, column)

        # Adjust stretch
        # for row in range(rows):
        #     self.dockWidget.setRowStretch(row, 1)
        # for column in range(columns):
        #     self.dockWidget.setColumnStretch(column, 1)
            
    
    def set_widget_properties_recursive(self, widget):
        """
        Recursively sets the minimum size and size policy for a widget and all its children.
        """
        try:
            widget.setMinimumSize(0, 0)
            widget.setSizePolicy(QSizePolicy.Minimum, QSizePolicy.Minimum)
        except:
            pass

        for child in widget.findChildren(QWidget):
            self.set_widget_properties_recursive(child)
        for child in widget.findChildren(QGroupBox):
            self.set_widget_properties_recursive(child)

class MMConfigWidget(GladosWidget):
    """
    The micromanager-glados-pycromanager configuration plugin.
    Allows users to change all configs specified in MM
    """
    def __init__(self, viewer: napari.viewer.Viewer, parent=None): #type: ignore
        """
        Initialize the micromanager-config plugin
        """
        super().__init__(viewer = viewer, parent=parent)
        self.type = "MMConfig"
        
        #Get some info from core to put in shared_data
        self.shared_data._defaultFocusDevice = self.core.get_focus_device()
        logging.info(f"Default focus device set to {self.shared_data._defaultFocusDevice}")
        
        #Start docwidget
        self.dockWidget = microManagerControlsUI_plugin(self) #type:ignore
        self.setLayout(self.dockWidget)
        
        
        self.set_widget_properties_recursive(self)
        
        self.getFirstOrderWidgets()
        self.getMainWindowSize()
        
        self.setMinimumSize(200, 200)
        self.setBaseSize(200,200)
        
        logging.info("dockWidget_MMConfig started")


class MDAWidget(GladosWidget):
    """
    The micromanager-glados-pycromanager multi-dimensional acquisition plugin
    """
    def __init__(self, viewer: napari.viewer.Viewer, parent=None): #type:ignore
        """
        Initialize the Multi-D acquisition plugin
        """
        super().__init__(viewer = viewer, parent=parent)
        self.type = "MDA"
        
        self.dockWidget = MDAGlados_plugin(self) #type:ignore
        self.setLayout(self.dockWidget)
        
        from PyQt5.QtWidgets import QApplication, QWidget, QGridLayout, QGroupBox, QLabel, QVBoxLayout, QPushButton, QSizePolicy

        # self.dockWidget.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        
        
        self.getFirstOrderWidgets()
        self.getMainWindowSize()
        logging.info("dockwidget_MDA started")

class AutonomousMicroscopyWidget(GladosWidget):
    """
    The micromanager-glados-pycromanager autonomous microscopy widget plugin
    """
    def __init__(self, viewer: napari.viewer.Viewer, parent=None): #type:ignore
        """
        Initialize the AutonomousMicroscopyWidget plugin
        """
        super().__init__(viewer = viewer, parent=parent)
        
        #Add the full micro manager controls UI
        self.dockWidget = autonomousMicroscopy_plugin(self) #type:ignore
        
        self.setLayout(self.dockWidget)
        logging.info("dockWidget_AutonomousMicroscopy started")
    
    def resizeEvent(self, event):
        """"
        We don't want the GladosWidget resizeEvent for AutonomousMicroscopy
        """
        return super().resizeEvent(event)
#endregion

#region Main Call
class MainWidget(QWidget):
    """
    The main call when napari-glados is started
    Basically starts-up all the initialization and starts all widgets
    """
    def __init__(self, viewer: napari.viewer.Viewer): #type:ignore
        """
        Initialize the GladosPycroManager plugin call
        """
        super().__init__()
        self._viewer = viewer
        global shared_data
        
        # Create an instance of the shared_data class
        shared_data = Shared_data()
        
        core = Core()
        shared_data.core = core
        shared_data._headless = False
        
        MM_JSON = None
        livestate = False
        
        self.core = core
        self.shared_data = shared_data
        self.napariViewer = viewer
        self.MM_JSON = MM_JSON
        self.livestate = livestate
    
        includecustomUI = False
        include_flowChart_automatedMicroscopy = True
        
        #Set up logging at correct level        
        # Create handlers
        file_handler = logging.FileHandler('Glados_logpath.log')
        stream_handler = logging.StreamHandler()

        # Create a formatter
        formatter = logging.Formatter("%(asctime)s [%(levelname)s] %(message)s [%(filename)s:%(funcName)s:%(lineno)d]")

        # Set the formatter for both handlers
        file_handler.setFormatter(formatter)
        stream_handler.setFormatter(formatter)

        # Get the root logger
        logger = logging.getLogger()

        # Set the logging level
        logger.setLevel(logging.INFO)

        # Remove existing streamhandlers
        for handler in logger.handlers:
            if isinstance(handler, logging.StreamHandler):
                logger.removeHandler(handler)
        # Add handlers to the root logger
        logger.addHandler(file_handler)
        logger.addHandler(stream_handler)

        # logging.basicConfig(handlers=[file_handler, stream_handler], level=logging.INFO,format="%(asctime)s [%(levelname)s] %(filename)s:%(lineno)d - %(message)s")
        logging.info("Main napari Glados-pycromanager plugin started")
        
        #Initialise napari-scalebar
        napariViewer = viewer
        showScaleBar(viewer)
        
        #Add the individual widgets
        
        #Full MM control
        MMconfigWidget = MMConfigWidget(viewer, parent=self)
        self._viewer.window.add_dock_widget(MMconfigWidget, area='top',tabify=True,name='Config')
        
        #Multi-D acquisition window
        custom_widget_MDA = MDAWidget(viewer, parent=self)
        napariViewer.window.add_dock_widget(custom_widget_MDA, area="top", name="Multi-D acquisition",tabify=True)

        #Autonomous microscopy
        autonomousMicroscopyWidget = AutonomousMicroscopyWidget(viewer, parent=self)
        napariViewer.window.add_dock_widget(autonomousMicroscopyWidget, area="top", name="Glados",tabify=True)

        logging.info('Napari-glados-pycromanager plugin fully loaded')

#endregion