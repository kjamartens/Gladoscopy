#region imports
#Add inclusion of this folder:
import sys, os
from PyQt5.QtWidgets import QGroupBox
sys.path.append('glados-pycromanager\\glados_pycromanager\\GUI\\nodz')
from PyQt5 import QtCore, QtWidgets
import nodz_main #type: ignore
from PyQt5.QtCore import QObject, pyqtSignal
from MMcontrols import MMConfigUI, ConfigInfo
from MDAGlados import MDAGlados
from PyQt5.QtWidgets import QApplication, QGraphicsScene, QMainWindow, QGraphicsView, QPushButton, QVBoxLayout, QTextEdit, QWidget, QTabWidget, QMenu, QAction, QColorDialog, QHBoxLayout, QCheckBox, QDoubleSpinBox
from PyQt5.QtCore import Qt, QSize
from PyQt5 import QtGui
from PyQt5.QtWidgets import QGridLayout, QPushButton
from PyQt5.QtWidgets import QLineEdit, QInputDialog, QDialog, QLineEdit, QComboBox, QVBoxLayout, QDialogButtonBox, QMenu, QAction
from PyQt5.QtGui import QFont, QColor, QTextDocument, QAbstractTextDocumentLayout
from PyQt5.QtCore import QRectF
from qtpy.QtWidgets import QFileDialog, QMessageBox
from qtpy.QtWidgets import QFileDialog
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
from Real_Time_Analysis import * #type: ignore
import HelperFunctions #type: ignore
import logging
import utils
from nodz import nodz_utils
from PyQt5.QtWidgets import QApplication, QComboBox
from PyQt5.QtWidgets import QApplication, QSizePolicy, QSpacerItem, QVBoxLayout, QScrollArea, QMainWindow, QWidget, QSpinBox, QLabel
#endregion

#region Dialogs_Nodz
class AnalysisScoringVisualisationDialog(QDialog):
    """
    A Dialog that is created for analysis/scoring/visualisation methods in the Nodz layout. Basically based on EVE's flexible file-finding function methodology. Also used for real-time analysis dialog.
    """
    def __init__(self, parent=None, currentNode=None, addVisualisationBox = False):
        """
        Advanced input dialog.

        Args:
            parent (QWidget): Parent widget.
            currentNode (Nodz): Node data.
            addVisualisationBox: A boolean indicating whether to add a visualization CheckBox (default is False). 

        Returns:
            tuple: A tuple containing the line edit and combo box input from the user.
        """
        super().__init__()
        
        self.currentData = {}
        
        # Create layout
        layout = QVBoxLayout()
        
        self.mainLayout = QGridLayout()
        layout.addLayout(self.mainLayout)
        
        bottomHbox = QHBoxLayout()
        
        if addVisualisationBox:
            self.visualisationBox = QCheckBox()
            visualisationLabel = QLabel('Visualise')
            visualiseHbox = QHBoxLayout()
            visualiseHbox.addWidget(self.visualisationBox)
            visualiseHbox.addWidget(visualisationLabel)
            bottomHbox.addLayout(visualiseHbox)
            
        #Add a OK/cancel button set:
        button_box = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        button_box.accepted.connect(self.accept)
        button_box.rejected.connect(self.reject)
        
        bottomHbox.addWidget(button_box)
        #Add this to the bottom of the layout, stretching horizontally but centering in the center:
        layout.addLayout(bottomHbox)
        
        self.setLayout(layout)

class nodz_analysisDialog(AnalysisScoringVisualisationDialog):
    """
    A Dialog that is created for analysis methods in the Nodz layout. Basically based on EVE's flexible file-finding function methodology.
    """
    def __init__(self, parent=None, currentNode=None):
        """
        Initializes the Analysis Options window.
        
        Args:
            parent: Parent widget (default is None).
            currentNode: Current node (default is None).
        
        Returns:
            None
        """
        super().__init__(parent, currentNode)
        self.setWindowTitle("Analysis Options")
        self.setMinimumSize(400,100)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        
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
        utils.layout_init(self.mainLayout,'',displaynameMapping,current_dropdown = self.comboBox_analysisFunctions,nodzInfo=parent)
        
        # if currentNode.scoring_analysis_currentData == {}: #type:ignore
        #     utils.preLoadOptions_analysis(self.mainLayout,self.currentData)
        # else: 
            
        #Add an expanding spacer at the bottom:
        spacer_item = QSpacerItem(
            20, 40, QSizePolicy.Minimum, QSizePolicy.Expanding
        )
        # Add the spacer item to the grid layout
        self.mainLayout.addItem(spacer_item, 99, 0)
        
        #Pre-load the options if they're in the current node info
        utils.preLoadOptions_analysis(self.mainLayout,currentNode.scoring_analysis_currentData) #type:ignore
        

class nodz_realTimeAnalysisDialog(AnalysisScoringVisualisationDialog):
    """
    A Dialog that is created for real-time analysis methods in the Nodz layout. Basically based on EVE's flexible file-finding function methodology.
    """
    def __init__(self, parent=None, currentNode=None,addVisualisationBox=True):
        """
        Initializes the Real-Time Analysis Options window.
        
        Args:
            parent: The parent widget (default is None).
            currentNode: The current node (default is None).
            addVisualisationBox: A boolean indicating whether to add a visualization CheckBox (default is True). 
        
        Returns:
            None
        """
        
        super().__init__(parent, currentNode,addVisualisationBox)
        self.setWindowTitle("Real-Time Analysis Options")
        
        #Let's try to get all possible RT analysis options
        realTimeAnalysisFunctions = utils.functionNamesFromDir('AutonomousMicroscopy\\Real_Time_Analysis')
        
        allDisplayNames,displaynameMapping = utils.displayNamesFromFunctionNames(realTimeAnalysisFunctions,'')
        #Store this mapping also in the node
        self.currentData['__displayNameFunctionNameMap__'] = displaynameMapping
        
        #Add a dropbox with all the options
        self.comboBox_RTanalysisFunctions = QComboBox(self)
        if len(realTimeAnalysisFunctions) > 0:
            for item in realTimeAnalysisFunctions:
                displayNameI, displaynameMappingI = utils.displayNamesFromFunctionNames([item],'')
                self.comboBox_RTanalysisFunctions.addItem(displayNameI[0]) 
        
        self.mainLayout.addWidget(self.comboBox_RTanalysisFunctions, 0, 1)
        #give it an objectName:
        self.comboBox_RTanalysisFunctions.setObjectName('comboBox_RTanalysisFunctions_KEEP')
        #Give it a connect-callback if it's changed (then the layout should be changed)
        self.comboBox_RTanalysisFunctions.currentIndexChanged.connect(lambda index, layout=self.mainLayout, dropdown=self.comboBox_RTanalysisFunctions,displaynameMapping=displaynameMapping: utils.layout_changedDropdown(layout,dropdown,displaynameMapping))
        #Also give it a connect-callback to store the currentinfo:
        self.comboBox_RTanalysisFunctions.currentIndexChanged.connect(lambda index, parentdata=self: utils.updateCurrentDataUponDropdownChange(parentdata))

        # pre-load all args/kwargs and their edit values - then hide all of them
        utils.layout_init(self.mainLayout,'',displaynameMapping,current_dropdown = self.comboBox_RTanalysisFunctions,nodzInfo=parent,skipInput=True)
        
        #Pre-load the options if they're in the current node info
        if 'real_time_analysis_currentData' in vars(currentNode):
            if '__realTimeVisualisation__' in currentNode.real_time_analysis_currentData and currentNode.real_time_analysis_currentData['__realTimeVisualisation__']: #type:ignore
                self.visualisationBox.setChecked(True)
            
            utils.preLoadOptions_realtime(self.mainLayout,currentNode.real_time_analysis_currentData) #type:ignore

class nodz_analysisMeasurementDialog(nodz_analysisDialog):
    """
    A Dialog that is created for analysis methods in the Nodz layout. Basically based on EVE's flexible file-finding function methodology.
    """
    def __init__(self, parent=None, currentNode=None):
        """
        Dummy init function.
        """
        super().__init__(parent, currentNode)
        self.setWindowTitle("Analysis Measurement Options")

class nodz_openStoreDataDialog(QDialog):
    def __init__(self, parentNode=None):
        """
        Initializes the TimerDialog.
        
        Args:
            parentNode: The parent node of the TimerDialog. If provided, the timerInfo will be set to the timerInfo of the parentNode.
        
        Returns:
            None
        """
        super().__init__(None)
        self.setWindowTitle("StoreData Dialog")
        self.storeDataInfo = 0
        if parentNode is not None:
            from PyQt5.QtWidgets import QApplication, QVBoxLayout, QMainWindow, QWidget
            self.storeDataInfo = parentNode.storeDataInfo

        button_box = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        button_box.accepted.connect(self.updateFields)
        button_box.accepted.connect(self.accept)
        button_box.rejected.connect(self.reject)
        
        # Create the QVBoxLayout
        layout = QVBoxLayout()

        #Create two line-edits and add them:
        self.item_to_store_lineEdit = QLineEdit()
        if 'item_to_store' in self.storeDataInfo: #type:ignore
            self.item_to_store_lineEdit.setText(self.storeDataInfo['item_to_store']) #type:ignore
        else:
            self.storeDataInfo['item_to_store'] = ''
        self.item_to_store_lineEdit.textChanged.connect(lambda value: self.updateFields)
        self.store_location_lineEdit = QLineEdit()
        if 'store_location' in self.storeDataInfo: #type:ignore
            self.store_location_lineEdit.setText(self.storeDataInfo['store_location']) #type:ignore
        else:
            self.storeDataInfo['store_location'] = ''
        self.store_location_lineEdit.textChanged.connect(lambda value: self.updateFields)
            

        # Add the QMainWindow to the QVBoxLayout
        layout.addWidget(self.item_to_store_lineEdit)
        layout.addWidget(self.store_location_lineEdit)

        layout.addWidget(button_box)
        
        self.setLayout(layout)
        
    def updateFields(self):
        self.storeDataInfo['item_to_store'] = self.item_to_store_lineEdit.text()
        self.storeDataInfo['store_location'] = self.store_location_lineEdit.text()
        
class nodz_openTimerDialog(QDialog):
    """
    A Dialog that is created for timer in the Nodz layout. 
    """
    def __init__(self, parentNode=None):
        """
        Initializes the TimerDialog.
        
        Args:
            parentNode: The parent node of the TimerDialog. If provided, the timerInfo will be set to the timerInfo of the parentNode.
        
        Returns:
            None
        """
        super().__init__(None)
        self.setWindowTitle("Timer Dialog")
        self.timerInfo = 0
        if parentNode is not None:
            from PyQt5.QtWidgets import QApplication, QVBoxLayout, QMainWindow, QWidget
            self.timerInfo = parentNode.timerInfo

        button_box = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        button_box.accepted.connect(self.accept)
        button_box.rejected.connect(self.reject)
        
        # Create the QVBoxLayout
        layout = QVBoxLayout()

        # Create a QWidget to contain the QGridLayout
        entryVal = QDoubleSpinBox()
        entryVal.setDecimals(2)
        entryVal.setSingleStep(0.1)
        entryVal.setValue(self.timerInfo)
        entryVal.valueChanged.connect(lambda value: setattr(self, 'timerInfo', value))
        # Add the QMainWindow to the QVBoxLayout
        layout.addWidget(entryVal)

        layout.addWidget(button_box)
        
        self.setLayout(layout)



