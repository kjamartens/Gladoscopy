from PyQt5 import QtCore, QtWidgets
#Add inclusion of this folder:
import sys, os
sys.path.append('Testing/Nodz-master')
import nodz_main
from PyQt5.QtWidgets import QApplication, QGraphicsScene, QMainWindow, QGraphicsView, QPushButton, QVBoxLayout, QWidget, QTabWidget
from PyQt5.QtCore import Qt, QSize

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()

        # Create a central widget and set a vertical layout
        self.central_widget = QWidget()
        self.layout = QVBoxLayout(self.central_widget)
        self.setCentralWidget(self.central_widget)

        # Create a QTabWidget
        self.tab_widget = QTabWidget()
        self.layout.addWidget(self.tab_widget)

        # Create a QWidget to hold the QGraphicsView
        self.graphics_view_tab = QWidget()

        # Create a QVBoxLayout to hold the QGraphicsView within the QWidget
        self.graphics_view_layout = QVBoxLayout(self.graphics_view_tab)

        # Create a QGraphicsView
        scene = QGraphicsScene()
        self.graphics_view = QtWidgets.QGraphicsView(scene)
        # self.graphics_view.setAlignment(Qt.AlignCenter)

        # Add the QGraphicsView to the QVBoxLayout
        self.graphics_view_layout.addWidget(self.graphics_view)

        # Add the QWidget with the QGraphicsView to the QTabWidget
        self.tab_widget.addTab(self.graphics_view_tab, 'Graphics View')

        # Create a QPushButton
        self.buttonGetConnections = QPushButton("Connections")
        self.layout.addWidget(self.buttonGetConnections)
        # Connect the clicked signal of the button to your callback function
        self.buttonGetConnections.clicked.connect(self.getConnections)

        # Create a QPushButton
        self.buttonSave = QPushButton("Save")
        self.layout.addWidget(self.buttonSave)
        # Connect the clicked signal of the button to your callback function
        self.buttonSave.clicked.connect(self.storeInfo)

        # Create a QPushButton
        self.buttonLoad = QPushButton("Load")
        self.layout.addWidget(self.buttonLoad)
        # Connect the clicked signal of the button to your callback function
        self.buttonLoad.clicked.connect(self.loadInfo)
 
        self.last_size = QSize()
        self.updateGraphicsViewAspectRatio()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if event.size() != self.last_size:
            self.last_size = event.size()
            self.updateGraphicsViewAspectRatio()

    def updateGraphicsViewAspectRatio(self):
        try:
            nodz.setFixedSize(QSize(self.graphics_view.width(),self.graphics_view.height()))
        except:
            pass

    # Define your callback function
    def getConnections(self):
        print( nodz.evaluateGraph())

    def storeInfo(self):
        nodz.saveGraph(filePath='Testing'+os.sep+'GraphStore.json')
        
    def loadInfo(self):
        nodz.clearGraph()
        nodz.loadGraph(filePath='Testing'+os.sep+'GraphStore.json')

app = QApplication(sys.argv)
window = MainWindow()
window.show()
# sys.exit(app.exec_())

# try:
# app = QtWidgets.QApplication([])
# except:
#     # I guess we're running somewhere that already has a QApp created
#     app = None
global nodz
nodz = nodz_main.Nodz(window.graphics_view)
# nodz = nodz_main.Nodz(None)
# nodz.loadConfig(filePath='')
nodz.initialize()
nodz.show()
#Needs this as init
window.updateGraphicsViewAspectRatio()


######################################################################
# Test signals
######################################################################

# Nodes
@QtCore.pyqtSlot(str)
def on_nodeCreated(nodeName):
    print('node created : ', nodeName)

@QtCore.pyqtSlot(str)
def on_nodeDeleted(nodeName):
    print('node deleted : ', nodeName)

@QtCore.pyqtSlot(str, str)
def on_nodeEdited(nodeName, newName):
    print('node edited : {0}, new name : {1}'.format(nodeName, newName))

@QtCore.pyqtSlot(str)
def on_nodeSelected(nodesName):
    print('node selected : ', nodesName)

