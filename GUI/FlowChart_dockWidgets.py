#Add inclusion of this folder:
import sys, os
sys.path.append('.\\GUI\\nodz')
from PyQt5 import QtCore, QtWidgets
import nodz_main #type: ignore
from PyQt5.QtCore import QObject, pyqtSignal
from MMcontrols import MMConfigUI, ConfigInfo
from MDAGlados import MDAGlados
from PyQt5.QtWidgets import QApplication, QGraphicsScene, QMainWindow, QGraphicsView, QPushButton, QVBoxLayout, QWidget, QTabWidget, QMenu, QAction
from PyQt5.QtCore import Qt, QSize
from PyQt5 import QtGui
from PyQt5.QtWidgets import QGridLayout, QPushButton
from PyQt5.QtWidgets import QLineEdit, QInputDialog, QDialog, QLineEdit, QComboBox, QVBoxLayout, QDialogButtonBox, QMenu, QAction
from PyQt5.QtGui import QFont, QColor, QTextDocument, QAbstractTextDocumentLayout
from PyQt5.QtCore import QRectF
import numpy as np
import os
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
import HelperFunctions #type: ignore
import logging
import utils

from PyQt5.QtWidgets import QApplication, QComboBox

class AnalysisScoringVisualisationDialog(QDialog):
    def __init__(self, parent=None, currentNode=None):
        """
        Advanced input dialog.

        Args:
            parent (QWidget): Parent widget.
            currentNode (Nodz): Node data.

        Returns:
            tuple: A tuple containing the line edit and combo box input from the user.
        """
        super().__init__()
        
        self.currentData = {}
        
        # Create layout
        layout = QVBoxLayout()
        
        self.mainLayout = QGridLayout()
        layout.addLayout(self.mainLayout)
        
        #Add a OK/cancel button set:
        button_box = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        button_box.accepted.connect(self.accept)
        button_box.rejected.connect(self.reject)
        #Add this to the bottom of the layout, stretching horizontally but centering in the center:
        layout.addWidget(button_box)
        
        self.setLayout(layout)

class nodz_analysisDialog(AnalysisScoringVisualisationDialog):
    def __init__(self, parent=None, currentNode=None):
        super().__init__(parent, currentNode)
        self.setWindowTitle("Analysis Options")
        
        #Let's try to get all possible analysis options
        analysisFunctions_Images = utils.functionNamesFromDir('AutonomousMicroscopy\\Analysis_Images')
        analysisFunctions_Measurements = utils.functionNamesFromDir('AutonomousMicroscopy\\Analysis_Measurements')
        analysisFunctions_Shapes = utils.functionNamesFromDir('AutonomousMicroscopy\\Analysis_Shapes')
        #Also add them back to back
        all_analysisFunctions = analysisFunctions_Images + analysisFunctions_Measurements + analysisFunctions_Shapes
        
        allDisplayNames,displaynameMapping = utils.displayNamesFromFunctionNames(all_analysisFunctions,'')
        #Store this mapping also in the node
        self.currentData['__displayNameFunctionNameMap__'] = displaynameMapping
        
        #Add a dropbox with all the options
        self.comboBox_analysisFunctions = QComboBox(self)
        if len(analysisFunctions_Images) > 0:
            for item in analysisFunctions_Images:
                displayNameI, displaynameMappingI = utils.displayNamesFromFunctionNames([item],'')
                self.comboBox_analysisFunctions.addItem(displayNameI[0])
            self.comboBox_analysisFunctions.insertSeparator(len(analysisFunctions_Images)-1)  
        if len(analysisFunctions_Measurements) > 0:
            for item in analysisFunctions_Measurements:
                displayNameI, displaynameMappingI = utils.displayNamesFromFunctionNames([item],'')
                self.comboBox_analysisFunctions.addItem(displayNameI[0])
            self.comboBox_analysisFunctions.insertSeparator(len(analysisFunctions_Images)+len(analysisFunctions_Measurements)-1)
        if len(analysisFunctions_Shapes) > 0:
            for item in analysisFunctions_Shapes:
                displayNameI, displaynameMappingI = utils.displayNamesFromFunctionNames([item],'')
                self.comboBox_analysisFunctions.addItem(displayNameI[0])
            self.comboBox_analysisFunctions.insertSeparator(len(analysisFunctions_Images)+len(analysisFunctions_Measurements)+len(analysisFunctions_Shapes)-1)          

        self.mainLayout.addWidget(self.comboBox_analysisFunctions, 0, 1)
        #give it an objectName:
        self.comboBox_analysisFunctions.setObjectName('comboBox_analysisFunctions_KEEP')
        #Give it a connect-callback if it's changed (then the layout should be changed)
        self.comboBox_analysisFunctions.currentIndexChanged.connect(lambda index, layout=self.mainLayout, dropdown=self.comboBox_analysisFunctions,displaynameMapping=displaynameMapping: utils.layout_changedDropdown(layout,dropdown,displaynameMapping))
        #Also give it a connect-callback to store the currentinfo:
        self.comboBox_analysisFunctions.currentIndexChanged.connect(lambda index, parentdata=self: utils.updateCurrentDataUponDropdownChange(parentdata))

        
        # pre-load all args/kwargs and their edit values - then hide all of them
        utils.layout_init(self.mainLayout,'',displaynameMapping,current_dropdown = self.comboBox_analysisFunctions)
        
        #Pre-load the options if they're in the current node info
        utils.preLoadOptions(self.mainLayout,currentNode.scoring_analysis_currentData)
        
        
        

class nodz_analysisMeasurementDialog(nodz_analysisDialog):
    def __init__(self, parent=None, currentNode=None):
        super().__init__(parent, currentNode)
        self.setWindowTitle("Analysis Measurement Options")

class nodz_openMMConfigDialog(QDialog):
    def __init__(self, parentNode=None, storedConfigsStrings=None):
        """
        Opens a dialog to modify the OpenMM configs of a node
        
        Args:
            parentNode (Node): The node to modify the configs of.
            storedConfigsStrings (list of tuples): A list of tuples with the name of the config and the value of the config.
            
        Returns:
            A tuple with the configs as a dictionary and the list of configs as strings.
        """
        super().__init__(None)
        self.newConfigUI = type(MMConfigUI)
        
        self.setWindowTitle("MM config Dialog")
        if parentNode is not None:
            from PyQt5.QtWidgets import QApplication, QVBoxLayout, QMainWindow, QWidget
            
            self.MMlayout = parentNode.MMconfigInfo.mainLayout
            
            #Create a new MMconfigUI with the same components as parentNode.MMconfigInfo:
            self.newConfigUI = MMConfigUI(parentNode.MMconfigInfo.config_groups, showConfigs=parentNode.MMconfigInfo.showConfigs, showLiveMode=parentNode.MMconfigInfo.showLiveMode, showROIoptions =parentNode.MMconfigInfo.showROIoptions, showStages=parentNode.MMconfigInfo.showStages, showCheckboxes=parentNode.MMconfigInfo.showCheckboxes,changes_update_MM=parentNode.MMconfigInfo.changes_update_MM)
            if parentNode.MMconfigInfo.changes_update_MM:
                print('WARNING! Nodz is actually changing the configs real-time rather than only when they are ran!')
            
            #Change some configs that are stored from last time this node was openend:
            if storedConfigsStrings is not None and len(storedConfigsStrings)>0:
                for storedConfigString in storedConfigsStrings:
                    #Find the config that has this name:
                    for config_id in self.newConfigUI.config_groups:
                        thisConfig = self.newConfigUI.config_groups[config_id]
                        if thisConfig.configGroupName() == storedConfigString[0]:
                            foundConfigId = config_id
                            #Set the checkbox to true:
                            self.newConfigUI.configCheckboxes[foundConfigId].setChecked(True)
                            #Set the value correctly in the GUI:
                            self.newConfigUI.updateValueInGUI(foundConfigId,storedConfigString[1])
                            break
            
            button_box = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
            button_box.accepted.connect(self.accept)
            button_box.rejected.connect(self.reject)
            
            # Create the QVBoxLayout
            layout = QVBoxLayout()

            # Create a QWidget to contain the QGridLayout
            grid_widget = QWidget()
            grid_widget.setLayout(self.newConfigUI.mainLayout) #type:ignore
            # Add the QMainWindow to the QVBoxLayout
            layout.addWidget(grid_widget)

            layout.addWidget(button_box)
            
            self.setLayout(layout)
        
    def ConfigsToBeChanged(self):
        """
        Returns the configs that have been changed in the MM config Dialog.
        
        Returns:
            A list of tuples with the name of the config and the value of the config that has been changed.
        """
        #Get the new value of all configs that are/should/want to be changed:
        ConfigsToBeChanged = []
        for config_id in range(len(self.newConfigUI.config_groups)):
            if self.newConfigUI.configCheckboxes[config_id].isChecked():
                #Add config name and new value
                ConfigsToBeChanged.append([self.newConfigUI.config_groups[config_id].configGroupName(),self.newConfigUI.currentConfigUISingleValue(config_id)])
        
        #Not adding ,self.newConfigUI.config_groups[config_id] (all info) for pickling reasons
        
        return ConfigsToBeChanged
        
        return self.newConfigUI

    # def getExposureTime(self):
    #     return self.mdaconfig.exposure_ms

    # def getmdaData(self):
    #     return self.mdaconfig

