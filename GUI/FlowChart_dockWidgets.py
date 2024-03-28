from PyQt5 import QtCore, QtWidgets
#Add inclusion of this folder:
import sys, os
sys.path.append('C:\\Users\\SMIPC2\\Documents\\GitHub\\ScopeGUI\\GUI\\nodz')
import nodz_main #type: ignore
from PyQt5.QtWidgets import QApplication, QGraphicsScene, QMainWindow, QGraphicsView, QPushButton, QVBoxLayout, QWidget, QTabWidget, QMenu, QAction
from PyQt5.QtCore import Qt, QSize
from PyQt5 import QtGui
from PyQt5.QtWidgets import QGridLayout, QPushButton
from PyQt5.QtWidgets import QLineEdit, QInputDialog, QDialog, QLineEdit, QComboBox, QVBoxLayout, QDialogButtonBox, QMenu, QAction
from PyQt5.QtGui import QFont, QColor, QTextDocument, QAbstractTextDocumentLayout
from PyQt5.QtCore import QRectF

class CustomGraphicsView(QtWidgets.QGraphicsView):
    def resizeEvent(self, event):
        super().resizeEvent(event)
        self.updateGraphicsViewSize()
    
    def updateGraphicsViewSize(self):
        nodz.setFixedSize(self.viewport().size())

