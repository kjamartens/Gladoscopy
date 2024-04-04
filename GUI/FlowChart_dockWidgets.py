#Add inclusion of this folder:
import sys, os
sys.path.append('C:\\Users\\SMIPC2\\Documents\\GitHub\\ScopeGUI\\GUI\\nodz')
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

class AdvancedInputDialog(QDialog):
    def __init__(self, parent=None, parentData=None):
        super().__init__(parent)
        
        self.setWindowTitle("Advanced Input Dialog")
        
        # Create line edit
        self.line_edit = QLineEdit()
        
        # Create combobox
        self.combo_box = QComboBox()
        self.combo_box.addItems(["Option 1", "Option 2", "Option 3"])
        
        # Create button box
        button_box = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        button_box.accepted.connect(self.accept)
        button_box.rejected.connect(self.reject)
        
        # Create layout
        layout = QVBoxLayout()
        layout.addWidget(self.line_edit)
        layout.addWidget(self.combo_box)
        layout.addWidget(button_box)
        
        self.setLayout(layout)
        
    def getInputs(self):
        return self.line_edit.text(), self.combo_box.currentText()

class nodz_openMDADialog(QDialog):
    def __init__(self, parent=None, parentData=None):
        super().__init__(parent)
        
        self.setWindowTitle("MDA Dialog")
        if parentData is not None:
            from PyQt5.QtWidgets import QApplication, QVBoxLayout, QMainWindow, QWidget
            testQWidget = QWidget()
            
            self.mdaconfig = MDAGlados(parentData.core,None,None,parentData.shared_data,hasGUI=True)
            
            button_box = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
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

class FoVFindImaging_singleCh_configs(QDialog):
    def __init__(self, parent=None, parentData=None):
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
        super().resizeEvent(event)
        self.updateGraphicsViewSize()
    
    def updateGraphicsViewSize(self):
        nodz.setFixedSize(self.viewport().size())

class GladosGraph():
    #Also adds these values correctly for each node:
        # self.n_connect_at_start = 0 #number of others connected at start (which should all be finished!)
        # self.connectedToFinish = []
        # self.connectedToData = []
        
    def __init__(self,parent):
        self.parent = parent
        self.nodes = []
        self.startNodeIndex = -1
        # self.unstartedNodes = []
        # self.ongoingNodes = []
        # self.finishedNodes = []


        
    def addRawGraphEval(self,graphEval):
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
        QObject.__init__(self)
        super().__init__()
        self.signals = []

    def add_signal(self, signal_name):
        # Dynamically add a new signal to the object
        setattr(self, signal_name, self.new_signal)
        self.signals.append(self.new_signal)

    def print_signals(self):
        for signal in self.signals:
            print(signal)

    def emit_all_signals(self):
        for signal in self.signals:
            signal.emit()
            logging.debug(f"emitting signal {signal}")