class nodz_openMDADialog(QDialog):
    def __init__(self, parent=None, parentData=None, currentNode = None):
        """
        Dialog for the MDA options.
        
        Args:
            parent (QtWidgets.QWidget): Parent widget of the dialog.
            parentData (FlowChartCore): Instance of the FlowChartCore class.
            currentNode (FlowChartNode): Instance of the FlowChartNode class.
            
        Returns:
            List: List of tuples, each containing the configuration name and its new value.
        """
        super().__init__(parent)
        self.parent = parent
        self.parentData = parentData
        self.currentNode=  currentNode
        
        self.setWindowTitle("MDA Dialog")
        if parentData is not None:
            from PyQt5.QtWidgets import QApplication, QVBoxLayout, QMainWindow, QWidget
            testQWidget = QWidget()
            
            if currentNode is not None:
                #Create a new MDAGlados with all the same components as currentNode.mdaData:
                self.mdaconfig = MDAGlados(parentData.core,None,None,parentData.shared_data,
                    hasGUI=True,
                    GUI_show_channel=currentNode.mdaData.GUI_show_channel,
                    GUI_show_exposure=currentNode.mdaData.GUI_show_exposure,
                    GUI_show_order=currentNode.mdaData.GUI_show_order,
                    GUI_show_storage=currentNode.mdaData.GUI_show_storage,
                    GUI_show_time=currentNode.mdaData.GUI_show_time,
                    GUI_show_xy=currentNode.mdaData.GUI_show_xy,
                    GUI_show_z=currentNode.mdaData.GUI_show_z,
                    GUI_acquire_button=False,
                    order = currentNode.mdaData.order,
                    num_time_points=currentNode.mdaData.num_time_points,
                    time_interval_s=currentNode.mdaData.time_interval_s,
                    z_start=currentNode.mdaData.z_start,
                    z_end=currentNode.mdaData.z_end,
                    z_step=currentNode.mdaData.z_step,
                    z_stage_sel = currentNode.mdaData.z_stage_sel,
                    z_nr_steps = currentNode.mdaData.z_nr_steps,
                    z_step_distance = currentNode.mdaData.z_step_distance,
                    z_nrsteps_radio_sel = currentNode.mdaData.z_nrsteps_radio_sel,
                    z_stepdistance_radio_sel= currentNode.mdaData.z_stepdistance_radio_sel,
                    channel_group=currentNode.mdaData.channel_group,
                    channels=currentNode.mdaData.channels,
                    channel_exposures_ms=currentNode.mdaData.channel_exposures_ms,
                    xy_positions=currentNode.mdaData.xy_positions,
                    xyz_positions=currentNode.mdaData.xyz_positions,
                    position_labels=currentNode.mdaData.position_labels,
                    exposure_ms=currentNode.mdaData.exposure_ms,
                    storage_folder=currentNode.mdaData.storageFolder,
                    storage_file_name=currentNode.mdaData.storageFileName)
            else: #This should never happen, but otherwise just open a new mdaglados instance
                self.mdaconfig = MDAGlados(parentData.core,None,None,parentData.shared_data,hasGUI=True)
            
            button_box = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
            button_box.accepted.connect(self.mdaconfig.showOptionChanged)
            button_box.accepted.connect(self.accept)
            button_box.rejected.connect(self.reject)
            

            # Create the QVBoxLayout
            layout = QVBoxLayout()

            # Create a QWidget to contain the QGridLayout
            grid_widget = QWidget()
            grid_widget.setLayout(self.mdaconfig.gui) #type:ignore
            # Add the QMainWindow to the QVBoxLayout
            layout.addWidget(grid_widget)

            layout.addWidget(button_box)
            
            self.setLayout(layout)
        
    def getInputs(self):
        return self.mdaconfig.mda

    def getExposureTime(self):
        return self.mdaconfig.exposure_ms

    def getmdaData(self):
        return self.mdaconfig

from PyQt5.QtWidgets import QApplication, QSizePolicy, QSpacerItem, QVBoxLayout, QScrollArea, QMainWindow, QWidget, QSpinBox, QLabel
class nodz_openScoringEndDialog(QDialog):
    def __init__(self, parent=None, parentData=None):
        super().__init__(parent)
        self.setWindowTitle("Scoring End")
        #Add an OK/Cancel box
        button_box = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        button_box.accepted.connect(self.accept)
        button_box.rejected.connect(self.reject)

        # Create the QVBoxLayout
        layout = QVBoxLayout()

        # Create a QWidget to contain the QGridLayout
        self.grid_widget = QGridLayout()
            
        self.nrVarsSpinbox = QSpinBox()
        self.nrVarsSpinbox.setMinimum(1)
        self.nrVarsSpinbox.valueChanged.connect(self.updateLayout)
        self.grid_widget.addWidget(self.nrVarsSpinbox,0,0)

        self.variableContainer = QGridLayout()
        # self.grid_widget.addLayout(self.variableContainer,1,0)
        
        self.variableContainerscrollArea = QScrollArea(self)
        self.variableContainerscrollArea.setWidgetResizable(True)
        self.variableContainerscrollAreaWidgetContents = QWidget()
        self.variableContainerscrollAreaWidgetContents.setLayout(self.variableContainer)
        self.variableContainerscrollArea.setWidget(self.variableContainerscrollAreaWidgetContents)
        self.grid_widget.addWidget(self.variableContainerscrollArea,1,0)
        
        # Set a fixed size for the QScrollArea
        self.variableContainerscrollArea.setFixedSize(QSize(300, 300))  # Adjust the size as needed
        # Add the QMainWindow to the QVBoxLayout
        layout.addLayout(self.grid_widget)

        layout.addWidget(button_box)
        
        self.setLayout(layout)
        
        #Add a spacer item at the bottom of the variableContainer so it's pushing it down down down
        spacerItem = QSpacerItem(20, 40, QSizePolicy.Policy.Minimum, QSizePolicy.Policy.Expanding)
        self.variableContainer.addItem(spacerItem, 999, 0)


        self.labels = []
        self.lineEdits = []
        
        #And update the layout at the start:
        self.updateLayout()
        
    def updateLayout(self):
        nrVars = self.nrVarsSpinbox.value()
        for label in self.labels:
            self.layout().removeWidget(label)
            label.deleteLater()
        for lineEdit in self.lineEdits:
            self.layout().removeWidget(lineEdit)
            lineEdit.deleteLater()

        self.labels = []
        self.lineEdits = []

        for i in range(nrVars):
            label = QLabel(f"Variable {i+1}:")
            lineEdit = QLineEdit()
            self.variableContainer.addWidget(label,i,0)
            self.labels.append(label)
            self.variableContainer.addWidget(lineEdit,i,1)
            self.lineEdits.append(lineEdit)

class FoVFindImaging_singleCh_configs(QDialog):
    def __init__(self, parent=None, parentData=None):
        """
        Advanced dialog for user to input the configuration for a single channel single FOV imaging experiment.

        Args:
            parent (QWidget): The parent widget for this dialog. Defaults to None.
            parentData: The data object for this app. Defaults to None.

        Returns:
            mdaData: The mdaData object with all the user input.
        """
        super().__init__(parent)
        
        self.setWindowTitle("Advanced Input Dialog")
        if parentData is not None:
            core = parentData.core
            
            
            # Get all config groups
            allConfigGroups={}
            nrconfiggroups = core.get_available_config_groups().size()
            for config_group_id in range(nrconfiggroups):
                allConfigGroups[config_group_id] = ConfigInfo(core,config_group_id)
            
            #Create the MM config via all config groups
            self.MMconfig = MMConfigUI(allConfigGroups, showConfigs = True,showStages=False,showROIoptions=False,showLiveMode=False,number_config_columns=5,changes_update_MM = False, showCheckboxes=True)
            
            button_box = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
            button_box.accepted.connect(self.accept)
            button_box.rejected.connect(self.reject)
                
            #Set the layout
            layout = QVBoxLayout()
            layout.addLayout(self.MMconfig.mainLayout)
            layout.addWidget(button_box)
            
            self.setLayout(layout)
        
    def getInputs(self):
        return self.MMconfig.getUIConfigInfo(onlyChecked=True)

