
#region imports
import logging
import os
import sys

import napari
from pycromanager import Core
from PyQt5.QtCore import QTimer
from PyQt5.QtGui import QFont
from PyQt5.QtWidgets import QGridLayout, QGroupBox, QLabel, QScrollArea, QSizePolicy, QSpacerItem, QVBoxLayout, QWidget

os.environ['NAPARI_ASYNC'] = '1'
os.environ['NAPARI_OCTREE'] = '1'

#Sys insert to allow for proper importing from module via debug
if 'glados_pycromanager' not in sys.modules and 'site-packages' not in __file__:
    sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..')))

import glados_pycromanager.Core.microscopeInterfaceLayer as MIL
import glados_pycromanager.GUI.napariGlados as napariGladosModule

from glados_pycromanager.GUI.napariGlados import *  #type: ignore

# Obtain the helperfunctions
# import glados_pycromanager.GUI.HelperFunctions #type: ignore
from glados_pycromanager.GUI.napariHelperFunctions import (  #type:ignore
    InitateNapariUI,
    getLayerIdFromName,
    showScaleBar,  #type: ignore
)
from glados_pycromanager.GUI.sharedFunctions import Shared_data  #type: ignore
from glados_pycromanager.GUI.utils import *  #type: ignore
from glados_pycromanager.GUI.utils import CustomMainWindow  #type:ignore

#endregion

#region Widget Definition
class GladosWidget(QWidget):
    """
    The main Class of glados-pycromanager widget that gets added to napari.
    """

    #: Debounce window for the resize-driven relayout (T-F6). A splitter drag
    #: delivers a QResizeEvent per pixel; the rebuild runs once at the end.
    RELAYOUT_DEBOUNCE_MS = 150

    def __init__(self, viewer: napari.viewer.Viewer, parent=None): #type: ignore
        """
        Init a glados widget, mostly passing around parent variables to daughter (plugin) variables. Used to be global-specified, but doesn't work with napari plugins for some reason.
        """
        super().__init__()
        self.setBaseSize(200,200)
        self._viewer = viewer
        self.type = None
        self.layoutInfo = None

        # T-F6: the relayout below tears down and rebuilds the whole scroll area,
        # so it must not run per pixel of a splitter drag. `resizeEvent` records
        # what layout the new size wants and restarts this timer; the rebuild
        # happens once, when the drag settles.
        self._pendingLayout = None
        self._appliedLayout = None
        self._relayoutTimer = QTimer(self)
        self._relayoutTimer.setSingleShot(True)
        self._relayoutTimer.setInterval(self.RELAYOUT_DEBOUNCE_MS)
        self._relayoutTimer.timeout.connect(self._applyPendingLayout)
        
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
                wanted = ('rows', 1)
            elif height > width * 1.25:  # Tall window
                wanted = ('columns', 1)
            elif width > height:  # Landscape
                wanted = ('rows', 2)
            else:  # Portrait
                wanted = ('columns', 2)

            self._scheduleGroupBoxLayout(wanted)

            super().resizeEvent(event)

    def _scheduleGroupBoxLayout(self, wanted):
        """Queue a relayout, coalescing a whole drag into one rebuild (T-F6).

        Most resize events during a drag land in the *same* orientation bucket,
        so a layout that matches what is already applied is dropped outright and
        costs nothing at all.
        """
        if wanted == self._appliedLayout:
            self._pendingLayout = None
            return

        self._pendingLayout = wanted
        timer = getattr(self, '_relayoutTimer', None)
        if timer is None:  # pre-__init__ resize; fall back to the direct call
            self._applyPendingLayout()
            return
        timer.start(self.RELAYOUT_DEBOUNCE_MS)

    def _applyPendingLayout(self):
        pending = self._pendingLayout
        if pending is None:
            return
        self._pendingLayout = None
        rowsOrColumns, n_items = pending
        self.set_groupBoxLayout(rowsOrColumns=rowsOrColumns, n_items=n_items)
        self._appliedLayout = pending
        
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
        # T-F6: these are orphaned by setParent(None) -- previously that was the
        # end of it, so every relayout leaked a QScrollArea (plus its container
        # and grid layout) that nothing ever destroyed. The group boxes are safe:
        # the loop above already re-parented them out of the old container.
        for i in reversed(range(self.dockWidget.count())):
            widget = self.dockWidget.itemAt(i).widget()
            if widget is not None:
                logging.debug(f"removing {widget}")
                self.dockWidget.removeWidget(widget)
                widget.setParent(None)
                # Only the scroll area we built here is ours to destroy. Anything
                # else that turns up as a direct child is left alone rather than
                # risking the deletion of a live control.
                if isinstance(widget, QScrollArea):
                    widget.deleteLater()

        #Create the following structure: scrollArea --> container --> mainGridLayout
        #create a QScrollArea
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
        self.scrollArea = scrollArea
    
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
        from glados_pycromanager.GUI.Analysis_dockWidgets import microManagerControlsUI_plugin
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
        
        from glados_pycromanager.GUI.Analysis_dockWidgets import MDAGlados_plugin
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
        # self.layoutInfo.set_font_and_margins_recursive(self.layoutInfo,font=QFont("Arial", 7)) #type:ignore
        # self.adjustSize()
        self.layoutInfo.adjustSize() #type:ignore
        super().resizeEvent(event)
        # self.layoutInfo.set_font_and_margins_recursive(self.layoutInfo,font=QFont("Arial", 7)) #type:ignore

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
        from glados_pycromanager.GUI.Analysis_dockWidgets import autonomousMicroscopy_plugin
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
        from glados_pycromanager.GUI.Analysis_dockWidgets import gladosSliders_plugin
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