@QtCore.pyqtSlot(str, object)
def on_nodeMoved(nodeName, nodePos):
    print('node {0} moved to {1}'.format(nodeName, nodePos))

@QtCore.pyqtSlot(str)
def on_nodeDoubleClick(nodeName,nodepos):
    print('double click on node : {0} at pos {1}'.format(nodeName,nodepos))

# Attrs
@QtCore.pyqtSlot(str, int)
def on_attrCreated(nodeName, attrId):
    print('attr created : {0} at index : {1}'.format(nodeName, attrId))

@QtCore.pyqtSlot(str, int)
def on_attrDeleted(nodeName, attrId):
    print('attr Deleted : {0} at old index : {1}'.format(nodeName, attrId))

@QtCore.pyqtSlot(str, int, int)
def on_attrEdited(nodeName, oldId, newId):
    print('attr Edited : {0} at old index : {1}, new index : {2}'.format(nodeName, oldId, newId))

# Connections
@QtCore.pyqtSlot(str, str, str, str)
def on_connected(srcNodeName, srcPlugName, destNodeName, dstSocketName):
    print('connected src: "{0}" at "{1}" to dst: "{2}" at "{3}"'.format(srcNodeName, srcPlugName, destNodeName, dstSocketName))

@QtCore.pyqtSlot(str, str, str, str)
def on_disconnected(srcNodeName, srcPlugName, destNodeName, dstSocketName):
    print('disconnected src: "{0}" at "{1}" from dst: "{2}" at "{3}"'.format(srcNodeName, srcPlugName, destNodeName, dstSocketName))

# Graph
@QtCore.pyqtSlot()
def on_graphSaved():
    print('graph saved !')

@QtCore.pyqtSlot()
def on_graphLoaded():
    print('graph loaded !')

@QtCore.pyqtSlot()
def on_graphCleared():
    print('graph cleared !')

@QtCore.pyqtSlot()
def on_graphEvaluated():
    print('graph evaluated !')

# Other
@QtCore.pyqtSlot(object)
def on_keyPressed(key):
    print('key pressed : ', key)

nodz.signal_NodeCreated.connect(on_nodeCreated)
nodz.signal_NodeDeleted.connect(on_nodeDeleted)
nodz.signal_NodeEdited.connect(on_nodeEdited)
nodz.signal_NodeSelected.connect(on_nodeSelected)
nodz.signal_NodeMoved.connect(on_nodeMoved)
nodz.signal_NodeDoubleClicked.connect(on_nodeDoubleClick)

nodz.signal_AttrCreated.connect(on_attrCreated)
nodz.signal_AttrDeleted.connect(on_attrDeleted)
nodz.signal_AttrEdited.connect(on_attrEdited)

nodz.signal_PlugConnected.connect(on_connected)
nodz.signal_SocketConnected.connect(on_connected)
nodz.signal_PlugDisconnected.connect(on_disconnected)
nodz.signal_SocketDisconnected.connect(on_disconnected)

nodz.signal_GraphSaved.connect(on_graphSaved)
nodz.signal_GraphLoaded.connect(on_graphLoaded)
nodz.signal_GraphCleared.connect(on_graphCleared)
nodz.signal_GraphEvaluated.connect(on_graphEvaluated)

nodz.signal_KeyPressed.connect(on_keyPressed)


######################################################################
# Test API
######################################################################

# Node A
nodeA = nodz.createNode(name='nodeA', preset='node_preset_1', position=QtCore.QPoint(50010,50010))

nodz.createAttribute(node=nodeA, name='Aattr1', index=-1, preset='attr_preset_1',
                     plug=True, socket=False, dataType=int)

nodz.createAttribute(node=nodeA, name='Aattr2', index=-1, preset='attr_preset_1',
                     plug=False, socket=True, dataType=int)

# nodz.createAttribute(node=nodeA, name='Aattr3', index=-1, preset='attr_preset_2',
#                      plug=True, socket=True, dataType=int)

# nodz.createAttribute(node=nodeA, name='Aattr4', index=-1, preset='attr_preset_2',
#                      plug=True, socket=True, dataType=int)