class CustomGraphicsView(QtWidgets.QGraphicsView):
    def resizeEvent(self, event):
        """
        Handles resizing of the graphics view.
        
        Args:
            event (QResizeEvent): The resize event.
        """
        super().resizeEvent(event)
        self.updateGraphicsViewSize()
    
    def updateGraphicsViewSize(self):
        """
        Updates the size of the GraphicsView to match its viewport size.

        This function is called automatically when the viewport is resized.

        Args:
            None

        Returns:
            None
        """
        nodz.setFixedSize(self.viewport().size())

class GladosGraph():
    #Also adds these values correctly for each node:
        # self.n_connect_at_start = 0 #number of others connected at start (which should all be finished!)
        # self.connectedToFinish = []
        # self.connectedToData = []
        
    def __init__(self,parent):
        """
        Initialize a GladosGraph object

        This function initializes a GladosGraph object.

        Args:
            parent (nodz_mda.GladosFlowchart): The nodz_mda flowchart object.

        Returns:
            None

        """ 
        self.parent = parent
        self.nodes = []
        self.startNodeIndex = -1
        # self.unstartedNodes = []
        # self.ongoingNodes = []
        # self.finishedNodes = []

    def addRawGraphEval(self,graphEval):
        """
        Adds information about connections to the nodes in a graphEval

        This function adds information about connections to the nodes in a graphEval.
        In particular, it adds to each node the nodes it is connected to
        based on the connections in graphEval.

        Args:
            graphEval (list): A list of tuples that describe the connections in the graph.
                Each tuple has the form (sending_node_name, receiving_node_name)

        Returns:
            None

        """
        
        #We'll get a structure like this:
        # [('scoreStart_0.Start', '1s timer_0.start'), ('1s timer_0.Finished', '2s timer_0.start'), ('2s timer_0.Finished', 'scoreEnd_0.End')]
        
        # for graphEvalPartFull in graphEval:
        #     sendingNode = self.parent.findNodeByName(graphEvalPartFull[0].split('.')[0])
            
        #     receivingNode = self.parent.findNodeByName(graphEvalPartFull[1].split('.')[0])
        #     if graphEvalPartFull[0].split('.')[1] == 'Finished': #Later determine based on defineNodeInfo
        #         sendingNode.connectedToFinish.append(receivingNode)
                
        #     if graphEvalPartFull[1].split('.')[1] == 'Done': #Later determine based on defineNodeInfo
        #         sendingNode.connectedToData.append(receivingNode)
            
        #     if graphEvalPartFull[1].split('.')[1] == 'Start': #Later determine based on defineNodeInfo
        #         receivingNode.n_connect_at_start += 1
            
        #Also generate a list of all nodes in this graph
        self.allNodeNames = []
        for graphEvalPartFull in graphEval:
            for graphEvalPartFull2 in graphEvalPartFull:
                graphEvalPart = graphEvalPartFull2.split('.')[0]
                if graphEvalPart not in self.allNodeNames:
                    self.allNodeNames.append(graphEvalPart)
        
        for nodeName in self.allNodeNames:
            self.nodes.append(self.parent.findNodeByName(nodeName))

class NodeSignalManager(QObject):
    new_signal = pyqtSignal()
    
    def __init__(self):
        """
        Constructor for the NodeSignalManager class.

        This class is used to manage the signals emitted by nodes in the graph.
        This is a generic class to handle the signals of any number of nodes.

        Args:
            None

        Returns:
            None
        """
        QObject.__init__(self)
        super().__init__()
        self.signals = []

    def add_signal(self, signal_name):
        """
        Adds a new signal to the NodeSignalManager class.

        This function is used to dynamically add a new signal to the object.

        Args:
            signal_name (str): The name of the signal to be added.

        Returns:
            None
        """
        # Dynamically add a new signal to the object
        setattr(self, signal_name, self.new_signal)
        self.signals.append(self.new_signal)

    def print_signals(self):
        """
        Prints all the signals managed by this class.

        Args:
            None

        Returns:
            None
        """
        for signal in self.signals:
            print(signal)

    def emit_all_signals(self):
        """
        Emits all the signals managed by this class.

        Args:
            None

        Returns:
            None
        """
        for signal in self.signals:
            signal.emit()
            print(f"emitting signal {signal}")