class nodz_openMMConfigDialog(QDialog):
    
    """
    Opens a dialog to modify the MM configs of a node
    """
    def __init__(self, parentNode=None, storedConfigsStrings=None):
        """
        Opens a dialog to modify the Micromanager configs of a node
        
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
            self.newConfigUI = MMConfigUI(parentNode.MMconfigInfo.config_groups, showConfigs=parentNode.MMconfigInfo.showConfigs,showShutterOptions=parentNode.MMconfigInfo.showShutterOptions, showLiveSnapExposureButtons=parentNode.MMconfigInfo.showLiveSnapExposureButtons, showROIoptions =parentNode.MMconfigInfo.showROIoptions, showStages=parentNode.MMconfigInfo.showStages, showCheckboxes=parentNode.MMconfigInfo.showCheckboxes,changes_update_MM=parentNode.MMconfigInfo.changes_update_MM,autoSaveLoad=False)
            
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
        for config_id in range(len(self.newConfigUI.config_groups)): #type:ignore
            if self.newConfigUI.configCheckboxes[config_id].isChecked(): #type:ignore
                #Add config name and new value
                ConfigsToBeChanged.append([self.newConfigUI.config_groups[config_id].configGroupName(),self.newConfigUI.currentConfigUISingleValue(config_id)]) #type:ignore
        
        #Not adding ,self.newConfigUI.config_groups[config_id] (all info) for pickling reasons
        
        return ConfigsToBeChanged
        
        return self.newConfigUI

    # def getExposureTime(self):
    #     return self.mdaconfig.exposure_ms

    # def getmdaData(self):
    #     return self.mdaconfig

class nodz_visualisationDialog(QDialog):
    """
    Opens a dialog to modify the visualisation settings
    """
    def __init__(self, parentNode=None):
        """
        Opens a dialog to modify the visualisation settings
        
        Args:
            parentNode (Node): The node to modify the configs of.
            
        Returns:
            A tuple with the configs as a dictionary and the list of configs as strings.
        """
        super().__init__(None)
        
        self.setWindowTitle("Visualisation Dialog")
        if parentNode is not None:
            from PyQt5.QtWidgets import QApplication, QVBoxLayout, QMainWindow, QWidget, QFormLayout
            layout_sub = QFormLayout()
            if 'layerName' not in parentNode.visualisation_currentData or parentNode.visualisation_currentData['layerName'] is not None:
                connectedNodes = nodz_utils.getConnectedNodes(parentNode, 'topAttr')
                if len(connectedNodes)>0:
                    connectedNode = connectedNodes[0]
                    defaultText = connectedNode.name
                else:
                    defaultText = 'newLayer'
            else:
                defaultText = parentNode.visualisation_currentData['layerName']
            self.layerNameEdit = QLineEdit()
            self.layerNameEdit.setText(defaultText)
            layout_sub.addRow("Layer name:", self.layerNameEdit)
            
            import napari
            
            self.colormapComboBox = QComboBox()
            colormaps = napari.utils.colormaps.AVAILABLE_COLORMAPS #type:ignore
            for colormap in colormaps:
                self.colormapComboBox.addItem(colormap)
            
            if 'colormap' not in parentNode.visualisation_currentData or parentNode.visualisation_currentData['colormap'] is None:
                self.colormapComboBox.setCurrentText('gray')
            else:
                self.colormapComboBox.setCurrentText(parentNode.visualisation_currentData['colormap'])
            
            self.colormapComboBox.addItem("Use new config")
            layout_sub.addRow("Colormap:", self.colormapComboBox)
            
            button_box = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
            button_box.accepted.connect(self.accept)
            button_box.rejected.connect(self.reject)
            
            # Create the QVBoxLayout
            layout = QVBoxLayout()

            # Add the QMainWindow to the QVBoxLayout
            layout.addLayout(layout_sub)

            layout.addWidget(button_box)
            
            self.setLayout(layout)

class nodz_openMDADialog(QDialog):
    """
    Dialog for the MDA options within the Nodz environment.
    """
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
        self.parent = parent #type:ignore
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
                    storage_folder=currentNode.mdaData.storage_folder,
                    storage_file_name=currentNode.mdaData.storage_file_name,
                    node = currentNode)
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
        """
        Get the inputs from the MDA configuration.
        
        Returns:
            The inputs from the MDA configuration.
        """
        
        return self.mdaconfig.mda

    def getExposureTime(self):
        """
        Get the exposure time in milliseconds.
        
        Returns:
            int: The exposure time in milliseconds.
        """
        return self.mdaconfig.exposure_ms

    def getmdaData(self):
        """
        Get the MDA data.
        
        Returns:
            The MDA configuration data.
        """
        return self.mdaconfig

class nodz_openScoringEndDialog(QDialog):
    """
    The ScoringEnd (i.e. the end of the scoring) dialog window.
    """
    def __init__(self, parent=None, currentNode=None):
        """
        Initialize the ScoringEnd (i.e. the end of the scoring) dialog window.
        
        Args:
            parent: The parent widget (default is None).
            currentNode: The current node (default is None).
        
        Returns:
            None
        """
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

        #Pre-load labels/line-Edits with the current sockets:
        self.labels = []
        self.lineEdits = []
        if currentNode is not None:
            currentSockets = list(currentNode.sockets.items())
            for socket in currentSockets:
                label = QLabel(f"Score {len(self.labels)+1}:")
                lineEdit = QLineEdit()
                lineEdit.setText(socket[0])
                self.variableContainer.addWidget(label,len(self.labels),0)
                self.variableContainer.addWidget(lineEdit,len(self.labels),1)
                self.labels.append(label)
                self.lineEdits.append(lineEdit)
        
        self.nrVarsSpinbox.setValue(len(self.labels)) 
        #And update the layout at the start:
        # self.updateLayout()
        
    def updateLayout(self):
        """
        Updates the scoreEnd layout based on the number of variables (i.e. number of connectable score parameters) specified.
        
            Args:
                None
        
            Returns:
                None
        """
        nrVars = self.nrVarsSpinbox.value()
        if nrVars == len(self.labels)-1: #If we want to remove the last one
            tobeRemovedLabel = self.labels[-1]
            tobeRemovedLineEdit = self.lineEdits[-1]
            self.layout().removeWidget(tobeRemovedLabel)
            tobeRemovedLabel.deleteLater()
            self.layout().removeWidget(tobeRemovedLineEdit)
            tobeRemovedLineEdit.deleteLater()
            self.labels.pop()
            self.lineEdits.pop()
        elif nrVars == len(self.labels)+1: #if we want to add one...
            label = QLabel(f"Score {len(self.labels)+1}:")
            lineEdit = QLineEdit()
            self.variableContainer.addWidget(label,len(self.labels),0)
            self.variableContainer.addWidget(lineEdit,len(self.labels),1)
            self.labels.append(label)
            self.lineEdits.append(lineEdit)
        elif nrVars == len(self.labels): 
            pass
        else: #Else, we added a fully new number, so we reset everything
            for label in self.labels:
                self.layout().removeWidget(label)
                label.deleteLater()
            for lineEdit in self.lineEdits:
                self.layout().removeWidget(lineEdit)
                lineEdit.deleteLater()

            self.labels = []
            self.lineEdits = []

            for i in range(nrVars):
                label = QLabel(f"Score {i+1}:")
                lineEdit = QLineEdit()
                self.variableContainer.addWidget(label,i,0)
                self.labels.append(label)
                self.variableContainer.addWidget(lineEdit,i,1)
                self.lineEdits.append(lineEdit)

class FoVFindImaging_singleCh_configs(QDialog):
    """
    I BELIEVE DEPRECATED (may 2024)
    Advanced dialog for user to input the configuration for a single channel single FOV imaging experiment.
    """
    def __init__(self, parent=None, parentData=None):
        """
        I BELIEVE DEPRECATED (may 2024)
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
            self.MMconfig = MMConfigUI(allConfigGroups, showConfigs = True,showStages=False,showROIoptions=False,showLiveMode=False,number_config_columns=5,changes_update_MM = False, showCheckboxes=True,autoSaveLoad=False)
            
            button_box = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
            button_box.accepted.connect(self.accept)
            button_box.rejected.connect(self.reject)
                
            #Set the layout
            layout = QVBoxLayout()
            layout.addLayout(self.MMconfig.mainLayout)
            layout.addWidget(button_box)
            
            self.setLayout(layout)
        
    def getInputs(self):
        """
        Get the UI configuration information.
        
        Args:
            onlyChecked (bool): A boolean flag indicating whether to return only the checked UI configuration information.
        
        Returns:
            dict: A dictionary containing the UI configuration information.
        """
        return self.MMconfig.getUIConfigInfo(onlyChecked=True)
#endregion