class flowChart_dockWidgetF(nodz_main.Nodz):
    def __init__(self,core=None,shared_data=None,MM_JSON=None):
        #Create a Vertical+horizontal layout:
        self.mainLayout = QGridLayout()
        
        # Create a QGraphicsView
        # scene = QGraphicsScene()
        self.graphics_view = CustomGraphicsView()
        
        super(flowChart_dockWidgetF, self).__init__(parent=self.graphics_view)
        
        # self.graphics_view.setScene(scene)
        # Add the QGraphicsView to the mainLayout
        self.mainLayout.addWidget(self.graphics_view)
        
        # self.nodz = super(flowChart_dockWidgetF, self).__init__(parent=self.graphics_view,core=core,shared_data=shared_data,MM_JSON=MM_JSON)
        
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
                
        # Set the size policy for self.graphics_view
        # self.graphics_view.setSizePolicy(QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Expanding)


        self.nodes = []
        
        self.nodeCounter={}
        self.nodeCounter['acquisition'] = 0
        self.nodeCounter['analysis'] = 0
        self.nodeCounter['scoring'] = 0
        self.nodeCounter['decision'] = 0
        
        #Initialise with a few dummy nodes
        # Node A
        self.nodes.append(self.createNode(name='nodeA', preset='node_preset_1', position=QtCore.QPoint(5010,5010)))

        self.createAttribute(node=self.findNodeByName('nodeA'),name='Aattr1', index=-1, preset='attr_preset_1',
                            plug=True, socket=False, dataType=int)
        self.createAttribute(node=self.findNodeByName('nodeA'), name='Aattr2', index=-1, preset='attr_preset_1',
                            plug=False, socket=True, dataType=int)

        # Node B
        self.nodes.append(self.createNode(name='nodeB', preset='node_imaging',position=QtCore.QPoint(5070,5010)))

        self.createAttribute(node=self.findNodeByName('nodeB'), name='Battr1', index=-1, preset='attr_preset_1',
                            plug=True, socket=False, dataType=int)

        self.createAttribute(node=self.findNodeByName('nodeB'), name='Battr2', index=-1, preset='attr_preset_1',
                            plug=True, socket=False, dataType=int)
        
        #Focus on the nodes
        self._focus()
    
    def findNodeByName(self, name):
        for node in self.nodes:
            if node.name == name:
                return node
        return None
    
    #replace the contextMenuEvent in nodz with this custom function:
    def contextMenuEvent(self, QMouseevent):
        context_menu = QMenu(self)
        
        sub_menu_startstop = QMenu("Start/stop", self)

        new_acq_node_action = QAction("New MDA/Acquisition node", self)
        new_analysis_node_action = QAction("New Analysis node", self)
        new_scoring_node_action = QAction("New Scoring node", self)
        new_decision_node_action = QAction("New Decision node", self)
        
        new_start_node_action = QAction("Start node", self)
        new_stop_node_action = QAction("Stop node", self)

        context_menu.addMenu(sub_menu_startstop)
        context_menu.addAction(new_acq_node_action)
        context_menu.addAction(new_analysis_node_action)
        context_menu.addAction(new_scoring_node_action)
        context_menu.addAction(new_decision_node_action)
        
        sub_menu_startstop.addAction(new_start_node_action)
        sub_menu_startstop.addAction(new_stop_node_action)
        
        new_acq_node_action.triggered.connect(lambda _, event=QMouseevent: self.createNodeFromRightClick(event,nodeType='acquisition'))
        new_analysis_node_action.triggered.connect(lambda _, event=QMouseevent:  self.createNodeFromRightClick(event,nodeType='analysis'))
        new_scoring_node_action.triggered.connect(lambda _, event=QMouseevent:  self.createNodeFromRightClick(event,nodeType='scoring'))
        new_decision_node_action.triggered.connect(lambda _, event=QMouseevent:  self.createNodeFromRightClick(event,nodeType='decision'))
        
        new_start_node_action.triggered.connect(lambda _, event=QMouseevent:  self.createStartStopNodeFromRightClick(event,nodeType='start'))
        new_stop_node_action.triggered.connect(lambda _, event=QMouseevent:  self.createStartStopNodeFromRightClick(event,nodeType='stop'))

        # Show the context menu at the event's position
        # context_menu.exec_(self.mapToScene(QMouseevent.pos()))
        context_menu.exec_(QMouseevent.globalPos())

    def createStartStopNodeFromRightClick(self,event,nodeType='start'):
        if nodeType == 'start':
            name="Start"
            #Create the node
            self.nodes.append(self.createNode(name=name, preset='start_node', position=self.mapToScene(event.pos())))
            #Only add a start attribute
            self.createAttribute(node=self.findNodeByName(name), name='Start', index=-1, preset='attr_preset_1',
                            plug=True, socket=False,dataType=bool)
        elif nodeType == 'stop':
            name="Stop"
            #Create the node
            self.nodes.append(self.createNode(name=name, preset='stop_node', position=self.mapToScene(event.pos())))
            #Only add a start attribute
            self.createAttribute(node=self.findNodeByName(name), name='Stop', index=-1, preset='attr_preset_1',
                            plug=False, socket=True,dataType=bool)

    def createNodeFromRightClick(self,event,nodeType=None):
        #Find all nodes that have (partial) name with nodeType:
        name = str(nodeType)+"_"+str(self.nodeCounter[nodeType])
        self.nodeCounter[nodeType]+=1
        
        #Create the node
        self.nodes.append(self.createNode(name=name, preset=nodeType, position=self.mapToScene(event.pos())))
        
        #Add attribute, dummy for now:
        if nodeType == 'acquisition':
            self.createAttribute(node=self.findNodeByName(name), name='Acq start', index=-1, preset='attr_preset_1',
                            plug=False, socket=True,dataType=bool)
            self.createAttribute(node=self.findNodeByName(name), name='Data', index=-1, preset='attr_preset_1',
                            plug=True, socket=False)
            self.createAttribute(node=self.findNodeByName(name), name='Finished', index=-1, preset='attr_preset_1',
                            plug=True, socket=False,dataType=bool)
        else:
            self.createAttribute(node=self.findNodeByName(name), name='dummy1', index=-1, preset='attr_preset_1',
                            plug=True, socket=False, dataType=int)
            self.createAttribute(node=self.findNodeByName(name), name='dummy2', index=-1, preset='attr_preset_1',
                            plug=False, socket=True, dataType=int)
            

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