class flowChart_dockWidgetF(nodz_main.Nodz):
    """
    Class that represents a Flowchart dock widget in napari-Glados. 
    Inherits from Nodz, which is a graph drawing tool.
    
    """
    def __init__(self,core=None,shared_data=None,MM_JSON=None):
        """
        Class that represents a Flowchart dock widget in napari-Glados. 
        Inherits from Nodz, which is a graph drawing tool.

        This functions initializes a flowchart dock widget in napari-Glados.
        It takes the napari viewer, the core Micro-Manager object, a
        shared_data object, and a JSON file containing the Micro-Manager
        settings.
        """
        #Create a QGridLayout:
        self.mainLayout = QGridLayout()
        
        
        #Add a few buttons to the left side:
        self.buttonsArea = QVBoxLayout()
        self.mainLayout.addLayout(self.buttonsArea,0,0)
        self.debugScoringButton = QPushButton('Debug Scoring')
        self.buttonsArea.addWidget(self.debugScoringButton)
        self.debugScoringButton.clicked.connect(lambda index: self.debugScoring())
        self.storePickleButton = QPushButton('Store Pickle')
        self.buttonsArea.addWidget(self.storePickleButton)
        self.storePickleButton.clicked.connect(lambda index: self.storePickle())
        self.loadPickleButton = QPushButton('Load Pickle')
        self.buttonsArea.addWidget(self.loadPickleButton)
        self.loadPickleButton.clicked.connect(lambda index: self.loadPickle())
        
        
        # Create a QGraphicsView 
        self.graphics_view = CustomGraphicsView()
        super(flowChart_dockWidgetF, self).__init__(parent=self.graphics_view)
        self.defineNodeInfo()
        
        # Add the QGraphicsView to the mainLayout
        self.mainLayout.addWidget(self.graphics_view,0,1)
        
        #Global variables for MM/napari
        self.core = core
        self.shared_data = shared_data
        self.MM_JSON=MM_JSON
        
        global nodz
        nodz = self
        self.initialize()
        self.show()
        #Needs these lines as init
        self.graphics_view.updateGraphicsViewSize()
        self.nodes = []
        self.nodeCounter={}
        
        
        #Connect required deleted/double clicked signals
        self.signal_NodeDeleted.connect(self.NodeRemoved)
        self.signal_NodeCreatedNodeItself.connect(self.NodeAdded)
        self.signal_NodeDoubleClicked.connect(self.NodeDoubleClicked)
        self.signal_PlugConnected.connect(self.PlugConnected)
        self.signal_PlugDisconnected.connect(self.PlugOrSocketDisconnected)
        self.signal_SocketConnected.connect(self.SocketConnected)
        
        #Focus on the nodes
        self._focus()
    
    def explore_attributes(self, obj, indent=0):
        """
        Recursively print the attributes of an object.

        This function is used for debugging purposes to explore the attributes of an object.
        It will print the attributes of `obj` and all of its sub-attributes, up to a maximum
        depth of 20.

        Parameters
        ----------
        obj : object
            The object to explore
        indent : int, optional
            The indentation level, by default 0
        """
        if indent < 20:
            attributes = vars(obj)
            for attr_name in attributes:
                if not attr_name.startswith('_'):
                    attr = getattr(obj, attr_name)
                    if not callable(attr):
                        print(" " * indent + attr_name)
                    else:
                        print(" " * indent + attr_name + '()')
                    if hasattr(attr, '__dict__'):
                        self.explore_attributes(attr, indent + 2)
                # except:
                #     pass
    
    def storePickle(self):
        """
        Save the current graph to a pickle file.

        This function saves the current graph to a pickle file, which can be loaded later using `loadPickle()`.
        """
        self.saveGraph('Testgraph.json')
    
    def loadPickle(self):
        """
        Load the graph from a pickle file.

        This function loads the graph from a pickle file created using `storePickle()`.
        """
        import pickle, copy
        #Fully clear graph and delete all nodes from memory:
        self.clearGraph()
        self.nodes = []
        #Set all counters to 0:
        for nodeType in self.nodeInfo:
            self.nodeInfo[nodeType]['NodeCounter'] = 0
            self.nodeInfo[nodeType]['NodeCounterNeverReset'] = 0
        self.loadGraph_KM('Testgraph.json')
    
    def nodeLookupName_withoutCounter(self,nodeName):
        """
        Returns the node name without the counter suffix.

        Given a node name like "MyNode_0" this function returns "MyNode".

        Parameters
        ----------
        nodeName : str
            The node name to strip the counter from.

        Returns
        -------
        str
            The node name without the counter suffix.
        """
        #Find the last underscore ('_0, _1, etc')
        index_last_underscore = nodeName.rfind('_')
        nodeNameNC = nodeName[:index_last_underscore]
        #Now get the correct lookup name by looking through all nodeInfo items
        for node_name, node_data in self.nodeInfo.items():
            # Check if the name matches the specific value
            if 'name' in node_data and node_data['name'] == nodeNameNC:
                finalNodeName = node_name
        
        return finalNodeName
    
    def PlugOrSocketConnected(self,srcNodeName, plugAttribute, dstNodeName, socketAttribute):
        """
        Handle when a plug or socket is connected.

        When a plug or socket is connected, this function is called. It will check if the destination
        node should be marked as 'started' or 'finished' based on the attributes connected.
        """
        
        print(f"plug/socket connected start: {srcNodeName}, {plugAttribute}, {dstNodeName}, {socketAttribute}")
        
        #First of all, abort if this exact connection is already made - this is called when loading the graph:
        # srcNode = self.findNodeByName(srcNodeName)
        # for plug in srcNode.plugs: #type:ignore
        #     if plug == plugAttribute:
        #         plugitem = srcNode.plugs[plug] #type:ignore
        #         #Look at all connections
        #         for connection in plugitem.connections:
        #             #Check if the connection is already made
        #             if connection.plugAttr == plugAttribute and connection.socketAttr == socketAttribute and connection.plugNode == srcNodeName and connection.socketNode == dstNodeName:
        #                 print('skipping this!')
        #                 return
        
        # sourceNode = self.findNodeByName(srcNodeName)
        # if plugAttribute in self.nodeInfo[self.nodeLookupName_withoutCounter(srcNodeName)]['finishedAttributes']: 
        #     destinationNode = self.findNodeByName(dstNodeName)
        #     #The destination node needs one extra to be started...
        #     destinationNode.n_connect_at_start += 1 #type: ignore
            
        #     #And the finished event of the source node is connected to the 'we finished one of the prerequisites' at the destination node
        #     sourceNode.customFinishedEmits.signals[0].connect(destinationNode.oneConnectionAtStartIsFinished) #type: ignore
        #     # sourceNode.customFinishedEmits.signals[0].connect(lambda: destinationNode.oneConnectionAtStartIsFinished) #type: ignore
        # logging.debug(f"plug/socket connected end: {srcNodeName}, {plugAttribute}, {dstNodeName}, {socketAttribute}")
    
    def PlugOrSocketDisconnected(self,srcNodeName, plugAttribute, dstNodeName, socketAttribute):
        """
        Handle when a plug or socket is disconnected.

        When a plug or socket is disconnected, this function is called. It will disconnect
        the finished event of the source node from the 'we finished one of the prerequisites' at the destination node.
        """
        print('plugorsocketdisconnected')
        # sourceNode = self.findNodeByName(srcNodeName)
        # if plugAttribute in self.nodeInfo[self.nodeLookupName_withoutCounter(srcNodeName)]['finishedAttributes']:
        #     signal = sourceNode.customFinishedEmits.signals[0] #type: ignore
        #     try:
        #         signal.disconnect()
        #     except:
        #         print('attempted to disconnect a disconnected signal')
        
        # destinationNode = self.findNodeByName(dstNodeName)
        # destinationNode.n_connect_at_start -= 1 #type:ignore
                
        # logging.debug(f"plug/socket disconnected: {srcNodeName}, {plugAttribute}, {dstNodeName}, {socketAttribute}")
    
    def PlugConnected(self,srcNodeName, plugAttribute, dstNodeName, socketAttribute):
        """
        Handle when a plug is connected.

        When a plug is connected, this function is called. It will check if the destination
        node should be marked as 'started' based on the attributes connected.
        """
        #Check if all are non-Nones:
        print('plug connected')
        # if any([srcNodeName is None, plugAttribute is None, dstNodeName is None, socketAttribute is None]):
        #     return
        # else:
        #     self.PlugOrSocketConnected(srcNodeName, plugAttribute, dstNodeName, socketAttribute)

    def SocketConnected(self,srcNodeName, plugAttribute, dstNodeName, socketAttribute):
        """
        Handle when a socket is connected.

        When a socket is connected, this function is called. It does not do anything
        special, it only exists to keep the Node class happy by having a method that
        corresponds to the 'SocketConnected' signal from the FlowChart.
        """
        #Check if all are non-Nones:
        print('socket connected')
        # if any([srcNodeName is None, plugAttribute is None, dstNodeName is None, socketAttribute is None]):
        #     return
        # else:
            # self.PlugOrSocketConnected(srcNodeName, plugAttribute, dstNodeName, socketAttribute)
    
    def NodeRemoved(self,nodeNames):
        """
        Handle when one or more nodes are removed from the flowchart.

        When one or more nodes are removed from the flowchart, this function is called.
        It will update the node counters of the corresponding node types.
        """
        logging.info('one or more nodes are removed!')
        for nodeName in nodeNames:
            for node_type, node_data in self.nodeInfo.items():
                if node_data['name'] in nodeName:
                    # if self.nodeInfo[node_type]['MaxNodeCounter'] < np.inf:
                    self.nodeInfo[node_type]['NodeCounter'] -= 1
            
            #Also remove from self.nodes:
            node = self.findNodeByName(nodeName)
            try:
                self.nodes.remove(node)
            except:
                print(f"failed to remove node: {nodeName}")
    
    def NodeAdded(self,node):
        """
        Handle when one or more nodes are created in the flowchart.

        When one or more nodes are created in the flowchart, this function is called.
        It does some pre-processing of the node and then calls performPostNodeCreation_Start.
        """
        logging.info('one or more nodes are created!')
        nodeType = self.nodeLookupName_withoutCounter(node.name)
        self.performPostNodeCreation_Start(node,nodeType)
    
    def NodeDoubleClicked(self,nodeName):
        """
        Handle double-clicking on a node in the flowchart.

        When a node is double-clicked, this function is called. Depending on the node, this 
        function will open a dialog to modify the node's data.
        """
        currentNode = self.findNodeByName(nodeName)
        if 'acquisition' in nodeName:
            dialog = nodz_openMDADialog(parentData=self,currentNode = currentNode)
            if dialog.exec_() == QDialog.Accepted:
                logging.debug(f"MDA dialog input: {dialog.getInputs()}")
            
            # currentNode.mdaData.exposure_ms = dialog.getExposureTime()
            # currentNode.mdaData.mda = dialog.getInputs()#type:ignore
            dialogmdaData = dialog.getmdaData()
            attrs_to_not_copy = ['gui','core','shared_data','has_GUI','data','staticMetaObject','MDA_completed','MM_JSON']
            #Loop over all attributes in dialogmdaData:
            for attrs in vars(dialogmdaData):
                if attrs not in attrs_to_not_copy:
                    setattr(currentNode.mdaData,attrs,getattr(dialogmdaData,attrs)) #type:ignore
            
            currentNode.displayText = str(dialog.getInputs())#type:ignore
            currentNode.update() #type:ignore
        elif 'changeProperties' in nodeName:
            currentNode = self.findNodeByName(nodeName)
            #Show dialog:
            dialog = nodz_openMMConfigDialog(parentNode=currentNode,storedConfigsStrings = currentNode.MMconfigInfo.config_string_storage) #type:ignore
            if dialog.exec_() == QDialog.Accepted:
                #Update the results of this dialog into the nodz node
                self.changeConfigStorageInNodz(currentNode,dialog.ConfigsToBeChanged())
        elif 'changeStagePos' in nodeName:
            currentNode = self.findNodeByName(nodeName)
            #Show dialog:
            dialog = nodz_openMMConfigDialog(parentNode=currentNode,storedConfigsStrings = currentNode.MMconfigInfo.config_string_storage) #type:ignore
            if dialog.exec_() == QDialog.Accepted:
                #Update the results of this dialog into the nodz node
                self.changeConfigStorageInNodz(currentNode,dialog.ConfigsToBeChanged())
        elif 'analysisMeasurement' in nodeName:
            currentNode = self.findNodeByName(nodeName)
            #TODO: pre-load dialog.currentData with currentNode.currentData if that exists (better naming i guess) to hold all pre-selected data 
            dialog = nodz_analysisDialog(currentNode = currentNode, parent = self)
            if dialog.exec_() == QDialog.Accepted:
                #Update the results of this dialog into the nodz node
                currentNode.scoring_analysis_currentData = dialog.currentData
                logging.info('Pressed OK on analysisMeasurementDialog')
        elif 'timer' in nodeName:
            currentNode.callAction(self) #type:ignore
        elif 'scoringStart' in nodeName:
            currentNode.callAction(self) #type:ignore
        elif 'scoringEnd' in nodeName:
            dialog = nodz_openScoringEndDialog(parentData=self,parent=self)
            if dialog.exec_() == QDialog.Accepted:
                dialogLineEdits = []
                for lineEdit in dialog.lineEdits:
                    dialogLineEdits.append(lineEdit.text())
                currentNode.scoring_end_currentData['Variables'] = dialogLineEdits #type: ignore
                #the dialogLineEdits should be the new sockets of the current node. However, if a plug with the name already exists, it shouldn't be changed.
                
                import time
                #We loop over the sockets:
                for socket_id in reversed(range(len(currentNode.sockets))):
                    socketFull = list(currentNode.sockets.items())[socket_id]
                    socket = socketFull[0]
                    #We check if the socket is in dialogLineEdits:
                    if socket not in dialogLineEdits:
                        # pos_in_dialogLineEdits = dialogLineEdits.index(socket)
                        # #If it is, we move it to its new location
                        # self.editAttribute(currentNode,socket_id,newName = None,newIndex=attr_offset)
                        # print(f"moving socket {socket} to {attr_offset}")
                        # attr_offset+=1
                    # else:
                        #If it isn't, we just delete it:
                        self.deleteAttribute(currentNode,socket_id)
                        self.update()
                        time.sleep(0.05)
                
                #Then we create new sockets or move existing sockets:
                for socket_new in dialogLineEdits:
                    pos_in_dialogLineEdits = dialogLineEdits.index(socket_new)
                    if socket_new not in currentNode.sockets:
                        self.createAttribute(currentNode, name=socket_new, index=pos_in_dialogLineEdits, preset='attr_default', plug=False, socket=True, dataType=None, socketMaxConnections=1)
                        self.update()
                        time.sleep(0.05)
                    else: #Else we move it from some other location to where we want it
                        #Find this socket in currentNode.sockets.items():
                        socketFull = list(currentNode.sockets.items())
                        pos_in_node_info = [socket_id for socket_id in range(len(socketFull)) if socketFull[socket_id][0] == socket_new][0]
                        old_pos = socketFull[pos_in_node_info][1].index
                        #Physically move it
                        self.editAttribute(currentNode,old_pos,newName = None, newIndex=socket_id)
                        self.update()
                        time.sleep(0.05)
                
                self.update()
                print(dialogLineEdits)
                print('Pressed OK on scoringEnd')
    
    def defineNodeInfo(self):
        """
        Define the node information for all nodes in the flowchart.

        This function is called once at the initialization of the flowchart.
        It returns a dictionary containing all nodes and their info.
        The info is used by the flowchart to create the nodes and their connections.
        
        It also contains layout information (colors and such)
        """
        self.nodeInfo = {}
        
        #We define the node info for each type of node like this: (might be expanded in the future)
        self.nodeInfo['acquisition'] = {}
        self.nodeInfo['acquisition']['name'] = 'acquisition'
        self.nodeInfo['acquisition']['displayName'] = 'Acquisition'
        self.nodeInfo['acquisition']['startAttributes'] = ['Acquisition start']
        self.nodeInfo['acquisition']['finishedAttributes'] = ['Finished']
        self.nodeInfo['acquisition']['dataAttributes'] = []
        self.nodeInfo['acquisition']['NodeCounter'] = 0
        self.nodeInfo['acquisition']['NodeCounterNeverReset'] = 0
        self.nodeInfo['acquisition']['MaxNodeCounter'] = np.inf
        
        self.nodeInfo['changeProperties'] = {}
        self.nodeInfo['changeProperties']['name'] = 'changeProperties'
        self.nodeInfo['changeProperties']['displayName'] = 'Change Properties'
        self.nodeInfo['changeProperties']['startAttributes'] = ['Start']
        self.nodeInfo['changeProperties']['finishedAttributes'] = ['Done']
        self.nodeInfo['changeProperties']['dataAttributes'] = []
        self.nodeInfo['changeProperties']['NodeCounter'] = 0
        self.nodeInfo['changeProperties']['NodeCounterNeverReset'] = 0
        self.nodeInfo['changeProperties']['MaxNodeCounter'] = np.inf
        
        self.nodeInfo['changeStagePos'] = {}
        self.nodeInfo['changeStagePos']['name'] = 'changeStagePos'
        self.nodeInfo['changeStagePos']['displayName'] = 'Change Stage Position'
        self.nodeInfo['changeStagePos']['startAttributes'] = ['Start']
        self.nodeInfo['changeStagePos']['finishedAttributes'] = ['Done']
        self.nodeInfo['changeStagePos']['dataAttributes'] = []
        self.nodeInfo['changeStagePos']['NodeCounter'] = 0
        self.nodeInfo['changeStagePos']['NodeCounterNeverReset'] = 0
        self.nodeInfo['changeStagePos']['MaxNodeCounter'] = np.inf
        
        self.nodeInfo['analysisGrayScaleTest'] = {}
        self.nodeInfo['analysisGrayScaleTest']['name'] = 'analysisGrayScaleTest'
        self.nodeInfo['analysisGrayScaleTest']['displayName'] = 'Analysis Grayscale Test [Measurement]'
        self.nodeInfo['analysisGrayScaleTest']['startAttributes'] = ['Analysis start']
        self.nodeInfo['analysisGrayScaleTest']['finishedAttributes'] = ['Finished']
        self.nodeInfo['analysisGrayScaleTest']['dataAttributes'] = ['Output']
        self.nodeInfo['analysisGrayScaleTest']['NodeCounter'] = 0
        self.nodeInfo['analysisGrayScaleTest']['NodeCounterNeverReset'] = 0
        self.nodeInfo['analysisGrayScaleTest']['MaxNodeCounter'] = np.inf
        
        self.nodeInfo['analysisMeasurement'] = {}
        self.nodeInfo['analysisMeasurement']['name'] = 'analysisMeasurement'
        self.nodeInfo['analysisMeasurement']['displayName'] = 'Analysis [Measurement]'
        self.nodeInfo['analysisMeasurement']['startAttributes'] = ['Analysis start']
        self.nodeInfo['analysisMeasurement']['finishedAttributes'] = ['Finished']
        self.nodeInfo['analysisMeasurement']['dataAttributes'] = ['Output']
        self.nodeInfo['analysisMeasurement']['NodeCounter'] = 0
        self.nodeInfo['analysisMeasurement']['NodeCounterNeverReset'] = 0
        self.nodeInfo['analysisMeasurement']['MaxNodeCounter'] = np.inf
        
        self.nodeInfo['analysisShapes'] = {}
        self.nodeInfo['analysisShapes']['name'] = 'analysisShapes'
        self.nodeInfo['analysisShapes']['displayName'] = 'Analysis [Shapes]'
        self.nodeInfo['analysisShapes']['startAttributes'] = ['Analysis start']
        self.nodeInfo['analysisShapes']['finishedAttributes'] = ['Finished']
        self.nodeInfo['analysisShapes']['dataAttributes'] = ['Output']
        self.nodeInfo['analysisShapes']['NodeCounter'] = 0
        self.nodeInfo['analysisShapes']['NodeCounterNeverReset'] = 0
        self.nodeInfo['analysisShapes']['MaxNodeCounter'] = np.inf
        
        self.nodeInfo['analysisImages'] = {}
        self.nodeInfo['analysisImages']['name'] = 'analysisImages'
        self.nodeInfo['analysisImages']['displayName'] = 'Analysis [Images]'
        self.nodeInfo['analysisImages']['startAttributes'] = ['Analysis start']
        self.nodeInfo['analysisImages']['finishedAttributes'] = ['Finished']
        self.nodeInfo['analysisImages']['dataAttributes'] = ['Output']
        self.nodeInfo['analysisImages']['NodeCounter'] = 0
        self.nodeInfo['analysisImages']['NodeCounterNeverReset'] = 0
        self.nodeInfo['analysisImages']['MaxNodeCounter'] = np.inf
        
        self.nodeInfo['scoringStart'] = {}
        self.nodeInfo['scoringStart']['name'] = 'scoringStart'
        self.nodeInfo['scoringStart']['displayName'] = 'Scoring start'
        self.nodeInfo['scoringStart']['startAttributes'] = []
        self.nodeInfo['scoringStart']['finishedAttributes'] = ['Start']
        self.nodeInfo['scoringStart']['dataAttributes'] = []
        self.nodeInfo['scoringStart']['NodeCounter'] = 0
        self.nodeInfo['scoringStart']['NodeCounterNeverReset'] = 0
        self.nodeInfo['scoringStart']['MaxNodeCounter'] = 1
        
        self.nodeInfo['scoringEnd'] = {}
        self.nodeInfo['scoringEnd']['name'] = 'scoringEnd'
        self.nodeInfo['scoringEnd']['displayName'] = 'Scoring end'
        self.nodeInfo['scoringEnd']['startAttributes'] = ['End']
        self.nodeInfo['scoringEnd']['finishedAttributes'] = []
        self.nodeInfo['scoringEnd']['dataAttributes'] = []
        self.nodeInfo['scoringEnd']['NodeCounter'] = 0
        self.nodeInfo['scoringEnd']['NodeCounterNeverReset'] = 0
        self.nodeInfo['scoringEnd']['MaxNodeCounter'] = 1
        
        self.nodeInfo['onesectimer'] = {}
        self.nodeInfo['onesectimer']['name'] = '1s timer'
        self.nodeInfo['onesectimer']['displayName'] = '1s timer'
        self.nodeInfo['onesectimer']['startAttributes'] = ['Start']
        self.nodeInfo['onesectimer']['finishedAttributes'] = ['Finished']
        self.nodeInfo['onesectimer']['dataAttributes'] = []
        self.nodeInfo['onesectimer']['NodeCounter'] = 0
        self.nodeInfo['onesectimer']['NodeCounterNeverReset'] = 0
        self.nodeInfo['onesectimer']['MaxNodeCounter'] = np.inf
        self.nodeInfo['twosectimer'] = {}
        self.nodeInfo['twosectimer']['name'] = '2s timer'
        self.nodeInfo['twosectimer']['displayName'] = '2s timer'
        self.nodeInfo['twosectimer']['startAttributes'] = ['Start']
        self.nodeInfo['twosectimer']['finishedAttributes'] = ['Finished']
        self.nodeInfo['twosectimer']['dataAttributes'] = []
        self.nodeInfo['twosectimer']['NodeCounter'] = 0
        self.nodeInfo['twosectimer']['NodeCounterNeverReset'] = 0
        self.nodeInfo['twosectimer']['MaxNodeCounter'] = np.inf
        self.nodeInfo['threesectimer'] = {}
        self.nodeInfo['threesectimer']['name'] = '3s timer'
        self.nodeInfo['threesectimer']['displayName'] = '3s timer'
        self.nodeInfo['threesectimer']['startAttributes'] = ['Start']
        self.nodeInfo['threesectimer']['finishedAttributes'] = ['Finished']
        self.nodeInfo['threesectimer']['dataAttributes'] = []
        self.nodeInfo['threesectimer']['NodeCounter'] = 0
        self.nodeInfo['threesectimer']['NodeCounterNeverReset'] = 0
        self.nodeInfo['threesectimer']['MaxNodeCounter'] = np.inf
        
        
        #We also add some custom JSON info about the node layout (colors and such)
        import json
        self.nodeLayout = json.loads('''{
            
            "scoringStart": {
                "bg": [80, 180, 80, 255],
                "border": [50, 50, 50, 255],
                "border_sel": [170, 80, 80, 255],
                "text": [180, 180, 240, 255]
            },
            "scoringEnd": {
                "bg": [180, 80, 80, 255],
                "border": [50, 50, 50, 255],
                "border_sel": [170, 80, 80, 255],
                "text": [180, 180, 240, 255]
            },
            "acquisition": {
                "bg": [80, 80, 180, 255],
                "border": [50, 50, 50, 255],
                "border_sel": [170, 80, 80, 255],
                "text": [180, 180, 240, 255]
            },
            "changeProperties": {
                "bg": [180, 80, 180, 255],
                "border": [50, 50, 50, 255],
                "border_sel": [170, 80, 80, 255],
                "text": [180, 180, 240, 255]
            },
            "changeStagePos": {
                "bg": [120, 20, 180, 255],
                "border": [50, 50, 50, 255],
                "border_sel": [170, 80, 80, 255],
                "text": [180, 180, 240, 255]
            }
            
            
            
        }''')
        self.addConfig(self.nodeLayout)
    
    def debugScoring(self):
        """
        Function to get some debug information from the scoring function(s)
        """
        print("Debug Scoring")
        scoreGraph = self.prepareGraph(methodName = "Score")
        
        
        print(self)
        print(self.evaluateGraph())
    
    def prepareGraph(self, methodName='Score'):
        """
        Function to prepare a graph based on the flowchart's connections.
        The resulting graph will have all nodes connected by edges based on the connections
        in the flowchart
        """
        graphEval = self.evaluateGraph()
        if methodName == 'Score':
            scoreGraph = GladosGraph(self)
            scoreGraph.addRawGraphEval(graphEval)
            for node in scoreGraph.nodes:
                self.giveInfoOnNode(node)
            return scoreGraph

    def findNodeByName(self, name):
        """
        Function to find a node based on its name attribute

        Args:
            name (str): The name of the node to find

        Returns:
            nodz.node: The node with the given name or None if not found
        """
        for node in self.nodes:
            #check if the attribute 'name' is found:
            if hasattr(node, 'name'):
                if node.name == name:
                    return node
        return None
    
    def changeConfigStorageInNodz(self,currentNode,configNameSet):
        """
        Function to change the config storage of a nodz node from the double-click popup to the MMconfigInfo class stored inside the node.

        This is useful when storing and loading configurations for a node, as the MMconfigInfo class can be serialized and deserialized.

        Args:
            currentNode (nodz.Node): The node to change the config storage of.
            configNameSet (set of tuples): A set of tuples in the form (configName, selectedValue)
        """
        #Changes a config from a double-click config popup to the MMconfig stored inside the nodz node itself (i.e. storing/loading of configs)
        
        #Add all of them to the MMconfigInfo.config_string_storage:
        currentNode.MMconfigInfo.config_string_storage=[]
        for singleConfig in configNameSet:
            currentNode.MMconfigInfo.config_string_storage.append([singleConfig[0],singleConfig[1]])
        return
    
    #replace the contextMenuEvent in nodz with this custom function:
    def contextMenuEvent(self, QMouseevent):
        """
        Function to create a context menu when right-clicking on the nodz canvas

        This function creates a context menu with all available node types that the user can select from, and adds the node to the nodz canvas at the position of the mouse click.

        Args:
            QMouseevent (PyQt5.QtGui.QMouseEvent): The mouse event that triggered this context menu
        """
        context_menu = QMenu(self)
        
        #Dynamically add all node types
        for node_type, node_data in self.nodeInfo.items():
            new_subAction = QAction(node_data['displayName'], self)
            context_menu.addAction(new_subAction)
            
            # Define a closure to capture the current value of node_type
            def create_lambda(node_type):
                return lambda _, event=QMouseevent: self.createNodeFromRightClick(event, nodeType=node_type)
            # Connect each action to its own lambda function
            new_subAction.triggered.connect(create_lambda(node_type))
            
        # Show the context menu at the event's position
        context_menu.exec_(QMouseevent.globalPos())

    def createNewNode(self, nodeType, event):
        """
        Creates a new node on the nodz canvas, with name and preset specified.

        This function creates a new node on the nodz canvas at the position of the mouse event.
        The name of the node is specified by appending a number to the nodeType parameter.
        The preset of the node is set to 'node_preset_1'.

        Args:
            nodeType (str): The type of node to create.
            event (PyQt5.QtGui.QMouseEvent): The mouse event that triggered this node creation.
        Returns:
            nodz.Node: The created nodz node.
        """
        if self.nodeInfo[nodeType]['NodeCounter'] >= self.nodeInfo[nodeType]['MaxNodeCounter']:
            print('Not allowed! Maximum number of nodes of this type reached')
            return
        
        #Create the new node with correct name and preset
        newNode = self.createNode(name=nodeType+"_", preset = 'node_preset_1', position=self.mapToScene(event.pos()),displayName = self.nodeInfo[nodeType]['displayName'])
        
        #Do post-node-creation functions - does this via the pyqtsignal!
    
    def performPostNodeCreation_Start(self,newNode,nodeType):
        """
        Handles post-node-creation functions for nodes.

        This function handles post-node-creation functions for nodes, such as
        setting the node name and preset, and adding custom attributes.

        Args:
            newNode (nodz.Node): The newly created node.
            nodeType (str): The type of node that was created.
        """
        if not newNode.createdFromLoading: #Normal case when it's simply created from the nodz canvas
            newNodeName = self.nodeInfo[nodeType]['name']+"_"+str(self.nodeInfo[nodeType]['NodeCounterNeverReset'])
            #Increase the nodeCounter - use the neverReset one to completely eliminate options of same-named nodes ever
            self.nodeInfo[nodeType]['NodeCounter']+=1
            self.nodeInfo[nodeType]['NodeCounterNeverReset']+=1
        elif newNode.createdFromLoading: #Special case in case it's created from loading the whole graph
            newNodeName = newNode.name #Don't change the name
            self.nodeInfo[nodeType]['NodeCounter']+=1
            #Get the node name:
            lastUnderscore = newNode.name.rfind('_')
            newNodeNumber = int(newNode.name[lastUnderscore+1:])
            #And set the nodecounterneverreset to be this value +1 or higher
            if self.nodeInfo[nodeType]['NodeCounterNeverReset'] < newNodeNumber+1:
                self.nodeInfo[nodeType]['NodeCounterNeverReset'] = newNodeNumber+1
            
        if nodeType in self.config:
            configtype = nodeType
        else:
            configtype = 'node_preset_1'
            
        
        #Change name, change sdisplayName, change preset:
        newNode.changeName(newNodeName)
        newNode.changeDisplayName(self.nodeInfo[nodeType]['displayName'])
        newNode.changePreset(configtype)
        
        self.nodes.append(newNode)
        
        if len(self.nodeInfo[nodeType]['startAttributes']) > 0:
            newNode.customStartEmits = NodeSignalManager()
        else:
            newNode.customStartEmits = None
        if len(self.nodeInfo[nodeType]['finishedAttributes']) > 0:
            newNode.customFinishedEmits = NodeSignalManager()
        else:
            newNode.customFinishedEmits = None
        if len(self.nodeInfo[nodeType]['dataAttributes']) > 0:
            newNode.customDataEmits = NodeSignalManager()
        else:
            newNode.customDataEmits = None
        
        #Add custom attributes where necessary
        for attr in self.nodeInfo[nodeType]['startAttributes']:
            self.createAttribute(node=newNode, name=attr, index=-1, preset='attr_preset_1', plug=False, socket=True)
            newNode.customStartEmits.add_signal(attr) #type: ignore
        for attr in self.nodeInfo[nodeType]['finishedAttributes']:
            self.createAttribute(node=newNode, name=attr, index=-1, preset='attr_preset_1', plug=True, socket=False)
            newNode.customFinishedEmits.add_signal(attr) #type: ignore
        for attr in self.nodeInfo[nodeType]['dataAttributes']:
            self.createAttribute(node=newNode, name=attr, index=-1, preset='attr_preset_1', plug=True, socket=False)
            newNode.customDataEmits.add_signal(attr) #type: ignore
        
        if len(self.nodeInfo[nodeType]['startAttributes']) > 0:
            newNode.customStartEmits.print_signals() #type: ignore
        if len(self.nodeInfo[nodeType]['finishedAttributes']) > 0:
            newNode.customFinishedEmits.print_signals() #type: ignore
        if len(self.nodeInfo[nodeType]['dataAttributes']) > 0:
            newNode.customDataEmits.print_signals()  #type: ignore
            
        #Custom functions that should be done
        if nodeType == 'acquisition':
            #Attach a MDA data to this node
            newNode.mdaData = MDAGlados(self.core,self.MM_JSON,None,self.shared_data,hasGUI=True) # type: ignore
            
            #Do the acquisition upon callAction
            newNode.callAction = lambda self, node=newNode: node.mdaData.MDA_acq_from_GUI()
            
            #Add the node emits of 'finishing' upon MDA completion.
            newNode.mdaData.MDA_completed.connect(lambda self, node = newNode: node.customFinishedEmits.emit_all_signals())
            #Note: the recorded MDA data is stored in node.mdaData.data - any analysis method should find/read this.
            #The core is at node.mdaData.core
            
            #Also connect the node's finishedMDA
            newNode.mdaData.MDA_completed.connect(newNode.finishedmda)
        elif nodeType == 'changeProperties':
            #attach MMconfigUI to this:
            
            
            
            # Get all config groups
            allConfigGroups={}
            nrconfiggroups = self.core.get_available_config_groups().size() #type:ignore
            for config_group_id in range(nrconfiggroups):
                allConfigGroups[config_group_id] = ConfigInfo(self.core,config_group_id)
        
            newNode.MMconfigInfo = MMConfigUI(allConfigGroups,showConfigs = True,showStages=False,showROIoptions=False,showLiveMode=False,number_config_columns=5,changes_update_MM = False,showCheckboxes = True) # type: ignore
            
            
            #Add the callaction
            newNode.callAction = lambda self, node=newNode: self.MMconfigChangeRan(node)
            newNode.callActionRelatedObject = self #this line is required to run a function from within this class
        elif nodeType == 'changeStagePos':
            # Get all config groups
            allConfigGroups={}
            nrconfiggroups = self.core.get_available_config_groups().size() #type:ignore
            for config_group_id in range(nrconfiggroups):
                allConfigGroups[config_group_id] = ConfigInfo(self.core,config_group_id)
        
            newNode.MMconfigInfo = MMConfigUI(allConfigGroups,showConfigs = False,showStages=True,showROIoptions=False,showLiveMode=False,number_config_columns=5,changes_update_MM = False,showCheckboxes = True,showRelativeStages = True) # type: ignore
            
            #Add the callaction
            newNode.callAction = lambda self, node=newNode: self.MMstageChangeRan(node)
            newNode.callActionRelatedObject = self #this line is required to run a function from within 
        elif nodeType == 'analysisGrayScaleTest':
            newNode.callAction = lambda self, node=newNode: self.GrayScaleTest(node)
            newNode.callActionRelatedObject = self #this line is required to run a function from within this class
        elif nodeType == 'analysisMeasurement':
            newNode.callAction = lambda self, node=newNode: self.scoring_analysis_ran(node)
            newNode.callActionRelatedObject = self #this line is required to run a function from within this class
        elif nodeType == 'onesectimer':
            newNode.callAction = lambda self, node=newNode, timev = 1: self.timerCallAction(node,timev=timev)
            newNode.callActionRelatedObject = self #this line is required to run a function from within this class
        elif nodeType == 'twosectimer':
            newNode.callAction = lambda self, node=newNode, timev = 2: self.timerCallAction(node,timev=timev)
            newNode.callActionRelatedObject = self #this line is required to run a function from within this class
        elif nodeType == 'threesectimer':
            newNode.callAction = lambda self, node=newNode, timev = 3: self.timerCallAction(node,timev=timev)
            newNode.callActionRelatedObject = self #this line is required to run a function from within this class
        elif nodeType == 'scoringStart':
            newNode.callAction = lambda self, node=newNode: self.scoringStart(node)
            newNode.callActionRelatedObject = self #this line is required to run a function from within this class
        elif nodeType == 'scoringEnd':
            newNode.callAction = lambda self, node=newNode: self.scoringEnd(node)
            newNode.callActionRelatedObject = self #this line is required to run a function from within this class
        else:
            newNode.callAction = None

        newNode.update()
    
    def scoring_analysis_ran(self,node):
        
        #Find the node that is connected (i.e. downstream) to this
        connectedNode = None
        for connection in self.evaluateGraph():
            if connection[1][connection[1].rfind('.')+1:] == 'Analysis start':
                if connection[1][:connection[1].rfind('.')] == node.name:
                    connectedNodeName = connection[0][:connection[0].rfind('.')]
                    connectedNode = self.findNodeByName(connectedNodeName)
        if connectedNode is None:
            print('Error! No connected node found for scoring analysis')
            return
        
        #First assess that it's a MDA node:
        if 'acquisition' not in connectedNode.name:
            print('Error! Acquisition not connected to Grayscale test!')
        else:
            #And then find the mdaData object
            mdaDataobject = connectedNode.mdaData
            
            #Figure out which function is selected in the scoring_analysis node
            selectedFunction = utils.functionNameFromDisplayName(node.scoring_analysis_currentData['__selectedDropdownEntryAnalysis__'],node.scoring_analysis_currentData['__displayNameFunctionNameMap__'])
            #Figure out the belonging evaluation-text
            evalText = utils.getFunctionEvalTextFromCurrentData(selectedFunction,node.scoring_analysis_currentData,'mdaDataobject.data','self.shared_data.core')
            #And evaluate the custom function with custom parameters
            output = eval(evalText) #type:ignore
            
            #Display final output to the user for now
            print(f"FINAL OUTPUT FROM NODE {node.name}: {output}")
            
            #Finish up
            self.finishedEmits(node)
    
    def MMstageChangeRan(self,node):
        print('MMstageChange')
        self.finishedEmits(node)
        
    def MMconfigChangeRan(self,node):
        """
        Handle the configuration change event for a node.

        This function handles the configuration change event for a node, by
        changing the desired configs in the Core.

        Args:
            node (nodz.Node): The node that has triggered the event.
        """
        print('MMconfigChangeRan')
        #We need to change some configs (probably):
        for config_to_change in node.MMconfigInfo.config_string_storage:
            #Change the config, and wait for the config to be changed
            self.core.set_config(config_to_change[0],config_to_change[1]) #type:ignore
            self.core.wait_for_config(config_to_change[0],config_to_change[1])#type:ignore
        self.finishedEmits(node)
    
    def GrayScaleTest(self,node):
        """
        This function is the action function for the Grayscale Test node in the Flowchart.

        This function takes the data from the MDA node, which should be connected
        to the Grayscale Test node, and performs a grayscale analysis on the data.

        Args:
            node (nodz.Node): The node that has triggered the event.

        """
        #Find the node that is connected to this
        connectedNode = node.sockets['Analysis start'].connected_slots[0].parentItem()
        #First assess that it's a MDA node:
        if 'acquisition' not in connectedNode.name:
            print('Error! Acquisition not connected to Grayscale test!')
        else:
            #And then find the mdaData object
            mdaDataobject = connectedNode.mdaData
            #Thow this into the analysis:
            
            avgGrayVal = eval(HelperFunctions.createFunctionWithKwargs("AverageIntensity.AvgGrayValue",NDTIFFStack="mdaDataobject.data",core="mdaDataobject.core"))
            print(f"found avg gray val: {avgGrayVal}")
            
        self.finishedEmits(node)

    def finishedEmits(self,node):
        """
        This function emits the customFinishedEmits signal of a node.

        Args:
            node (nodz.Node): The node that needs to finish.

        Returns:
            None
        """
        node.customFinishedEmits.emit_all_signals()

    def GraphToSignals(self):
        """Idea: we evaluate the graph at this time point, connect all signals/emits:
        
        """
        print('graphicing to signals')
        #Loop over all nodes:
        for node in self.nodes:
            node.n_connect_at_start = 0
            signal = node.customFinishedEmits.signals[0] #type: ignore
            try:
                #This disconnects all signals
                signal.disconnect()
            except:
                print('attempted to disconnect a disconnected signal')
            
        #Create all required signal connections
        currentgraph = self.evaluateGraph()
        for connection in currentgraph:
            plugAttribute = connection[0][connection[0].rfind('.')+1:]
            socketAttribute = connection[1][connection[1].rfind('.')+1:]
            srcNodeName = connection[0][:connection[0].rfind('.')]
            dstNodeName = connection[1][:connection[1].rfind('.')]
            
            typeOfFinishedAttributes_of_srcNode = self.nodeInfo[self.nodeLookupName_withoutCounter(srcNodeName)]['finishedAttributes']
            typeOfStartAttributes_of_dstNode = self.nodeInfo[self.nodeLookupName_withoutCounter(dstNodeName)]['startAttributes']
            
            if plugAttribute in typeOfFinishedAttributes_of_srcNode and socketAttribute in typeOfStartAttributes_of_dstNode:
                srcNode = self.findNodeByName(srcNodeName)#self.nodeInfo[self.nodeLookupName_withoutCounter(srcNodeName)]
                dstNode = self.findNodeByName(dstNodeName)
                #The destination node needs one extra to be started...
                dstNode.n_connect_at_start += 1 #type: ignore
                
                #And the finished event of the source node is connected to the 'we finished one of the prerequisites' at the destination node
                srcNode.customFinishedEmits.signals[0].connect(dstNode.oneConnectionAtStartIsFinished) #type: ignore
                print(f"connected {srcNodeName} to {dstNodeName} via {plugAttribute} to {socketAttribute}")
            else:
                print(f"not connected {srcNodeName} to {dstNodeName} via {plugAttribute} to {socketAttribute}")
            
        
        # if plugAttribute in self.nodeInfo[self.nodeLookupName_withoutCounter(srcNodeName)]['finishedAttributes']: 
        #     destinationNode = self.findNodeByName(dstNodeName)
        #     #The destination node needs one extra to be started...
        #     destinationNode.n_connect_at_start += 1 #type: ignore
            
        #     #And the finished event of the source node is connected to the 'we finished one of the prerequisites' at the destination node
        #     sourceNode.customFinishedEmits.signals[0].connect(destinationNode.oneConnectionAtStartIsFinished) #type: ignore
        #     # sourceNode.customFinishedEmits.signals[0].connect(lambda: destinationNode.oneConnectionAtStartIsFinished) #type: ignore
    def scoringStart(self,node):
        """
        This function is the action function for the Scoring Start node in the Flowchart.

        This function signals to the rest of the flowchart that it's time to start
        the scoring routine.

        Args:
            node (nodz.Node): The node that has triggered the event.

        Returns:
            None
        """
        print('Starting the score routine!')
        
        self.GraphToSignals()
        
        self.finishedEmits(node)
        
    def scoringEnd(self,node):
        """
        This function is the action function for the Scoring End node in the Flowchart.

        This function signals to the rest of the flowchart that the scoring routine is finished.

        Args:
            node (nodz.Node): The node that has triggered the event.

        Returns:
            None
        """
        print('Scoring finished fully!')
        print('----------------------')
        # self.finishedEmits(node)

    def timerCallAction(self,node,timev):
        """
        This function is the action function for the Timer Call node in the Flowchart.

        This function waits for a specified amount of time before triggering the next node in the flowchart.

        Args:
            node (nodz.Node): The node that has triggered the event.
            timev (float): The time to wait in seconds.

        Returns:
            None
        """
        import time
        print('start time sleeping')
        time.sleep(timev)
        print('end time sleeping')
        self.finishedEmits(node)

    def createNodeFromRightClick(self,event,nodeType=None):
        """
        This function creates a new node in the flowchart when the user right-clicks in the flowchart area. Mostly a wrapper function

        Args:
            event (QMouseEvent): The mouse event that triggered this function.
            nodeType (str): The type of node to create. Defaults to None.

        Returns:
            None
        """
        self.createNewNode(nodeType,event)

    def giveInfoOnNode(self,node):
        """
        Prints information about a node in the flowchart

        This function prints some basic information about a node in the flowchart.

        Args:
            node (nodz.Node): The node to get information about.

        Returns:
            None
        """
        print('--------')
        print(node)
        print(f"node name: {node.name}")
        print(f"incoming connections: {node.n_connect_at_start}" )
        # print(f"outgoing connections - finished: {node.connectedToFinish}")
        # print(f"outgoing connections - data: {node.connectedToData}")

    def getNodz(self):
        return self
    
    def focus(self):
        self._focus()

def flowChart_dockWidgets(core,MM_JSON,main_layout,sshared_data):
    """
    Creates a dock widget with a flowchart for running analysis workflows

    This function creates a dock widget with a flowchart for running analysis workflows.

    Args:
        core (pycro-manager.Core): A connection to the micro-manager API.
        MM_JSON (dict): A dictionary containing the settings from the Micro-Manager settings file.
        main_layout (PyQt5.QtWidgets.QVBoxLayout): The main layout of the dock widget.
        sshared_data (Shared_data): A shared data class instance containing shared data between widgets.

    Returns:
        flowChart_dockWidgetF: The flowchart dock widget.
    """

    global shared_data, napariViewer
    shared_data = sshared_data
    napariViewer = shared_data.napariViewer
    
    #Create the a flowchart testing
    flowChart_dockWidget = flowChart_dockWidgetF(core=core,shared_data=shared_data,MM_JSON=MM_JSON)
    main_layout.addLayout(flowChart_dockWidget.mainLayout,0,0)
    
    flowChart_dockWidget.getNodz()
    
    return flowChart_dockWidget