#region NodzHelperClasses
class CustomGraphicsView(QtWidgets.QGraphicsView):
    """
    Create a custom Graphics View for the Nodz container
    """
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
    """ 
    Create a 'graph' in code-form of all connections in the scoring or acquisition flowchart. Basically gives information about what node is connected to what other nodes
    """
    #Also adds these values correctly for each node:
        # self.n_connect_at_start = 0 #number of others connected at start (which should all be finished!)
        # self.connectedToFinish = []
        # self.connectedToData = []
        
    def __init__(self,parent):
        """
        Initialize a GladosGraph object
        Create a 'graph' in code-form of all connections in the scoring or acquisition flowchart. Basically gives information about what node is connected to what other nodes

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
    """
    The NodeSignalManager class is used to manage the signals emitted and received by nodes in the graph (i.e. those created by connections).
    This is a generic class to handle the signals of any number of nodes.
    """
    
    #pyqtSignals need to be outside init def
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
            logging.debug(f"emitting signal {signal}")
#endregion

class GladosNodzFlowChart_dockWidget(nodz_main.Nodz):
    """
    Class that represents a Flowchart dock widget in napari-Glados. 
    Inherits from Nodz, which is a graph drawing tool.
    
    Main class of all Nodz-based Glados automisation.
    """
    def __init__(self,core=None,shared_data=None,MM_JSON=None,parent=None):
        """
        Initializes the GladosNodzFlowChart_dockWidget in napari-Glados. 
        Inherits from Nodz, which is a graph drawing tool.
        
        Main class of all Nodz-based Glados automisation.
        
        Args:
            core: Core object for MM/napari integration.
            shared_data: Shared data object.
            MM_JSON: JSON object for MM/napari integration.
        
        Returns:
            None
        """
        
        #If run as plugin, we need to specify the globals like this:
        if parent is not None:
            global livestate, napariViewer
            livestate = parent.livestate
            napariViewer = parent.napariViewer
            parent.shared_data = shared_data
            shared_data.napariViewer = napariViewer
        
        self.parent = parent
        
        #Create a QGridLayout:
        self.mainLayout = QGridLayout()
        
        self.fullRunOngoing = False
        
        #Add a few buttons:
        self.buttonsArea = QVBoxLayout()
        self.loadPickleButton = QPushButton('Load Graph')
        self.buttonsArea.addWidget(self.loadPickleButton)
        self.loadPickleButton.clicked.connect(lambda index: self.loadGraphJSON())
        self.runScoringButton = QPushButton('Start run!')
        self.buttonsArea.addWidget(self.runScoringButton)
        self.runScoringButton.clicked.connect(lambda index: self.fullAutonomousRunStart())
        self.runScoringButton = QPushButton('Run Scoring Only')
        self.buttonsArea.addWidget(self.runScoringButton)
        self.runScoringButton.clicked.connect(lambda index: self.runScoringOnly())
        self.runScoringButton = QPushButton('Run Scoring + Acq')
        self.buttonsArea.addWidget(self.runScoringButton)
        self.runScoringButton.clicked.connect(lambda index: self.runScoring())
        self.storePickleButton = QPushButton('Store Graph')
        self.buttonsArea.addWidget(self.storePickleButton)
        self.storePickleButton.clicked.connect(lambda index: self.storeGraphJSON())
        self.runAcquiringButton = QPushButton('Run Acquiring')
        self.buttonsArea.addWidget(self.runAcquiringButton)
        self.runAcquiringButton.clicked.connect(lambda index: self.runAcquiring())
        self.debugScoringButton = QPushButton('Debug Scoring')
        self.buttonsArea.addWidget(self.debugScoringButton)
        self.debugScoringButton.clicked.connect(lambda index: self.debugScoring())
        
        #import qgroupbox:
        from qtpy.QtWidgets import QGroupBox    
    
        self.decision_groupbox = QGroupBox("Decision Widget")
        # self.buttonsArea.addWidget(self.decision_groupbox)
        self.decisionWidget = DecisionWidget(nodzinstance=self)
        self.decision_groupbox.setLayout(self.decisionWidget.layout())
        
        self.scanwidget_groupbox = QGroupBox("Scan Widget")
        newgridlayout = QGridLayout()
        self.scanwidget_groupbox.setLayout(newgridlayout)
        self.scanningWidget = ScanningWidget(nodzinstance=self)
        newgridlayout.addWidget(self.scanningWidget)
        
        self.variablesWidget = VariablesWidget(nodzinstance=self)
        newgridlayout.addWidget(self.variablesWidget)
        
        # Create a QGraphicsView 
        self.graphics_view = CustomGraphicsView()
        super(GladosNodzFlowChart_dockWidget, self).__init__(parent=self.graphics_view)
        self.defineNodeInfo()
        
        # Add the QGraphicsView to the mainLayout and allt he other layouts
        self.mainLayout.addWidget(self.graphics_view,0,0)
        self.mainLayout.addLayout(self.buttonsArea,0,1)
        self.mainLayout.addWidget(self.decision_groupbox,0,2)
        self.mainLayout.addWidget(self.scanwidget_groupbox,0,3)
        self.mainLayout.addWidget(self.variablesWidget,0,4)
        
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
        self.preventAcq=False #Set to true if you want to prevent smart acquisition (i.e. scoring-only, never passing to acq)
        
        #Connect required deleted/double clicked signals
        self.signal_NodeDeleted.connect(self.NodeRemoved)
        self.signal_NodeCreatedNodeItself.connect(self.NodeAdded)
        self.signal_NodeFullyInitialisedNodeItself.connect(self.NodeFullyInitialised)
        self.signal_NodeDoubleClicked.connect(self.NodeDoubleClicked)
        self.signal_PlugConnected.connect(self.PlugConnected)
        self.signal_PlugDisconnected.connect(self.PlugOrSocketDisconnected)
        self.signal_SocketConnected.connect(self.SocketConnected)
        
        #Focus on the nodes
        self._focus()
    
    #region NodzFlowChart Node Methods
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
        self.nodeInfo['acquisition'] = self.singleNodeTypeInit()
        self.nodeInfo['acquisition']['name'] = 'acquisition'
        self.nodeInfo['acquisition']['displayName'] = 'Acquisition'
        self.nodeInfo['acquisition']['startAttributes'] = ['Acquisition start']
        self.nodeInfo['acquisition']['finishedAttributes'] = ['Finished']
        self.nodeInfo['acquisition']['bottomAttributes'] = ['Visual','Real-time']
        
        self.nodeInfo['changeProperties'] = self.singleNodeTypeInit()
        self.nodeInfo['changeProperties']['name'] = 'changeProperties'
        self.nodeInfo['changeProperties']['displayName'] = 'Change Properties'
        self.nodeInfo['changeProperties']['startAttributes'] = ['Start']
        self.nodeInfo['changeProperties']['finishedAttributes'] = ['Done']
        
        self.nodeInfo['visualisation'] = self.singleNodeTypeInit()
        self.nodeInfo['visualisation']['name'] = 'visualisation'
        self.nodeInfo['visualisation']['displayName'] = 'Visualisation'
        self.nodeInfo['visualisation']['topAttributes'] = ['Start']
        self.nodeInfo['visualisation']['NodeSize'] = 60
        
        self.nodeInfo['realTimeAnalysis'] = self.singleNodeTypeInit()
        self.nodeInfo['realTimeAnalysis']['name'] = 'realTimeAnalysis'
        self.nodeInfo['realTimeAnalysis']['displayName'] = 'Real-Time analysis'
        self.nodeInfo['realTimeAnalysis']['topAttributes'] = ['Start']
        self.nodeInfo['realTimeAnalysis']['NodeSize'] = 60
        
        self.nodeInfo['reporting'] = self.singleNodeTypeInit()
        self.nodeInfo['reporting']['name'] = 'reporting'
        self.nodeInfo['reporting']['displayName'] = 'Report'
        self.nodeInfo['reporting']['topAttributes'] = ['Start']
        self.nodeInfo['reporting']['NodeSize'] = 40
        
        self.nodeInfo['changeStagePos'] = self.singleNodeTypeInit()
        self.nodeInfo['changeStagePos']['name'] = 'changeStagePos'
        self.nodeInfo['changeStagePos']['displayName'] = 'Change Stage Position'
        self.nodeInfo['changeStagePos']['startAttributes'] = ['Start']
        self.nodeInfo['changeStagePos']['finishedAttributes'] = ['Done']
        
        self.nodeInfo['analysisMeasurement'] = self.singleNodeTypeInit()
        self.nodeInfo['analysisMeasurement']['name'] = 'analysisMeasurement'
        self.nodeInfo['analysisMeasurement']['displayName'] = 'Analysis [Measurement]'
        self.nodeInfo['analysisMeasurement']['startAttributes'] = ['Analysis start']
        self.nodeInfo['analysisMeasurement']['finishedAttributes'] = ['Finished']
        self.nodeInfo['analysisMeasurement']['dataAttributes'] = ['Output']
        self.nodeInfo['analysisMeasurement']['bottomAttributes'] = ['Visual']
        
        self.nodeInfo['analysisShapes'] = self.singleNodeTypeInit()
        self.nodeInfo['analysisShapes']['name'] = 'analysisShapes'
        self.nodeInfo['analysisShapes']['displayName'] = 'Analysis [Shapes]'
        self.nodeInfo['analysisShapes']['startAttributes'] = ['Analysis start']
        self.nodeInfo['analysisShapes']['finishedAttributes'] = ['Finished']
        self.nodeInfo['analysisShapes']['dataAttributes'] = ['Output']
        
        self.nodeInfo['analysisImages'] = self.singleNodeTypeInit()
        self.nodeInfo['analysisImages']['name'] = 'analysisImages'
        self.nodeInfo['analysisImages']['displayName'] = 'Analysis [Images]'
        self.nodeInfo['analysisImages']['startAttributes'] = ['Analysis start']
        self.nodeInfo['analysisImages']['finishedAttributes'] = ['Finished']
        self.nodeInfo['analysisImages']['dataAttributes'] = ['Output']
        
        self.nodeInfo['scoringStart'] = self.singleNodeTypeInit()
        self.nodeInfo['scoringStart']['name'] = 'scoringStart'
        self.nodeInfo['scoringStart']['displayName'] = 'Scoring start'
        self.nodeInfo['scoringStart']['finishedAttributes'] = ['Start']
        self.nodeInfo['scoringStart']['MaxNodeCounter'] = 1
        self.nodeInfo['scoringStart']['NodeSize'] = 60
        
        self.nodeInfo['scoringEnd'] = self.singleNodeTypeInit()
        self.nodeInfo['scoringEnd']['name'] = 'scoringEnd'
        self.nodeInfo['scoringEnd']['displayName'] = 'Scoring end'
        self.nodeInfo['scoringEnd']['startAttributes'] = ['End']
        self.nodeInfo['scoringEnd']['bottomAttributes'] = ['Report']
        self.nodeInfo['scoringEnd']['MaxNodeCounter'] = 1
        self.nodeInfo['scoringEnd']['NodeSize'] = 60
        
        self.nodeInfo['acqStart'] = self.singleNodeTypeInit()
        self.nodeInfo['acqStart']['name'] = 'acqStart'
        self.nodeInfo['acqStart']['displayName'] = 'Acquiring start'
        self.nodeInfo['acqStart']['finishedAttributes'] = ['Start']
        self.nodeInfo['acqStart']['MaxNodeCounter'] = 1
        self.nodeInfo['acqStart']['NodeSize'] = 60
        
        self.nodeInfo['acqEnd'] = self.singleNodeTypeInit()
        self.nodeInfo['acqEnd']['name'] = 'acqEnd'
        self.nodeInfo['acqEnd']['displayName'] = 'Acquiring end'
        self.nodeInfo['acqEnd']['startAttributes'] = ['End']
        self.nodeInfo['acqEnd']['MaxNodeCounter'] = 1
        self.nodeInfo['acqEnd']['NodeSize'] = 60
        
        self.nodeInfo['timer'] = self.singleNodeTypeInit()
        self.nodeInfo['timer']['name'] = 'timer'
        self.nodeInfo['timer']['displayName'] = 'Timer'
        self.nodeInfo['timer']['startAttributes'] = ['Start']
        self.nodeInfo['timer']['finishedAttributes'] = ['Finished']
        
        self.nodeInfo['storeData'] = self.singleNodeTypeInit()
        self.nodeInfo['storeData']['name'] = 'storeData'
        self.nodeInfo['storeData']['displayName'] = 'Store Data'
        self.nodeInfo['storeData']['startAttributes'] = ['Store']
        
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
        newNode.flowChart = self
        if nodeType in self.config:
            configtype = nodeType
        else:
            configtype = 'node_preset_1'
            
        
        #Change name, change sdisplayName, change preset:
        newNode.changeName(newNodeName)
        newNode.changeDisplayName(self.nodeInfo[nodeType]['displayName'])
        newNode.changePreset(configtype)
        
        self.nodes.append(newNode)
        
        self.updateNumberStartFinishedDataAttributes(newNode,nodeType)
        
        #Custom functions that should be done
        if nodeType == 'acquisition':
            #Attach a MDA data to this node
            parentV = None
            if self.parent is not None:
                parentV = self.parent
                
            
            #Set the variableNodz info, maybe later do this in seperate function?
            newNode.variablesNodz['data'] = {}
            from ndtiff import NDTiffDataset
            newNode.variablesNodz['data']['type'] = [NDTiffDataset, np.ndarray]
            newNode.variablesNodz['data']['data'] = None
            newNode.variablesNodz['data']['importance'] = 'Default'
            newNode.variablesNodz['order'] = {}
            newNode.variablesNodz['order']['type'] = [str]
            newNode.variablesNodz['order']['data'] = None
            newNode.variablesNodz['order']['importance'] = 'Informative'
            newNode.variablesNodz['exposure_ms'] = {}
            newNode.variablesNodz['exposure_ms']['type'] = [float]
            newNode.variablesNodz['exposure_ms']['data'] = None
            newNode.variablesNodz['exposure_ms']['importance'] = 'Informative'
            newNode.variablesNodz['n_timepoints'] = {}
            newNode.variablesNodz['n_timepoints']['type'] = [int]
            newNode.variablesNodz['n_timepoints']['data'] = None
            newNode.variablesNodz['n_timepoints']['importance'] = 'Informative'
            newNode.variablesNodz['time_interval_ms'] = {}
            newNode.variablesNodz['time_interval_ms']['type'] = [float]
            newNode.variablesNodz['time_interval_ms']['data'] = None
            newNode.variablesNodz['time_interval_ms']['importance'] = 'Informative'
            newNode.variablesNodz['xy_positions'] = {}
            newNode.variablesNodz['xy_positions']['type'] = [np.ndarray]
            newNode.variablesNodz['xy_positions']['data'] = None
            newNode.variablesNodz['xy_positions']['importance'] = 'Informative'
            newNode.variablesNodz['n_xy_positions'] = {}
            newNode.variablesNodz['n_xy_positions']['type'] = [int]
            newNode.variablesNodz['n_xy_positions']['data'] = None
            newNode.variablesNodz['n_xy_positions']['importance'] = 'Informative'
            newNode.variablesNodz['z_positions'] = {}
            newNode.variablesNodz['z_positions']['type'] = [np.ndarray]
            newNode.variablesNodz['z_positions']['data'] = None
            newNode.variablesNodz['z_positions']['importance'] = 'Informative'
            newNode.variablesNodz['n_z_positions'] = {}
            newNode.variablesNodz['n_z_positions']['type'] = [int]
            newNode.variablesNodz['n_z_positions']['data'] = None
            newNode.variablesNodz['n_z_positions']['importance'] = 'Informative'
            newNode.variablesNodz['channel_group'] = {}
            newNode.variablesNodz['channel_group']['type'] = [str]
            newNode.variablesNodz['channel_group']['data'] = None
            newNode.variablesNodz['channel_group']['importance'] = 'Informative'
            newNode.variablesNodz['channels'] = {}
            newNode.variablesNodz['channels']['type'] = [np.ndarray]
            newNode.variablesNodz['channels']['data'] = None
            newNode.variablesNodz['channels']['importance'] = 'Informative'
            newNode.variablesNodz['n_channels'] = {}
            newNode.variablesNodz['n_channels']['type'] = [int]
            newNode.variablesNodz['n_channels']['data'] = None
            newNode.variablesNodz['n_channels']['importance'] = 'Informative'
            newNode.variablesNodz['storage_path'] = {}
            newNode.variablesNodz['storage_path']['type'] = [str]
            newNode.variablesNodz['storage_path']['data'] = None
            newNode.variablesNodz['storage_path']['importance'] = 'Informative'
            
            #Attach a MDA data to this node
            newNode.mdaData = MDAGlados(self.core,self.MM_JSON,None,self.shared_data,hasGUI=True,parent=parentV,node=newNode) # type: ignore
            
            #Do the acquisition upon callAction
            newNode.callAction = lambda self, node=newNode: node.mdaData.MDA_acq_from_Node(node)
            
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
        
        
            newNode.MMconfigInfo = MMConfigUI(allConfigGroups,showConfigs = True,showStages=False,showROIoptions=False,showShutterOptions=False,showLiveSnapExposureButtons=False,number_config_columns=5,changes_update_MM = False,showCheckboxes = True,autoSaveLoad=False) # type: ignore
            
            #Add the callaction
            newNode.callAction = lambda self, node=newNode: self.MMconfigChangeRan(node)
            newNode.callActionRelatedObject = self #this line is required to run a function from within this class
        elif nodeType == 'changeStagePos':
            # Get all config groups
            allConfigGroups={}
            nrconfiggroups = self.core.get_available_config_groups().size() #type:ignore
            for config_group_id in range(nrconfiggroups):
                allConfigGroups[config_group_id] = ConfigInfo(self.core,config_group_id)
        
            newNode.MMconfigInfo = MMConfigUI(allConfigGroups,showConfigs = False,showStages=True,showROIoptions=False,showLiveMode=False,number_config_columns=5,changes_update_MM = False,showCheckboxes = True,showRelativeStages = True, autoSaveLoad=False) # type: ignore
            
            #Add the callaction
            newNode.callAction = lambda self, node=newNode: self.MMstageChangeRan(node)
            newNode.callActionRelatedObject = self #this line is required to run a function from within 
        elif nodeType == 'analysisGrayScaleTest':
            newNode.callAction = lambda self, node=newNode: self.GrayScaleTest(node)
            newNode.callActionRelatedObject = self #this line is required to run a function from within this class
        elif nodeType == 'analysisMeasurement':
            newNode.callAction = lambda self, node=newNode: self.AnalysisNode_started(node)
            newNode.callActionRelatedObject = self #this line is required to run a function from within this class
            
            #initialise the scoring_analysis_currentData values:
            #Rather stupidly, but I create the double-click-dialog, but just never show it.
            dialog = nodz_analysisDialog(currentNode = newNode, parent = self)
            newNode.scoring_analysis_currentData=dialog.currentData
            
        elif nodeType == 'timer':
            newNode.callAction = lambda self, node=newNode: self.timerCallAction(node)
            newNode.callActionRelatedObject = self #this line is required to run a function from within this class
        elif nodeType == 'storeData':
            newNode.callAction = lambda self, node=newNode: self.storeDataCallAction(node)
            newNode.callActionRelatedObject = self #this line is required to run a function from within this class
        elif nodeType == 'scoringStart':
            newNode.callAction = lambda self, node=newNode: self.scoringStart(node)
            newNode.callActionRelatedObject = self #this line is required to run a function from within this class
        elif nodeType == 'scoringEnd':
            newNode.callAction = lambda self, node=newNode: self.scoringEnd(node)
            newNode.callActionRelatedObject = self #this line is required to run a function from within this class
            #Update the decisionwidget after loading the scoringEnd node:
            self.decisionWidget.updateAllDecisions()
        elif nodeType == 'acqEnd':
            newNode.callAction = lambda self, node=newNode: self.acquiringEnd(node)
            newNode.callActionRelatedObject = self #this line is required to run a function from within this class
        else:
            newNode.callAction = None

        newNode.update()

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
                self.set_readable_text_after_dialogChange(currentNode,dialog,'acquisition')
                logging.debug(f"MDA dialog input: {dialog.getInputs()}")
            
            # currentNode.mdaData.exposure_ms = dialog.getExposureTime()
            # currentNode.mdaData.mda = dialog.getInputs()#type:ignore
            dialogmdaData = dialog.getmdaData()
            attrs_to_not_copy = ['gui','core','shared_data','has_GUI','data','staticMetaObject','MDA_completed','MM_JSON']
            #Loop over all attributes in dialogmdaData:
            for attrs in vars(dialogmdaData):
                if attrs not in attrs_to_not_copy:
                    setattr(currentNode.mdaData,attrs,getattr(dialogmdaData,attrs)) #type:ignore
            
            currentNode.update() #type:ignore
        elif 'changeProperties' in nodeName:
            currentNode = self.findNodeByName(nodeName)
            #Show dialog:
            if 'MMconfigInfo' in vars(currentNode):
                storedConfigsStrings = currentNode.MMconfigInfo.config_string_storage #type: ignore
            else:
                currentNode.MMconfigInfo = [] #type: ignore
                storedConfigsStrings = None
            dialog = nodz_openMMConfigDialog(parentNode=currentNode,storedConfigsStrings = storedConfigsStrings) #type:ignore
            if dialog.exec_() == QDialog.Accepted:
                self.set_readable_text_after_dialogChange(currentNode,dialog,'changeProperties')
                #Update the results of this dialog into the nodz node   
                self.changeConfigStorageInNodz(currentNode,dialog.ConfigsToBeChanged())
        elif 'visualisation_' in nodeName:
            currentNode = self.findNodeByName(nodeName)
            #Show dialog:
            dialog = nodz_visualisationDialog(parentNode=currentNode) #type:ignore
            if dialog.exec_() == QDialog.Accepted:
                self.set_readable_text_after_dialogChange(currentNode,dialog,'visualisation')
                currentNode.visualisation_currentData['layerName'] = dialog.layerNameEdit.text() #type:ignore
                currentNode.visualisation_currentData['colormap'] = dialog.colormapComboBox.currentText() #type:ignore
        elif 'changeStagePos' in nodeName:
            currentNode = self.findNodeByName(nodeName)
            #Show dialog:
            dialog = nodz_openMMConfigDialog(parentNode=currentNode,storedConfigsStrings = currentNode.MMconfigInfo.config_string_storage) #type:ignore
            if dialog.exec_() == QDialog.Accepted:
                #Update the results of this dialog into the nodz node
                self.changeConfigStorageInNodz(currentNode,dialog.ConfigsToBeChanged())
        elif 'analysisMeasurement' in nodeName:
            currentNode = self.findNodeByName(nodeName)
            dialog = nodz_analysisDialog(currentNode = currentNode, parent = self)
            if dialog.exec_() == QDialog.Accepted:
                #Update the results of this dialog into the nodz node
                currentNode.scoring_analysis_currentData = dialog.currentData #type:ignore
                try:
                    self.set_readable_text_after_dialogChange(currentNode,dialog,'analysisMeasurement')
                except:
                    logging.warning('Failed to set text in analysisMeasurementDialog')
                logging.info('Pressed OK on analysisMeasurementDialog')
            
            
            utils.analysis_outputs_to_variableNodz(currentNode)
                    
        elif 'realTimeAnalysis' in nodeName:
            currentNode = self.findNodeByName(nodeName)
            #TODO: pre-load dialog.currentData with currentNode.currentData if that exists (better naming i guess) to hold all pre-selected data 
            dialog = nodz_realTimeAnalysisDialog(currentNode = currentNode, parent = self)
            if dialog.exec_() == QDialog.Accepted:
                #Update the results of this dialog into the nodz node
                currentNode.real_time_analysis_currentData = dialog.currentData #type:ignore
                currentNode.real_time_analysis_currentData['__selectedDropdownEntryRTAnalysis__'] = dialog.comboBox_RTanalysisFunctions.currentText() #type:ignore
                currentNode.real_time_analysis_currentData['__realTimeVisualisation__'] = dialog.visualisationBox.isChecked() #type:ignore 
                self.set_readable_text_after_dialogChange(currentNode,dialog,'RTanalysisMeasurement')
                logging.info('Pressed OK on RTanalysis')
                
        elif 'timer' in nodeName:
            dialog = nodz_openTimerDialog(parentNode=currentNode) #type:ignore
            if dialog.exec_() == QDialog.Accepted:
                currentNode.timerInfo = dialog.timerInfo #type:ignore
                self.set_readable_text_after_dialogChange(currentNode,dialog,'timer')
            # currentNode.callAction(self) #type:ignore
        elif 'storeData' in nodeName:
            dialog = nodz_openStoreDataDialog(parentNode=currentNode) #type:ignore
            if dialog.exec_() == QDialog.Accepted:
                currentNode.storeDataInfo = dialog.storeDataInfo #type:ignore
                self.set_readable_text_after_dialogChange(currentNode,dialog,'storeData')
        elif 'scoringStart' in nodeName:
            currentNode.callAction(self) #type:ignore
        elif 'scoringEnd' in nodeName:
            dialog = nodz_openScoringEndDialog(parent=self,currentNode=currentNode)
            if dialog.exec_() == QDialog.Accepted:
                dialogLineEdits = []
                for lineEdit in dialog.lineEdits:
                    dialogLineEdits.append(lineEdit.text())
                self.update_scoring_end(currentNode,dialogLineEdits)
                #Update the node itself
                self.update()
                nodeType = self.nodeLookupName_withoutCounter(nodeName)
                self.updateNumberStartFinishedDataAttributes(currentNode,nodeType)
                self.update()
                
                #Update the decisionwidget:
                self.decisionWidget.updateAllDecisions()
                logging.info(dialogLineEdits)
                logging.info('Pressed OK on scoringEnd')
    
    def singleNodeTypeInit(self):
        """ 
        Initialise the info for a single node type. Hand-in-hand with defineNodeInfo.
        """
        init = {}
        init['name'] = 'name'
        init['displayName'] = 'DisplayName'
        init['startAttributes'] = []
        init['finishedAttributes'] = []
        init['dataAttributes'] = []
        init['bottomAttributes'] = []
        init['topAttributes'] = []
        init['NodeCounter'] = 0
        init['NodeCounterNeverReset'] = 0
        init['MaxNodeCounter'] = np.inf
        init['NodeSize'] = 100
        return init

    def NodeAdded(self,node):
        """
        Handle when one or more nodes are created in the flowchart.

        When one or more nodes are created in the flowchart, this function is called.
        It does some pre-processing of the node and then calls performPostNodeCreation_Start.
        """
        logging.info('one or more nodes are created!')
        nodeType = self.nodeLookupName_withoutCounter(node.name)
        self.performPostNodeCreation_Start(node,nodeType)

    def NodeFullyInitialised(self,node):
        """
        Handle when a node is fully initialised.
        
        Specifically, when all e.g. data['NODES_SCORING_SCORING'] from loading is added to the node, only after that, this will run.

        This function is called when a node is fully initialised. It does some
        post-initialisation processing for nodes based on their type.

        Parameters
        ----------
        node : Node
            The node that has been fully initialised.
        """
        nodeType = self.nodeLookupName_withoutCounter(node.name)
        if nodeType == 'scoringEnd':
            self.update_scoring_end(node,node.scoring_end_currentData['Variables'])

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
    
    def finishedEmits(self,node):
        """
        This function emits the customFinishedEmits signal of a node, and allt he customDataEmits

        Args:
            node (nodz.Node): The node that needs to finish.

        Returns:
            None
        """
        node.status='finished'
        self.update()
        if node.customFinishedEmits is not None and len(node.customFinishedEmits.signals)>0:
            node.customFinishedEmits.emit_all_signals()
        if node.customDataEmits is not None and len(node.customDataEmits.signals)>0:
            node.customDataEmits.emit_all_signals()

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
        if 'scoringEnd' in node.name:
            print('hi')
        # print(f"outgoing connections - finished: {node.connectedToFinish}")
        # print(f"outgoing connections - data: {node.connectedToData}")
    #endregion
    
    #region NodzFlowChart Helpers
    def obtainAllNodes(self):
        """ 
        Obtain all nodes, return them
        """
        return self.nodes
    
    def updateNumberStartFinishedDataAttributes(self,newNode,nodeType):
        """
        Updates custom attributes for a new node based on the specified node type.
        
        Args:
            newNode: The new node to update custom attributes for.
            nodeType: The type of the node to determine which custom attributes to update.
        
        Returns:
            None
        """
        
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
        if len(self.nodeInfo[nodeType]['bottomAttributes']) > 0:
            newNode.customBottomEmits = NodeSignalManager()
        else:
            newNode.customBottomEmits = None
        if len(self.nodeInfo[nodeType]['topAttributes']) > 0:
            newNode.customTopEmits = NodeSignalManager()
        else:
            newNode.customTopEmits = None
            
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
        for attr in self.nodeInfo[nodeType]['bottomAttributes']:
            self.createAttribute(node=newNode, name=attr, index=-1, preset='attr_preset_1', plug=False, socket=False, bottomAttr=True)
            newNode.customBottomEmits.add_signal(attr) #type: ignore
        for attr in self.nodeInfo[nodeType]['topAttributes']:
            self.createAttribute(node=newNode, name=attr, index=-1, preset='attr_preset_1', plug=False, socket=False, topAttr=True)
            newNode.customTopEmits.add_signal(attr) #type: ignore
        
        if len(self.nodeInfo[nodeType]['startAttributes']) > 0:
            newNode.customStartEmits.print_signals() #type: ignore
        if len(self.nodeInfo[nodeType]['finishedAttributes']) > 0:
            newNode.customFinishedEmits.print_signals() #type: ignore
        if len(self.nodeInfo[nodeType]['dataAttributes']) > 0:
            newNode.customDataEmits.print_signals()  #type: ignore
        
        logging.debug("updated custom attributes")
        
    def advNodeInfo(self,node,event):
        """
        Show advanced information about a node in a popup window.
        
        Args:
            node: The node object for which advanced information is to be displayed.
            event: The event triggering the display of advanced information.
        
        Returns:
            None
        """
        #Create a quick popup window with a line edit and an ok/cancel:
        dialog = QDialog()
        dialog.setWindowTitle('Node info')
        dialog.setModal(True)
        layout = QVBoxLayout(dialog)

        
        textEdit = QTextEdit()
        
        attrs_to_show = ['name','displayName','nodePreset','plugs','sockets','scoring_analysis_currentData','scoring_end_currentData','scoring_scoring_currentData','scoring_visualisation_currentData','visualisation_currentData','real_time_analysis_currentData']
        
        text_to_show = ''
        for attr in attrs_to_show:
            if hasattr(node,attr):
                text_to_show += f'{attr}: {str(getattr(node,attr))}\n'
        
        #Custom add these ones:
        if hasattr(node,'mdaData'):
            if hasattr(node.mdaData,'mda'):
                text_to_show += f'mda: {str(node.mdaData.mda)}\n'
        if hasattr(node,'MMconfigInfo'):
            if hasattr(node.MMconfigInfo,'config_string_storage'):
                text_to_show += f'config_string_storage: {str(node.MMconfigInfo.config_string_storage)}\n'
        
        textEdit.setText(text_to_show)
        layout.addWidget(textEdit)

        buttonBox = QDialogButtonBox(QDialogButtonBox.Ok, dialog)
        layout.addWidget(buttonBox)

        buttonBox.accepted.connect(dialog.accept)
        
        if dialog.exec_() == QDialog.Accepted:
            logging.debug('advanced node info closed')

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
        finalNodeName=None
        #Now get the correct lookup name by looking through all nodeInfo items
        for node_name, node_data in self.nodeInfo.items():
            # Check if the name matches the specific value
            if 'name' in node_data and node_data['name'] == nodeNameNC:
                finalNodeName = node_name
        
        return finalNodeName
    
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
    
    def changeNodeName(self, node, event):
        """
        Change the name of a node.
        
        Args:
            node: The node whose name will be changed.
            event: The event triggering the name change.
        
        Returns:
            None
        """
        #Create a quick popup window with a line edit and an ok/cancel:
        dialog = QDialog()
        dialog.setWindowTitle('Change node name')
        dialog.setModal(True)
        layout = QVBoxLayout(dialog)

        lineEdit = QLineEdit()
        lineEdit.setText(node.displayName)
        layout.addWidget(lineEdit)

        buttonBox = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel, Qt.Horizontal, dialog) #type:ignore
        buttonBox.accepted.connect(dialog.accept)
        buttonBox.rejected.connect(dialog.reject)
        layout.addWidget(buttonBox)

        if dialog.exec_() == QDialog.Accepted:
            node.displayName = lineEdit.text()
        
    def changeNodeColor(self, node, event):
        """
        Change the color of a node.
        
        Args:
            node: The node object whose color will be changed.
            event: The event that triggers the color change.
        
        Returns:
            None
        """
        color = QColorDialog.getColor()
        node.alternateFillColor = color.getRgb()
        #Force the change in the node:
        node.BGcolChanged()
        node.update()
        logging.debug(f"Node color changed to {node.alternateFillColor}")

    def set_readable_text_after_dialogChange(self,currentNode,dialog,nodeType):
        """Script which sets a readable text inside the textfield of the currentNode after a dialog is closed (i.e. a popup window is closed).

        Args:
            currentNode (Nodz Node): Current Nodz Node
            dialog (QDialog): Dialog output
            nodeType (str): Type of node
        """
        displayHTMLtext = ''
        if nodeType == 'analysisMeasurement':
            methodName = dialog.currentData['__selectedDropdownEntryAnalysis__']
            methodFunctionName = [i for i in dialog.currentData['__displayNameFunctionNameMap__'] if i[0] == methodName][0][1]
            reqKwValues = []
            optKwValues = []
            
            reqKwargs = utils.reqKwargsFromFunction(methodFunctionName)
            optKwargs = utils.optKwargsFromFunction(methodFunctionName)
            
            for key in dialog.currentData:
                for rkw in reqKwargs:
                    if rkw in key and '#'+methodFunctionName+'#' in key:
                        reqKwValues.append(dialog.currentData[key])
                for okw in optKwargs:
                    if okw in key and '#'+methodFunctionName+'#' in key:
                        optKwValues.append(dialog.currentData[key])
            
            displayHTMLtext = f"<b>{methodName}</b>"
            for i in range(len(reqKwValues)):
                displayHTMLtext += f"<br><b>{reqKwargs[i]}</b>: {reqKwValues[i]}"
            for i in range(len(optKwValues)):
                displayHTMLtext += f"<br><i>{optKwargs[i]}</i>: {optKwValues[i]}"
        
        elif nodeType == 'RTanalysisMeasurement':
            methodName = dialog.currentData['__selectedDropdownEntryRTAnalysis__']
            methodFunctionName = [i for i in dialog.currentData['__displayNameFunctionNameMap__'] if i[0] == methodName][0][1]
            reqKwValues = []
            optKwValues = []
            
            reqKwargs = utils.reqKwargsFromFunction(methodFunctionName)
            optKwargs = utils.optKwargsFromFunction(methodFunctionName)
            
            for key in dialog.currentData:
                for rkw in reqKwargs:
                    if rkw in key and '#'+methodFunctionName+'#' in key:
                        reqKwValues.append(dialog.currentData[key])
                for okw in optKwargs:
                    if okw in key and '#'+methodFunctionName+'#' in key:
                        optKwValues.append(dialog.currentData[key])
            
            displayHTMLtext = f"<b>{methodName}</b>"
            for i in range(len(reqKwValues)):
                displayHTMLtext += f"<br><b>{reqKwargs[i]}</b>: {reqKwValues[i]}"
            for i in range(len(optKwValues)):
                displayHTMLtext += f"<br><i>{optKwargs[i]}</i>: {optKwValues[i]}"
        elif nodeType == 'visualisation':
            displayHTMLtext = f"<b>Layer name: {dialog.layerNameEdit.text()}</b>"
            if dialog.colormapComboBox.currentText() != 'None':
                displayHTMLtext += f"<br>Colormap: {dialog.colormapComboBox.currentText()}"
        elif nodeType == 'acquisition':
            displayHTMLtext = f"<b>{len(dialog.getInputs())} frames with order {dialog.mdaconfig.order}</b>"
            if dialog.mdaconfig.GUI_exposure_enabled:
                displayHTMLtext += f"<br>{dialog.getExposureTime()} ms exposure time"
            if dialog.mdaconfig.GUI_show_time:
                displayHTMLtext += f"<br>{dialog.mdaconfig.num_time_points} time points"
            if dialog.mdaconfig.GUI_show_channel:
                displayHTMLtext += f"<br>{len(dialog.mdaconfig.channel_exposures_ms)} channels in group {dialog.mdaconfig.channel_group}"
            if dialog.mdaconfig.GUI_show_xy:
                displayHTMLtext += f"<br>{len(dialog.mdaconfig.xy_positions)} XY positions"
            if dialog.mdaconfig.GUI_show_z:
                if dialog.mdaconfig.z_nr_steps is not None:
                    displayHTMLtext += f"<br>{dialog.mdaconfig.z_nr_steps} Z positions"
                else:
                    nrZsteps = (dialog.mdaconfig.z_end-dialog.mdaconfig.z_start)//dialog.mdaconfig.z_step_distance
                    displayHTMLtext += f"<br>{nrZsteps} Z positions"
        elif nodeType == 'changeProperties':
            displayHTMLtext = f"Changing {len(dialog.ConfigsToBeChanged())} config(s):"
            for config in dialog.ConfigsToBeChanged():
                displayHTMLtext += f"<br>{config[0]} to {config[1]}"
        elif nodeType == 'scoreEnd':
            import time
            from datetime import datetime
            displayHTMLtext = f"<i> {datetime.fromtimestamp(time.time()).strftime('%Y-%m-%d %H:%M:%S')}</i>"
            for score_entry in dialog[0]:
                displayHTMLtext += f"<br><b>{score_entry}:</b> {format(dialog[1][score_entry],'.2f')}"
            if len(dialog) > 2:
                displayHTMLtext += f"<br><b>{dialog[2]}</b>"
        elif nodeType == 'scoreStart':
            import time
            from datetime import datetime
            displayHTMLtext = "<b>Scoring started at:</b>"
            displayHTMLtext += f"<br><i> {datetime.fromtimestamp(time.time()).strftime('%Y-%m-%d %H:%M:%S')}</i>"
        elif nodeType == 'timer':
            displayHTMLtext = f"<b>Timer:</b> wait {str(round(dialog.timerInfo, 2))} s"
        elif nodeType == 'storeData':
            displayHTMLtext = "TODO-StoreData"
        #And update the display
        currentNode.updateDisplayText(displayHTMLtext)
        return displayHTMLtext

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
        devices = self.shared_data.core.get_loaded_devices() #type:ignore
        devices = [devices.get(i) for i in range(devices.size())]
        devicesOfType = []
        #Loop over devices
        for device in devices:
            if self.shared_data.core.get_device_type(device).to_string() == devicetype: #type:ignore
                logging.debug("found " + device + " of type " + devicetype)
                devicesOfType.append(device)
        return devicesOfType

    def PlugOrSocketConnected(self,srcNodeName, plugAttribute, dstNodeName, socketAttribute):
        """
        Handle when a plug or socket is connected.

        When a plug or socket is connected, this function is called. It will check if the destination
        node should be marked as 'started' or 'finished' based on the attributes connected.
        """
        logging.info(f"plug/socket connected start: {srcNodeName}, {plugAttribute}, {dstNodeName}, {socketAttribute}")
    
    def PlugOrSocketDisconnected(self,srcNodeName, plugAttribute, dstNodeName, socketAttribute):
        """
        Handle when a plug or socket is disconnected.

        When a plug or socket is disconnected, this function is called. It will disconnect
        the finished event of the source node from the 'we finished one of the prerequisites' at the destination node.
        """
        logging.info('plugorsocketdisconnected')
    
    def PlugConnected(self,srcNodeName, plugAttribute, dstNodeName, socketAttribute):
        """
        Handle when a plug is connected.

        When a plug is connected, this function is called. It will check if the destination
        node should be marked as 'started' based on the attributes connected.
        """
        #Check if all are non-Nones:
        logging.info('plug connected')

    def SocketConnected(self,srcNodeName, plugAttribute, dstNodeName, socketAttribute):
        """
        Handle when a socket is connected.

        When a socket is connected, this function is called. It does not do anything
        special, it only exists to keep the Node class happy by having a method that
        corresponds to the 'SocketConnected' signal from the FlowChart.
        """
        #Only one specific use-case at the moment:
        #If a connection is made between any node N to an analysisMeasurement node, and if there is at least one acquisition node linked at or downstream of N, and if the input of the analysisMeasurement is not already defined, and if the input is actually an image, fill the input data of the analysisMeasurement node to be the data of this acquisition node.
         
        
        #Possibly later, for any other nodes, set the 'input' of the right node to the 'default' of the left node, if typing accomodates.
        
        #TODO
        #First, we need to create some function to look at the downstream-connected nodes of some node - this needs to be a rather proper function.
        
        if 'analysisMeasurement_' in dstNodeName:
            import nodz.nodz_utils
            srcNode = nodz_utils.findNodeByName(self,srcNodeName)
            dstNode = nodz_utils.findNodeByName(self,dstNodeName)
            
            downstreamConnections = nodz_utils.findConnectedToNode(self.evaluateGraph(),dstNodeName,[],upstream=False,downstream=True) 
            #Note: first entry is always closest to node.
            #So we check if there is at least one acquisition node downstream of the dstNode:
            shortestConnectedAcquisition = None
            for connection in downstreamConnections:
                if 'acquisition_' in connection:
                    shortestConnectedAcquisition = nodz_utils.findNodeByName(self,connection)
                    break
            
            if shortestConnectedAcquisition is not None:
                for function in dstNode.scoring_analysis_currentData['__displayNameFunctionNameMap__']: #type:ignore
                    inputOfFunction = utils.inputFromFunction(function[1])[0][0]
                    
                    lineEditName = 'LineEdit#'+function[1]+'#'+inputOfFunction['name'] #type:ignore
                    lineEditVarName = 'LineEditVariable#'+function[1]+'#'+inputOfFunction['name'] #type:ignore
                    lineEditAdvName = 'LineEditAdv#'+function[1]+'#'+inputOfFunction['name'] #type:ignore
                    if lineEditVarName in dstNode.scoring_analysis_currentData: #type:ignore
                        if dstNode.scoring_analysis_currentData[lineEditVarName] == '': #type:ignore
                            import ndtiff
                            if ndtiff.NDTiffDataset in inputOfFunction['type']: #type:ignore
                                if ndtiff.NDTiffDataset in shortestConnectedAcquisition.variablesNodz['data']['type']:
                                    dstNode.scoring_analysis_currentData[lineEditVarName] = 'data@'+shortestConnectedAcquisition.name #type:ignore
                                
        
        
        #Check if all are non-Nones:
        logging.info('socket connected')
    
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
    
    def GraphToSignals(self):
        """Idea: we evaluate the graph at this time point, connect all signals/emits:
        
        """
        logging.debug('graphicing to signals')
        #Loop over all nodes:
        for node in self.nodes:
            node.n_connect_at_start = 0
            node.n_connect_at_start_finished = 0
            #Disconnect all signals, but only if there are any
            if node.customFinishedEmits is not None and len(node.customFinishedEmits.signals)>0:
                signal = node.customFinishedEmits.signals[0] #type: ignore
                try:
                    #This disconnects all signals
                    signal.disconnect()
                except:
                    #Otherwise we FULLY reset the signal?
                    logging.warning('attempted to disconnect a disconnected signal')
                    # nodeType = self.nodeLookupName_withoutCounter(node.name)
                    # if len(self.nodeInfo[nodeType]['finishedAttributes']) > 0:
                    #     node.customFinishedEmits = NodeSignalManager()
                    #     for attr in self.nodeInfo[nodeType]['finishedAttributes']:
                    #         node.customFinishedEmits.add_signal(attr) #type: ignore
                    # else:
                    #     node.customFinishedEmits = None
            
            if node.customDataEmits is not None and len(node.customDataEmits.signals)>0:
                signal = node.customDataEmits.signals[0] #type: ignore
                try:
                    #This disconnects all signals
                    signal.disconnect()
                except:
                    logging.warning('attempted to disconnect a disconnected signal')
                    # nodeType = self.nodeLookupName_withoutCounter(node.name)
                    # if len(self.nodeInfo[nodeType]['dataAttributes']) > 0:
                    #     node.customDataEmits = NodeSignalManager()
                    #     for attr in self.nodeInfo[nodeType]['dataAttributes']:
                    #         node.customDataEmits.add_signal(attr) #type: ignore
                    # else:
                    #     node.customDataEmits = None
            
        #Create all required signal connections
        currentgraph = self.evaluateGraph()
        for connection in currentgraph:
            plugAttribute = connection[0][connection[0].rfind('.')+1:]
            socketAttribute = connection[1][connection[1].rfind('.')+1:]
            srcNodeName = connection[0][:connection[0].rfind('.')]
            dstNodeName = connection[1][:connection[1].rfind('.')]
            
            if self.nodeLookupName_withoutCounter(srcNodeName) is not None and self.nodeLookupName_withoutCounter(dstNodeName) is not None:
                typeOfFinishedAttributes_of_srcNode = self.nodeInfo[self.nodeLookupName_withoutCounter(srcNodeName)]['finishedAttributes']
                typeOfDataAttributes_of_srcNode = self.nodeInfo[self.nodeLookupName_withoutCounter(srcNodeName)]['dataAttributes']
                typeOfStartAttributes_of_dstNode = self.nodeInfo[self.nodeLookupName_withoutCounter(dstNodeName)]['startAttributes']
            
                #Connect the finished event of the source node to the 'we finished one of the prerequisites' at the destination node
                if plugAttribute in typeOfFinishedAttributes_of_srcNode and socketAttribute in typeOfStartAttributes_of_dstNode:
                    srcNode = self.findNodeByName(srcNodeName)
                    dstNode = self.findNodeByName(dstNodeName)
                    #The destination node needs one extra to be started...
                    dstNode.n_connect_at_start += 1 #type: ignore
                    
                    #And the finished event of the source node is connected to the 'we finished one of the prerequisites' at the destination node
                    srcNode.customFinishedEmits.signals[0].connect(dstNode.oneConnectionAtStartIsFinished) #type: ignore
                    
                    logging.info(f"connected Finish {srcNodeName} to {dstNodeName} via {plugAttribute} to {socketAttribute}")
                #Same for data
                elif plugAttribute in typeOfDataAttributes_of_srcNode and socketAttribute in typeOfStartAttributes_of_dstNode:
                    srcNode = self.findNodeByName(srcNodeName)
                    dstNode = self.findNodeByName(dstNodeName)
                    #The destination node needs one extra to be started...
                    dstNode.n_connect_at_start += 1 #type: ignore
                    
                    #And the finished event of the source node is connected to the 'we gave data' at the destination node
                    srcNode.customDataEmits.signals[0].connect(dstNode.oneConnectionAtStartProvidesData) #type: ignore
                    logging.info(f"connected Data {srcNodeName} to {dstNodeName} via {plugAttribute} to {socketAttribute}")
                else:
                    logging.warning(f"not connected {srcNodeName} to {dstNodeName} via {plugAttribute} to {socketAttribute}")
    
    def getNodz(self):
        """
        Return the current instance of the class.
        
        Returns:
            object: The current instance of the class.
        """
        return self
    #endregion
    
    #region NodzFlowChart Saving Loading
    def storeGraphJSON(self):
        """
        Save the current graph to a JSON file.

        This function saves the current graph to a JSON file, which can be loaded later using `loadPickle()`.
        """
        filename, _ = QFileDialog.getSaveFileName(self, 'Save file', '', 'JSON files (*.json)')
        if filename:
            if not filename.endswith('.json'):
                filename += '.json'
            with open(filename, 'wb') as f:
                self.saveGraph(filename)
    
    def loadGraphJSON(self):
        """
        Load the graph from a JSON file.

        This function loads the graph from a JSON file created using `storeGraphJSON()`.
        """        
        filename, _ = QFileDialog.getOpenFileName(self, 'Open file', '', 'JSON files (*.json)')
        if filename:
            try:
                #Fully clear graph and delete all nodes from memory:
                self.clearGraph()
                self.nodes = []
                #Set all counters to 0:
                for nodeType in self.nodeInfo:
                    self.nodeInfo[nodeType]['NodeCounter'] = 0
                    self.nodeInfo[nodeType]['NodeCounterNeverReset'] = 0
                #Load the graph
                with open(filename, 'rb') as f:
                    self.loadGraph_KM(filename)
            except:
                msg = QMessageBox()
                msg.setIcon(QMessageBox.Warning)
                msg.setText("Could not load file: " + filename)
                msg.setWindowTitle("Warning")
                msg.setStandardButtons(QMessageBox.Ok)
                msg.exec_()
    #endregion
    
    #region NodzFlowChart Node-specific
    def update_scoring_end(self,currentNode,dialogLineEdits):
        """
        Update the "scoring end" current node with new dialog line edits.
        
        Args:
            currentNode: The current node to update.
            dialogLineEdits: The new sockets of the current node.
        
        Returns:
            None
        """
        
        currentNode.scoring_end_currentData['Variables'] = dialogLineEdits #type: ignore
        
        #the dialogLineEdits should be the new sockets of the current node. However, if a plug with the name already exists, it shouldn't be changed.
        import time
        sleepTime = 0.02
        for _ in range(3): #Just repeat everything 3 times and hope it solves itself
            self.update()
            time.sleep(sleepTime)
            current_sockets = [item[0] for item in list(currentNode.sockets.items())]
            if dialogLineEdits != current_sockets:
                
                #We loop over the sockets:
                for socket_id in reversed(range(len(currentNode.sockets))):
                    socketFull = list(currentNode.sockets.items())[socket_id]
                    socket = socketFull[0]
                    #We check if the socket is in dialogLineEdits:
                    if socket not in dialogLineEdits:
                        #If it isn't, we just delete it:
                        self.deleteAttribute(currentNode,socket_id)
                        time.sleep(sleepTime)
                        self.update()
                        time.sleep(sleepTime)
                
                
                #Check which are different (index-wise) between dialogLineEdits and current_sockets:
                diff_indexes = []
                same_indexes = []
                for i in range(min(len(dialogLineEdits),len(current_sockets))):
                    if dialogLineEdits[i] != current_sockets[i]:
                        diff_indexes.append(i)
                    else:
                        same_indexes.append(i)
                #Also append indexes if dialogLineEdits is longer than current_sockets:
                if len(dialogLineEdits) > len(current_sockets):
                    for i in range(len(current_sockets),len(dialogLineEdits)):
                        diff_indexes.append(i)
                
                offset = 100
                #Then we create new sockets or move existing sockets, only for those that have a different pos
                for socket_new in ([dialogLineEdits[i] for i in diff_indexes]):
                    pos_in_dialogLineEdits = dialogLineEdits.index(socket_new)
                    if socket_new not in currentNode.sockets:
                        self.createAttribute(currentNode, name=socket_new, index=pos_in_dialogLineEdits+offset, preset='attr_default', plug=False, socket=True, dataType=None, socketMaxConnections=1)
                        time.sleep(sleepTime)
                        self.update()
                        time.sleep(sleepTime)
                    else: #Else we move it from some other location to where we want it
                        #Find this socket in currentNode.sockets.items():
                        socketFull = list(currentNode.sockets.items())
                        pos_in_node_info = [socket_id for socket_id in range(len(socketFull)) if socketFull[socket_id][0] == socket_new][0]
                        old_pos = socketFull[pos_in_node_info][1].index
                        #Physically move it
                        self.editAttribute(currentNode,old_pos,newName = None, newIndex=pos_in_dialogLineEdits+offset)
                        time.sleep(sleepTime)
                        self.update()
                        time.sleep(sleepTime)
        
        #We also need to add these attributes to the nodes startAttributes in self.nodeInfo:
        self.nodeInfo[self.nodeLookupName_withoutCounter(currentNode.name)]['startAttributes'] = dialogLineEdits
    
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
    
    def AnalysisNode_started(self,node):
        """
        Perform the Analysis set in a node
        
        Args:
            node: The node for which calls the analysis
        
        Returns:
            None
        """
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
        
        #Dictionary of nodes to pass around variables.
        nodeDict = utils.createNodeDictFromNodes(self.nodes)
        
        #Figure out which function is selected in the scoring_analysis node
        selectedFunction = utils.functionNameFromDisplayName(node.scoring_analysis_currentData['__selectedDropdownEntryAnalysis__'],node.scoring_analysis_currentData['__displayNameFunctionNameMap__'])
        #Figure out the belonging evaluation-text
        evalText = utils.getFunctionEvalTextFromCurrentData(selectedFunction,node.scoring_analysis_currentData,'self.shared_data.core','',nodzInfo=self,skipp2=True)
        # #First assess that it's a MDA node:
        # if 'acquisition' not in connectedNode.name and 'analysisMeasurement' not in connectedNode.name:
        #     print('Error! Acquisition or analysismeasurement not connected to analysismeasurement!')
        # else:
        #     if 'acquisition' in connectedNode.name:
        #         #And then find the mdaData object
        #         mdaDataobject = connectedNode.mdaData
                
        #     elif 'analysisMeasurement' in connectedNode.name:
        #         dataobject = connectedNode.scoring_analysis_currentData['__output__']
                
        #         #Figure out which function is selected in the scoring_analysis node
        #         selectedFunction = utils.functionNameFromDisplayName(node.scoring_analysis_currentData['__selectedDropdownEntryAnalysis__'],node.scoring_analysis_currentData['__displayNameFunctionNameMap__'])
        #         #Figure out the belonging evaluation-text
        #         evalText = utils.getFunctionEvalTextFromCurrentData(selectedFunction,node.scoring_analysis_currentData,'dataobject','self.shared_data.core',nodzInfo=self)
                
        #And evaluate the custom function with custom parameters
        output = eval(evalText) #type:ignore
        
        #Display final output to the user for now
        logging.info(f"FINAL OUTPUT FROM NODE {node.name}: {output}")
        
        #Set the status of the nodz-coupled vis and real-time to finished:
        #Look at the 'Visual' bottom attribute and visualise if needed
        visualAttr = node.bottomAttrs['Visual']
        if len(visualAttr.connections) > 0:
            visual_connected_node_name = visualAttr.connections[0].socketNode
            for nodeV in self.nodes:
                if nodeV.name == visual_connected_node_name:
                    visual_connected_node = nodeV
                    
                    selectedFunction = utils.functionNameFromDisplayName(node.scoring_analysis_currentData['__selectedDropdownEntryAnalysis__'],node.scoring_analysis_currentData['__displayNameFunctionNameMap__'])
                    visualEvalText = utils.getFunctionEvalTextFromCurrentData(selectedFunction,node.scoring_analysis_currentData,'(output,napariLayer)','self.shared_data.core',nodzInfo=self)
                    visualEvalText = visualEvalText.replace(selectedFunction,f'{selectedFunction}_visualise') #type:ignore
                    
                    chosenLayerType = 'points'
                    
                    layerTypeInfo = [
                        ['Analysis_Measurements','points'],
                        ['Analysis_Shapes','shapes'],
                        ['Analysis_Images','image'],
                    ]
                    
                    folderName = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))+os.sep+'AutonomousMicroscopy'+os.sep
                    
                    for layerType in layerTypeInfo:
                        for root, dirs, files in os.walk(folderName+layerType[0]):
                            for file in files:
                                if selectedFunction.split('.')[0] in file: #type:ignore
                                    if file.endswith(".py"):
                                        with open(os.path.join(root, file), 'r') as f:
                                            filecontent = f.read()
                                        if selectedFunction.split('.')[1]+'(' in filecontent: #type:ignore
                                            chosenLayerType = layerType[1]
                                            break #to avoid searching in other files for this function
                    
                    
                    layerName = visual_connected_node.visualisation_currentData['layerName']
                    
                    #If a layer with this name already exists, simply remove it:
                    for layer in self.shared_data.napariViewer.layers: #type:ignore
                        if layer.name == layerName:
                            self.shared_data.napariViewer.layers.remove(layer) #type:ignore
                            
                    cmap = visual_connected_node.visualisation_currentData['colormap']
                    if chosenLayerType == 'points':
                        viewer = self.shared_data.napariViewer #type:ignore
                        napariLayer = viewer.add_points(
                            data=None,
                            text=None,
                            name=layerName,
                            colormap = cmap
                        )
                    elif chosenLayerType == 'shapes':
                        viewer = self.shared_data.napariViewer #type:ignore
                        napariLayer = viewer.add_shapes(
                            data=None,
                            name=layerName,
                            colormap = cmap
                        )
                    elif chosenLayerType == 'image':
                        logging.info('creating new image layer')
                        viewer = self.shared_data.napariViewer #type:ignore
                        im = np.random.random((30, 30))
                        napariLayer = viewer.add_image(
                            data=im,
                            name=layerName,
                            colormap = cmap
                        )
                    
                    visualOutput = eval(visualEvalText)
                    
                    visual_connected_node.status = 'finished'
            
            
        node.scoring_analysis_currentData['__output__'] = output
        
        #Store the output as NodzVariables
        utils.analysis_outputs_store_as_variableNodz(node)
        
        
        #Finish up
        self.finishedEmits(node)
    
    def MMstageChangeRan(self,node):
        #TODO: Implement this :)
        """
        Change the stage of the microscope based on the node info
        
        Args:
            node: The MM node to change the stage for.
        
        Returns:
            None
        """
        logging.info('MMstageChange')
        self.finishedEmits(node)
        
    def MMconfigChangeRan(self,node):
        """
        Handle the configuration change event for a node.

        This function handles the configuration change event for a node, by
        changing the desired configs in the Core.

        Args:
            node (nodz.Node): The node that has triggered the event.
        """
        logging.info('MMconfigChangeRan')
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
            logging.info(f"found avg gray val: {avgGrayVal}")
            
        self.finishedEmits(node)

    def acquiringStart(self,node):
        """
        This function is the action function for the Acquiring Start node in the Flowchart.

        This function signals to the rest of the flowchart that it's time to start
        the Acquiring routine.

        Args:
            node (nodz.Node): The node that has triggered the event.

        Returns:
            None
        """
        if self.preventAcq == False:
            print('Starting the acquiring routine!')
            
            self.GraphToSignals()
            
            self.finishedEmits(node)
        else:
            logging.warning('Would have started acquiring, but was prevented!')
    
    def acquiringEnd(self,node):
        """
        This function is the action function for the Acquiring End node in the Flowchart.

        This function signals to the rest of the flowchart that the Acquiring routine is ended

        Args:
            node (nodz.Node): The node that has triggered the event.

        Returns:
            None
        """
        print("End Acquiring")
        if self.fullRunOngoing:
            #if there are more positions to look at...
            if self.fullRunCurrentPos+1 < self.fullRunPositions['nrPositions']:
                self.fullRunCurrentPos +=1
                #And start a new score/acq at a new pos:
                self.startNewScoreAcqAtPos()
            else:
                self.singleRunOngoing = False
                print('All done!')
        self.finishedEmits(node)
    
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
        
        #Set all connected nodes to idle
        connectedNodes = nodz_utils.findConnectedToNode(self.evaluateGraph(),node.name,[])
        for connectedNode in connectedNodes:
            for nodeC in self.nodes:
                if nodeC.name == connectedNode:
                    nodeC.status='idle'
        
        self.set_readable_text_after_dialogChange(node,'','scoreStart')
        
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
        #Find the nodes that are connected downstream of this:
        data = {}
        attrs = []
        for attr in node.attrs:
            connectedNode = None
            for connection in self.evaluateGraph():
                if connection[1][connection[1].rfind('.')+1:] == attr:
                    if connection[1][:connection[1].rfind('.')] == node.name:
                        connectedNodeName = connection[0][:connection[0].rfind('.')]
                        connectedNode = self.findNodeByName(connectedNodeName)
        
                    data[attr] = connectedNode.scoring_analysis_currentData['__output__'] #type:ignore
                    attrs.append(attr)
                    print(f"Data found for {attr}: {data[attr]}")
        
        try:
            testPassed = self.decisionWidget.testCurrentDecision()
            testPassedText = 'Test is Passed' if testPassed else 'Test is Not Passed'
            readableText = self.set_readable_text_after_dialogChange(node,[attrs,data,testPassedText],'scoreEnd')
            
            print('Scoring finished fully!')
            if testPassed:
                print("Test is... Passed!")
                
                #Find the acqStart node:
                acqStartNode = None
                flowChart = self
                if len(flowChart.nodes) > 0:
                    #Find the scoringEnd node in flowChart:
                    for nodeF in flowChart.nodes:
                        if 'acqStart_' in nodeF.name:
                            acqStartNode = nodeF
                
                #Run the scoring_start routine:
                if acqStartNode is not None:
                    logging.info('Starting acquisition routine!')
                    self.acquiringStart(acqStartNode)
                else:
                    logging.error('Could not find acqStart node in flowchart')
                
            elif not testPassed:
                print("Test is... Not Passed!")
                #Go to next XY position
                if self.fullRunOngoing:
                    if self.fullRunCurrentPos+1 < self.fullRunPositions['nrPositions']:
                        self.fullRunCurrentPos +=1
                        #And start a new score/acq at a new pos:
                        self.startNewScoreAcqAtPos()
                    else:
                        self.singleRunOngoing = False
                        print('All done!')
            print('----------------------')
            self.finishedEmits(node)

        except:
            testPassed = False
            node.status = 'error'
            testPassedText = 'Error when assessing test'
            readableText = self.set_readable_text_after_dialogChange(node,[attrs,data,testPassedText],'scoreEnd')
        
        
        #Find the reporting node(s)
        connectedNodes = nodz_utils.getConnectedNodes(node, 'bottomAttr')
        for node in connectedNodes:
            print(node.name)
            if 'reporting_' in node.name:
                node.status = 'running'
                if 'SLACK' in self.shared_data.globalData: #type:ignore
                    if self.shared_data.globalData['SLACK']['TOKEN'] is not None and not len(self.shared_data.globalData['SLACK']['TOKEN']) == 0: #type:ignore
                        slackReadableText = readableText
                        slackReadableText = slackReadableText.replace('<br>','\r\n')
                        slackReadableText = slackReadableText.replace('<i>','_')
                        slackReadableText = slackReadableText.replace('</i>','_')
                        slackReadableText = slackReadableText.replace('<b>','*')
                        slackReadableText = slackReadableText.replace('</b>','*')
                        slackReadableText = "New Score: \n" + slackReadableText
                        self.shared_data.globalData['SLACK']['CLIENT'].chat_postMessage(channel=self.shared_data.globalData['SLACK']['CHANNEL'],text=slackReadableText) #type:ignore
                        node.status = 'finished'
                    else:
                        node.status = 'error'
                else:
                    node.status = 'error'
        
        self.preventAcq = False
    
    def timerCallAction(self,node):
        """
        This function is the action function for the Timer Call node in the Flowchart.

        This function waits for a specified amount of time before triggering the next node in the flowchart.

        Args:
            node (nodz.Node): The node that has triggered the event.
        Returns:
            None
        """
        import time
        time.sleep(node.timerInfo)
        self.finishedEmits(node)
    
    def storeDataCallAction(self,node):
        
        """
        This function is the action function for the storeData Call node in the Flowchart.

        This function stores data.

        Args:
            node (nodz.Node): The node that has triggered the event.
        """
        
        #Get the store-data from a variable
        data_to_store = node.storeDataInfo['item_to_store']
        if '@' in data_to_store:
            nodeDict = utils.createNodeDictFromNodes(node.flowChart.nodes)
            storeInfo = nodeDict[data_to_store.split('@')[1]].variablesNodz[data_to_store.split('@')[0]]['data']
        else:
            storeInfo = data_to_store
            
        store_location = node.storeDataInfo['store_location']
        if '@' in store_location and '{' in store_location and '}' in store_location:
            nodeDict = utils.createNodeDictFromNodes(node.flowChart.nodes)
            #Find a regex like this:
            import re
            matches = re.finditer("{[a-zA-Z0-9._%+-]+@[a-zA-Z0-9._%+-]+}",store_location)
            #Find all the matches
            updating_string = store_location
            for match in matches:
                startpos = match.regs[0][0]
                endpos = match.regs[0][1]
                foundstring = store_location[startpos:endpos]
                #Remove the curly braces
                foundstring_data = foundstring[1:-1]
                #run getting the data of this match
                #Assuming string
                data = str(nodeDict[foundstring_data.split('@')[1]].variablesNodz[foundstring_data.split('@')[0]]['data'])
                
                #Replace this in the updating_string
                updating_string = updating_string.replace(foundstring,"'"+data+"'")
            
            #Replace backslashes since they're escapechars
            updating_string_backslash = updating_string.replace('\\','\\\\')
            storeLoc = eval(updating_string_backslash)
            
        else:
            storeLoc = store_location
        
        # storeInfo
        # storeLoc
        
        #Check if storeInfo is image-like:
        if isinstance(storeInfo, np.ndarray) and storeInfo.ndim > 1:
            #Check if we want to store a tiff
            if storeLoc[-4:] == '.tif' or storeLoc[-5:] == '.tiff':
                import tifffile
                tifffile.imsave(storeLoc,storeInfo)
                logging.info(f'Stored TIF image at {storeLoc}')
        
        self.finishedEmits(node)
    #endregion
    
    #region NodzFlowChart runs
    def fullAutonomousRunStart(self):
        """
        Starts a full autonomous run - i.e. scoring and acquisition
        
        Args:
            self: The object instance.
        
        Returns:
            None
        """
        print('Starting a full run')
        self.preventAcq = True
        
        #General idea: first check if there are no glaring errors (scoring, position)
        #then go to whatever start position based on the xy positions
        #then run scoring+acquisition there
        
        self.fullRunOngoing = True
        self.fullRunCurrentPos = 0
        self.fullRunPositions = self.scanningWidget.getPositionInfo()
        self.startNewScoreAcqAtPos()

    def startNewScoreAcqAtPos(self):
        """
        Starts a new score acquisition at the current microscope position.
        
        Args:
            None
        
        Returns:
            None
        """
        
        import time
        positions = self.fullRunPositions
        pos = self.fullRunCurrentPos
        
        #Set all stages correct
        for stage in positions[pos]['STAGES']:
            stagepos = positions[pos][stage]
            #Check if this stage is an XY stage device...
            #Since then we need to do something 2-dimensional
            if stage in self.getDevicesOfDeviceType('XYStageDevice'):
                logging.info(f'Moving stage {stage} to position {stagepos}')
                self.shared_data.core.set_xy_position(stage,stagepos[0],stagepos[1]) #type:ignore
                self.shared_data.core.wait_for_system() #type:ignore
            else:#else we can move a 1d stage:
                logging.info(f'Moving stage {stage} to position {stagepos}')
                self.shared_data.core.set_position(stage,stagepos[0]) #type:ignore
                self.shared_data.core.wait_for_system() #type:ignore
        
        self.runScoring()
    
    def runScoringOnly(self):
        """
        Run ONLY the scoring process at the current position. Actively prevents acquisition
        
        Args:
            None
        
        Returns:
            None
        """
        self.preventAcq = True
        
        #Find the scoring_start node:
        scoreStartNode = None
        flowChart = self
        if len(flowChart.nodes) > 0:
            #Find the scoringEnd node in flowChart:
            for node in flowChart.nodes:
                if 'scoringStart_' in node.name:
                    scoreStartNode = node
        
        #Run the scoring_start routine:
        if scoreStartNode is not None:
            self.scoringStart(scoreStartNode)
        else:
            logging.error('Could not find scoringStart node in flowchart')
    
    def runScoring(self):
        """
        Runs the scoring process starting from the scoring_start node, without inhibiting acquisition later - i.e. the scoring before a possible acquisition
        
        Args:
            None
        
        Returns:
            None
        """
        self.preventAcq = False
        #Find the scoring_start node:
        scoreStartNode = None
        flowChart = self
        if len(flowChart.nodes) > 0:
            #Find the scoringEnd node in flowChart:
            for node in flowChart.nodes:
                if 'scoringStart_' in node.name:
                    scoreStartNode = node
        
        
        
        #Run the scoring_start routine:
        if scoreStartNode is not None:
            self.scoringStart(scoreStartNode)
        else:
            logging.error('Could not find scoringStart node in flowchart')
    
    def runAcquiring(self):
        """
        Run the acquiring process at this microscopy XY position
        
        Args:
            None
        
        Returns:
            None
        """
        print("Run Acquiring")
        
        #Find the acqStart node:
        acqStartNode = None
        flowChart = self
        if len(flowChart.nodes) > 0:
            #Find the scoringEnd node in flowChart:
            for node in flowChart.nodes:
                if 'acqStart_' in node.name:
                    acqStartNode = node
        
        #Run the scoring_start routine:
        if acqStartNode is not None:
            self.acquiringStart(acqStartNode)
        else:
            logging.error('Could not find acqStart node in flowchart')
    
    def debugScoring(self):
        """
        Function to get some debug information from the scoring function(s)
        """
        print("Debug Scoring")
        scoreGraph = self.prepareGraph(methodName = "Score")
        
        
        print(self)
        print(self.evaluateGraph())
    #endregion
    
    #region NodzFlowChart GraphArea functions
    def contextMenuEvent(self, QMouseevent):
        """
        Function to create a context menu when right-clicking on the nodz canvas

        This function creates a context menu with all available node types that the user can select from, and adds the node to the nodz canvas at the position of the mouse click.

        Args:
            QMouseevent (PyQt5.QtGui.QMouseEvent): The mouse event that triggered this context menu
        """
        #Check if we are right-clicking on a node:
        item_at_mouse = self.scene().itemAt(self.mapToScene(QMouseevent.pos()), QtGui.QTransform())
        
        if item_at_mouse == None:
            context_menu = QMenu(self)
            
            #Dynamically add all node types
            for node_type, node_data in self.nodeInfo.items():
                new_subAction = QAction(node_data['displayName'], self)
                context_menu.addAction(new_subAction)
                # Define a closure to capture the current value of node_type
                def create_lambda(node_type):
                    """
                    Create a lambda function that calls the createNodeFromRightClick method with the specified node type.
                    
                    Args:
                        node_type: The type of node to be created.
                    
                    Returns:
                        A lambda function that takes an event and calls createNodeFromRightClick with the specified node type.
                    """
                    return lambda _, event=QMouseevent: self.createNodeFromRightClick(event, nodeType=node_type)
                # Connect each action to its own lambda function
                new_subAction.triggered.connect(create_lambda(node_type))
                
            # Show the context menu at the event's position
            context_menu.exec_(QMouseevent.globalPos())
        elif item_at_mouse in self.nodes:
            
            context_menu = QMenu(self)
            
            #Add a change-name option
            changeName_subAction = QAction('Change name', self)
            context_menu.addAction(changeName_subAction)
            def create_lambda_changeName(item_at_mouse):
                """
                Creates a lambda function to change the name of a node.
                
                Args:
                    item_at_mouse: The item at the mouse position.
                
                Returns:
                    A lambda function that calls the changeNodeName method with the item_at_mouse and event as arguments.
                """
                return lambda _, event=QMouseevent: self.changeNodeName(item_at_mouse, event)
            changeName_subAction.triggered.connect(create_lambda_changeName(item_at_mouse))
            
            #Add a change-color option
            changeColor_subAction = QAction('Change color', self)
            context_menu.addAction(changeColor_subAction)
            def create_lambda_changeColor(item_at_mouse):
                """
                Creates a lambda function that changes the color of a node.
                
                Args:
                    item_at_mouse: The item at the mouse position.
                
                Returns:
                    A lambda function that calls the 'changeNodeColor' method with the specified item and event.
                """
                return lambda _, event=QMouseevent: self.changeNodeColor(item_at_mouse, event)
            changeColor_subAction.triggered.connect(create_lambda_changeColor(item_at_mouse))
            
            #Add a advanced-info option
            advNodeInfo_subAction = QAction('Advanced Node info', self)
            context_menu.addAction(advNodeInfo_subAction)
            def create_lambda_advNodeInfo(item_at_mouse):
                """
                Create a lambda function to call the advNodeInfo method with the given item at mouse position.
                
                Args:
                    item_at_mouse: The item at the mouse position to be passed to the advNodeInfo method.
                
                Returns:
                    A lambda function that calls the advNodeInfo method with the item_at_mouse and event parameters.
                """
                return lambda _, event=QMouseevent: self.advNodeInfo(item_at_mouse, event)
            advNodeInfo_subAction.triggered.connect(create_lambda_advNodeInfo(item_at_mouse))
            
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
        newNode = self.createNode(name=nodeType+"_", preset = 'node_preset_1', position=self.mapToScene(event.pos()),displayName = self.nodeInfo[nodeType]['displayName'],nodeInfo=self.nodeInfo[nodeType])
        
        #Do post-node-creation functions - does this via the pyqtsignal!
        return newNode
    
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
    
    def focus(self):
        """
        Focuses on the entire canvas
        
        Args:
            None
        
        Returns:
            None
        """
        self._focus()
    #endregion

#region ScanningWidget
class ScanningWidget(QWidget):
    """ 
    The scanning widget which handles the xy(z) scanning in a full autonomous runs. Mainly contains multiple advScanGridLayouts() which each individually handle a single method of xy(z) scanning.
    """
    def __init__(self, nodzinstance=None,parent=None):
        """
        Initializes the scanning widget class.
        
        Args:
            nodzinstance: The nodz instance to be associated with.
            parent: The parent widget.
        
        Returns:
            None
        """
        super().__init__(parent)
        # super().__init__()
        self.nodzinstance=nodzinstance
        self.scanMode = 'LoadPos'
        self.scanArray_modes = [
                            ['LoadPos','Load a POS list']]
                
        self.scanLayouts = {}
        self.currentMode = None
        
        self.create_GUI()
    
    def create_GUI(self):
        """
        Create scanning widget GUI with mode dropdown and corresponding advScanGridLayout layouts.
        
        Args:
            None
        
        Returns:
            None
        """
        self.mode_dropdown = QComboBox()
        self.mode_dropdown.addItems([option[1] for option in self.scanArray_modes])
        self.mode_layout = QGridLayout()
        self.mode_layout.addWidget(QLabel('Mode: '),0,0)
        self.mode_layout.addWidget(self.mode_dropdown,0,1)

        from PyQt5.QtWidgets import QHBoxLayout
        for mode_option in self.scanArray_modes:
            self.scanLayouts[mode_option[0]] = advScanGridLayout(mode=mode_option[0],parent=self)
            
            self.scanLayouts[mode_option[0]].setVisible(True) #False
        
        self.layoutV = QVBoxLayout()
        self.layoutV.addLayout(self.mode_layout)
        counter = 2
        for mode_option in self.scanArray_modes:
            self.mode_layout.addWidget(self.scanLayouts[mode_option[0]],counter,0,1,2)
            counter+=1
        self.setLayout(self.layoutV)
        
        self.mode_dropdown.currentIndexChanged.connect(self.changeScanMode)
        self.changeScanMode()

    def changeScanMode(self):
        """
        Change the scan mode based on the selected index. - i.e. hide all non-chosen advScanGridLayouts and show the chosen one.
        
        Args:
            None
        
        Returns:
            None
        """
        for groupbox in self.scanLayouts.values():
            groupbox.setVisible(False) #False
            
        try:
            self.scanLayouts[self.scanArray_modes[self.mode_dropdown.currentIndex()][0]].setVisible(True)
            
            self.currentMode = self.scanArray_modes[self.mode_dropdown.currentIndex()][0]
        except:
            pass

    def getPositionInfo(self):
        """
        Get the position information of the chosen advScanGridLayout. (i.e. list of XY(Z) positions)
        
        Returns:
            The position information.
        """
        return self.scanLayouts[self.scanArray_modes[self.mode_dropdown.currentIndex()][0]].getPositionInfo()

class advScanGridLayout(QGroupBox):
    """ 
    advScanGridLayouts each individually handle a single method of xy(z) scanning. Easiest example is 'loading a POS file'.
    The advScanGridLayouts are created in the ScanningWidget class
    The layouts should be based around the self.mode parameter, where the .mode is a string which defines the methodologies used. The modes are defined in the ScanningWidget class
    Currently implemented:
        'LoadPos': Load a POS list
    """
    def __init__(self, mode=None,parent=None):
        """
        Initializes the class with the given mode and parent.
        
        Args:
            mode (str): The mode to be set for the class.
            parent (object): The parent object associated with this class.
        
        Returns:
            None
        """
        self.parent = parent #type:ignore
        super().__init__(parent)
        self.mode = mode
        self.scanningInfoGUI = {}
        #Create a QGridLayout to place in this groupbox:
        try:
            self.setLayout(QGridLayout())
        except:
            pass
        #Create a quick label that we place in 1,1:
        self.layout().addWidget(QLabel(f"{mode}",self))
        if mode == 'LoadPos':
            self.loadPos_update()
    
    def update(self):
        """
        General Update class, can be called from the parent class
        
        Args:
            self: The object itself.
        
        Returns:
            None
        """
        print('update')
    
    def getPositionInfo(self):
        """
        General method to get the opsition info. Should basically return a well-formatted XY(Z) position list - see self.mode == LoadPos for an example.
        
        Args:
            None
        
        Returns:
            dict: A dictionary containing position information
        """
        if self.mode == 'LoadPos':
            positions = {}
            #Read a JSON:
            import json
            with open(self.scanningInfoGUI['LoadPos']['fileName'], 'r') as f:
                xypositionsRaw = json.load(f)

            positions['nrPositions'] = len(xypositionsRaw['map']['StagePositions']['array'])
            for pos_id in range(positions['nrPositions']):
                positions[pos_id] = {}
                positions[pos_id]['STAGES'] = []
                if 'DefaultXYStage' in xypositionsRaw['map']['StagePositions']['array'][pos_id]:
                    positions[pos_id]['STAGES'].append(xypositionsRaw['map']['StagePositions']['array'][pos_id]['DefaultXYStage']['scalar'])
                if 'DefaultZStage' in xypositionsRaw['map']['StagePositions']['array'][pos_id]:
                    positions[pos_id]['STAGES'].append(xypositionsRaw['map']['StagePositions']['array'][pos_id]['DefaultZStage']['scalar'])
                
                for stage in positions[pos_id]['STAGES']:
                    devicePositions = xypositionsRaw['map']['StagePositions']['array'][pos_id]['DevicePositions']['array']
                    for devicePosition in devicePositions:
                        if stage == devicePosition['Device']['scalar']:
                            positions[pos_id][stage] = devicePosition['Position_um']['array']
                
            return positions
    
    def loadPos_update(self):
        """
        Update function specific for the 'loadPos' method - linked from the general update() method.
        
        Args:
            None
        
        Returns:
            None
        """
        self.scanningInfoGUI['LoadPos'] = {}
        
        def load_pos_file():
            """
            Load POS file using QFileDialog and set the filename in the line edit widget.
            
            Args:
                None
            
            Returns:
                None
            """
            from qtpy.QtWidgets import QFileDialog
            filename, _ = QFileDialog.getOpenFileName(self,'Open file', '', '*.POS Files (*.pos)')
            if filename:
                self.lineEdit_posFilename.setText(filename)
                self.scanningInfoGUI['LoadPos']['fileName'] = filename

        def update_file_name(new_file_name):
            """
            Update the file name in the scanning information GUI.
            
            Args:
                new_file_name (str): The new file name to be set in the scanning information GUI.
            
            Returns:
                None
            """
            self.scanningInfoGUI['LoadPos']['fileName'] = new_file_name
    
        self.lineEdit_posFilename = QLineEdit()
        self.layout().addWidget(self.lineEdit_posFilename,1,0) #type:ignore
        self.lineEdit_posFilename.textChanged.connect(lambda x: update_file_name(x))

        button_browsePosFile = QPushButton('...')
        self.layout().addWidget(button_browsePosFile,1,1) #type:ignore
        button_browsePosFile.clicked.connect(load_pos_file)
#endregion

#region DecisionWidget
class DecisionWidget(QWidget):
    """ 
    The decisionWidget handles having all the advDecisionLayouts, which are used for different scoring/passing/decision metrics (i.e. saying 'this field-of-view is good enough').
    Look at advDecisionGridLayout for implementation of the actual decision routines.
    """
    def __init__(self, nodzinstance=None,parent=None):
        """
        Initializes the DecisionWidget class.  Importantly defines the individual modes of the advDecisionLayout.
        
        Args:
            nodzinstance (object, optional): An instance of the nodz class. Defaults to None.
            parent (object, optional): The parent object. Defaults to None.
        
        Returns:
            None
        """
        super().__init__(parent)
        # super().__init__()
        self.nodzinstance=nodzinstance
        self.decisionMode = 'DirectDecision'
        self.decisionArray_modes = [
                            ['DirectDecision','Direct Decision'],
                            ['FullScan','Full Scan, then acquire'],
                            ['RandomScan','Randomly scan Nth percentile, then acquire'],
                            ['StayOnFOV','Conditionally stay on a FoV']]
        
        self.decisionArray_decisionTypes = {}
        self.decisionArray_decisionTypes['DirectDecision'] = [
                            ['AND_Score','All scoring conditions met'],
                            ['OR_Score','Any scoring condition met'],
                            ['Advanced','Advanced scoring condition']]
        self.decisionArray_decisionTypes['FullScan'] = [
                            ]
        self.decisionArray_decisionTypes['RandomScan'] = [
                            ]
        self.decisionArray_decisionTypes['StayOnFOV'] = [
                            ]
        
        self.finalDecisionLayout = QVBoxLayout()
        
        self.decisionLayouts = {}
        self.currentMode = None
        self.currentDecision = None
        
        self.create_GUI()
    
    def create_GUI(self):
        """
        Create GUI for decision making. Importantly adds all the advDecisionLayouts with individual modes.
        
        Args:
            None
        
        Returns:
            None
        """
        # self.setWindowTitle('Decision')
        self.mode_dropdown = QComboBox()
        self.mode_dropdown.addItems([option[1] for option in self.decisionArray_modes])
        self.mode_layout = QGridLayout()
        self.mode_layout.addWidget(QLabel('Mode: '),0,0)
        self.mode_layout.addWidget(self.mode_dropdown,0,1)

        from PyQt5.QtWidgets import QHBoxLayout
        for mode_option in self.decisionArray_modes:
            self.decisionLayouts[mode_option[0]] = QWidget()
            #Add a layout to this widget:
            self.decisionLayouts[mode_option[0]].layout = QHBoxLayout()
            self.decisionLayouts[mode_option[0]].setLayout(self.decisionLayouts[mode_option[0]].layout)
            self.decisionLayouts[mode_option[0]].setVisible(False) #False
            
            self.decisionLayouts[mode_option[0]].mode_dropdown = QComboBox()
            self.decisionLayouts[mode_option[0]].mode_dropdown.addItems([option[1] for option in self.decisionArray_decisionTypes[mode_option[0]]])
            
            self.decisionLayouts[mode_option[0]].mode_layout = QGridLayout()
            self.decisionLayouts[mode_option[0]].mode_layout.addWidget(QLabel('Decision mode: '),0,0)
            self.decisionLayouts[mode_option[0]].mode_layout.addWidget(self.decisionLayouts[mode_option[0]].mode_dropdown,0,1)
            self.decisionLayouts[mode_option[0]].decisiontypes={}
            
            counter2 = 1
            for option in self.decisionArray_decisionTypes[mode_option[0]]:
                self.decisionLayouts[mode_option[0]].decisiontypes[option[0]] = advDecisionGridLayout(mode=mode_option[0],decision=option[0],parent=self)
                self.decisionLayouts[mode_option[0]].decisiontypes[option[0]].setVisible(False)
                self.decisionLayouts[mode_option[0]].mode_layout.addWidget(self.decisionLayouts[mode_option[0]].decisiontypes[option[0]],counter2,0,1,2)
                counter2+=1
            
            self.decisionLayouts[mode_option[0]].layout.addLayout(self.decisionLayouts[mode_option[0]].mode_layout)
            
        self.layoutV = QVBoxLayout()
        self.layoutV.addLayout(self.mode_layout)
        counter = 2
        for mode_option in self.decisionArray_modes:
            self.mode_layout.addWidget(self.decisionLayouts[mode_option[0]],counter,0,1,2)
            counter+=1
        self.setLayout(self.layoutV)
        
        for mode_option in self.decisionArray_modes:
            self.decisionLayouts[mode_option[0]].mode_dropdown.currentIndexChanged.connect(self.changeDecisionMode)
        
        self.mode_dropdown.currentIndexChanged.connect(self.changeMode)
        self.changeMode()
        self.changeDecisionMode()

    def changeMode(self):
        """
        Change the mode of the decision layout. Mostly hides/shows individual decisionLayouts.
        
        Args:
            None
        
        Returns:
            None
        """
        for groupbox in self.decisionLayouts.values():
            groupbox.setVisible(False) #False
        try:
            self.decisionLayouts[self.decisionArray_modes[self.mode_dropdown.currentIndex()][0]].setVisible(True)
        except:
            pass

    def changeDecisionMode(self):        
        """
        Change the decision mode by setting the visibility of decision layouts. Mostly hides/shows individual decisionLayouts and sets its own mode/decision.
        
        Args:
            None
        
        Returns:
            None
        """
        #Set all of these: self.decisionLayouts[currentMode][currentDecision].setVisible(True) to invis:
        for mode in self.decisionLayouts:
            for option in self.decisionLayouts[mode].decisiontypes:
                if isinstance(self.decisionLayouts[mode].decisiontypes[option],advDecisionGridLayout):
                    self.decisionLayouts[mode].decisiontypes[option].setVisible(False)
        
        # #Then, we do something specific based on this decision:
        currentMode = self.decisionArray_modes[self.mode_dropdown.currentIndex()][0]
        currentDecisionLong = self.decisionLayouts[currentMode].mode_dropdown.currentText()
        currentDecision = ''
        for option in self.decisionArray_decisionTypes[currentMode]:
            if currentDecisionLong == option[1]:
                currentDecision = option[0]
        
        self.decisionLayouts[currentMode].decisiontypes[currentDecision].setVisible(True)
        self.currentMode = currentMode
        self.currentDecision = currentDecision
    
    def updateAllDecisions(self):
        """
        Update all decisions in the decision layouts.
        
        Args:
            None
        
        Returns:
            None
        """
        for mode in self.decisionLayouts:
            for option in self.decisionLayouts[mode].decisiontypes:
                self.decisionLayouts[mode].decisiontypes[option].update()

    def testCurrentDecision(self):
        """
        Tests whether the current FoV passes the currently selected Decision. Mostly wrapper for calling test_decision of the chosen decision in advDecisionGridLayout
        
        Args:
            None
        
        Returns:
            bool: True if the test for the current decision passed, False otherwise.
        """
        testPassed = self.decisionLayouts[self.currentMode].decisiontypes[self.currentDecision].test_decision()
        return testPassed

class advDecisionGridLayout(QGroupBox):
    """ 
    advDecisionGridLayout each individually handle a single method of decision. Easiest example is DirectDecision mode with 'AND_SCORE' decision.
    Each layout requires a MODE and a DECISION, where the MODE is one of four options (DirectDecision, fullscan, randomscan, stayonfov) --> see ScanningWidget init, and the DECISION is more flexible (i.e. 'all scores are passed', or 'at least 1 score is passed' in the DirectDecision mode)
    The advDecisionGridLayout are created in the DecisionWidget class
    Currently implemented:
        'DirectDecision' --> 'AND_Score': Checks if all scores are passed.
    """
    def __init__(self, mode=None,decision=None,parent=None):
        """
        Initialize the class with the provided mode, decision, and parent.
        
        Args:
            mode (str): The mode to be set for the instance.
            decision (str): The decision to be set for the instance.
            parent (object): The parent object associated with this instance.
        
        Returns:
            None
        """
        self.parent = parent #type:ignore
        super().__init__(parent)
        self.mode = mode
        self.decision = decision
        self.decisionInfoGUI = {} #Will finally contain all decision info in GUI form!
        #Create a QGridLayout to place in this groupbox:
        self.setLayout(QGridLayout())
        #Create a quick label that we place in 1,1:
        self.layout().addWidget(QLabel(f"{mode} and {decision}",self),1,1) #type:ignore
        if mode == 'DirectDecision':
            if decision == 'AND_Score':
                self.directDecision_AND_Score_update()
    
    def update(self):
        """
        Update the object based on the current mode and decision.
        
        Args:
            None
        
        Returns:
            None
        """
        if self.mode == 'DirectDecision':
            if self.decision == 'AND_Score':
                self.directDecision_AND_Score_update()
    
    def test_decision(self):
        """
        Make a decision based on the mode and decision type. Should always output a boolean
        
        Args:
            mode (str): The mode of decision making.
            decision (str): The type of decision to be made.
        
        Returns:
            str: The result of the decision making process.
        """
        if self.mode == 'DirectDecision':
            if self.decision == 'AND_Score':
                return self.directDecision_AND_Score_test()
    
    def getScoreMetrics(self):
        """
        Get the score metrics from the scoringEnd node.
        
        Args:
            None
        
        Returns:
            list: A list of score metrics (i.e. sockets of score node).
        """
        scoreMetrics = []
        #Get all score metrics (i.e. sockets of score node)
        flowChart = self.parent.nodzinstance
        if len(flowChart.nodes) > 0:
            #Find the scoringEnd node in flowChart:
            for node in flowChart.nodes:
                if 'scoringEnd_' in node.name:
                    break
            
            #Now get the scores from here:
            for socket in node.sockets:
                scoreMetrics.append(socket)
        return scoreMetrics
    
    def remove_widgets_in_layout(self,layout):
        """
        Removes all widgets in the given layout recursively.
        
        Args:
            layout: The layout from which widgets will be removed.
        
        Returns:
            None
        """
        while layout.count():
            item = layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()
            elif item.layout() is not None:
                self.remove_widgets_in_layout(item.layout())
    
    def directDecision_AND_Score_test(self):
        """
        Code to test whether the current score passes the decision matrix or not. Should always output a boolean
        """
        finalTest = False
        scoreMetrics = self.getScoreMetrics()
        
        #Get all score metrics (i.e. sockets of score node)
        flowChart = self.parent.nodzinstance
        if len(flowChart.nodes) > 0:
            #Find the scoringEnd node in flowChart:
            for node in flowChart.nodes:
                if 'scoringEnd_' in node.name:
                    break
        
        #Find the nodes that are connected downstream of this:
        data = {}
        for attr in node.attrs:
            connectedNode = None
            for connection in flowChart.evaluateGraph():
                if connection[1][connection[1].rfind('.')+1:] == attr:
                    if connection[1][:connection[1].rfind('.')] == node.name:
                        connectedNodeName = connection[0][:connection[0].rfind('.')]
                        connectedNode = flowChart.findNodeByName(connectedNodeName)
        
                    data[attr] = connectedNode.scoring_analysis_currentData['__output__'] #type:ignore
        
        #Data now contains the values of the scores
        self.decisionInfoGUI
        scoreMetric = 'ScoreA'
        indivBooleans = {}
        for scoreMetric in scoreMetrics:
            hbox = self.decisionInfoGUI[scoreMetric]
            operator = hbox['dropdown'].currentText()
            value = hbox['lineedit'].text()
            
            if eval(f"{data[scoreMetric]} {operator} {value}"):
                indivBooleans[scoreMetric] = True
            else:
                indivBooleans[scoreMetric] = False
        
        if all(indivBooleans.values()):
            finalTest = True
        
        return finalTest
    
    def directDecision_AND_Score_update(self):
        """
        Code to update the GUI of the DirectDecision_AND_Score groupbox
        """
        from PyQt5.QtWidgets import QComboBox, QHBoxLayout, QLabel, QLineEdit, QPushButton
        self.remove_widgets_in_layout(self.layout())
        
        self.outerLayout = QVBoxLayout()
        self.layout().addLayout(self.outerLayout,0,0) #type:ignore
        
        #Get out of this function if flowChart isn't initialised yet (i.e. first start-up):
        try:
            self.parent.nodzinstance.nodes
        except RuntimeError:
            return
        
        scoreMetrics = self.getScoreMetrics()
        
        for scoreMetric in scoreMetrics:
            hbox = QHBoxLayout()
            label = QLabel(scoreMetric)
            hbox.addWidget(label)
            dropdown = QComboBox()
            dropdown.addItems(['>','>=','==','<=','<','!='])
            hbox.addWidget(dropdown)
            lineedit = QLineEdit()
            hbox.addWidget(lineedit)
            self.decisionInfoGUI[scoreMetric] = {}
            self.decisionInfoGUI[scoreMetric]['dropdown'] = dropdown
            self.decisionInfoGUI[scoreMetric]['lineedit'] = lineedit
            self.outerLayout.addLayout(hbox)
#endregion

#region VariablesWidget

from PyQt5.QtWidgets import QTableWidget

class HoverTableWidget(QTableWidget):
    cellHovered = pyqtSignal(int, int)

    def __init__(self,parent=None):
        super().__init__(parent)
        self.setMouseTracking(True)  # Enable mouse tracking without pressing a button
        self.setSortingEnabled(True) #Enable sorting the columns
        self.verticalHeader().hide() #Hide the row numbering

    def mouseMoveEvent(self, event):
        index = self.indexAt(event.pos())
        if index.isValid():
            self.cellHovered.emit(index.row(), index.column())
        super().mouseMoveEvent(event)

    def leaveEvent(self, event):
        # Emit cellHovered signal with invalid index when mouse leaves
        self.cellHovered.emit(-1, -1)
        super().leaveEvent(event)
        
class VariablesBase(QWidget):
    """ 
    Show the variables of all nodz-instances, possibly filtered on connectedNodz only.
    """
    def __init__(self, 
                nodzinstance:GladosNodzFlowChart_dockWidget,
                parent=None,
                doubleClickEffect=None,
                doubleClickLineEditChange=None,
                connectedNode_showOnlyDownstream=None,
                typeInfo=None):
        """
        Initializes the scanning widget class.
        
        Args:
            nodzinstance: The nodz instance to be associated with.
            parent: The parent widget.
            doubleClickEffect: what you want to do if double-clicked. Options: None, 'updateLineEdit'
            
        
        Returns:
            None
        """
        super().__init__(parent)
        # super().__init__()
        self.nodzinstance=nodzinstance
        
        if typeInfo is not None:
            #if typeInfo is not in an array, put it inside one
            if isinstance(typeInfo,type):
                typeInfo = [typeInfo]
            
            #Specifically check if there is a FLOAT type, but no INT type. If so, add the INT type as well
            hasFloatInt = [0,0]
            for typev in typeInfo:
                if typev == int:
                    hasFloatInt[1] = 1
                elif typev == float:
                    hasFloatInt[0] = 1
            if hasFloatInt == [1,0]:
                typeInfo.append(int)
                
        self.typeInfo = typeInfo
        
        self.create_GUI()
        
        return self
    
    def create_GUI(self):
        """
        Create a QTableWidget GUI
        """
        logging.info('Inside variableswidget-createGUi')
        self.buttonTest = QPushButton("Update")
        self.buttonTest.clicked.connect(self.updateVariables)
        
        self.lineEditHover = QLabel("Hover over a Cell",self)
        self.lineEditHover.setEnabled(False)
        
        headers = ["CellValue", "Origin", "Name", "Value", "Importance", "Type", "LastChanged"]
        self.variablesTableWidget = HoverTableWidget()
        self.variablesTableWidget.setColumnCount(len(headers))
        self.variablesTableWidget.setHorizontalHeaderLabels(headers)
        
        # Connect the cellDoubleClicked signal to a custom slot
        self.variablesTableWidget.cellClicked.connect(self.on_cell_clicked)
        self.variablesTableWidget.cellDoubleClicked.connect(self.on_cell_double_clicked)
        self.variablesTableWidget.cellHovered.connect(self.on_cell_hovered)
        
        self.layoutV = QVBoxLayout()
        self.layoutV.addWidget(self.buttonTest)
        self.layoutV.addWidget(self.lineEditHover)
        self.layoutV.addWidget(self.variablesTableWidget)
        self.setLayout(self.layoutV)
        

    def on_cell_hovered(self, row, column):
        # Get the hovered entry
        try:
            #Specifically, get the origin Nodz
            hovered_entry = self.variablesTableWidget.item(row,1).text()# self.variablesTableWidget.item(row, column).text()
        except:
            hovered_entry = None
            
        #Loop over the nods in the nodzinstance:
        for node in self.nodzinstance.nodes:
            from PyQt5.QtWidgets import QGraphicsColorizeEffect, QGraphicsEffect, QGraphicsDropShadowEffect, QGraphicsView, QApplication
            if node.name == hovered_entry:                
                #Add a green shadow effect if it's the one hovered over.
                effect = QGraphicsDropShadowEffect()
                effect.setBlurRadius(60)
                effect.setColor(QColor(0, 200, 100, 230))
                effect.setOffset(0,0)

                node.setGraphicsEffect(effect)
            else:
                node.setGraphicsEffect(None)
                
        self.lineEditHover.setText(f"Hovered: {hovered_entry}")

    def on_cell_clicked(self, row, column):
        self.selected_entry = []
        for col in range(self.variablesTableWidget.columnCount()):
            textEntry = ''
            try:
                textEntry = self.variablesTableWidget.item(row, col).text()
            except AttributeError:
                textEntry = 'None'
            self.selected_entry.append(textEntry)
            
    def on_cell_double_clicked(self, row, column):
        #Figure out the selected row
        self.selected_entry = []
        for col in range(self.variablesTableWidget.columnCount()):
            textEntry = ''
            try:
                textEntry = self.variablesTableWidget.item(row, col).text()
            except AttributeError:
                textEntry = 'None'
            self.selected_entry.append(textEntry)
    
    def get_selected_entry(self):
        return getattr(self, 'selected_entry', None)
    
    def updateVariables(self):
        """
        Update the nodz-variables.
        """
        allNodes = self.nodzinstance.obtainAllNodes()
        
        allvariableData = {}
        for node in allNodes:
            for var in node.variablesNodz:
                pos = len(allvariableData)
                correctTyping = False
                if self.typeInfo is not None:
                    variableTypes = node.variablesNodz[var]['type']
                    if isinstance(variableTypes,type):
                        variableTypes = [variableTypes]
                    if isinstance(self.typeInfo,type):
                        self.typeInfo = [self.typeInfo]
                    
                    for variableType in variableTypes:
                        for selftype in self.typeInfo:
                            if variableType == selftype:
                                correctTyping = True
                else: #if no typing specified, accept everything
                    correctTyping = True
                
                if correctTyping:
                    allvariableData[pos] = node.variablesNodz[var]
                    allvariableData[pos]['NodeOrigin'] = node.name
                    allvariableData[pos]['VariableName'] = var
            
            
        # Set the number of rows
        self.variablesTableWidget.setRowCount(len(allvariableData))

        from PyQt5.QtWidgets import QTableWidgetItem
        from datetime import datetime
        # Fill the table with data
        for row_id in range(len(allvariableData)):
            varData = allvariableData[row_id]
            # headers = ["CellValue", "Origin", "Name", "Value", "Importance","Type", "LastChanged"]
            self.variablesTableWidget.setItem(row_id, 1, QTableWidgetItem(str(varData['NodeOrigin'])))
            self.variablesTableWidget.setItem(row_id, 2, QTableWidgetItem(str(varData['VariableName'])))
            self.variablesTableWidget.setItem(row_id, 3, QTableWidgetItem(str(varData['data'])))
            self.variablesTableWidget.setItem(row_id, 4, QTableWidgetItem(str(varData['importance'])))
            self.variablesTableWidget.setItem(row_id, 5, QTableWidgetItem(str(varData['type'])))
            if varData['lastUpdateTime'] is not None:
                self.variablesTableWidget.setItem(row_id, 6, QTableWidgetItem(str(datetime.fromtimestamp(varData['lastUpdateTime']).strftime("%H:%M:%S %d-%m-%Y"))))
            else:
                self.variablesTableWidget.setItem(row_id, 6, QTableWidgetItem('None'))

class VariablesWidget(VariablesBase):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

class VariablesDialog(QDialog, VariablesBase):
    def __init__(self, *args, **kwargs):
        QDialog.__init__(self)
        variablesWidget = VariablesBase.__init__(self, *args, **kwargs)
        self.setWindowTitle("Variables Dialog")
        #Create a container layout:
        # layout = QVBoxLayout()
        
        
        # Set font size for all items in the table
        font = QFont()
        font.setPointSize(7)  # Set the desired font size
        variablesWidget.variablesTableWidget.setFont(font)

        # Set font size for headers
        header_font = QFont()
        header_font.setPointSize(10)  # Set the desired font size for headers
        variablesWidget.variablesTableWidget.horizontalHeader().setFont(header_font)
        variablesWidget.variablesTableWidget.verticalHeader().setFont(header_font)
        
        from PyQt5.QtWidgets import QApplication, QTableWidget, QTableWidgetItem, QHeaderView

        # Make the table more compact
        variablesWidget.variablesTableWidget.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        variablesWidget.variablesTableWidget.verticalHeader().setSectionResizeMode(QHeaderView.Stretch)
        variablesWidget.variablesTableWidget.verticalHeader().setDefaultSectionSize(25)  # Set the default height of each row

        
        #Update the variables
        variablesWidget.updateVariables()
        self.layout().addWidget(variablesWidget)
        
        
        
        self.buttonBox = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        self.buttonBox.accepted.connect(self.accept)
        self.buttonBox.rejected.connect(self.reject)
        
        # Add button box to the layout
        self.layout().addWidget(self.buttonBox)
        self.setMinimumSize(600,300)
        self.setBaseSize(600,300)
        
    def on_cell_double_clicked(self, row, column):
        super().on_cell_double_clicked(row, column)
        #remove hover-effect
        self.variablesTableWidget.cellHovered.emit(-1, -1)
        self.accept()  # Close the dialog with the Accepted result
        
#endregion



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
        GladosNodzFlowChart_dockWidget: The flowchart dock widget.
    """

    global shared_data, napariViewer
    shared_data = sshared_data
    napariViewer = shared_data.napariViewer
    
    #Create the a flowchart testing
    flowChart_dockWidget = GladosNodzFlowChart_dockWidget(core=core,shared_data=shared_data,MM_JSON=MM_JSON)
    main_layout.addLayout(flowChart_dockWidget.mainLayout,0,0)
    
    flowChart_dockWidget.getNodz()
    
    return flowChart_dockWidget