class flowChart_dockWidgetF(nodz_main.Nodz):
    def __init__(self,core=None,shared_data=None,MM_JSON=None):
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
        self.saveGraph('Testgraph.json')
    
    def loadPickle(self):
        import pickle, copy
        self.loadGraph_KM('Testgraph.json')
    
    def nodeLookupName_withoutCounter(self,nodeName):
        
        
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
        
        sourceNode = self.findNodeByName(srcNodeName)
        if plugAttribute in self.nodeInfo[self.nodeLookupName_withoutCounter(srcNodeName)]['finishedAttributes']: 
            destinationNode = self.findNodeByName(dstNodeName)
            #The destination node needs one extra to be started...
            destinationNode.n_connect_at_start += 1 #type: ignore
            
            #And the finished event of the source node is connected to the 'we finished one of the prerequisites' at the destination node
            sourceNode.customFinishedEmits.signals[0].connect(destinationNode.oneConnectionAtStartIsFinished) #type: ignore
            # sourceNode.customFinishedEmits.signals[0].connect(lambda: destinationNode.oneConnectionAtStartIsFinished) #type: ignore
        logging.debug(f"plug/socket connected end: {srcNodeName}, {plugAttribute}, {dstNodeName}, {socketAttribute}")
        
    def PlugOrSocketDisconnected(self,srcNodeName, plugAttribute, dstNodeName, socketAttribute):
        
        sourceNode = self.findNodeByName(srcNodeName)
        if plugAttribute in self.nodeInfo[self.nodeLookupName_withoutCounter(srcNodeName)]['finishedAttributes']:
            signal = sourceNode.customFinishedEmits.signals[0] #type: ignore
            try:
                signal.disconnect()
            except:
                print('attempted to disconnect a disconnected signal')
        
        destinationNode = self.findNodeByName(dstNodeName)
        destinationNode.n_connect_at_start -= 1 #type:ignore
                
        logging.debug(f"plug/socket disconnected: {srcNodeName}, {plugAttribute}, {dstNodeName}, {socketAttribute}")
        
    def PlugConnected(self,srcNodeName, plugAttribute, dstNodeName, socketAttribute):
        #Check if all are non-Nones:
        if any([srcNodeName is None, plugAttribute is None, dstNodeName is None, socketAttribute is None]):
            return
        else:
            self.PlugOrSocketConnected(srcNodeName, plugAttribute, dstNodeName, socketAttribute)
            
    def SocketConnected(self,srcNodeName, plugAttribute, dstNodeName, socketAttribute):
        #Check if all are non-Nones:
        if any([srcNodeName is None, plugAttribute is None, dstNodeName is None, socketAttribute is None]):
            return
        else:
            self.PlugOrSocketConnected(srcNodeName, plugAttribute, dstNodeName, socketAttribute)
    
    def NodeRemoved(self,nodeNames):
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
        logging.info('one or more nodes are created!')
        nodeType = self.nodeLookupName_withoutCounter(node.name)
        self.performPostNodeCreation_Start(node,nodeType)
    
    def NodeDoubleClicked(self,nodeName):
        currentNode = self.findNodeByName(nodeName)
        if 'acquisition' in nodeName:
            dialog = nodz_openMDADialog(parentData=self)
            if dialog.exec_() == QDialog.Accepted:
                logging.debug(f"MDA dialog input: {dialog.getInputs()}")
            
            # currentNode.mdaData.exposure_ms = dialog.getExposureTime()
            # currentNode.mdaData.mda = dialog.getInputs()#type:ignore
            dialogmdaData = dialog.getmdaData()
            attrs_to_not_copy = ['gui','core','shared_data','has_GUI','data','staticMetaObject','MDA_completed','MM_JSON']
            #Loop over all attributes in dialogmdaData:
            for attrs in vars(dialogmdaData):
                if attrs not in attrs_to_not_copy:
                    setattr(currentNode.mdaData,attrs,getattr(dialogmdaData,attrs))
            
            currentNode.displayText = str(dialog.getInputs())#type:ignore
            currentNode.update() #type:ignore
        
        if 'timer' in nodeName:
            currentNode.callAction(self) #type:ignore
    
        if 'scoringStart' in nodeName:
            currentNode.callAction(self) #type:ignore
    
    def defineNodeInfo(self):
        self.nodeInfo = {}
        
        #We define the node info for each type of node like this: (might be expanded in the future)
        self.nodeInfo['acquisition'] = {}
        self.nodeInfo['acquisition']['name'] = 'acquisition'
        self.nodeInfo['acquisition']['displayName'] = 'Acquisition'
        self.nodeInfo['acquisition']['startAttributes'] = ['Acquisition start']
        self.nodeInfo['acquisition']['finishedAttributes'] = ['Finished']
        self.nodeInfo['acquisition']['dataAttributes'] = []
        self.nodeInfo['acquisition']['NodeCounter'] = 0
        self.nodeInfo['acquisition']['MaxNodeCounter'] = np.inf
        
        self.nodeInfo['analysisGrayScaleTest'] = {}
        self.nodeInfo['analysisGrayScaleTest']['name'] = 'analysisGrayScaleTest'
        self.nodeInfo['analysisGrayScaleTest']['displayName'] = 'Analysis Grayscale Test [Measurement]'
        self.nodeInfo['analysisGrayScaleTest']['startAttributes'] = ['Analysis start']
        self.nodeInfo['analysisGrayScaleTest']['finishedAttributes'] = ['Finished']
        self.nodeInfo['analysisGrayScaleTest']['dataAttributes'] = ['Output']
        self.nodeInfo['analysisGrayScaleTest']['NodeCounter'] = 0
        self.nodeInfo['analysisGrayScaleTest']['MaxNodeCounter'] = np.inf
        
        self.nodeInfo['analysisMeasurement'] = {}
        self.nodeInfo['analysisMeasurement']['name'] = 'analysisMeasurement'
        self.nodeInfo['analysisMeasurement']['displayName'] = 'Analysis [Measurement]'
        self.nodeInfo['analysisMeasurement']['startAttributes'] = ['Analysis start']
        self.nodeInfo['analysisMeasurement']['finishedAttributes'] = ['Finished']
        self.nodeInfo['analysisMeasurement']['dataAttributes'] = ['Output']
        self.nodeInfo['analysisMeasurement']['NodeCounter'] = 0
        self.nodeInfo['analysisMeasurement']['MaxNodeCounter'] = np.inf
        
        self.nodeInfo['analysisShapes'] = {}
        self.nodeInfo['analysisShapes']['name'] = 'analysisShapes'
        self.nodeInfo['analysisShapes']['displayName'] = 'Analysis [Shapes]'
        self.nodeInfo['analysisShapes']['startAttributes'] = ['Analysis start']
        self.nodeInfo['analysisShapes']['finishedAttributes'] = ['Finished']
        self.nodeInfo['analysisShapes']['dataAttributes'] = ['Output']
        self.nodeInfo['analysisShapes']['NodeCounter'] = 0
        self.nodeInfo['analysisShapes']['MaxNodeCounter'] = np.inf
        
        self.nodeInfo['analysisImages'] = {}
        self.nodeInfo['analysisImages']['name'] = 'analysisImages'
        self.nodeInfo['analysisImages']['displayName'] = 'Analysis [Images]'
        self.nodeInfo['analysisImages']['startAttributes'] = ['Analysis start']
        self.nodeInfo['analysisImages']['finishedAttributes'] = ['Finished']
        self.nodeInfo['analysisImages']['dataAttributes'] = ['Output']
        self.nodeInfo['analysisImages']['NodeCounter'] = 0
        self.nodeInfo['analysisImages']['MaxNodeCounter'] = np.inf
        
        self.nodeInfo['scoringStart'] = {}
        self.nodeInfo['scoringStart']['name'] = 'scoringStart'
        self.nodeInfo['scoringStart']['displayName'] = 'Scoring start'
        self.nodeInfo['scoringStart']['startAttributes'] = []
        self.nodeInfo['scoringStart']['finishedAttributes'] = ['Start']
        self.nodeInfo['scoringStart']['dataAttributes'] = []
        self.nodeInfo['scoringStart']['NodeCounter'] = 0
        self.nodeInfo['scoringStart']['MaxNodeCounter'] = 1
        
        self.nodeInfo['scoringEnd'] = {}
        self.nodeInfo['scoringEnd']['name'] = 'scoringEnd'
        self.nodeInfo['scoringEnd']['displayName'] = 'Scoring end'
        self.nodeInfo['scoringEnd']['startAttributes'] = ['End']
        self.nodeInfo['scoringEnd']['finishedAttributes'] = []
        self.nodeInfo['scoringEnd']['dataAttributes'] = []
        self.nodeInfo['scoringEnd']['NodeCounter'] = 0
        self.nodeInfo['scoringEnd']['MaxNodeCounter'] = 1
        
        self.nodeInfo['onesectimer'] = {}
        self.nodeInfo['onesectimer']['name'] = '1s timer'
        self.nodeInfo['onesectimer']['displayName'] = '1s timer'
        self.nodeInfo['onesectimer']['startAttributes'] = ['Start']
        self.nodeInfo['onesectimer']['finishedAttributes'] = ['Finished']
        self.nodeInfo['onesectimer']['dataAttributes'] = []
        self.nodeInfo['onesectimer']['NodeCounter'] = 0
        self.nodeInfo['onesectimer']['MaxNodeCounter'] = np.inf
        self.nodeInfo['twosectimer'] = {}
        self.nodeInfo['twosectimer']['name'] = '2s timer'
        self.nodeInfo['twosectimer']['displayName'] = '2s timer'
        self.nodeInfo['twosectimer']['startAttributes'] = ['Start']
        self.nodeInfo['twosectimer']['finishedAttributes'] = ['Finished']
        self.nodeInfo['twosectimer']['dataAttributes'] = []
        self.nodeInfo['twosectimer']['NodeCounter'] = 0
        self.nodeInfo['twosectimer']['MaxNodeCounter'] = np.inf
        self.nodeInfo['threesectimer'] = {}
        self.nodeInfo['threesectimer']['name'] = '3s timer'
        self.nodeInfo['threesectimer']['displayName'] = '3s timer'
        self.nodeInfo['threesectimer']['startAttributes'] = ['Start']
        self.nodeInfo['threesectimer']['finishedAttributes'] = ['Finished']
        self.nodeInfo['threesectimer']['dataAttributes'] = []
        self.nodeInfo['threesectimer']['NodeCounter'] = 0
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
    
    def prepareGraph(self, methodName='Score'):
        graphEval = self.evaluateGraph()
        if methodName == 'Score':
            scoreGraph = GladosGraph(self)
            scoreGraph.addRawGraphEval(graphEval)
            for node in scoreGraph.nodes:
                self.giveInfoOnNode(node)
            return scoreGraph

    def findNodeByName(self, name):
        for node in self.nodes:
            #check if the attribute 'name' is found:
            if hasattr(node, 'name'):
                if node.name == name:
                    return node
        return None
    
    #replace the contextMenuEvent in nodz with this custom function:
    def contextMenuEvent(self, QMouseevent):
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
        if self.nodeInfo[nodeType]['NodeCounter'] >= self.nodeInfo[nodeType]['MaxNodeCounter']:
            print('Not allowed! Maximum number of nodes of this type reached')
            return
        
        #Create the new node with correct name and preset
        newNode = self.createNode(name=nodeType+"_", preset = 'node_preset_1', position=self.mapToScene(event.pos()),displayName = self.nodeInfo[nodeType]['displayName'])
        
        #Do post-node-creation functions - does this via the pyqtsignal!
    
    def performPostNodeCreation_Start(self,newNode,nodeType):
        newNodeName = self.nodeInfo[nodeType]['name']+"_"+str(self.nodeInfo[nodeType]['NodeCounter'])
        #Increase the nodeCounter
        self.nodeInfo[nodeType]['NodeCounter']+=1
        
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
        elif nodeType == 'analysisGrayScaleTest':
            newNode.callAction = lambda self, node=newNode: self.GrayScaleTest(node)
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
        else:
            newNode.callAction = None

        newNode.update()
    
    def GrayScaleTest(self,node):
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
        node.customFinishedEmits.emit_all_signals()

    def scoringStart(self,node):
        print('Starting the score routine!')
        self.finishedEmits(node)

    def timerCallAction(self,node,timev):
        import time
        print('start time sleeping')
        time.sleep(timev)
        print('end time sleeping')
        self.finishedEmits(node)

    def createNodeFromRightClick(self,event,nodeType=None):
        # if nodeType == 'acquisition':
        self.createNewNode(nodeType,event)

    def giveInfoOnNode(self,node):
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
    global shared_data, napariViewer
    shared_data = sshared_data
    napariViewer = shared_data.napariViewer
    
    #Create the a flowchart testing
    flowChart_dockWidget = flowChart_dockWidgetF(core=core,shared_data=shared_data,MM_JSON=MM_JSON)
    main_layout.addLayout(flowChart_dockWidget.mainLayout,0,0)
    
    flowChart_dockWidget.getNodz()
    
    return flowChart_dockWidget