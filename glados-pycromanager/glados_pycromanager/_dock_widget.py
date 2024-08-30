
#region imports
import napari
from qtpy.QtWidgets import QWidget
from PyQt5.QtWidgets import QWidget
from PyQt5.QtWidgets import QScrollArea
import sys
import os
from pycromanager import Core
import logging
from PyQt5.QtWidgets import QApplication, QWidget, QGridLayout, QGroupBox, QLabel, QVBoxLayout, QPushButton, QSizePolicy

from typing import List
os.environ['NAPARI_ASYNC'] = '1'

def is_pip_installed():
    return 'site-packages' in __file__ or 'dist-packages' in __file__

if is_pip_installed():
    from glados_pycromanager.GUI.AnalysisClass import * #type:ignore
    from glados_pycromanager.GUI.utils import CustomMainWindow #type:ignore
    from glados_pycromanager.GUI.napariHelperFunctions import getLayerIdFromName, InitateNapariUI #type:ignore
    from glados_pycromanager.GUI.napariGlados import * #type: ignore
    from glados_pycromanager.GUI.sharedFunctions import Shared_data, periodicallyUpdate #type: ignore
    from glados_pycromanager.GUI.utils import * #type: ignore
    #Import all scripts in the custom script folders
    from glados_pycromanager.AutonomousMicroscopy.Analysis_Measurements import * #type: ignore
    from glados_pycromanager.AutonomousMicroscopy.Real_Time_Analysis import * #type: ignore
    # Obtain the helperfunctions
    # import glados_pycromanager.GUI.HelperFunctions #type: ignore
    from glados_pycromanager.GUI.napariHelperFunctions import showScaleBar #type: ignore
