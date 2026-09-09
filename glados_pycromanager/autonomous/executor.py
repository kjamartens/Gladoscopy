"""Autonomous-microscopy runtime executor.

Carved out of `glados_pycromanager/GUI/FlowChart_dockWidgets.py` in
Phase 8.4 of `claude_project.md`. Hosts two things:

* ``WorkerSignals`` + ``generalNodzCallActionWorker`` — the ``QRunnable``
  that asynchronously runs node call-actions (Timer / MMconfigChangeRan /
  AnalysisNode / CustomFunctionNode). The ``eval(evalText)`` inside
  ``run()`` is what Phase 9 replaces with a registry dispatch.
* ``FlowchartExecutorMixin`` — every per-node-type start/finish/callAction
  method (NodzFlowChart Node-specific region) and every high-level run
  orchestrator (NodzFlowChart runs region) used to live on
  ``GladosNodzFlowChart_dockWidget``. They are now mixin methods so the
  dock widget still has the same public surface (it inherits from this
  mixin), but the bulk of the runtime code lives outside the god-file.

The star-imports from the three plugin packages are required so that
``eval(evalText)`` and ``eval("<Module>.__function_metadata__()")``
can resolve node-function names at this module's globals scope.
"""

from __future__ import annotations

import json
import logging
import os
import re
import sys
import tempfile
import time
import webbrowser
from datetime import datetime