class PerformanceModeWidget(GladosWidget):
    """
    Dock widget hosting the Performance Mode start/stop toggle + report.
    See glados_pycromanager/GUI/performance_mode_widget.py.

    Not opened automatically by MainWidget - it's a hidden/opt-in entry in
    napari's Plugins menu (see napari.yaml), so it needs to fall back to
    whichever entry point's `shared_data` is live: this module's (set by
    MainWidget, the napari-plugin path) or napariGlados.py's (set by
    runNapariPycroManager, the standalone `glados` command path).
    """
    def __init__(self, viewer: napari.viewer.Viewer, parent=None): #type:ignore
        super().__init__(viewer=viewer, parent=parent)

        if parent is None:
            self.shared_data = shared_data or getattr(napariGladosModule, 'shared_data', None)

        layout = QVBoxLayout()
        if self.shared_data is None:
            layout.addWidget(QLabel(
                "Open 'Run Glados-PycroManager' first, then reopen Performance Mode from the Plugins menu."
            ))
        else:
            from glados_pycromanager.GUI.performance_mode_widget import PerformanceModeWidget as _PerformanceModePanel
            self.dockWidget = _PerformanceModePanel(self.shared_data) #type:ignore
            layout.addWidget(self.dockWidget) # type: ignore
        self.setLayout(layout)
        logging.debug("dockWidget_PerformanceMode started")

    def resizeEvent(self, event):
        """"
        We don't want the GladosWidget resizeEvent for PerformanceMode
        """
        return super().resizeEvent(event)
#endregion

#Module-level handle to the running session's shared_data, set by MainWidget.
#Lets standalone Plugins-menu entries (e.g. PerformanceModeWidget) reach the
#live shared_data without being a dock added by MainWidget itself.
shared_data = None

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
        
        #Set up logging in the AppData folder, INFO and DEBUG
        from glados_pycromanager.observability.logger import set_up_logger
        set_up_logger()

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

        #Performance Mode is a diagnostic tool, not opened by default. Users open it
        #on demand via Plugins > Glados-PycroManager > Performance Mode.

        logging.info('Napari-glados-pycromanager plugin fully loaded')

#endregion