else:
    sys.path.append(os.path.dirname(os.path.abspath(__file__))+"\\GUI")
    sys.path.append(os.path.dirname(os.path.abspath(__file__))+"\\AutonomousMicroscopy")
    sys.path.append(os.path.dirname(os.path.abspath(__file__))+"\\AutonomousMicroscopy\\MainScripts")
    sys.path.append(os.path.dirname(os.path.abspath(__file__))+"\\GUI\\nodz")
    from AnalysisClass import * #type:ignore
    from utils import CustomMainWindow #type:ignore
    from napariHelperFunctions import getLayerIdFromName, InitateNapariUI #type:ignore
    from napariGlados import * #type: ignore
    from sharedFunctions import Shared_data, periodicallyUpdate #type: ignore
    from utils import * #type: ignore
    # Add the folder 2 folders up to the system path
    sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    #Import all scripts in the custom script folders
    from Analysis_Measurements import * #type: ignore
    from Real_Time_Analysis import * #type: ignore
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
        self.setBaseSize(200,200)
        self._viewer = viewer
        self.type = None
        self.layoutInfo = None
        
        if parent is not None:
            self.core = parent.core
            self.MM_JSON = parent.MM_JSON
            self.livestate = parent.livestate
            self.shared_data = parent.shared_data
            self.napariViewer = parent.napariViewer
    
    def getFirstOrderWidgets(self):
        """
        Determine the 'main' widgets inside the 'main' groupbox (i.e. the configs/settings/stages widgets inside the MMconfig)
        
        Should be handled somewhat differently if it's the first time run (not a scrollarea yet), or subsequently (inside a scrollarea).
        """
        firstOrderWidgets = []
        #Check if the dockwidget is a Qscrollarea:
        if isinstance(self.dockWidget.layout().itemAt(0).widget(),QScrollArea):
            for i in range(self.dockWidget.layout().itemAt(0).widget().widget().layout().count()):
                item = self.dockWidget.layout().itemAt(0).widget().widget().layout().itemAt(i)
                widget = item.widget()
                if widget is not None:
                    firstOrderWidgets.append(widget)
                    widget.setSizePolicy(QSizePolicy.MinimumExpanding, QSizePolicy.MinimumExpanding)
                    # widget.setMinimumSize(50,50)
                    logging.debug(f"Widget {i}: {widget.objectName() if widget.objectName() else widget}")
            
        else: #First time:
            for i in range(self.dockWidget.count()):
                item = self.dockWidget.itemAt(i)
                widget = item.widget()
                if widget is not None:
                    firstOrderWidgets.append(widget)
                    widget.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Preferred)
                    logging.debug(f"Widget {i}: {widget.objectName() if widget.objectName() else widget}")
        
        return firstOrderWidgets
        
    def resizeEvent(self, event):
        """"
        Called when the window is resized
        Chooses to sort the widgets into rows or columns based on whether it's vertical or horizontal.
        """
        
        #Don't do this if it's autonomous microscopy - not made for this.
        if self.type == None or self.type == "AutonomousMicroscopy":
            super().resizeEvent(event)
            return
        else:
            width = self.size().width()
            height = self.size().height()
            
            # Determine the layout based on the window size
            if width > height * 1.25:  # Wide window
                self.set_groupBoxLayout(rowsOrColumns='rows', n_items=1)
            elif height > width * 1.25:  # Tall window
                self.set_groupBoxLayout(rowsOrColumns='columns', n_items=1)
            elif width > height:  # Landscape
                self.set_groupBoxLayout(rowsOrColumns='rows', n_items=2)
            else:  # Portrait
                self.set_groupBoxLayout(rowsOrColumns='columns', n_items=2)
                
            super().resizeEvent(event)
        
    def set_groupBoxLayout(self, rowsOrColumns='rows', n_items=1):
        """"
        Main function that sets individual widgets inside a groupbox to be rows or columns.
        """
        #Determine nr rows and columns
        allWidgets = self.getFirstOrderWidgets()
        n_widgets = len(allWidgets)
        if rowsOrColumns == 'rows':
            rows = n_items
            columns = n_widgets // rows
        elif rowsOrColumns == 'columns':
            columns = n_items
            rows = n_widgets // columns
            
        # Clear the layout first
        for i in reversed(range(n_widgets)):
            widget = allWidgets[i]
            logging.debug(f"allwidgets: {allWidgets}, widget: {widget}")
            if widget is not None:
                if isinstance(self.dockWidget,QScrollArea):
                    self.dockWidget.layout().removeWidget(widget)
                else:
                    self.dockWidget.removeWidget(widget)
                widget.setParent(None)
        
        #remove all children of self.dockWidget:
        for i in reversed(range(self.dockWidget.count())):
            widget = self.dockWidget.itemAt(i).widget()
            if widget is not None:
                logging.debug(f"removing {widget}")
                self.dockWidget.removeWidget(widget)
                widget.setParent(None)
                
        
        #Create the following structure: scrollArea --> container --> mainGridLayout
        #create a QScrollArea
        from PyQt5.QtCore import Qt
        scrollArea = QScrollArea()
        scrollArea.setWidgetResizable(True)
        self.container = QWidget()
        self.container.setMinimumSize(300, 300) 
        
        #Add them all
        mainGridLayout = QGridLayout()
        self.container.setLayout(mainGridLayout)
        scrollArea.setWidget(self.container)
        
        # Add group boxes to the layout
        for index, group_box in enumerate(allWidgets):
            row = index // columns
            column = index % columns
            logging.debug(f"adding {group_box} to row {row}, column {column}")
            mainGridLayout.addWidget(group_box, row, column)

        #add a spacer item to push the entire gridwindow to the top-left of the scroll area
        from PyQt5.QtWidgets import QSpacerItem
        self.expandingspacer = QSpacerItem(10000, 10000, QSizePolicy.Expanding, QSizePolicy.Expanding)
        mainGridLayout.addItem(self.expandingspacer, rows+1, columns + 1)
        
        #Figure out what the minimum size is of the container without the expanding spacer
        containerMinSize = self.container.minimumSizeHint()
        containerMinSize -= self.expandingspacer.minimumSize()
        
        #Force this to be the minimum size
        # Set the minimum size of QGroupBox based on its size hint
        self.container.setMinimumSize(containerMinSize)  
        self.container.setSizePolicy(
            QSizePolicy(QSizePolicy.MinimumExpanding, QSizePolicy.MinimumExpanding)
        )

        # Adjust stretch
        for row in range(rows):
            mainGridLayout.setRowStretch(row, 1)
        for column in range(columns):
            mainGridLayout.setColumnStretch(column, 1)
        
        #Finally add this scroll area to the dockWidget.
        self.dockWidget.addWidget(scrollArea,0,0)
    
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
        self.MMconfigPlugin = microManagerControlsUI_plugin(self) #type:ignore
        self.dockWidget = self.MMconfigPlugin
        self.setLayout(self.dockWidget)
        
        self.getFirstOrderWidgets()
        self.setMinimumSize(200, 200)
        self.setBaseSize(200,200)
        
        logging.debug("dockWidget_MMConfig started")

    def resizeEvent(self, event):
        """"
        Called when the window is resized
        Basically just updates the font/margins
        """
        from PyQt5.QtGui import QFont
        self.layoutInfo.set_font_and_margins_recursive(self.layoutInfo,font=QFont("Arial", 7)) #type:ignore
        # self.adjustSize()
        self.layoutInfo.adjustSize() #type:ignore
        super().resizeEvent(event)
        self.layoutInfo.set_font_and_margins_recursive(self.layoutInfo,font=QFont("Arial", 7)) #type:ignore

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
        
        #Init a few things
        self.getFirstOrderWidgets()
        self.setMinimumSize(200, 200)
        self.setBaseSize(200,200)
        
        logging.debug("dockwidget_MDA started")

    def resizeEvent(self, event):
        """"
        Called when the window is resized
        Basically just updates the font/margins
        """
        from PyQt5.QtGui import QFont
        self.layoutInfo.set_font_and_margins_recursive(self.layoutInfo,font=QFont("Arial", 7)) #type:ignore
        # self.adjustSize()
        self.layoutInfo.adjustSize() #type:ignore
        super().resizeEvent(event)
        self.layoutInfo.set_font_and_margins_recursive(self.layoutInfo,font=QFont("Arial", 7)) #type:ignore

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
        if is_pip_installed():
            from glados_pycromanager.GUI.Analysis_dockWidgets import autonomousMicroscopy_plugin
        else:
            from Analysis_dockWidgets import autonomousMicroscopy_plugin
        self.dockWidget = autonomousMicroscopy_plugin(self) #type:ignore
        
        self.setLayout(self.dockWidget)
        logging.debug("dockWidget_AutonomousMicroscopy started")
    
    def resizeEvent(self, event):
        """"
        We don't want the GladosWidget resizeEvent for AutonomousMicroscopy
        """
        return super().resizeEvent(event)
    