# nodz.createAttribute(node=nodeA, name='Aattr5', index=-1, preset='attr_preset_3',
#                      plug=True, socket=True, dataType=int, plugMaxConnections=1, socketMaxConnections=-1)

# nodz.createAttribute(node=nodeA, name='Aattr6', index=-1, preset='attr_preset_3',
#                      plug=True, socket=True, dataType=int, plugMaxConnections=1, socketMaxConnections=-1)



# # Node B
nodeB = nodz.createNode(name='nodeB', preset='node_preset_1',position=QtCore.QPoint(50070,50010))

nodz.createAttribute(node=nodeB, name='Battr1', index=-1, preset='attr_preset_1',
                     plug=True, socket=False, dataType=int)

nodz.createAttribute(node=nodeB, name='Battr2', index=-1, preset='attr_preset_1',
                     plug=True, socket=False, dataType=int)

nodz.createAttribute(node=nodeB, name='Battr3', index=-1, preset='attr_preset_2',
                     plug=True, socket=False, dataType=int)

nodz.createAttribute(node=nodeB, name='Battr\nNewline\nNewline4', index=-1, preset='attr_preset_3',
                     plug=True, socket=False, dataType=int)



# Node C
nodeC = nodz.createNode(name='nodeC', preset='node_preset_1',position=QtCore.QPoint(50015,50010))

nodz.createAttribute(node=nodeC, name='Cattr1', index=-1, preset='attr_preset_1',
                     plug=False, socket=True, dataType=int)

nodz.createAttribute(node=nodeC, name='Cattr2', index=-1, preset='attr_preset_1',
                     plug=True, socket=False, dataType=int)

nodz.createAttribute(node=nodeC, name='Cattr3', index=-1, preset='attr_preset_1',
                     plug=True, socket=False, dataType=int)

nodz.createAttribute(node=nodeC, name='Cattr4', index=-1, preset='attr_preset_2',
                     plug=False, socket=True, dataType=int)

nodz.createAttribute(node=nodeC, name='Cattr5', index=-1, preset='attr_preset_2',
                     plug=False, socket=True, dataType=int)

nodz.createAttribute(node=nodeC, name='Cattr6', index=-1, preset='attr_preset_3',
                     plug=True, socket=False, dataType=int)

nodz.createAttribute(node=nodeC, name='Cattr7', index=-1, preset='attr_preset_3',
                     plug=True, socket=False, dataType=int)

nodz.createAttribute(node=nodeC, name='Cattr8', index=-1, preset='attr_preset_3',
                     plug=True, socket=False, dataType=int)


nodeNew = nodz.createNode(name='New node!', preset='node_preset_1',position=QtCore.QPoint(50045,50010))

nodz.createAttribute(node=nodeNew, name='New attribute', index=-1, preset='attr_preset_1',
                     plug=False, socket=True, dataType=int)

nodz.createAttribute(node=nodeNew, name='Another new attribute', index=-1, preset='attr_preset_2',
                     plug=True, socket=False, dataType=int)


# Please note that this is a local test so once the graph is cleared
# and reloaded, all the local variables are not valid anymore, which
# means the following code to alter nodes won't work but saving/loading/
# clearing/evaluating will.

# Connection creation
# nodz.createConnection('nodeB', 'Battr2', 'nodeA', 'Aattr1')
# nodz.createConnection('nodeB', 'Battr1', 'nodeA', 'Aattr1')

# Attributes Edition
nodz.editAttribute(node=nodeC, index=0, newName=None, newIndex=-1)
nodz.editAttribute(node=nodeC, index=-1, newName='NewAttrName', newIndex=None)

# # Attributes Deletion
# nodz.deleteAttribute(node=nodeC, index=-1)


# # Nodes Edition
# nodz.editNode(node=nodeC, newName='newNodeName')

# # Nodes Deletion
# nodz.deleteNode(node=nodeC)


# # Graph
print( nodz.evaluateGraph())

# nodz.saveGraph(filePath='Enter your path')

# nodz.clearGraph()

# nodz.loadGraph(filePath='Enter your path')



if app:
    # command line stand alone test... run our own event loop
    sys.exit(app.exec_())