import appdirs
import napari
import numpy as np
import pyperclip
import tifffile
from ndtiff import NDTiffDataset
from PIL import Image
from PyQt5 import QtGui, QtWidgets
from PyQt5.QtCore import (
    QObject,
    QRunnable,
    QSize,
    Qt,
    QThreadPool,
    QTimer,
    pyqtSignal,
)
from PyQt5.QtGui import QColor, QFont, QIcon, QTextCursor
from PyQt5.QtWidgets import (
    QAction,
    QApplication,
    QCheckBox,
    QColorDialog,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QFormLayout,
    QGraphicsDropShadowEffect,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMenu,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QSpacerItem,
    QSpinBox,
    QSplitter,
    QTableWidget,
    QTableWidgetItem,
    QTabWidget,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

if "glados_pycromanager" not in sys.modules and "site-packages" not in __file__:
    sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

import glados_pycromanager.Core.microscopeInterfaceLayer as MIL
import glados_pycromanager.GUI.nodz.nodz_main as NodzMain
import glados_pycromanager.GUI.nodz.nodz_utils as nodz_utils
import glados_pycromanager.GUI.utils as utils
from glados_pycromanager.autonomous import registry
from glados_pycromanager.autonomous.types import GladosGraph
from glados_pycromanager.AutonomousMicroscopy.Analysis_Measurements import *
from glados_pycromanager.AutonomousMicroscopy.CustomFunctions import *
from glados_pycromanager.AutonomousMicroscopy.Real_Time_Analysis import *
from glados_pycromanager.Core.MDAGlados import MDAGlados
from glados_pycromanager.GUI.MMcontrols import ConfigInfo, MMConfigUI
from glados_pycromanager.GUI.slack_settings_dialog import (
    SlackSettingsDialog,
)
from glados_pycromanager.GUI.slack_settings_dialog import (
    apply_to_shared_data as _apply_slack_settings,
)
from glados_pycromanager.GUI.napari_bridge import get_bridge


def _replace_visualisation_layer(shared_data, layerType, layerName, colormap):
    """Create an RT-visualisation layer for a node, on the GUI thread (T-F9).

    The node call-actions that use this run on a `QThreadPool` worker, and they
    used to remove and add `viewer.layers` entries from there directly -- the
    classic route to an inconsistent layer list or a vispy segfault. The bridge
    performs the swap on the GUI thread and hands the layer back, because the
    node's `..._visualise` function is called with it.

    Returns `None` if there is no bridge (no shared_data / no viewer yet).
    """
    bridge = get_bridge(shared_data)
    if bridge is None:
        logging.error('No napari bridge available; cannot create layer %s', layerName)
        return None

    if layerType == 'points':
        return bridge.replace_layer('points', name=layerName, data=None, text=None)
    if layerType == 'shapes':
        return bridge.replace_layer('shapes', name=layerName, data=None)
    if layerType == 'image':
        logging.debug('creating new image layer')
        return bridge.replace_layer(
            'image', name=layerName, data=np.random.random((30, 30)), colormap=colormap)

    logging.error('Unknown RT-visualisation layer type: %s', layerType)
    return None


# Define a WorkerSignals class to handle signals
class WorkerSignals(QObject):
    """  
    Signals belonging to generalNodzCallActionWorker
    """
    finished = pyqtSignal()

class generalNodzCallActionWorker(QRunnable):
    
    """ 
    General worker that can do async running of callActions belonging to nodes.
    """
    
    def __init__(self,nodzType,args):
        """ 
        Init only passes nodzType and args to the super class.
        """
        super().__init__()
        self.nodzType = nodzType
        self.args = args
        self.signals = WorkerSignals()
        logging.debug(f"GeneralNodzCallActionworker INIT with nodzType: {self.nodzType} and args: {self.args}")
    
    def run(self):
        """ 
        Running of the different callActions belonging to all nodes.
        """
        logging.debug(f"GeneralNodzCallActionworker RUN with nodzType: {self.nodzType} and args: {self.args}")
        #Timer
        if self.nodzType == 'Timer':
            time.sleep(self.args['wait_time'])
        elif self.nodzType == 'MMconfigChangeRan':
            #We need to change some configs (probably):
            for config_to_change in self.args['config_string_storage']:
                
                #Find the correct config_group in MMconfig:
                for config_group_id_loop in self.args['MMconfig'].config_groups:
                    config_group_name = self.args['MMconfig'].config_groups[config_group_id_loop].configGroupName()
                    if config_group_name == config_to_change[0]:
                        config_group_id = config_group_id_loop
                        #Over-write the grouptype like this:
                        config_group_type = 'InputField'
                        if self.args['MMconfig'].config_groups[config_group_id].isInputField():
                            config_group_type = 'InputField'
                        if self.args['MMconfig'].config_groups[config_group_id].isDropDown():
                            config_group_type = 'DropDown'
                        if self.args['MMconfig'].config_groups[config_group_id].isSlider():
                            config_group_type = 'Slider'
                
                if config_group_type == 'DropDown':
                    logging.debug('Changing dropDown value from MMconfig-Nodz!')
                    #Change the config, and wait for the config to be changed - this works for groups
                    self.args['core'].set_config(config_to_change[0],config_to_change[1]) #type:ignore
                    self.args['core'].wait_for_config(config_to_change[0],config_to_change[1])#type:ignore
                elif config_group_type == 'InputField':
                    logging.info('Changing inputField value from MMconfig-Nodz!')
                    CurrentText = config_to_change[1]
                    #Get the config group name:
                    configGroupName = self.args['MMconfig'].config_groups[config_group_id].configGroupName()

                    #An Editfield config by definition (?) only has a single property underneath, so get that:
                    underlyingProperty = self.args['MMconfig'].config_groups[config_group_id].core.get_available_configs(configGroupName).get(0)
                    configdata = self.args['MMconfig'].config_groups[config_group_id].core.get_config_data(configGroupName,underlyingProperty)
                    device_label = configdata.get_setting(0).get_device_label()
                    property_name = configdata.get_setting(0).get_property_name()

                    #Set this property:
                    self.args['MMconfig'].config_groups[config_group_id].core.set_property(device_label,property_name,CurrentText)
                    logging.info(f"Changed {device_label}.{property_name} to {CurrentText}")
                elif config_group_type == 'Slider':
                    logging.debug('Changing slider value from MMconfig-Nodz!')
                    newValue = config_to_change[1]
                    #Get the true value from the conversion - not required in MMconfig-nodz:
                    trueValue = newValue
                    
                    #Get the config group name:
                    configGroupName = self.args['MMconfig'].config_groups[config_group_id].configGroupName()
                    #Set in MM:
                    #A slider config by definition (?) only has a single property underneath, so get that:
                    underlyingProperty = self.args['MMconfig'].config_groups[config_group_id].core.get_available_configs(configGroupName).get(0)
                    configdata = self.args['MMconfig'].config_groups[config_group_id].core.get_config_data(configGroupName,underlyingProperty)
                    device_label = configdata.get_setting(0).get_device_label()
                    property_name = configdata.get_setting(0).get_property_name()

                    #Set this property:
                    self.args['MMconfig'].config_groups[config_group_id].core.set_property(device_label,property_name,trueValue)
                    logging.info(f"Changed {device_label}.{property_name} to {trueValue}")
                    
        elif self.nodzType == 'AnalysisNode' or self.nodzType == 'CustomFunctionNode':
            #Get all the necessary info
            evalText = self.args['evalText']
            nodeDict = self.args['nodeDict']
            node = self.args['node']
            core = self.args['core']
            shared_data = self.args['shared_data']
            self.shared_data = shared_data
            logging.info(evalText)
            #Phase 9.5: dispatch via the autonomous registry instead of bare eval.
            #The function name is parsed out of evalText and looked up in
            #_REGISTRY; arg expressions resolve against the worker's scope
            #plus the nodzVariable dict.
            scope = {
                **globals(),
                **nodeDict,
                'self': self,
                'core': core,
                'shared_data': shared_data,
            }
            node.output = registry.dispatch_from_eval_text(evalText, scope=scope)
        
        #Emit that the node is finished :) 
        self.signals.finished.emit()



class FlowchartExecutorMixin:
    """Mixin holding the autonomous-flowchart runtime methods.

    Provides per-node-type start/finish/callAction handlers and the
    high-level run orchestration (full run, init-only, scoring-only,
    acquiring-only, interrupt). Uses ``self`` for everything the original
    methods did — meant to be inherited alongside ``NodzMain.Nodz`` by
    ``GladosNodzFlowChart_dockWidget``.
    """

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
        sleepTime = 0.02
        for _ in range(3): #Just repeat everything 3 times and hope it solves itself
            self.update()
            time.sleep(sleepTime)
            current_sockets = [item[0] for item in list(currentNode.sockets.items())]
            if dialogLineEdits != current_sockets:
                
                for socket_id in reversed(range(len(currentNode.attrs))):
                    socket = currentNode.attrs[socket_id]
                    #We check if the socket is in dialogLineEdits:
                    if socket not in dialogLineEdits and socket in current_sockets:
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
    
    def update_plugs_fromDialog(self,currentNode,dialogLineEdits):
        """
        Update the "scoring end" current node with new dialog line edits.
        
        Args:
            currentNode: The current node to update.
            dialogLineEdits: The new sockets of the current node.
        
        Returns:
            None
        """
                
        #the dialogLineEdits should be the new plugs of the current node. However, if a plug with the name already exists, it shouldn't be changed.
        sleepTime = 0.02
        for _ in range(3): #Just repeat everything 3 times and hope it solves itself
            self.update()
            time.sleep(sleepTime)
            current_plugs = [item[0] for item in list(currentNode.plugs.items())]
            if dialogLineEdits != current_plugs:
                
                for plug_id in reversed(range(len(currentNode.attrs))):
                    plug = currentNode.attrs[plug_id]
                    #We check if the plug is in dialogLineEdits:
                    if plug not in dialogLineEdits and plug in current_plugs:
                        logging.debug(plug_id)
                        #If it isn't, we just delete it:
                        self.deleteAttribute(currentNode,plug_id)
                        time.sleep(sleepTime)
                        self.update()
                        time.sleep(sleepTime)
                
                #Check which are different (index-wise) between dialogLineEdits and current_plugs:
                diff_indexes = []
                same_indexes = []
                for i in range(min(len(dialogLineEdits),len(current_plugs))):
                    if dialogLineEdits[i] != current_plugs[i]:
                        diff_indexes.append(i)
                    else:
                        same_indexes.append(i)
                #Also append indexes if dialogLineEdits is longer than current_plugs:
                if len(dialogLineEdits) > len(current_plugs):
                    for i in range(len(current_plugs),len(dialogLineEdits)):
                        diff_indexes.append(i)
                
                offset = 100
                #Then we create new plugs or move existing plugs, only for those that have a different pos
                for plug_new in ([dialogLineEdits[i] for i in diff_indexes]):
                    pos_in_dialogLineEdits = dialogLineEdits.index(plug_new)
                    if plug_new not in currentNode.plugs:
                        self.createAttribute(currentNode, name=plug_new, index=pos_in_dialogLineEdits+offset, preset='attr_default', plug=True, socket=False, dataType=None)
                        time.sleep(sleepTime)
                        self.update()
                        time.sleep(sleepTime)
                    else: #Else we move it from some other location to where we want it
                        #Find this plug in currentNode.plugs.items():
                        plugFull = list(currentNode.plugs.items())
                        pos_in_node_info = [plug_id for plug_id in range(len(plugFull)) if plugFull[plug_id][0] == plug_new][0]
                        old_pos = plugFull[pos_in_node_info][1].index
                        #Physically move it
                        self.editAttribute(currentNode,old_pos,newName = None, newIndex=pos_in_dialogLineEdits+offset)
                        time.sleep(sleepTime)
                        self.update()
                        time.sleep(sleepTime)
        
        #We also need to add these attributes to the nodes startAttributes in self.nodeInfo:
        self.nodeInfo[self.nodeLookupName_withoutCounter(currentNode.name)]['finishedAttributes'] = dialogLineEdits
    
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
    
    def changeRelStageStorageInNodz(self,currentNode,relstageinfo):
        
        currentNode.MMconfigInfo.relstage_string_storage=relstageinfo
    
    def AnalysisNode_DEBUG_started(self,node):
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
            logging.error('Error! No connected node found for scoring analysis')
            return
        
        #Dictionary of nodes to pass around variables.
        nodeDict = utils.createNodeDictFromNodes(self.nodes)
        nodzInfo = node.flowChart
        
        #Figure out which function is selected in the scoring_analysis node
        selectedFunction = utils.functionNameFromDisplayName(node.scoring_analysis_currentData['__selectedDropdownEntryAnalysis__'],node.scoring_analysis_currentData['__displayNameFunctionNameMap__'])
        #Figure out the belonging evaluation-text
        evalText = utils.getFunctionEvalTextFromCurrentData(selectedFunction,node.scoring_analysis_currentData,'self.shared_data.core','',nodzInfo=self,skipp2=True)
        
        #Phase 9.5: dispatch via registry instead of bare eval.
        output = registry.dispatch_from_eval_text(
            evalText,
            scope={**globals(), **nodeDict, 'self': self, 'nodzInfo': nodzInfo},
        )
        
        #Display final output to the user for now
        logging.info(f"Final output from node {node.name}: {output}")
        
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
                    
                    #Figure out which visualisation we want to do
                    chosenLayerType = None
                    try:
                        fnctmetadata = eval(f"{selectedFunction.split('.')[0]}.__function_metadata__()")
                        visType = fnctmetadata[selectedFunction.split('.')[1]]['visualisation_type']
                        
                        if visType == 'value' or visType == 'points' or visType == 'Value' or visType == 'Points' or visType == 'Values' or visType == 'values':
                            chosenLayerType = 'points'
                        elif visType == 'Image' or visType == 'image':
                            chosenLayerType = 'image'
                        elif visType == 'Shapes' or visType == 'shapes' or visType == 'Shape' or visType == 'shape':
                            chosenLayerType = 'shapes'
                        logging.debug(f'Will perform RTvisualisation with layer type: {chosenLayerType}')
                    except Exception as e:
                        logging.error(f"Issue with finding RTvisualisation type of a analysisnode: error: {e}")
                    
                    if chosenLayerType != None:
                        
                        layerName = visual_connected_node.visualisation_currentData['layerName']
                        cmap = visual_connected_node.visualisation_currentData['colormap']

                        # T-F9: this method runs on a QThreadPool worker, so the
                        # layer swap goes through the GUI-thread bridge instead
                        # of mutating viewer.layers from here. `replace_layer`
                        # does the remove and the add in one GUI-thread call, so
                        # no other thread can observe the gap between them, and
                        # blocks because the new layer is needed below.
                        napariLayer = _replace_visualisation_layer(
                            self.shared_data, chosenLayerType, layerName, cmap)
                        
                        visualOutput = registry.dispatch_from_eval_text(
                            visualEvalText,
                            scope={
                                **globals(),
                                **nodeDict,
                                'self': self,
                                'output': output,
                                'napariLayer': napariLayer,
                            },
                        )

                        visual_connected_node.status = 'finished'
                    else:
                        visual_connected_node.status = 'error'


        node.scoring_analysis_currentData['__output__'] = output
        
        #Store the output as NodzVariables
        utils.analysis_outputs_store_as_variableNodz(node)
        
        
        #Finish up
        self.finishedEmits(node)
    
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
            logging.error('Error! No connected node found for scoring analysis')
            return
        
        #Dictionary of nodes to pass around variables.
        nodeDict = utils.createNodeDictFromNodes(self.nodes)
        nodzInfo = node.flowChart
        
        #Figure out which function is selected in the scoring_analysis node
        selectedFunction = utils.functionNameFromDisplayName(node.scoring_analysis_currentData['__selectedDropdownEntryAnalysis__'],node.scoring_analysis_currentData['__displayNameFunctionNameMap__'])
        #Figure out the belonging evaluation-text
        evalText = utils.getFunctionEvalTextFromCurrentData(selectedFunction,node.scoring_analysis_currentData,'self.shared_data.core','',nodzInfo=self,skipp2=True)
        
        
        worker = generalNodzCallActionWorker(nodzType='AnalysisNode',args={"evalText":evalText, "nodeDict":nodeDict, "node":node, "core": self.core, "shared_data": self.shared_data})
        #Add the finished emit
        worker.signals.finished.connect(lambda: self.analysisNode_finished(node))
        #Star the worker
        self.thread_pool.start(worker)
        
    def analysisNode_finished(self,node):
        #Set the status of the nodz-coupled vis and real-time to finished:
        #Look at the 'Visual' bottom attribute and visualise if needed
        output = node.output
        #Dictionary of nodes to pass around variables.
        nodeDict = utils.createNodeDictFromNodes(self.nodes)
        nodzInfo = node.flowChart
        
        visualAttr = node.bottomAttrs['Visual']
        if len(visualAttr.connections) > 0:
            visual_connected_node_name = visualAttr.connections[0].socketNode
            for nodeV in self.nodes:
                if nodeV.name == visual_connected_node_name:
                    visual_connected_node = nodeV
                    
                    selectedFunction = utils.functionNameFromDisplayName(node.scoring_analysis_currentData['__selectedDropdownEntryAnalysis__'],node.scoring_analysis_currentData['__displayNameFunctionNameMap__'])
                    visualEvalText = utils.getFunctionEvalTextFromCurrentData(selectedFunction,node.scoring_analysis_currentData,'(output,napariLayer)','self.shared_data.core',nodzInfo=self)
                    visualEvalText = visualEvalText.replace(selectedFunction,f'{selectedFunction}_visualise') #type:ignore
                    
                    #Figure out which visualisation we want to do
                    chosenLayerType = None
                    try:
                        fnctmetadata = eval(f"{selectedFunction.split('.')[0]}.__function_metadata__()")
                        visType = fnctmetadata[selectedFunction.split('.')[1]]['visualisation_type']
                        
                        if visType == 'value' or visType == 'points' or visType == 'Value' or visType == 'Points' or visType == 'Values' or visType == 'values':
                            chosenLayerType = 'points'
                        elif visType == 'Image' or visType == 'image':
                            chosenLayerType = 'image'
                        elif visType == 'Shapes' or visType == 'shapes' or visType == 'Shape' or visType == 'shape':
                            chosenLayerType = 'shapes'
                        logging.debug(f'Will perform visualisation with layer type: {chosenLayerType}')
                    except Exception as e:
                        logging.error(f"Issue with finding visualisation type of a analysisnode: error: {e}")
                    
                    if chosenLayerType != None:
                        layerName = visual_connected_node.visualisation_currentData['layerName']
                        cmap = visual_connected_node.visualisation_currentData['colormap']

                        # T-F9: as in the scoring path above -- created on the
                        # GUI thread via the bridge, returned here because the
                        # node's visualise function is handed the layer.
                        napariLayer = _replace_visualisation_layer(
                            self.shared_data, chosenLayerType, layerName, cmap)
                        
                        #Phase 9.5: dispatch via registry instead of bare eval.
                        PerformVisualisation = registry.dispatch_from_eval_text(
                            visualEvalText,
                            scope={
                                **globals(),
                                **nodeDict,
                                'self': self,
                                'output': output,
                                'napariLayer': napariLayer,
                            },
                        )

                        visual_connected_node.status = 'finished'
                    else:
                        visual_connected_node.status = 'error'


        node.scoring_analysis_currentData['__output__'] = node.output
        
        #Store the output as NodzVariables
        utils.analysis_outputs_store_as_variableNodz(node)
        
        
        #Finish up
        self.finishedEmits(node)
    
    def CustomFunctionNode_started(self,node):
        """
        Perform the Custom Function set in a node
        
        Args:
            node: The node for which calls the analysis
        
        Returns:
            None
        """
        #Dictionary of nodes to pass around variables.
        nodeDict = utils.createNodeDictFromNodes(self.nodes)
        nodzInfo = node.flowChart
        
        #Figure out which function is selected in the customFunction node
        selectedFunction = utils.functionNameFromDisplayName(node.customFunction_currentData['__selectedDropdownEntryAnalysis__'],node.customFunction_currentData['__displayNameFunctionNameMap__'])
        #Figure out the belonging evaluation-text
        evalText = utils.getFunctionEvalTextFromCurrentData(selectedFunction,node.customFunction_currentData,'self.shared_data.core','',nodzInfo=self,skipp2=True)
        
        worker = generalNodzCallActionWorker(nodzType='CustomFunctionNode',args={"evalText":evalText, "nodeDict":nodeDict, "node":node, "core": self.core, "shared_data": self.shared_data})
        #Add the finished emit
        worker.signals.finished.connect(lambda: self.CustomFunctionNode_finished(node))
        #Star the worker
        self.thread_pool.start(worker)
        
        # #And evaluate the custom function with custom parameters
        # output = eval(evalText) #type:ignore
        
        # node.customFunction_currentData['__output__'] = output
        
        # #Store the output as NodzVariables
        # # utils.analysis_outputs_store_as_variableNodz(node)
        
        # #Finish up
        # self.finishedEmits(node)
    
    def CustomFunctionNode_finished(self,node):
        
        output = node.output
        node.customFunction_currentData['__output__'] = node.output
        
        #Store the output as NodzVariables #TODO
        utils.customFunction_outputs_store_as_variableNodz(node)
        
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
        
        for stor in node.MMconfigInfo.relstage_string_storage:
            if stor[0] == '__chosenRelStage__':
                stageToMove = stor[1]
        
        for stor in node.MMconfigInfo.relstage_string_storage:
            if stor[0] == stageToMove:
                distToMove = float(stor[1])
        
        self.core.set_relative_position(stageToMove,distToMove)
        
        self.finishedEmits(node)
        
    def MMconfigChangeRan(self,node):
        """
        Handle the configuration change event for a node.

        This function handles the configuration change event for a node, by
        changing the desired configs in the Core.

        Args:
            node (nodz.Node): The node that has triggered the event.
        """
        logging.debug('MMconfigChangeRan')
        
        
        #Create the worker
        worker = generalNodzCallActionWorker(nodzType='MMconfigChangeRan',args={"config_string_storage":node.MMconfigInfo.config_string_storage, "MMconfig":node.MMconfigInfo, "core": self.core})
        #Add the finished emit
        worker.signals.finished.connect(lambda: self.finishedEmits(node))
        #Star the worker
        self.thread_pool.start(worker)
        
        # self.finishedEmits(node)

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
            logging.debug('Starting the acquiring routine!')
            
            #Set all connected nodes to idle
            connectedNodes = nodz_utils.findConnectedToNode(self.evaluateGraph(),node.name,[])
            for connectedNode in connectedNodes:
                for nodeC in self.nodes:
                    if nodeC.name == connectedNode:
                        nodeC.status='idle'
            self.update()
                        
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
        #This finishedEmit needs to be at the start of this function :) 
        self.finishedEmits(node)
        logging.debug("End Acquiring----------------------------------------------------------")
        if self.fullRunOngoing:
            #if there are more positions to look at...
            if self.fullRunCurrentPos+1 < self.fullRunPositions['nrPositions']:
                logging.info(f'Just did position {self.fullRunCurrentPos+1}/{self.fullRunPositions["nrPositions"]}, continuing!--------------------------------------------------------')
                self.fullRunCurrentPos +=1
                #And start a new score/acq at a new pos:
                self.startNewScoreAcqAtPos()
            else:
                logging.info(f'ALLDONE Just did position {self.fullRunCurrentPos+1}/{self.fullRunPositions["nrPositions"]}, continuing!----------------------------------------------------------')
                self.singleRunOngoing = False
        else:
            logging.info("ACQUIRING FULL RUN IS NOT ONGOING--------------------------------------------")
        logging.debug("End Acquiring2------------------------------------------------------------")
        
    
    def initStart(self,node):
        """
        This function is the action function for the Initialisation Start node in the Flowchart.

        This function signals to the rest of the flowchart that it's time to start
        the init routine.

        Args:
            node (nodz.Node): The node that has triggered the event.

        Returns:
            None
        """
        logging.debug('Starting the initialisation routine!')
        
        #Set all connected nodes to idle
        connectedNodes = nodz_utils.findConnectedToNode(self.evaluateGraph(),node.name,[])
        for connectedNode in connectedNodes:
            for nodeC in self.nodes:
                if nodeC.name == connectedNode:
                    nodeC.status='idle'
        
        self.set_readable_text_after_dialogChange(node,'','initStart')
        
        self.GraphToSignals()
        #Effectively, only finishes the initStart node
        self.finishedEmits(node)
    
    def initEnd(self,node):
    
        logging.debug('Initialisation finished fully!')
        node.status = 'finished'
        #Find the acqStart node:
        scoringStartNode = None
        flowChart = self
        if len(flowChart.nodes) > 0:
            #Find the scoringEnd node in flowChart:
            for nodeF in flowChart.nodes:
                if 'scoringStart_' in nodeF.name:
                    scoringStartNode = nodeF
        
        #Run the scoring_start routine:
        if scoringStartNode is not None:
            if self.fullRunOngoing:
                logging.info('Starting full run routine!')
                self.startNewScoreAcqAtPos()
            else:
                logging.info('Starting single scoring only!')
                self.scoringStart(scoringStartNode)
        else:
            logging.error('Could not find scoringStartNode node in flowchart')
    
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
        
        if self.preventScoring == False:
            logging.debug('Starting the score routine!')
            
            #Set all connected nodes to idle
            connectedNodes = nodz_utils.findConnectedToNode(self.evaluateGraph(),node.name,[])
            for connectedNode in connectedNodes:
                for nodeC in self.nodes:
                    if nodeC.name == connectedNode:
                        nodeC.status='idle'
            
            #Get all connections:
            allConnections = []
            for connectedNode in connectedNodes:
                for nodeC in self.nodes:
                    if nodeC.name == connectedNode:
                        for attr in nodeC.sockets:
                            connections = nodeC.sockets[attr].connections
                            for connection in connections:
                                if connection not in allConnections:
                                    allConnections.append(connection)
                        for attr in nodeC.plugs:
                            connections = nodeC.plugs[attr].connections
                            for connection in connections:
                                if connection not in allConnections:
                                    allConnections.append(connection)
                        for attr in nodeC.topAttrs:
                            connections = nodeC.topAttrs[attr].connections
                            for connection in connections:
                                if connection not in allConnections:
                                    allConnections.append(connection)
                        for attr in nodeC.bottomAttrs:
                            connections = nodeC.bottomAttrs[attr].connections
                            for connection in connections:
                                if connection not in allConnections:
                                    allConnections.append(connection)
            
            for connection in allConnections:
                connection._pen.setColor(QColor(*self.config['connection_color']))
                connection.updatePath()
            
            self.set_readable_text_after_dialogChange(node,'','scoreStart')
            
            self.GraphToSignals()
            
            self.finishedEmits(node)
        else:
            logging.warning('Actively blocked scoring due to self.preventScoring!')
            
    def scoringEnd(self,node):
        """
        This function is the action function for the Scoring End node in the Flowchart.

        This function signals to the rest of the flowchart that the scoring routine is finished.

        Args:
            node (nodz.Node): The node that has triggered the event.

        Returns:
            None
        """
        self.finishedEmits(node)
        #Find the nodes that are connected downstream of this:
        try:
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
                        logging.debug(f"Data found for {attr}: {data[attr]}")
        except (KeyError, AttributeError, TypeError) as exc:
            logging.debug('Scoring data gather skipped: %s', exc)
        
        try:
            testPassed = self.decisionWidget.testCurrentDecision()
            testPassedText = 'Test is Passed' if testPassed else 'Test is Not Passed'
            # readableText = self.set_readable_text_after_dialogChange(node,[attrs,data,testPassedText],'scoreEnd')
            
            logging.info('Scoring finished fully!')
            if testPassed:
                logging.info("Test is... Passed!")
                
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
                logging.info("Test is... Not Passed!")
                #Go to next XY position
                if self.fullRunOngoing:
                    if self.fullRunCurrentPos+1 < self.fullRunPositions['nrPositions']:
                        self.fullRunCurrentPos +=1
                        #And start a new score/acq at a new pos:
                        self.startNewScoreAcqAtPos()
                    else:
                        self.singleRunOngoing = False
                        logging.info('All done!')
            logging.info('----------------------')

        except (AttributeError, KeyError, TypeError, ValueError) as exc:
            logging.error('Scoring decision evaluation failed: %s', exc)
            testPassed = False
            node.status = 'error'
            testPassedText = 'Error when assessing test'
            readableText = self.set_readable_text_after_dialogChange(node,[attrs,data,testPassedText],'scoreEnd')
        
        
        #Find the reporting node(s)
        connectedNodes = nodz_utils.getConnectedNodes(node, 'bottomAttr')
        for node in connectedNodes:
            logging.debug(node.name)
            if 'reporting_' in node.name:
                node.status = 'running'
                if self._slack_send_enabled():
                    slackReadableText = readableText
                    slackReadableText = slackReadableText.replace('<br>','\r\n')
                    slackReadableText = slackReadableText.replace('<i>','_')
                    slackReadableText = slackReadableText.replace('</i>','_')
                    slackReadableText = slackReadableText.replace('<b>','*')
                    slackReadableText = slackReadableText.replace('</b>','*')
                    slackReadableText = "New Score: \n" + slackReadableText
                    cfg = self.shared_data.config.webhook_config
                    from glados_pycromanager.errors import BackendError
                    from glados_pycromanager.notify.slack import send_slack_message
                    try:
                        send_slack_message(cfg, slackReadableText)
                        node.status = 'finished'
                    except BackendError as exc:
                        logging.warning('Slack reporting send failed: %s', exc)
                        node.status = 'error'
                else:
                    node.status = 'error'

        self.preventAcq = False
    
    def earlyScoringFail(self,node):
        #Sob asically it's the Scoring node, but hard-coded to fail.
        logging.info("Scoring early abandoned!")
        self.finishedEmits(node)
        node.status='finished'
        #Go to next XY position
        if self.fullRunOngoing:
            if self.fullRunCurrentPos+1 < self.fullRunPositions['nrPositions']:
                self.fullRunCurrentPos +=1
                #And start a new score/acq at a new pos:
                self.startNewScoreAcqAtPos()
            else:
                self.singleRunOngoing = False
                logging.info('All done!')
        
    
    def and_logicCallAction(self,node):
        """ 
        Runs when the and_logic gate is fully completed
        """
        #Honestly just needs to run the next nodes
        self.finishedEmits(node)
    
    def timerCallAction(self,node):
        """
        This function is the action function for the Timer Call node in the Flowchart.

        This function waits for a specified amount of time before triggering the next node in the flowchart.

        Args:
            node (nodz.Node): The node that has triggered the event.
        Returns:
            None
        """        
        #Get info
        vardata = utils.nodz_dataFromGeneralAdvancedLineEditDialog(node.timerInfo, node.flowChart)
        wait_time = float(vardata['wait_time'][0])

        #Create the worker
        worker = generalNodzCallActionWorker(nodzType='Timer',args={"wait_time":wait_time})
        #Add the finished emit
        worker.signals.finished.connect(lambda: self.finishedEmits(node))
        #Star the worker
        self.thread_pool.start(worker)
    
    def storeDataCallAction(self,node):
        
        """
        This function is the action function for the storeData Call node in the Flowchart.

        This function stores data.

        Args:
            node (nodz.Node): The node that has triggered the event.
        """
        
        #Extract Data
        varInfo = utils.nodz_dataFromGeneralAdvancedLineEditDialog(node.storeDataInfo,node.flowChart)
        
        #Get the store-data from a variable
        storeInfo = varInfo['item_to_store'][0]
        storeLoc = varInfo['store_location'][0]
        
        #Check if storeInfo is image-like:
        if isinstance(storeInfo, np.ndarray) and storeInfo.ndim > 1:
            #Check if we want to store a tiff
            if storeLoc[-4:] == '.tif' or storeLoc[-5:] == '.tiff':
                tifffile.imsave(storeLoc,storeInfo)
                logging.debug(f'Stored TIF image at {storeLoc}')
        
        self.finishedEmits(node)

    def changeGlobalVarCallAction(self,node):
        """
        The changeGlobalVarCallAction function is the action function for the change global var Call node in the Flowchart.
        
        Args:
            self: Refer to the class itself
            node: Identify which node triggered the event
        """
        varInfo = utils.nodz_dataFromGeneralAdvancedLineEditDialog(node.changeGlobalVarInfo,node.flowChart)
        
        variable = varInfo['globalVarName'][1]
        value = varInfo['globalVarValue'][0]
        
        utils.nodz_setVariableToValue(variable,value,node.flowChart)
        
        
        self.finishedEmits(node)
    
    def newGlobalVarCallAction(self,node):
        """
        The newGlobalVarCallAction function is the action function for the new global var Call node in the Flowchart.
        
        Args:
            self: Refer to the class itself
            node: Identify which node triggered the event
        """
        varInfo = utils.nodz_dataFromGeneralAdvancedLineEditDialog(node.newGlobalVarInfo,node.flowChart)
        
        variable = varInfo['globalVarName'][1]
        value = varInfo['globalVarValue'][0]
        
        #Create the new global Variable
        if variable  in node.flowChart.globalVariables:
            #If it's already present, give a warning for now, but still set it.
            logging.warning(f'New global variable {variable} defined with same name as already existing - overwriting it!')
            
        node.flowChart.globalVariables[variable] = {}
        node.flowChart.globalVariables[variable]['data'] = value
        #Try to find the type of the variable automatically, else just set it as str
        try:
            node.flowChart.globalVariables[variable]['type'] = [(type(eval(value)))]
        except (SyntaxError, NameError, ValueError, TypeError, AttributeError):
            #This will effectively set it as a string.
            node.flowChart.globalVariables[variable]['type'] = [(type(value))]
        node.flowChart.globalVariables[variable]['importance'] = 'informative'
        node.flowChart.globalVariables[variable]['lastUpdateTime'] = time.time()
        
        
        self.finishedEmits(node)
    
    def ifStatementCallAction(self,node):
        """
        The changeGlobalVarCallAction function is the action function for the change global var Call node in the Flowchart.
        
        Args:
            self: Refer to the class itself
            node: Identify which node triggered the event
        """
        
        varInfo = utils.nodz_dataFromGeneralAdvancedLineEditDialog(node.ifStatementInfo,node.flowChart)
        
        result = eval(str(varInfo['valueToCheck'][0])+varInfo['comparator'][0]+str(varInfo['valueCheckAgainst'][0]))
        
        if result == True:
            graph = node.flowChart.evaluateGraph()
            for graphConnection in graph:
                if graphConnection[0] == node.name+'.Succeed':
                    foundNodeName = graphConnection[1].split('.')[0]
                    foundNode = nodz_utils.findNodeByName(node.flowChart,foundNodeName)
                    node.status='finished'
                    foundNode.oneConnectionAtStartIsFinished()
                    break    
        elif result == False:
            graph = node.flowChart.evaluateGraph()
            for graphConnection in graph:
                if graphConnection[0] == node.name+'.Fail':
                    foundNodeName = graphConnection[1].split('.')[0]
                    foundNode = nodz_utils.findNodeByName(node.flowChart,foundNodeName)
                    node.status='finished'
                    foundNode.oneConnectionAtStartIsFinished()
                    break    
    
    def runInlineScriptCallAction(self,node):
        scriptText = node.InlineScriptInfo
        
        core = shared_data.core
        #Go over each line of scriptText, broken by a \n:
        lineData = scriptText.split('\n')
        errored=False
        for line in lineData:
            if errored:
                break
            try:
                eval(line)
                logging.debug(f'Ran commdand succesfully: {line}')
            except Exception as e:
                logging.error(f'Error with line {line}: {e}. Script broken off')
                errored=True
        
        if errored==False:
            logging.debug('Fully ran custom script!')
        
        self.finishedEmits(node)
    
    def runCaseSwitchCallAction(self,node):
        """ 
        Call action to runa  case/switch statement.
        """
        CurrentValueWantedVariable = utils.nodz_dataFromGeneralAdvancedLineEditDialog(node.caseSwitchInfo,node.flowChart)['Var'][0]
        
        
        #Alright so emitting the signals doesn't work because they're all connected.
        #So, idea is to evaluate the graph, find the correct linked node, and start that one from here.
        correctPlugFound = False
        graph = node.flowChart.evaluateGraph()
        for graphConnection in graph:
            if correctPlugFound == False and graphConnection[0] == node.name+'.'+str(CurrentValueWantedVariable):
                foundNodeName = graphConnection[1].split('.')[0]
                logging.debug(f"Node {node.name} found a case/switch with value {CurrentValueWantedVariable} connected to node {foundNodeName}")
                foundNode = nodz_utils.findNodeByName(node.flowChart,foundNodeName)
                foundNode.oneConnectionAtStartIsFinished()
                correctPlugFound = True
                node.status='finished'
                break
            
        #If none are found:
        if correctPlugFound == False:
            logging.warning('Case/Switch not found, using the Error')
            for graphConnection in graph:
                if graphConnection[0] == node.name+'.Error':
                    foundNodeName = graphConnection[1].split('.')[0]
                    foundNode = nodz_utils.findNodeByName(node.flowChart,foundNodeName)
                    foundNode.oneConnectionAtStartIsFinished()
                    node.status='finished'
    
    def runslackReportCallAction(self,node):
        """
        Call action to send a message to Slack
        """
        node.status='finished'
        try:
            readableText = utils.nodz_evaluateAdv(node.slackReportInfo,node.flowChart,skipEval=True)
            if readableText == None:
                readableText = node.slackReportInfo
            if self._slack_send_enabled():
                cfg = self.shared_data.config.webhook_config
                slackReadableText = readableText
                if not ("<img>" in node.slackReportInfo and "</img>" in node.slackReportInfo):
                    slackReadableText = slackReadableText.replace('<br>','\r\n')
                    slackReadableText = slackReadableText.replace('<i>','_')
                    slackReadableText = slackReadableText.replace('</i>','_')
                    slackReadableText = slackReadableText.replace('<b>','*')
                    slackReadableText = slackReadableText.replace('</b>','*')
                    from glados_pycromanager.notify.slack import send_slack_message
                    send_slack_message(cfg, slackReadableText)
                else: #we have an image!
                    #Extract the text between img tags:
                    imgInfo = re.findall('<img>(.*?)</img>',node.slackReportInfo)[0]
                    restText = re.sub('<img>(.*?)</img>','',node.slackReportInfo)
                    restText = restText.replace('<br>','\r\n')
                    restText = restText.replace('<i>','_')
                    restText = restText.replace('</i>','_')
                    restText = restText.replace('<b>','*')
                    restText = restText.replace('</b>','*')

                    #remove the curly brackets in imgInfo:
                    imgInfo = imgInfo.replace('{','')
                    imgInfo = imgInfo.replace('}','')

                    #Get the image
                    im = utils.nodz_evaluateVar(imgInfo,node.flowChart)
                    # Convert the ndarray to a PIL Image
                    image = Image.fromarray(im/65535*255)# Or convert to RGB
                    image = image.convert("RGB")

                    #Store the im as a PNG in a temporary folder:
                    tempDir = tempfile.TemporaryDirectory()
                    tempFile = os.path.join(tempDir.name,'slackImage.png')

                    # Save the image as a PNG file
                    image.save(tempFile, "PNG")
                    #Send the message with the read-tempFile
                    slack_image = cfg.slack_client.files_upload(
                        title="Glados Image",
                        channels=cfg.slack_channel,
                        content=open(tempFile, 'rb').read(),
                        initial_comment = restText,
                    )
        except Exception as e:  # noqa: BLE001 — wide net for any Slack/image error
            logging.warning('Slack report failed: %s', e)

        self.finishedEmits(node)

    def fullAutonomousRunStart(self):
        """
        Starts a full autonomous run - i.e. scoring and acquisition
        
        Args:
            self: The object instance.
        
        Returns:
            None
        """
        logging.info('Starting a full run')
        self.preventAcq = False
        self.preventScoring = False
        
        #General idea: first check if there are no glaring errors (scoring, position)
        #then go to whatever start position based on the xy positions
        #then run scoring+acquisition there
        
            
        
        self.fullRunOngoing = True
        self.fullRunCurrentPos = 0
        self.fullRunPositions = self.scanningWidget.getPositionInfo()
        # self.startNewScoreAcqAtPos()
        
        #Find the init_start node:
        initStartNode = None
        flowChart = self
        if len(flowChart.nodes) > 0:
            #Find the scoringEnd node in flowChart:
            for node in flowChart.nodes:
                if 'initStart_' in node.name:
                    initStartNode = node
        
        #Run the init_start routine:
        if initStartNode is not None:
            self.initStart(initStartNode)
        else:
            logging.error('Could not find initStart node in flowchart')

    def startNewScoreAcqAtPos(self):
        """
        Starts a new score acquisition at the current microscope position.
        
        Args:
            None
        
        Returns:
            None
        """
        
        positions = self.fullRunPositions
        pos = self.fullRunCurrentPos
        
        self.shared_data.warningErrorInfoInfo['Info']['Other'] = [f"Autonomous run is ongoing! Currently at pos {str(pos+1)}/{str(positions['nrPositions'])}  ({str(round(pos/positions['nrPositions']*100,2))}%)"]
        
        logging.info(f'Starting new score acq at position {pos} -------------------------------------------------------------------------------')
        
        #Set all stages correct
        for stage in positions[pos]['STAGES']:
            if stage != '':
                stagepos = positions[pos][stage]
                #Check if this stage is an XY stage device...
                #Since then we need to do something 2-dimensional
                if stage in self.getDevicesOfDeviceType('XYStageDevice'):
                    logging.debug(f'Moving stage {stage} to position {stagepos}')
                    self.shared_data.core.set_xy_position(stage,stagepos[0],stagepos[1]) #type:ignore
                    self.shared_data.core.wait_for_system() #type:ignore
                else:#else we can move a 1d stage:
                    logging.debug(f'Moving stage {stage} to position {stagepos}')
                    self.shared_data.core.set_position(stage,stagepos[0]) #type:ignore
                    self.shared_data.core.wait_for_system() #type:ignore
        
        self.runScoring()
    
    def runInitOnly(self):
        """
        Run ONLY the init process at the current position. Actively prevents scoring
        
        Args:
            None
        
        Returns:
            None
        """
        self.preventScoring = True
        self.preventAcq = False
        
        #Find the scoring_start node:
        initStartNode = None
        flowChart = self
        if len(flowChart.nodes) > 0:
            #Find the scoringEnd node in flowChart:
            for node in flowChart.nodes:
                if 'initStart_' in node.name:
                    initStartNode = node
        
        #Run the scoring_start routine:
        if initStartNode is not None:
            self.initStart(initStartNode)
        else:
            logging.error('Could not find initStart node in flowchart')
            
    
    def runScoringOnly(self):
        """
        Run ONLY the scoring process at the current position. Actively prevents acquisition
        
        Args:
            None
        
        Returns:
            None
        """
        self.preventAcq = True
        self.preventScoring = False
        
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
        self.preventScoring = False
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
        logging.info("Run Acquiring")
        
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
    
    def interruptRun(self):
        """
        Interrupt the run - stop the scoring/init/acq and stop ongoing acquisitions.
        """

        #Trying this for now:
        self.shared_data._mdaModeAcqData.abort()

        return

    def _slack_send_enabled(self):
        """Return True if Slack credentials look set up; log + return False otherwise.

        Centralizes the empty-token guard for every Slack-send call site so
        an unconfigured install no-ops with a single info log instead of
        triggering an AttributeError or an opaque Slack-side rejection.
        """
        cfg = getattr(self.shared_data.config, "webhook_config", None)
        if cfg is None:
            logging.info("Slack send skipped: webhook_config is not configured")
            return False
        token = (getattr(cfg, "slack_token", "") or "").strip()
        if not token:
            logging.info("Slack send skipped: no Slack token configured (set via 'Slack settings…')")
            return False
        if getattr(cfg, "slack_client", None) is None:
            logging.info("Slack send skipped: slack_client not initialised")
            return False
        return True

    def openSlackSettingsDialog(self):
        """Open the Slack settings dialog and persist on accept.

        Replaces the previously hard-coded WebhookConfig defaults — the
        user enters token/secret/channel at runtime; values are written
        back onto shared_data and persisted via the standard AppData JSON.
        """
        cfg = self.shared_data.config.webhook_config
        dialog = SlackSettingsDialog(
            parent=self.parent if self.parent is not None else None,
            token=cfg.slack_token or "",
            secret=cfg.slack_secret or "",
            channel=cfg.slack_channel or "",
        )
        if dialog.exec_() == QDialog.Accepted:
            token, secret, channel = dialog.values
            _apply_slack_settings(self.shared_data, token, secret, channel)
            utils.storeSharedData_GlobalData(self.shared_data)
    
    def debugScoring(self):
        """
        Function to get some debug information from the scoring function(s)
        """
        logging.debug("Debug Scoring")
        scoreGraph = self.prepareGraph(methodName = "Score")
        
        
        logging.debug(self)
        logging.debug(self.evaluateGraph())