class GladosSlidersWidget(GladosWidget):
    """
    The GladosSlidersWidget widget plugin
    """
    def __init__(self, viewer: napari.viewer.Viewer, parent=None): #type:ignore
        """
        Initialize the GladosSlidersWidget plugin
        """

        super().__init__(viewer=viewer, parent=parent)
        
        #Add the full micro manager controls UI
        if is_pip_installed():
            from glados_pycromanager.GUI.Analysis_dockWidgets import gladosSliders_plugin
        else:
            from Analysis_dockWidgets import gladosSliders_plugin
        self.dockWidget = gladosSliders_plugin(self) #type:ignore
        

        layout = QVBoxLayout()
        layout.addWidget(self.dockWidget) # type: ignore
        self.setLayout(layout)
        logging.debug("dockWidget_GladosSliders started")
    
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
        
        #Set up logging in the AppData folder, INFO and DEBUG
        utils.set_up_logger()

        logging.info("Main napari Glados-pycromanager plugin started")
        
        #Initialise napari-scalebar
        napariViewer = viewer
        showScaleBar(viewer)
        
        #Add the individual widgets
        
        #GladosLasers
        try:
            GladosLaserWidget = GladosSlidersWidget(viewer, parent=self)
            self._viewer.window.add_dock_widget(GladosLaserWidget, area='right',tabify=True,name='Lasers')
        except Exception as e:
            logging.error(f"Error loading GladosLaserWidget: {e}")
        
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