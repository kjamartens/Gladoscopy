import os
import re
import json

from PyQt5 import QtGui, QtCore, QtWidgets
from PyQt5.QtWidgets import QLineEdit, QInputDialog, QDialog, QLineEdit, QComboBox, QVBoxLayout, QDialogButtonBox, QMenu, QAction
from PyQt5.QtGui import QFont, QColor, QTextDocument, QAbstractTextDocumentLayout
from PyQt5.QtCore import QRectF
import nodz_utils as utils
from nodz_custom import *
import logging


defaultConfigPath = os.path.join(os.path.dirname(os.path.realpath(__file__)), 'default_config.json')


class Nodz(QtWidgets.QGraphicsView):

    """
    The main view for the node graph representation.

    The node view implements a state pattern to control all the
    different user interactions.

    """

    signal_NodeCreated = QtCore.pyqtSignal(object)
    signal_NodeCreatedNodeItself = QtCore.pyqtSignal(object)
    signal_NodeFullyInitialisedNodeItself = QtCore.pyqtSignal(object)
    signal_NodeDeleted = QtCore.pyqtSignal(object)
    signal_NodeEdited = QtCore.pyqtSignal(object, object)
    signal_NodeSelected = QtCore.pyqtSignal(object)
    signal_NodeMoved = QtCore.pyqtSignal(str, object)
    signal_NodeDoubleClicked = QtCore.pyqtSignal(str, object)

    signal_AttrCreated = QtCore.pyqtSignal(object, object)
    signal_AttrDeleted = QtCore.pyqtSignal(object, object)
    signal_AttrEdited = QtCore.pyqtSignal(object, object, object)

    signal_PlugConnectedStartConnection = QtCore.pyqtSignal(object, object, object, object) #Runs at the start of connection
    signal_PlugConnected = QtCore.pyqtSignal(object, object, object, object) #Runs at the end of connection
    signal_PlugDisconnected = QtCore.pyqtSignal(object, object, object, object)
    signal_SocketConnectedStartConnection = QtCore.pyqtSignal(object, object, object, object) #Runs at the start of connection
    signal_SocketConnected = QtCore.pyqtSignal(object, object, object, object) #Runs at the end of connection
    signal_SocketDisconnected = QtCore.pyqtSignal(object, object, object, object)

    signal_GraphSaved = QtCore.pyqtSignal()
    signal_GraphLoaded = QtCore.pyqtSignal()
    signal_GraphCleared = QtCore.pyqtSignal()
    signal_GraphEvaluated = QtCore.pyqtSignal()

    signal_KeyPressed = QtCore.pyqtSignal(object)
    signal_Dropped = QtCore.pyqtSignal()

    def __init__(self, parent, configPath=defaultConfigPath,core=None,shared_data=None,MM_JSON="TestStr"):
        """
        Initialize the graphics view.

        """
        super(Nodz, self).__init__(parent)
        
        # Load nodz configuration.
        self.loadConfig(configPath)
        
        #Global variables for MM/napari
        self.core = core
        self.shared_data = shared_data
        self.MM_JSON=MM_JSON


        # General data.
        self.gridVisToggle = True
        self.gridSnapToggle = False
        self._nodeSnap = False
        self.selectedNodes = None

        # Connections data.
        self.drawingConnection = False
        self.currentHoveredNode = None
        self.sourceSlot = None

        # Display options.
        self.currentState = 'DEFAULT'
        self.pressedKeys = list()
        
        return self

    def wheelEvent(self, event):
        """
        Zoom in the view with the mouse wheel.

        """
        self.currentState = 'ZOOM_VIEW'
        self.setTransformationAnchor(QtWidgets.QGraphicsView.AnchorUnderMouse)

        inFactor = 1.15
        outFactor = 1 / inFactor

        if event.angleDelta().y() > 0:
            zoomFactor = inFactor
        else:
            zoomFactor = outFactor

        self.scale(zoomFactor, zoomFactor)
        self.currentState = 'DEFAULT'

    def contextMenuEvent(self, QMouseevent):
        context_menu = QMenu(self)

        new_acq_node_action = QAction("New Acquisition node", self)
        new_analysis_node_action = QAction("New Analysis node", self)
        new_scoring_node_action = QAction("New Scoring node", self)
        new_decision_node_action = QAction("New Decision node", self)

        context_menu.addAction(new_acq_node_action)
        context_menu.addAction(new_analysis_node_action)
        context_menu.addAction(new_scoring_node_action)
        context_menu.addAction(new_decision_node_action)
        
        logging.debug(QMouseevent)
        new_acq_node_action.triggered.connect(lambda _, event=QMouseevent: self.createNewNode(event,'NewAcqNode'))
        new_analysis_node_action.triggered.connect(lambda _, event=QMouseevent: self.createNewNode(event,'NewAnalysisNode'))
        new_scoring_node_action.triggered.connect(lambda _, event=QMouseevent: self.createNewNode(event,'NewScoringNode'))
        new_decision_node_action.triggered.connect(lambda _, event=QMouseevent: self.createNewNode(event,'NewDecisionNode'))

        # Show the context menu at the event's position
        # context_menu.exec_(self.mapToScene(QMouseevent.pos()))
        context_menu.exec_(QMouseevent.globalPos())
        
    def createNewNode(self,event,name):
        print(event)
        NodeZ = self.createNode(name=name, preset='node_preset_1', position=self.mapToScene(event.pos()))
    
    def mousePressEvent(self, event):
        """
        Initialize tablet zoom, drag canvas and the selection.

        """
        
        #New node when pressing RightButton
        if (event.button() == QtCore.Qt.RightButton and event.modifiers() == QtCore.Qt.NoModifier): # type: ignore
            #Get a small context menu:
            self.contextMenuEvent(event)
            #Create a new node at mouse position
            # nodeZ = self.createNode(name='nodeZ', preset='node_preset_1', position=self.mapToScene(event.pos()))
        
        # Tablet zoom
        if (event.button() == QtCore.Qt.RightButton and #type:ignore
            event.modifiers() == QtCore.Qt.AltModifier): #type:ignore
            self.currentState = 'ZOOM_VIEW'
            self.initMousePos = event.pos()
            self.zoomInitialPos = event.pos()
            self.initMouse = QtGui.QCursor.pos()
            self.setInteractive(False)


        # Drag view
        # elif (event.button() == QtCore.Qt.MiddleButton and
        #       event.modifiers() == QtCore.Qt.AltModifier):
        elif (event.button() == QtCore.Qt.MiddleButton): #type:ignore
            self.currentState = 'DRAG_VIEW'
            self.prevPos = event.pos()
            self.setCursor(QtCore.Qt.ClosedHandCursor) #type:ignore
            self.setInteractive(False)


        # Rubber band selection
        elif (event.button() == QtCore.Qt.LeftButton and #type:ignore
              event.modifiers() == QtCore.Qt.NoModifier and #type:ignore
              self.scene().itemAt(self.mapToScene(event.pos()), QtGui.QTransform()) is None):
            self.currentState = 'SELECTION'
            self._initRubberband(event.pos())
            self.setInteractive(False)


        # Drag Item
        elif (event.button() == QtCore.Qt.LeftButton and #type:ignore
              event.modifiers() == QtCore.Qt.NoModifier and #type:ignore
              self.scene().itemAt(self.mapToScene(event.pos()), QtGui.QTransform()) is not None):
            self.currentState = 'DRAG_ITEM'
            self.setInteractive(True)


        # Add selection
        elif (event.button() == QtCore.Qt.LeftButton and #type:ignore
              QtCore.Qt.Key_Shift in self.pressedKeys and #type:ignore
              QtCore.Qt.Key_Control in self.pressedKeys): #type:ignore
            self.currentState = 'ADD_SELECTION'
            self._initRubberband(event.pos())
            self.setInteractive(False)


        # Subtract selection
        elif (event.button() == QtCore.Qt.LeftButton and #type:ignore
              event.modifiers() == QtCore.Qt.ControlModifier): #type:ignore
            self.currentState = 'SUBTRACT_SELECTION'
            self._initRubberband(event.pos())
            self.setInteractive(False)


        # Toggle selection
        elif (event.button() == QtCore.Qt.LeftButton and #type:ignore
              event.modifiers() == QtCore.Qt.ShiftModifier): #type:ignore
            self.currentState = 'TOGGLE_SELECTION'
            self._initRubberband(event.pos())
            self.setInteractive(False)


        else:
            self.currentState = 'DEFAULT'

        super(Nodz, self).mousePressEvent(event)

    def mouseMoveEvent(self, event):
        """
        Update tablet zoom, canvas dragging and selection.

        """
        # Zoom.
        if self.currentState == 'ZOOM_VIEW':
            offset = self.zoomInitialPos.x() - event.pos().x()

            if offset > self.previousMouseOffset:
                self.previousMouseOffset = offset
                self.zoomDirection = -1
                self.zoomIncr -= 1

            elif offset == self.previousMouseOffset:
                self.previousMouseOffset = offset
                if self.zoomDirection == -1:
                    self.zoomDirection = -1
                else:
                    self.zoomDirection = 1

            else:
                self.previousMouseOffset = offset
                self.zoomDirection = 1
                self.zoomIncr += 1

            if self.zoomDirection == 1:
                zoomFactor = 1.03
            else:
                zoomFactor = 1 / 1.03

            # Perform zoom and re-center on initial click position.
            pBefore = self.mapToScene(self.initMousePos)
            self.setTransformationAnchor(QtWidgets.QGraphicsView.AnchorViewCenter)
            self.scale(zoomFactor, zoomFactor)
            pAfter = self.mapToScene(self.initMousePos)
            diff = pAfter - pBefore

            self.setTransformationAnchor(QtWidgets.QGraphicsView.NoAnchor)
            self.translate(diff.x(), diff.y())

        # Drag canvas.
        elif self.currentState == 'DRAG_VIEW':
            offset = self.prevPos - event.pos()
            self.prevPos = event.pos()
            self.verticalScrollBar().setValue(self.verticalScrollBar().value() + offset.y())
            self.horizontalScrollBar().setValue(self.horizontalScrollBar().value() + offset.x())

        # RuberBand selection.
        elif (self.currentState == 'SELECTION' or
              self.currentState == 'ADD_SELECTION' or
              self.currentState == 'SUBTRACT_SELECTION' or
              self.currentState == 'TOGGLE_SELECTION'):
            self.rubberband.setGeometry(QtCore.QRect(self.origin, event.pos()).normalized())

        super(Nodz, self).mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        """
        Apply tablet zoom, dragging and selection.

        """
        # Zoom the View.
        if self.currentState == '.ZOOM_VIEW':
            self.offset = 0
            self.zoomDirection = 0
            self.zoomIncr = 0
            self.setInteractive(True)


        # Drag View.
        elif self.currentState == 'DRAG_VIEW':
            self.setCursor(QtCore.Qt.ArrowCursor) #type:ignore
            self.setInteractive(True)


        # Selection.
        elif self.currentState == 'SELECTION':
            self.rubberband.setGeometry(QtCore.QRect(self.origin,
                                                     event.pos()).normalized())
            painterPath = self._releaseRubberband()
            self.setInteractive(True)
            self.scene().setSelectionArea(painterPath)


        # Add Selection.
        elif self.currentState == 'ADD_SELECTION':
            self.rubberband.setGeometry(QtCore.QRect(self.origin,
                                                     event.pos()).normalized())
            painterPath = self._releaseRubberband()
            self.setInteractive(True)
            for item in self.scene().items(painterPath):
                item.setSelected(True)


        # Subtract Selection.
        elif self.currentState == 'SUBTRACT_SELECTION':
            self.rubberband.setGeometry(QtCore.QRect(self.origin,
                                                     event.pos()).normalized())
            painterPath = self._releaseRubberband()
            self.setInteractive(True)
            for item in self.scene().items(painterPath):
                item.setSelected(False)


        # Toggle Selection
        elif self.currentState == 'TOGGLE_SELECTION':
            self.rubberband.setGeometry(QtCore.QRect(self.origin,
                                                     event.pos()).normalized())
            painterPath = self._releaseRubberband()
            self.setInteractive(True)
            for item in self.scene().items(painterPath):
                if item.isSelected():
                    item.setSelected(False)
                else:
                    item.setSelected(True)

        self.currentState = 'DEFAULT'

        super(Nodz, self).mouseReleaseEvent(event)

    def keyPressEvent(self, event):
        """
        Save pressed key and apply shortcuts.

        Shortcuts are:
        DEL - Delete the selected nodes
        F - Focus view on the selection

        """
        if event.key() not in self.pressedKeys:
            self.pressedKeys.append(event.key())

        if event.key() in (QtCore.Qt.Key_Delete, QtCore.Qt.Key_Backspace): #type:ignore
            self._deleteSelectedNodes()

        if event.key() == QtCore.Qt.Key_F: #type:ignore
            self._focus()

        if event.key() == QtCore.Qt.Key_S: #type:ignore
            self._nodeSnap = True
            
        if event.key() == QtCore.Qt.Key_T: #type:ignore
            for node in self.scene().selectedItems():
                import random
                self.editNodeDisplayText(node, newDisplayText="NodeZZ"+str(random.randint(1, 10)))
                
        # Emit signal.
        self.signal_KeyPressed.emit(event.key())

    def keyReleaseEvent(self, event):
        """
        Clear the key from the pressed key list.

        """
        if event.key() == QtCore.Qt.Key_S: #type:ignore
            self._nodeSnap = False

        if event.key() in self.pressedKeys:
            self.pressedKeys.remove(event.key())

    def _initRubberband(self, position):
        """
        Initialize the rubber band at the given position.

        """
        self.rubberBandStart = position
        self.origin = position
        self.rubberband.setGeometry(QtCore.QRect(self.origin, QtCore.QSize()))
        self.rubberband.show()

    def _releaseRubberband(self):
        """
        Hide the rubber band and return the path.

        """
        painterPath = QtGui.QPainterPath()
        rect = self.mapToScene(self.rubberband.geometry())
        painterPath.addPolygon(rect)
        self.rubberband.hide()
        return painterPath

    def _focus(self):
        """
        Center on selected nodes or all of them if no active selection.

        """
        if self.scene().selectedItems():
            itemsArea = self._getSelectionBoundingbox()
            self.fitInView(itemsArea, QtCore.Qt.KeepAspectRatio) #type:ignore
        else:
            rect = self.scene().itemsBoundingRect() 
            center = rect.center()
            center.setX(center.x() + 400)  # Add 400 to the x-coordinate
            itemsArea = rect.adjusted(-50, -50, 50, 50)  # Adjust the bounding rect for padding
            self.fitInView(itemsArea, QtCore.Qt.KeepAspectRatio) #type:ignore

    def _getSelectionBoundingbox(self):
        """
        Return the bounding box of the selection.

        """
        bbx_min = None
        bbx_max = None
        bby_min = None
        bby_max = None
        bbw = 0
        bbh = 0
        for item in self.scene().selectedItems():
            pos = item.scenePos()
            x = pos.x()
            y = pos.y()
            w = x + item.boundingRect().width()
            h = y + item.boundingRect().height()

            # bbx min
            if bbx_min is None:
                bbx_min = x
            elif x < bbx_min:
                bbx_min = x
            # end if

            # bbx max
            if bbx_max is None:
                bbx_max = w
            elif w > bbx_max:
                bbx_max = w
            # end if

            # bby min
            if bby_min is None:
                bby_min = y
            elif y < bby_min:
                bby_min = y
            # end if

            # bby max
            if bby_max is None:
                bby_max = h
            elif h > bby_max:
                bby_max = h
            # end if
        # end if
        bbw = bbx_max - bbx_min #type:ignore
        bbh = bby_max - bby_min #type:ignore
        return QtCore.QRectF(QtCore.QRect(int(bbx_min), int(bby_min), int(bbw), int(bbh))) #type:ignore

    def _deleteSelectedNodes(self):
        """
        Delete selected nodes.

        """
        selected_nodes = list()
        for node in self.scene().selectedItems():
            selected_nodes.append(node.name) #type:ignore
            node._remove() #type:ignore

        # Emit signal.
        self.signal_NodeDeleted.emit(selected_nodes)

    def _returnSelection(self):
        """
        Wrapper to return selected items.

        """
        selected_nodes = list()
        if self.scene().selectedItems():
            for node in self.scene().selectedItems():
                selected_nodes.append(node.name) #type:ignore

        # Emit signal.
        self.signal_NodeSelected.emit(selected_nodes)


    ##################################################################
    # API
    ##################################################################

    def addConfig(self, config):
        self.config.update(config)

    def loadConfig(self, filePath):
        """
        Set a specific configuration for this instance of Nodz.

        :type  filePath: str.
        :param filePath: The path to the config file that you want to
                         use.

        """
        self.config = utils._loadConfig(filePath)

    def initialize(self):
        """
        Setup the view's behavior.

        """
        # Setup view.
        config = self.config
        self.setRenderHint(QtGui.QPainter.Antialiasing, config['antialiasing'])
        self.setRenderHint(QtGui.QPainter.TextAntialiasing, config['antialiasing'])
        self.setRenderHint(QtGui.QPainter.HighQualityAntialiasing, config['antialiasing_boost'])
        self.setRenderHint(QtGui.QPainter.SmoothPixmapTransform, config['smooth_pixmap'])
        self.setRenderHint(QtGui.QPainter.NonCosmeticDefaultPen, True)
        self.setViewportUpdateMode(QtWidgets.QGraphicsView.FullViewportUpdate)
        self.setTransformationAnchor(QtWidgets.QGraphicsView.AnchorUnderMouse)
        self.setHorizontalScrollBarPolicy(QtCore.Qt.ScrollBarAlwaysOff) #type:ignore
        self.setVerticalScrollBarPolicy(QtCore.Qt.ScrollBarAlwaysOff) #type:ignore
        self.rubberband = QtWidgets.QRubberBand(QtWidgets.QRubberBand.Rectangle, self)

        # Setup scene.
        scene = NodeScene(self)
        sceneWidth = config['scene_width']
        sceneHeight = config['scene_height']
        scene.setSceneRect(0, 0, sceneWidth, sceneHeight)
        self.setScene(scene)
        # Connect scene node moved signal
        scene.signal_NodeMoved.connect(self.signal_NodeMoved)

        # Tablet zoom.
        self.previousMouseOffset = 0
        self.zoomDirection = 0
        self.zoomIncr = 0

        # Connect signals.
        self.scene().selectionChanged.connect(self._returnSelection)


    # NODES
    def createNode(self, name='default', preset='node_default', position=None, alternate=True, displayText=None, displayName=None,skipCreateNodeSignal=False,createdFromNodzLoading=False,nodeInfo=None):
        """
        Create a new node with a given name, position and color.

        :type  name: str.
        :param name: The name of the node. The name has to be unique
                     as it is used as a key to store the node object.

        :type  preset: str.
        :param preset: The name of graphical preset in the config file.

        :type  position: QtCore.QPoint.
        :param position: The position of the node once created. If None,
                         it will be created at the center of the scene.

        :type  alternate: bool.
        :param alternate: The attribute color alternate state, if True,
                          every 2 attribute the color will be slightly
                          darker.

        :return : The created node

        """
        # Check for name clashes
        if name in self.scene().nodes.keys(): #type:ignore
            print('A node with the same name already exists : {0}'.format(name))
            print('Node creation aborted !')
            return
        else:
            nodeItem = NodeItem(name=name, alternate=alternate, preset=preset,
                                config=self.config, displayText = displayText, displayName=displayName,nodeInfo=nodeInfo)

            # Store node in scene.
            self.scene().nodes[name] = nodeItem #type:ignore

            if not position:
                # Get the center of the view.
                position = self.mapToScene(self.viewport().rect().center())

            # Set node position.
            self.scene().addItem(nodeItem)
            nodeItem.setPos(position - nodeItem.nodeCenter)
            
            #Add some info about whether it's loaded or not - if it's just created, the numbering should go up, ifi t's loaded, the numbering should stay without change
            if createdFromNodzLoading:
                nodeItem.createdFromLoading = True #type:ignore
            else:
                nodeItem.createdFromLoading = False #type:ignore

            if not skipCreateNodeSignal:
                # Emit signal.
                self.signal_NodeCreated.emit(name)
                self.signal_NodeCreatedNodeItself.emit(nodeItem)

            return nodeItem

    def deleteNode(self, node):
        """
        Delete the specified node from the view.

        :type  node: class.
        :param node: The node instance that you want to delete.

        """
        if not node in self.scene().nodes.values(): #type:ignore
            print('Node object does not exist !')
            print('Node deletion aborted !')
            return

        if node in self.scene().nodes.values(): #type:ignore
            nodeName = node.name
            node._remove()

            # Emit signal.
            self.signal_NodeDeleted.emit([nodeName])

    def editNode(self, node, newName=None):
        """
        Rename an existing node.

        :type  node: class.
        :param node: The node instance that you want to delete.

        :type  newName: str.
        :param newName: The new name for the given node.

        """
        if not node in self.scene().nodes.values(): #type:ignore
            print('Node object does not exist !')
            print('Node edition aborted !')
            return

        oldName = node.name

        if newName != None:
            # Check for name clashes
            if newName in self.scene().nodes.keys(): #type:ignore
                print('A node with the same name already exists : {0}'.format(newName))
                print('Node edition aborted !')
                return
            else:
                node.name = newName

        # Replace node data.
        self.scene().nodes[newName] = self.scene().nodes[oldName] #type:ignore
        self.scene().nodes.pop(oldName) #type:ignore

        # Store new node name in the connections
        if node.sockets:
            for socket in node.sockets.values():
                for connection in socket.connections:
                    connection.socketNode = newName

        if node.plugs:
            for plug in node.plugs.values():
                for connection in plug.connections:
                    connection.plugNode = newName

        node.update()

        # Emit signal.
        self.signal_NodeEdited.emit(oldName, newName)


    def editNodeDisplayText(self, node, newDisplayText=None):
        """
        Rename an existing node.

        :type  node: class.
        :param node: The node instance that you want to delete.

        :type  newDisplayText: str.
        :param newName: The new displayText for the node.

        """
        node.displayText = newDisplayText

        node.update()

    # ATTRS
    def createAttribute(self, node, name='default', index=-1, preset='attr_default', plug=True, socket=True, bottomAttr=False, topAttr=False, dataType=None, plugMaxConnections=-1, socketMaxConnections=-1):
        """
        Create a new attribute with a given name.

        :type  node: class.
        :param node: The node instance that you want to delete.

        :type  name: str.
        :param name: The name of the attribute. The name has to be
                     unique as it is used as a key to store the node
                     object.

        :type  index: int.
        :param index: The index of the attribute in the node.

        :type  preset: str.
        :param preset: The name of graphical preset in the config file.

        :type  plug: bool.
        :param plug: Whether or not this attribute can emit connections.

        :type  socket: bool.
        :param socket: Whether or not this attribute can receive
                       connections.

        :type  dataType: type.
        :param dataType: Type of the data represented by this attribute
                         in order to highlight attributes of the same
                         type while performing a connection.

        :type  plugMaxConnections: int.
        :param plugMaxConnections: The maximum connections that the plug can have (-1 for infinite).

        :type  socketMaxConnections: int.
        :param socketMaxConnections: The maximum connections that the socket can have (-1 for infinite).

        """
        if not node in self.scene().nodes.values(): #type:ignore
            print('Node object does not exist !')
            print('Attribute creation aborted !')
            return

        if name in node.attrs:
            print('An attribute with the same name already exists : {0}'.format(name))
            print('Attribute creation aborted !')
            return

        node._createAttribute(name=name, index=index, preset=preset, plug=plug, socket=socket, bottomAttr=bottomAttr, topAttr=topAttr, dataType=dataType, plugMaxConnections=plugMaxConnections, socketMaxConnections=socketMaxConnections)

        # Emit signal.
        self.signal_AttrCreated.emit(node.name, index)

    def deleteAttribute(self, node, index):
        """
        Delete the specified attribute.

        :type  node: class.
        :param node: The node instance that you want to delete.

        :type  index: int.
        :param index: The index of the attribute in the node.

        """
        if not node in self.scene().nodes.values(): #type:ignore
            print('Node object does not exist !')
            print('Attribute deletion aborted !')
            return

        node._deleteAttribute(index)

        # Emit signal.
        self.signal_AttrDeleted.emit(node.name, index)

    def editAttribute(self, node, index, newName=None, newIndex=None):
        """
        Edit the specified attribute.

        :type  node: class.
        :param node: The node instance that you want to delete.

        :type  index: int.
        :param index: The index of the attribute in the node.

        :type  newName: str.
        :param newName: The new name for the given attribute.

        :type  newIndex: int.
        :param newIndex: The index for the given attribute.

        """
        if not node in self.scene().nodes.values(): #type:ignore
            print('Node object does not exist !')
            print('Attribute creation aborted !')
            return

        if newName != None:
            if newName in node.attrs:
                print('An attribute with the same name already exists : {0}'.format(newName))
                print('Attribute edition aborted !')
                return
            else:
                oldName = node.attrs[index]

            # Rename in the slot item(s).
            if node.attrsData[oldName]['plug']:
                node.plugs[oldName].attribute = newName
                node.plugs[newName] = node.plugs[oldName]
                node.plugs.pop(oldName)
                for connection in node.plugs[newName].connections:
                    connection.plugAttr = newName

            if node.attrsData[oldName]['socket']:
                node.sockets[oldName].attribute = newName
                node.sockets[newName] = node.sockets[oldName]
                node.sockets.pop(oldName)
                for connection in node.sockets[newName].connections:
                    connection.socketAttr = newName

            # Replace attribute data.
            node.attrsData[oldName]['name'] = newName
            node.attrsData[newName] = node.attrsData[oldName]
            node.attrsData.pop(oldName)
            node.attrs[index] = newName

        if isinstance(newIndex, int):
            attrName = node.attrs[index]

            utils._swapListIndices(node.attrs, index, newIndex)

            # Refresh connections.
            for plug in node.plugs.values():
                plug.update()
                if plug.connections:
                    for connection in plug.connections:
                        if isinstance(connection.source, PlugItem):
                            connection.source = plug
                            connection.source_point = plug.center()
                        else:
                            connection.target = plug
                            connection.target_point = plug.center()
                        if newName:
                            connection.plugAttr = newName
                        connection.updatePath()

            for socket in node.sockets.values():
                socket.update()
                if socket.connections:
                    for connection in socket.connections:
                        if isinstance(connection.source, SocketItem):
                            connection.source = socket
                            connection.source_point = socket.center()
                        else:
                            connection.target = socket
                            connection.target_point = socket.center()
                        if newName:
                            connection.socketAttr = newName
                        connection.updatePath()

            self.scene().update()

        node.update()

        # Emit signal.
        if newIndex:
            self.signal_AttrEdited.emit(node.name, index, newIndex)
        else:
            self.signal_AttrEdited.emit(node.name, index, index)


    # GRAPH
    def saveGraph(self, filePath='path'):
        """
        Get all the current graph infos and store them in a .json file
        at the given location.

        :type  filePath: str.
        :param filePath: The path where you want to save your graph at.

        """
        data = dict()

        # Store nodes data.
        data['NODES'] = dict()
        data['NODES_MDA'] = dict()
        data['NODES_MMCONFIGCHANGE'] = dict()
        data['NODES_SCORING_ANALYSIS'] = dict()
        data['NODES_SCORING_VISUALISATION'] = dict()
        data['NODES_SCORING_SCORING'] = dict()
        data['NODES_SCORING_END'] = dict()
        data['NODES_VISUALISATION'] = dict()
        data['NODES_RT_ANALYSIS'] = dict()

        nodes = self.scene().nodes.keys() #type:ignore
        for node in nodes:
            nodeInst = self.scene().nodes[node] #type:ignore
            preset = nodeInst.nodePreset
            nodeAlternate = nodeInst.alternate

            data['NODES'][node] = {'preset': preset,
                                'position': [nodeInst.pos().x()+nodeInst.baseWidth/2, nodeInst.pos().y()+nodeInst.height/2],
                                'alternate': nodeAlternate,
                                'attributes': [],
                                'textbox_text': nodeInst.textbox.toHtml(),
                                'textboxheight': nodeInst.textboxheight,
                                'displayName': nodeInst.displayName,
                                'alternateFillColor': nodeInst.alternateFillColor}

            import numpy
            def convert_to_string(obj):
                if isinstance(obj, (int, float, numpy.int32)): #type:ignore
                    return str(obj)
                elif isinstance(obj, dict):
                    return {key: convert_to_string(value) for key, value in obj.items()}
                elif isinstance(obj, list):
                    return [convert_to_string(item) for item in obj]
                else:
                    return obj
            
            #Storing required MDA info
            data['NODES_MDA'][node] = {}
            if nodeInst.mdaData is not None:
                #Only store mda if its properly initialised as MDAGLados
                if isinstance(nodeInst.mdaData,MDAGlados):
                    #Skip some attributes in nodes_mda:
                    mdaattr_skip = ['MDA_completed','MM_JSON','core','data','shared_data','gui','layout']
                    for attr in vars(nodeInst.mdaData):
                        if attr not in mdaattr_skip:
                            #Also check if it's a Qtpy object:
                            if not isinstance(getattr(nodeInst.mdaData, attr), QtCore.QObject):
                                data['NODES_MDA'][node][attr] = getattr(nodeInst.mdaData, attr)

                    data['NODES_MDA'][node] = convert_to_string(data['NODES_MDA'][node])

            #Storing required MM-config-changing info:
            data['NODES_MMCONFIGCHANGE'][node] = {}
            if 'MMconfigInfo' in vars(nodeInst): 
                if nodeInst.MMconfigInfo is not None:
                    data['NODES_MMCONFIGCHANGE'][node] = nodeInst.MMconfigInfo.config_string_storage

            
            data['NODES_SCORING_ANALYSIS'][node] = {}
            if 'scoring_analysis_currentData' in vars(nodeInst):
                if nodeInst.scoring_analysis_currentData is not None:
                    data['NODES_SCORING_ANALYSIS'][node] = nodeInst.scoring_analysis_currentData
                    
            data['NODES_SCORING_VISUALISATION'][node] = {}
            if 'scoring_visualisation_currentData' in vars(nodeInst):
                if nodeInst.scoring_visualisation_currentData is not None:
                    data['NODES_SCORING_VISUALISATION'][node] = nodeInst.scoring_visualisation_currentData
                    
            data['NODES_SCORING_SCORING'][node] = {}
            if 'scoring_scoring_currentData' in vars(nodeInst):
                if nodeInst.scoring_scoring_currentData is not None:
                    data['NODES_SCORING_SCORING'][node] = nodeInst.scoring_scoring_currentData

            data['NODES_SCORING_END'][node] = {}
            if 'scoring_end_currentData' in vars(nodeInst):
                if nodeInst.scoring_end_currentData['Variables'] is not None:
                    data['NODES_SCORING_END'][node] = nodeInst.scoring_end_currentData

            data['NODES_VISUALISATION'][node] = {}
            if 'visualisation_currentData' in vars(nodeInst):
                if nodeInst.visualisation_currentData is not None:
                    data['NODES_VISUALISATION'][node] = nodeInst.visualisation_currentData

            data['NODES_RT_ANALYSIS'][node] = {}
            if 'real_time_analysis_currentData' in vars(nodeInst):
                if nodeInst.real_time_analysis_currentData is not None:
                    data['NODES_RT_ANALYSIS'][node] = nodeInst.real_time_analysis_currentData
                    
            attrs = nodeInst.attrs
            for attr in attrs:
                attrData = nodeInst.attrsData[attr]

                # serialize dataType if needed.
                if isinstance(attrData['dataType'], type):
                    attrData['dataType'] = str(attrData['dataType'])

                data['NODES'][node]['attributes'].append(attrData)


        # Store connections data.
        data['CONNECTIONS'] = self.evaluateGraph()


        # Save data.
        try:
            utils._saveData(filePath=filePath, data=data)
        except:
            print('Invalid path : {0}'.format(filePath))
            print('Save aborted !')
            return False

        # Emit signal.
        self.signal_GraphSaved.emit()

    def loadGraph_KM(self, filePath='path'):
        """
        Get all the stored info from the .json file at the given location
        and recreate the graph as saved.

        :type  filePath: str.
        :param filePath: The path where you want to load your graph from.

        """
        # Load data.
        if os.path.exists(filePath):
            data = utils._loadData(filePath=filePath)
        else:
            print('Invalid path : {0}'.format(filePath))
            print('Load aborted !')
            return False

        # Apply nodes data.
        nodesData = data['NODES']
        nodesName = nodesData.keys()
        allNodes = []
        
        
        
        def convert_to_correct_type(obj):
            if isinstance(obj, str):
                try:
                    # Try converting to integer
                    return int(obj)
                except ValueError:
                    try:
                        # Try converting to float
                        return float(obj)
                    except ValueError:
                        if obj.lower() == 'true':
                            return True
                        elif obj.lower() == 'false':
                            return False
                        else:
                            return obj
            elif isinstance(obj, dict):
                return {key: convert_to_correct_type(value) for key, value in obj.items()}
            elif isinstance(obj, list):
                return [convert_to_correct_type(item) for item in obj]
            else:
                return obj

        for name in nodesName:
            preset = nodesData[name]['preset']
            position = nodesData[name]['position']
            position = QtCore.QPointF(position[0], position[1])
            alternate = nodesData[name]['alternate']
            
            nodeType = ''.join(name.split('_')[:-1])
            
            node = self.createNode(name=name,
                                preset=preset,
                                position=position,
                                alternate=alternate, skipCreateNodeSignal=False,
                                displayText=nodesData[name]['textbox_text'],createdFromNodzLoading=True,
                                nodeInfo = self.nodeInfo[nodeType])
            if 'textboxheight' in nodesData[name]:
                node.textboxheight = nodesData[name]['textboxheight'] #type:ignore
            if 'displayName' in nodesData[name]:
                node.displayName = nodesData[name]['displayName'] #type:ignore
            if 'alternateFillColor' in nodesData[name]:
                node.alternateFillColor = nodesData[name]['alternateFillColor'] #type:ignore
                #Force the change in the node:
                node.BGcolChanged() #type:ignore
                node.update() #type:ignore
            
            #move to exact position
            node.setX(nodesData[name]['position'][0]-node.baseWidth/2)
            node.setY(nodesData[name]['position'][1]-node.height/2)
            
            #Restore MDA data
            if name in data['NODES_MDA']:
                if data['NODES_MDA'] is not None:
                    correctedmdadata = convert_to_correct_type(data['NODES_MDA'][name])
                    for attr in data['NODES_MDA'][name]:
                        setattr(node.mdaData,attr,correctedmdadata[attr]) #type:ignore

                
            #Restore MM-config-changing data
            if name in data['NODES_MMCONFIGCHANGE']:
                if 'MMconfigInfo' in vars(node):
                    if data['NODES_MMCONFIGCHANGE'] is not None:
                        mmconfigchangedata = data['NODES_MMCONFIGCHANGE'][name]
                        node.MMconfigInfo.config_string_storage = mmconfigchangedata #type:ignore
                
            #Restore scoring-data:
            if name in data['NODES_SCORING_ANALYSIS']:
                if 'scoring_analysis_currentData' in vars(node):
                    if data['NODES_SCORING_ANALYSIS'] is not None:
                        node.scoring_analysis_currentData = data['NODES_SCORING_ANALYSIS'][name] #type:ignore
            if name in data['NODES_SCORING_VISUALISATION']:
                if 'scoring_visualisation_currentData' in vars(node):
                    if data['NODES_SCORING_VISUALISATION'] is not None:
                        node.scoring_visualisation_currentData = data['NODES_SCORING_VISUALISATION'][name] #type:ignore
            if name in data['NODES_SCORING_SCORING']:
                if 'scoring_scoring_currentData' in vars(node):
                    if data['NODES_SCORING_SCORING'] is not None:
                        node.scoring_scoring_currentData = data['NODES_SCORING_SCORING'][name] #type:ignore
                        
            
            if name in data['NODES_SCORING_END']:
                if 'scoring_end_currentData' in vars(node):
                    if len(data['NODES_SCORING_END'][name]['Variables']) > 0:
                        node.scoring_end_currentData = data['NODES_SCORING_END'][name] #type:ignore
                        
            if name in data['NODES_VISUALISATION']:
                if 'visualisation_currentData' in vars(node):
                    if data['NODES_VISUALISATION'] is not None:
                        node.visualisation_currentData = data['NODES_VISUALISATION'][name] #type:ignore
            
            if name in data['NODES_RT_ANALYSIS']:
                if 'real_time_analysis_currentData' in vars(node):
                    if data['NODES_RT_ANALYSIS'] is not None:
                        node.real_time_analysis_currentData = data['NODES_RT_ANALYSIS'][name] #type:ignore
            #Do an emit after full loading:
            self.signal_NodeFullyInitialisedNodeItself.emit(node)
            allNodes.append(node)
            
        self.scene().update()
        self._focus()
        
        # Apply connections data.
        connectionsData = data['CONNECTIONS']

        for connection in connectionsData:
            source = connection[0]
            sourceNode = source.split('.')[0]
            sourceAttr = source.split('.')[1]

            target = connection[1]
            targetNode = target.split('.')[0]
            targetAttr = target.split('.')[1]

            self.createConnection(sourceNode, sourceAttr,
                                  targetNode, targetAttr, plugSkipSignalEmit=True, socketSkipSignalEmit=False)

        self.scene().update()
        
        self._focus()
        
        #Update the decisionwidget after loading the scoringEnd node:
        node.flowChart.decisionWidget.updateAllDecisions() #type:ignore

        # Emit signal.
        self.signal_GraphLoaded.emit()

    def loadGraph(self, filePath='path'):
        """
        Get all the stored info from the .json file at the given location
        and recreate the graph as saved.

        :type  filePath: str.
        :param filePath: The path where you want to load your graph from.

        """
        # Load data.
        if os.path.exists(filePath):
            data = utils._loadData(filePath=filePath)
        else:
            print('Invalid path : {0}'.format(filePath))
            print('Load aborted !')
            return False

        # Apply nodes data.
        nodesData = data['NODES']
        nodesName = nodesData.keys()

        for name in nodesName:
            preset = nodesData[name]['preset']
            position = nodesData[name]['position']
            position = QtCore.QPointF(position[0], position[1])
            alternate = nodesData[name]['alternate']

            node = self.createNode(name=name,
                                   preset=preset,
                                   position=position,
                                   alternate=alternate)

            # Apply attributes data.
            attrsData = nodesData[name]['attributes']

            for attrData in attrsData:
                index = attrsData.index(attrData)
                name = attrData['name']
                plug = attrData['plug']
                socket = attrData['socket']
                preset = attrData['preset']
                bottomAttr = attrData['bottomAttr']
                topAttr = attrData['topAttr']
                dataType = attrData['dataType']
                plugMaxConnections = attrData['plugMaxConnections']
                socketMaxConnections = attrData['socketMaxConnections']

                # un-serialize data type if needed
                if (isinstance(dataType, str) and dataType.find('<') == 0):
                    dataType = eval(str(dataType.split('\'')[1]))

                self.createAttribute(node=node,
                                    name=name,
                                    index=index,
                                    preset=preset,
                                    plug=plug,
                                    socket=socket,
                                    dataType=dataType,
                                    plugMaxConnections=plugMaxConnections,
                                    socketMaxConnections=socketMaxConnections
                                    )

        self.scene().update()
        
        # Apply connections data.
        connectionsData = data['CONNECTIONS']

        for connection in connectionsData:
            source = connection[0]
            sourceNode = source.split('.')[0]
            sourceAttr = source.split('.')[1]

            target = connection[1]
            targetNode = target.split('.')[0]
            targetAttr = target.split('.')[1]

            self.createConnection(sourceNode, sourceAttr,
                                targetNode, targetAttr)

        self.scene().update()
        
        self._focus()

        # Emit signal.
        self.signal_GraphLoaded.emit()

    def createConnection(self, sourceNode, sourceAttr, targetNode, targetAttr,plugSkipSignalEmit=False,socketSkipSignalEmit=False):
        """
        Create a manual connection.

        :type  sourceNode: str.
        :param sourceNode: Node that emits the connection.

        :type  sourceAttr: str.
        :param sourceAttr: Attribute that emits the connection.

        :type  targetNode: str.
        :param targetNode: Node that receives the connection.

        :type  targetAttr: str.
        :param targetAttr: Attribute that receives the connection.

        """
        if sourceAttr in self.scene().nodes[sourceNode].plugs: #type:ignore
            plug = self.scene().nodes[sourceNode].plugs[sourceAttr] #type:ignore
        elif sourceAttr in self.scene().nodes[sourceNode].bottomAttrs: #type:ignore
            plug = self.scene().nodes[sourceNode].bottomAttrs[sourceAttr] #type:ignore
        
        if targetAttr in self.scene().nodes[targetNode].sockets: #type:ignore
            socket = self.scene().nodes[targetNode].sockets[targetAttr] #type:ignore
        elif targetAttr in self.scene().nodes[targetNode].topAttrs: #type:ignore
            socket = self.scene().nodes[targetNode].topAttrs[targetAttr] #type:ignore

        connection = ConnectionItem(plug.center(), socket.center(), plug, socket)

        connection.plugNode = plug.parentItem().name
        connection.plugAttr = plug.attribute
        connection.socketNode = socket.parentItem().name
        connection.socketAttr = socket.attribute

        plug.connect(socket, connection,skipSignalEmit = plugSkipSignalEmit)
        socket.connect(plug, connection,skipSignalEmit = socketSkipSignalEmit)

        connection.updatePath()

        self.scene().addItem(connection)

        return connection

    def evaluateGraph(self):
        """
        Create a list of connection tuples.
        [("sourceNode.attribute", "TargetNode.attribute"), ...]

        """
        scene = self.scene()

        data = list()

        for item in scene.items():
            if isinstance(item, ConnectionItem):
                connection = item

                data.append(connection._outputConnectionData())

        # Emit Signal
        self.signal_GraphEvaluated.emit()

        return data

    def clearGraph(self):
        """
        Clear the graph.

        """
        self.scene().clear()
        self.scene().nodes = dict() #type:ignore

        # Emit signal.
        self.signal_GraphCleared.emit()

    ##################################################################
    # END API
    ##################################################################


class NodeScene(QtWidgets.QGraphicsScene):

    """
    The scene displaying all the nodes.

    """
    signal_NodeMoved = QtCore.pyqtSignal(str, object)

    def __init__(self, parent):
        """
        Initialize the class.

        """
        super(NodeScene, self).__init__(parent)

        # General.
        self.gridSize = parent.config['grid_size']

        # Nodes storage.
        self.nodes = dict()

    def dragEnterEvent(self, event):
        """
        Make the dragging of nodes into the scene possible.

        """
        event.setDropAction(QtCore.Qt.MoveAction) #type:ignore
        event.accept()

    def dragMoveEvent(self, event):
        """
        Make the dragging of nodes into the scene possible.

        """
        event.setDropAction(QtCore.Qt.MoveAction) #type:ignore
        event.accept()

    def dropEvent(self, event):
        """
        Create a node from the dropped item.

        """
        # Emit signal.
        self.signal_Dropped.emit(event.scenePos()) #type:ignore

        event.accept()

    def drawBackground(self, painter, rect):
        """
        Draw a grid in the background.

        """
        config = self.parent().config #type:ignore

        self._brush = QtGui.QBrush()
        self._brush.setStyle(QtCore.Qt.SolidPattern) #type:ignore
        self._brush.setColor(utils._convertDataToColor(config['bg_color']))

        painter.fillRect(rect, self._brush)

        if self.views()[0].gridVisToggle:
            leftLine = rect.left() - rect.left() % self.gridSize
            topLine = rect.top() - rect.top() % self.gridSize
            lines = list()

            i = int(leftLine)
            while i < int(rect.right()):
                lines.append(QtCore.QLineF(i, rect.top(), i, rect.bottom()))
                i += self.gridSize

            u = int(topLine)
            while u < int(rect.bottom()):
                lines.append(QtCore.QLineF(rect.left(), u, rect.right(), u))
                u += self.gridSize

            self.pen = QtGui.QPen()
            self.pen.setColor(utils._convertDataToColor(config['grid_color']))
            self.pen.setWidth(0)
            painter.setPen(self.pen)
            painter.drawLines(lines) #type:ignore
        
        self.drawBoundingBoxes(painter)

    def drawBoundingBoxes(self,painter):
        """
        Draw colorful bounding boxes around the scoring nodes and around the acquiring nodes
        """
        
        NodeListConnectionsScore = utils.findConnectedToNode(self.parent().evaluateGraph(),'scoringStart',[]) #type:ignore
        
        if len(NodeListConnectionsScore) > 0:
            self.drawBoundingBox(painter,NodeListConnectionsScore,boundingBorder=35,solidPaint=[50,150,50,75],linePaint=[0,200,0,200])
            
        NodeListConnectionsAcq = utils.findConnectedToNode(self.parent().evaluateGraph(),'acqStart',[]) #type:ignore
        
        if len(NodeListConnectionsAcq) > 0:
            self.drawBoundingBox(painter,NodeListConnectionsAcq,boundingBorder=35,solidPaint=[150,150,30,75],linePaint=[150,150,0,200])
        
    def drawBoundingBox(self,painter,NodeListConnections,boundingBorder=25,solidPaint=[50,150,50,75],linePaint=[0,200,0,200]):
        
        #We then look at all these nodes and find their top-left and bottom-right points:
        minleft = 1e8
        mintop = 1e8
        minright = -1e8
        minbottom = -1e8
        boundingBorder = boundingBorder
        for wantedNode in NodeListConnections:
            for node in self.parent().nodes: #type:ignore
                if node.name == wantedNode:
                    left = node.scenePos().x()
                    top = node.scenePos().y()
                    right = node.scenePos().x()+node.boundingRect().width()
                    bottom = node.scenePos().y()+node.boundingRect().height()
                    if left < minleft:
                        minleft = left
                    if top < mintop:
                        mintop = top
                    if right > minright:
                        minright = right
                    if bottom > minbottom:
                        minbottom = bottom
        
        #We draw a bounding box around the scoring nodes:
        painter.setBrush(utils._convertDataToColor(solidPaint))
        painter.setPen(utils._convertDataToColor(linePaint))

        painter.drawRoundedRect(int(minleft-boundingBorder), 
                                int(mintop-boundingBorder-10),
                                int(minright-minleft+boundingBorder*2),
                                int(minbottom-mintop+boundingBorder*2),
                                int(boundingBorder),
                                int(boundingBorder))

    def updateScene(self):
        """
        Update the connections position.

        """
        for connection in [i for i in self.items() if isinstance(i, ConnectionItem)]:
            connection.target_point = connection.target.center() #type:ignore
            connection.source_point = connection.source.center() #type:ignore
            connection.updatePath()


class NodeItem(QtWidgets.QGraphicsItem):

    """
    A graphic representation of a node containing attributes.

    """

    def __init__(self, name, alternate, preset, config, displayName = None, displayText = None, textbox=True, alternateFillColor = None, nodeInfo=None):
        """
        Initialize the class.

        :type  name: str.
        :param name: The name of the node. The name has to be unique
                    as it is used as a key to store the node object.

        :type  alternate: bool.
        :param alternate: The attribute color alternate state, if True,
                        every 2 attribute the color will be slightly
                        darker.

        :type  preset: str.
        :param preset: The name of graphical preset in the config file.

        """
        super(NodeItem, self).__init__()

        self.setZValue(1)

        # Storage
        self.name = name
        self.alternate = alternate
        self.nodePreset = preset
        self.attrPreset = None
        
        #Added by KM
        self.displayText = displayText
        self.displayName = displayName
        self.callAction = None
        self.callActionRelatedObject = None
        self.n_connect_at_start = 0 #number of others connected at start (which should all be finished!)        
        self.n_connect_at_start_finished = 0 #number of others connected at start which are finished already
        self.scoring_analysis_currentData = {}
        self.scoring_scoring_currentData = {}
        self.scoring_visualisation_currentData = {}
        self.alternateFillColor = alternateFillColor
        
        self.scoring_end_currentData = {}
        self.scoring_end_currentData['Variables'] = {}
        
        self.visualisation_currentData = {}
        self.real_time_analysis_currentData = {}
        
        self.status = 'idle' #status should be 'idle','running','finished'

        # Attributes storage.
        self.attrs = list()
        self.attrsData = dict()
        self.attrCount = 0
        self.currentDataType = None

        self.plugs = dict()
        self.sockets = dict()
        self.bottomAttrs = dict()
        self.topAttrs = dict()

        # Methods.
        import copy
        self.config = config.copy()
        if nodeInfo is not None:
            #Adjust the width
            self.config['node_width'] *= float(nodeInfo['NodeSize'])/100
        self._createStyle(self.config)
        
        self.textbox_exists = textbox
        self.textboxheight = 50
        self.textboxborder = 5
        self.mdaData = None

    def updateDisplayText(self,new_display_text):
        
        
        h = self.textboxheight
        
        td = QTextDocument()
        textToDisplay = ''
        if new_display_text is not None:
            textToDisplay = new_display_text
        td.setHtml(textToDisplay)
                
        #Change the textbox height so the text fits, capped at 300 px
        self.textboxheight = int(min(300,max(50,td.size().height())))
        self.update()
        
        self.scene().parent().editNodeDisplayText(self, newDisplayText=new_display_text) #type:ignore

    def changeName(self,new_name):
        if new_name != self.name:
            #Also update in self.scene(): (adding both new one and removing old one)
            self.scene().nodes[new_name] = self.scene().nodes[self.name] #type:ignore
            self.scene().nodes.pop(self.name) #type:ignore
            #And update the node name:
            self.name = new_name
    
    def changePreset(self,new_preset):
        self.nodePreset = new_preset
        self._createStyle(self.config)
    
    def changeDisplayName(self,new_Displayname):
        self.displayName = new_Displayname

    def oneConnectionAtStartProvidesData(self):
        #At the moment, does the same as oneConnectionAtStartIsFinished, but might be changedl ater:
        self.oneConnectionAtStartIsFinished()

    def oneConnectionAtStartIsFinished(self):
        self.n_connect_at_start_finished += 1
        logging.debug('Called oneConnectionAtStartIsFinished')
        logging.debug(f"n_connect_at_start_finished: {self.n_connect_at_start_finished}")
        logging.debug(f"n_connect_at_start: {self.n_connect_at_start}")
        if self.n_connect_at_start_finished == self.n_connect_at_start:
            self.n_connect_at_start_finished = 0 #to allow for looping :)
            logging.debug('All connections at start are finished')
            logging.info(f"Starting call action of node with name: {self.name}")
            self.status = 'running'
            self.update()
            if self.callAction is not None:
                if self.callActionRelatedObject is not None:
                    self.callAction(self.callActionRelatedObject) #type:ignore
                else:
                    self.callAction(self)

    def finishedmda(self):
        self.status = 'finished'
        self.update()
        logging.info('MDA finished within node')
        #MDA data is stored as self.mdaData.data
        logging.info(self.name)

    @property
    def height(self):
        """
        Increment the final height of the node every time an attribute
        is created.

        """
        
        nrSocketAttrs = 0
        nrPlugAttrs = 0
        nrBottomAttrs = 0
        nrTopAttrs = 0
        #loop over all attrs and add to socket or plug:
        for attr in self.attrs:
            if self.attrsData[attr]['plug']:
                nrPlugAttrs += 1
            elif self.attrsData[attr]['socket']:
                nrSocketAttrs += 1
            elif self.attrsData[attr]['bottomAttr']:
                nrBottomAttrs += 1
            elif self.attrsData[attr]['topAttr']:
                nrTopAttrs += 1
        
        if (nrPlugAttrs+nrSocketAttrs) > 0:
            return (self.baseHeight +
                    self.attrHeight * max(nrSocketAttrs, nrPlugAttrs) +
                    (1 if nrBottomAttrs >= 1 else 0) * self.bottomAttrHeight +
                    2*self.border +
                    #self.radius + 
                    self.textbox_exists * (self.textboxheight +
                    self.textboxborder * 2))
        else:
            try:
                return (self.baseHeight +
                        # self.border +
                        # 2 * self.radius + 
                        self.textbox_exists * (self.textboxheight +
                        self.textboxborder * 2))
            except:
                return 20

    @property
    def pen(self):
        """
        Return the pen based on the selection state of the node.

        """
        if self.isSelected():
            return self._penSel
        else:
            return self._pen

    def _createStyle(self, config):
        """
        Read the node style from the configuration file.

        """
        self.setAcceptHoverEvents(True)
        self.setFlag(QtWidgets.QGraphicsItem.ItemIsMovable) #type:ignore
        self.setFlag(QtWidgets.QGraphicsItem.ItemIsSelectable) #type:ignore

        # Dimensions.
        self.baseWidth  = config['node_width']
        self.baseHeight = config['node_height']
        self.attrHeight = config['node_attr_height']
        self.bottomAttrHeight = self.attrHeight*.8
        self.border = config['node_border']
        self.radius = config['node_radius']

        self.nodeCenter = QtCore.QPointF()
        self.nodeCenter.setX(self.baseWidth / 2.0)
        self.nodeCenter.setY(self.height / 2.0)

        self._brush = QtGui.QBrush()
        self._brush.setStyle(QtCore.Qt.SolidPattern) #type:ignore
        if self.alternateFillColor == None:
            self._brush.setColor(utils._convertDataToColor(config[self.nodePreset]['bg']))
        else:
            self._brush.setColor(utils._convertDataToColor(self.alternateFillColor))

        self._pen = QtGui.QPen()
        self._pen.setStyle(QtCore.Qt.SolidLine) #type:ignore
        self._pen.setWidth(self.border)
        self._pen.setColor(utils._convertDataToColor(config[self.nodePreset]['border']))

        self._penSel = QtGui.QPen()
        self._penSel.setStyle(QtCore.Qt.SolidLine) #type:ignore
        self._penSel.setWidth(self.border)
        self._penSel.setColor(utils._convertDataToColor(config[self.nodePreset]['border_sel']))

        self._textPen = QtGui.QPen()
        self._textPen.setStyle(QtCore.Qt.SolidLine) #type:ignore
        self._textPen.setColor(utils._convertDataToColor(config[self.nodePreset]['text']))

        self._nodeTextFont = QtGui.QFont(config['node_font'], config['node_font_size'], QtGui.QFont.Bold)
        self._attrTextFont = QtGui.QFont(config['attr_font'], config['attr_font_size'], QtGui.QFont.Normal)

        self._attrBrush = QtGui.QBrush()
        self._attrBrush.setStyle(QtCore.Qt.SolidPattern) #type:ignore

        self._attrBrushAlt = QtGui.QBrush()
        self._attrBrushAlt.setStyle(QtCore.Qt.SolidPattern) #type:ignore

        self._attrPen = QtGui.QPen()
        self._attrPen.setStyle(QtCore.Qt.SolidLine) #type:ignore

    def BGcolChanged(self):
        self._createStyle(self.config)

    def _createAttribute(self, name, index, preset, plug, socket, bottomAttr, topAttr, dataType, plugMaxConnections, socketMaxConnections):
        """
        Create an attribute by expanding the node, adding a label and
        connection items.

        :type  name: str.
        :param name: The name of the attribute. The name has to be
                    unique as it is used as a key to store the node
                    object.

        :type  index: int.
        :param index: The index of the attribute in the node.

        :type  preset: str.
        :param preset: The name of graphical preset in the config file.

        :type  plug: bool.
        :param plug: Whether or not this attribute can emit connections.

        :type  socket: bool.
        :param socket: Whether or not this attribute can receive
                    connections.

        :type  dataType: type.
        :param dataType: Type of the data represented by this attribute
                        in order to highlight attributes of the same
                        type while performing a connection.

        """
        if name in self.attrs:
            print('An attribute with the same name already exists on this node : {0}'.format(name))
            print('Attribute creation aborted !')
            return

        self.attrPreset = preset

        # Create a plug connection item.
        if plug:
            plugInst = PlugItem(parent=self,
                                attribute=name,
                                index=self.attrCount,
                                preset=preset,
                                dataType=dataType,
                                maxConnections=plugMaxConnections)

            self.plugs[name] = plugInst

        # Create a socket connection item.
        if socket:
            socketInst = SocketItem(parent=self,
                                    attribute=name,
                                    index=self.attrCount,
                                    preset=preset,
                                    dataType=dataType,
                                    maxConnections=socketMaxConnections)

            self.sockets[name] = socketInst

        #Create a bottom attribution item
        if bottomAttr:
            bottomAttrInst = BottomAttrItem(parent=self,
                                            attribute=name,
                                            index=self.attrCount,
                                            preset=preset,
                                            dataType=dataType,
                                            maxConnections=socketMaxConnections)

            self.bottomAttrs[name] = bottomAttrInst

        #Create a bottom attribution item
        if topAttr:
            topAttrInst = TopAttrItem(parent=self,
                                            attribute=name,
                                            index=self.attrCount,
                                            preset=preset,
                                            dataType=dataType,
                                            maxConnections=socketMaxConnections)

            self.topAttrs[name] = topAttrInst

        self.attrCount += 1

        # Add the attribute based on its index.
        if index == -1 or index > self.attrCount:
            self.attrs.append(name)
        else:
            self.attrs.insert(index, name)

        # Store attr data.
        self.attrsData[name] = {'name': name,
                                'socket': socket,
                                'plug': plug,
                                'bottomAttr': bottomAttr,
                                'topAttr': topAttr,
                                'preset': preset,
                                'dataType': dataType,
                                'plugMaxConnections': plugMaxConnections,
                                'socketMaxConnections': socketMaxConnections
                                }

        # Update node height.
        self.update()

    def _deleteAttribute(self, index):
        """
        Remove an attribute by reducing the node, removing the label
        and the connection items.

        :type  index: int.
        :param index: The index of the attribute in the node.

        """
        name = self.attrs[index]

        # Remove socket and its connections.
        if name in self.sockets.keys():
            for connection in self.sockets[name].connections:
                connection._remove()

            self.scene().removeItem(self.sockets[name])
            self.sockets.pop(name)

        # Remove plug and its connections.
        if name in self.plugs.keys():
            for connection in self.plugs[name].connections:
                connection._remove()
            for connection in self.bottomAttrs[name].connections:
                connection._remove()
            for connection in self.topAttrs[name].connections:
                connection._remove()

            self.scene().removeItem(self.plugs[name])
            self.plugs.pop(name)

        # Reduce node height.
        if self.attrCount > 0:
            self.attrCount -= 1

        # Remove attribute from node.
        if name in self.attrs:
            self.attrs.remove(name)

        self.update()

    def _remove(self):
        """
        Remove this node instance from the scene.

        Make sure that all the connections to this node are also removed
        in the process

        """
        self.scene().nodes.pop(self.name) #type:ignore

        # Remove all sockets connections.
        for socket in self.sockets.values():
            while len(socket.connections)>0:
                socket.connections[0]._remove()

        # Remove all plugs connections.
        for plug in self.plugs.values():
            while len(plug.connections)>0:
                plug.connections[0]._remove()


        for bottomAttr in self.bottomAttrs.values():
            while len(bottomAttr.connections)>0:
                bottomAttr.connections[0]._remove()
        for topAttr in self.topAttrs.values():
            while len(topAttr.connections)>0:
                topAttr.connections[0]._remove()


        # Remove node.
        scene = self.scene()
        scene.removeItem(self)
        scene.update()

    def boundingRect(self):
        """
        The bounding rect based on the width and height variables.

        """
        rect = QtCore.QRect(0, 0, int(self.baseWidth), int(self.height))
        rect = QtCore.QRectF(rect)
        return rect

    def shape(self):
        """
        The shape of the item.

        """
        path = QtGui.QPainterPath()
        path.addRect(self.boundingRect())
        return path

    def paint(self, painter, option, widget):
        """
        Paint the node and attributes.

        """
        self.painter = painter
        # Node base.
        painter.setBrush(self._brush)
        painter.setPen(self.pen)

        painter.drawRoundedRect(0, 0,
                                int(self.baseWidth),
                                int(self.height),
                                int(self.radius),
                                int(self.radius))

        # Node label.
        painter.setPen(self._textPen)
        painter.setFont(self._nodeTextFont)


        if self.displayName == None:
            painter.setPen(QColor(255,255,255))
            metrics = QtGui.QFontMetrics(painter.font())
            text_width = metrics.boundingRect(self.name).width() + 14
            text_height = metrics.boundingRect(self.name).height() + 14
            margin = (text_width - self.baseWidth) * 0.5
            textRect = QtCore.QRect(int(-margin),
                                    int(-text_height),
                                    int(text_width),
                                    int(text_height))
            painter.drawText(textRect,
                            QtCore.Qt.AlignCenter, #type:ignore
                            self.name)
        else:
            painter.setPen(QColor(255,255,255))
            metrics = QtGui.QFontMetrics(painter.font())
            text_width = metrics.boundingRect(self.displayName).width() + 14
            text_height = metrics.boundingRect(self.displayName).height() + 14
            margin = (text_width - self.baseWidth) * 0.5
            textRect = QtCore.QRect(int(-margin),
                                    int(-text_height),
                                    int(text_width),
                                    int(text_height))
            painter.drawText(textRect,
                            QtCore.Qt.AlignCenter, #type:ignore
                            self.displayName)

        #Draw the icon
        from PyQt5.QtGui import QPixmap
        if self.status == 'idle':
            self.icon = QPixmap('GUI/Icons/node_pending.png')
        elif self.status == 'running':
            self.icon = QPixmap('GUI/Icons/node_inProgress.png')
        elif self.status == 'finished':
            self.icon = QPixmap('GUI/Icons/node_completed.png')
        else:
            self.icon = QPixmap('GUI/Icons/node_error.png')
            
        iconSize = 15
        painter.drawPixmap(int(-margin-iconSize+14-5-iconSize/2), int(-text_height+iconSize*.66), int(iconSize), int(iconSize), self.icon)
        
        # statusRect = QtCore.QRect(int(-margin),
        #                         int(-text_height-text_height/2),
        #                         int(text_width),
        #                         int(text_height))
        # painter.drawText(statusRect,
        #                 QtCore.Qt.AlignCenter, #type:ignore
        #                 self.status)

        #Draw the textbox
        self.drawTextbox(painter)
        
        # Draw the attributes.
        offsetLeft = 0
        offsetRight = 0
        nrBottomAttrs = 0
        nrTopAttrs = 0
        for attr in self.attrs:
            nodzInst = self.scene().views()[0]
            config = nodzInst.config

            attrData = self.attrsData[attr]
            name = attr

            preset = attrData['preset']
            
            xoffset = 0
            offset = offsetLeft
            width = (self.baseWidth - self.border)
            height = self.attrHeight
            if attrData['plug'] and not attrData['socket']:
                xoffset = (self.baseWidth - self.border)/2
                offset = offsetRight
            if not (attrData['socket'] and attrData['plug']):
                width /= 2
                
            if attrData['bottomAttr']:
                bottomAttrOffset = 17
                #Determine width,height, xoffset, yoffset:
                totalNrBottomAttrs = len(self.bottomAttrs)
                width = (self.baseWidth - 2*self.border)/totalNrBottomAttrs-bottomAttrOffset
                height = self.bottomAttrHeight
                xmidpoint = (nrBottomAttrs/totalNrBottomAttrs+(1/totalNrBottomAttrs)/2)*self.baseWidth
                xoffset = xmidpoint - width/2
                # xoffset = nrBottomAttrs*(self.baseWidth/totalNrBottomAttrs)+bottomAttrOffset/2
                offset = max(offsetLeft,offsetRight)+5
                #Increment counter
                nrBottomAttrs += 1
            if attrData['topAttr']:
                #Determine width,height, xoffset, yoffset:
                totalNrTopAttrs = len(self.topAttrs)
                width = 0#(self.baseWidth - 2*self.border)/totalNrTopAttrs-topAttrs
                height = 0#self.bottomAttrHeight
                xmidpoint = 0#(nrBottomAttrs/totalNrBottomAttrs+(1/totalNrBottomAttrs)/2)*self.baseWidth
                xoffset = 0#xmidpoint - width/2
                # xoffset = nrBottomAttrs*(self.baseWidth/totalNrBottomAttrs)+bottomAttrOffset/2
                offset = 0#max(offsetLeft,offsetRight)+5
                #Increment counter
                nrTopAttrs += 1
            
            if not attrData['bottomAttr'] and not attrData['topAttr']:
                # Attribute rect.
                rect = QtCore.QRect(int(self.border / 2+xoffset),
                                    int(self.baseHeight + offset + self.textbox_exists*(self.textboxheight+self.textboxborder*2)),
                                    int(width),
                                    int(height))
                # Attribute base.
                
                self._attrBrush.setColor(utils._convertDataToColor(self.config[self.nodePreset]['bg']).darker(175))
                if self.alternate:
                    self._attrBrushAlt.setColor(utils._convertDataToColor(self.config[self.nodePreset]['bg']).darker(225))
                # self._attrBrush.setColor(utils._convertDataToColor(config[preset]['bg']))
                # if self.alternate:
                #     self._attrBrushAlt.setColor(utils._convertDataToColor(config[preset]['bg'], True, config['alternate_value']))

                self._attrPen.setColor(utils._convertDataToColor([0, 0, 0, 0]))
                painter.setPen(self._attrPen)
                if attrData['socket']:
                    painter.setBrush(self._attrBrush)
                    if (offset / self.attrHeight) % 2:
                        painter.setBrush(self._attrBrushAlt)
                elif attrData['plug']:
                    painter.setBrush(self._attrBrushAlt)
                    if (offset / self.attrHeight) % 2:
                        painter.setBrush(self._attrBrush)
                else:
                    painter.setBrush(self._attrBrush)
                painter.drawRect(rect)
            
            elif attrData['bottomAttr']:
                self._attrBrush.setColor(utils._convertDataToColor(self.config[self.nodePreset]['bg']).darker(175))
                painter.setBrush(self._attrBrush)
                
                self._attrPen.setColor(utils._convertDataToColor([0, 0, 0, 0]))
                painter.setPen(self._attrPen)
                    
                painter.drawRoundedRect(
                                    int(self.border / 2+xoffset),
                                    int(self.baseHeight + offset + self.textbox_exists*(self.textboxheight+self.textboxborder*2)),
                                    int(width),
                                    int(height),
                                    int(0),
                                    int(0))
                
                #Create a rect to later draw the text, but we don't draw this rect...
                rect = QtCore.QRect(int(self.border / 2+xoffset),
                                    int(self.baseHeight + offset + self.textbox_exists*(self.textboxheight+self.textboxborder*2)),
                                    int(width),
                                    int(height))

            # Attribute label.
            painter.setPen(utils._convertDataToColor(config[preset]['text']))
            painter.setFont(self._attrTextFont)

            # Search non-connectable attributes.
            if nodzInst.drawingConnection:
                if self == nodzInst.currentHoveredNode:
                    if (attrData['dataType'] != nodzInst.sourceSlot.dataType or
                        (nodzInst.sourceSlot.slotType == 'plug' and attrData['socket'] == False or
                         nodzInst.sourceSlot.slotType == 'socket' and attrData['plug'] == False)):
                        # Set non-connectable attributes color.
                        painter.setPen(utils._convertDataToColor(config['non_connectable_color']))
            if not attrData['topAttr']:
                textRect = QtCore.QRect(rect.left() + self.radius,
                                        rect.top(),
                                        rect.width() - 2*self.radius,
                                        rect.height())
                
                halignment = QtCore.Qt.AlignLeft #type:ignore
                valignment = QtCore.Qt.AlignVCenter #type:ignore
                if attrData['bottomAttr']:
                    halignment = QtCore.Qt.AlignCenter #type:ignore
                    valignment = QtCore.Qt.AlignTop #type:ignore
                    textRect = QtCore.QRect(rect.left() + self.radius,
                                        rect.top()-3,
                                        rect.width() - 2*self.radius,
                                        rect.height())
                elif attrData['plug'] and not attrData['socket']:
                    halignment = QtCore.Qt.AlignRight #type:ignore
                    valignment = QtCore.Qt.AlignVCenter #type:ignore
                
                painter.drawText(textRect, halignment | valignment, name) #type:ignore
                
                if not attrData['bottomAttr'] and not attrData['topAttr']:
                    if attrData['plug'] and not attrData['socket']:
                        offsetRight += self.attrHeight
                    else:
                        offsetLeft += self.attrHeight
                    
                    
        #At the end: draw the nodz again, but only the border:
        
        self.painter = painter
        # Node base.
        brush2 = QtGui.QBrush()
        brush2.setColor(utils._convertDataToColor([0, 0, 0, 0]))
        painter.setBrush(brush2)
        painter.setPen(self.pen)

        painter.drawRoundedRect(0, 0,
                                int(self.baseWidth),
                                int(self.height),
                                int(self.radius),
                                int(self.radius))
        

    def drawTextbox(self,painter):
        # Draw rectangle
        w = (self.baseWidth - self.border)-5*2
        h = self.textboxheight
        rectpos = [self.textboxborder,self.textboxborder,int(w),int(h)]
        textboxColor = self._brush.color().lighter(200)
        painter.setBrush(textboxColor)
        painter.setPen(QColor(0, 0, 0, 0))
        painter.drawRoundedRect(*rectpos,self.radius/2,self.radius/2)
        
        # # Draw text
        font = QFont('Arial', 12)
        painter.setFont(font)
        painter.setPen(QColor(0, 0, 0))
        
        td = QTextDocument()
        textToDisplay = ''
        # if self.nodePreset is not None:
        #     textToDisplay = textToDisplay+self.nodePreset
        #     if self.nodePreset == 'node_imaging':
        #         textToDisplay = textToDisplay+"<br><img src=\"GUI\\nodz\\nodz2.png\" width=\"50\" height = \"50\">"
        if self.displayText is not None:
            textToDisplay = self.displayText
        
        td.setHtml(textToDisplay)
        ctx = QAbstractTextDocumentLayout.PaintContext()
        ctx.clip = QRectF(0,0, w, h)
        
        #Move painter
        painter.translate(rectpos[0],rectpos[1])
        
        td.documentLayout().draw(painter, ctx)
        
        self.textbox = td
        
        #Move painter back
        painter.translate(-rectpos[0],-rectpos[1])

    def mousePressEvent(self, event):
        """
        Keep the selected node on top of the others.

        """
        nodes = self.scene().nodes #type:ignore
        for node in nodes.values():
            node.setZValue(1)

        for item in self.scene().items():
            if isinstance(item, ConnectionItem):
                item.setZValue(1)

        self.setZValue(2)

        super(NodeItem, self).mousePressEvent(event)

    def mouseDoubleClickEvent(self, event):
        """
        Emit a signal.
        """
        
        # if self.nodePreset == 'acquisition':
        #     dialog = nodz_openMDADialog(parentData=self.scene().views()[0])
        #     if dialog.exec_() == QDialog.Accepted:
        #         print(dialog.getInputs())
        #     print('hmm')
        # else:
        #     #Open a Dialog on double click
        #     dialog = FoVFindImaging_singleCh_configs(parentData=self.scene().views()[0])
        #     #Get the outputs from the dialog
        #     if dialog.exec_() == QDialog.Accepted:
        #         print(dialog.getInputs())
        #     #     text, combo_value = dialog.getInputs()
        #     #     print("Text:", text)
        #     #     print("Combo Value:", combo_value)
        
        # # #Update the node text from this dialog output:
        # self.scene().parent().editNodeDisplayText(self, newDisplayText=str(dialog.getInputs())) #type:ignore
        
        super(NodeItem, self).mouseDoubleClickEvent(event)
        self.scene().parent().signal_NodeDoubleClicked.emit(self.name,event.pos())#type:ignore

    def mouseMoveEvent(self, event):
        """
        .

        """
        if self.scene().views()[0].gridVisToggle:
            if self.scene().views()[0].gridSnapToggle or self.scene().views()[0]._nodeSnap:
                gridSize = self.scene().gridSize#type:ignore

                currentPos = self.mapToScene(event.pos().x() - self.baseWidth / 2,
                                             event.pos().y() - self.height / 2)

                snap_x = (round(currentPos.x() / gridSize) * gridSize) - gridSize/4
                snap_y = (round(currentPos.y() / gridSize) * gridSize) - gridSize/4
                snap_pos = QtCore.QPointF(snap_x, snap_y)
                self.setPos(snap_pos)

                self.scene().updateScene() #type:ignore
            else:
                self.scene().updateScene() #type:ignore
                super(NodeItem, self).mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        """
        .

        """
        # Emit node moved signal.
        self.scene().signal_NodeMoved.emit(self.name, self.pos()) #type:ignore
        super(NodeItem, self).mouseReleaseEvent(event)

    def hoverLeaveEvent(self, event):
        """
        .

        """
        nodzInst = self.scene().views()[0]

        for item in nodzInst.scene().items():
            if isinstance(item, ConnectionItem):
                item.setZValue(0)

        super(NodeItem, self).hoverLeaveEvent(event)


class SlotItem(QtWidgets.QGraphicsItem):

    """
    The base class for graphics item representing attributes hook.

    """

    def __init__(self, parent, attribute, preset, index, dataType, maxConnections):
        """
        Initialize the class.

        :param parent: The parent item of the slot.
        :type  parent: QtWidgets.QGraphicsItem instance.

        :param attribute: The attribute associated to the slot.
        :type  attribute: String.

        :param index: int.
        :type  index: The index of the attribute in the node.

        :type  preset: str.
        :param preset: The name of graphical preset in the config file.

        :param dataType: The data type associated to the attribute.
        :type  dataType: Type.

        """
        super(SlotItem, self).__init__(parent)

        # Status.
        self.setAcceptHoverEvents(True)

        # Storage.
        self.slotType = None
        self.attribute = attribute
        self.preset = preset
        self.index = index
        self.dataType = dataType

        # Style.
        self.brush = QtGui.QBrush()
        self.brush.setStyle(QtCore.Qt.SolidPattern) #type:ignore

        self.pen = QtGui.QPen()
        self.pen.setStyle(QtCore.Qt.SolidLine) #type:ignore

        # Connections storage.
        self.connected_slots = list()
        self.newConnection = None
        self.connections = list()
        self.maxConnections = maxConnections

    def accepts(self, slot_item):
        """
        Only accepts plug items that belong to other nodes, and only if the max connections count is not reached yet.

        """
        # no plug on plug or socket on socket
        hasPlugItem = isinstance(self, PlugItem) or isinstance(slot_item, PlugItem)
        hasSocketItem = isinstance(self, SocketItem) or isinstance(slot_item, SocketItem)
        if not (hasPlugItem and hasSocketItem):
            return False

        # no self connection
        if self.parentItem() == slot_item.parentItem():
            return False

        #no more than maxConnections
        if self.maxConnections>0 and len(self.connected_slots) >= self.maxConnections:
            return False

        #no connection with different types
        if slot_item.dataType != self.dataType:
            return False

        #otherwize, all fine.
        return True

    def mousePressEvent(self, event):
        """
        Start the connection process.

        """
        if event.button() == QtCore.Qt.LeftButton: #type:ignore
            self.newConnection = ConnectionItem(self.center(),
                                                self.mapToScene(event.pos()),
                                                self,
                                                None)

            self.connections.append(self.newConnection)
            self.scene().addItem(self.newConnection)

            nodzInst = self.scene().views()[0]
            nodzInst.drawingConnection = True
            nodzInst.sourceSlot = self
            nodzInst.currentDataType = self.dataType
        else:
            super(SlotItem, self).mousePressEvent(event)

    def mouseMoveEvent(self, event):
        """
        Update the new connection's end point position.

        """
        nodzInst = self.scene().views()[0]
        config = nodzInst.config
        if nodzInst.drawingConnection:
            mbb = utils._createPointerBoundingBox(pointerPos=event.scenePos().toPoint(),
                                                  bbSize=config['mouse_bounding_box'])

            # Get nodes in pointer's bounding box.
            targets = self.scene().items(mbb)

            if any(isinstance(target, NodeItem) for target in targets):
                if self.parentItem() not in targets:
                    for target in targets:
                        if isinstance(target, NodeItem):
                            nodzInst.currentHoveredNode = target
            else:
                nodzInst.currentHoveredNode = None

            # Set connection's end point.
            self.newConnection.target_point = self.mapToScene(event.pos()) #type:ignore
            self.newConnection.updatePath() #type:ignore
        else:
            super(SlotItem, self).mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        """
        Apply the connection if target_slot is valid.

        """
        nodzInst = self.scene().views()[0]
        if event.button() == QtCore.Qt.LeftButton: #type:ignore
            nodzInst.drawingConnection = False
            nodzInst.currentDataType = None


            #KM: Added a small square around cursor when selecting a slot, makes it easier to select it
            pos = event.scenePos().toPoint()
            # Define the error radius
            error_radius = 10
            # Create a QRectF with a slightly larger area around the scene position
            search_rect = QRectF(pos.x() - error_radius, pos.y() - error_radius,
                                    2 * error_radius, 2 * error_radius)
            # Get the items within the search rectangle
            items_in_rect = self.scene().items(search_rect)

            #Select a slotItem in this target - assuming only one.
            target = None
            for item in items_in_rect:
                if isinstance(item, SlotItem):
                    target = item
                    pass

            # target = self.scene().itemAt(event.scenePos().toPoint(), QtGui.QTransform())

            if not isinstance(target, SlotItem):
                self.newConnection._remove() #type:ignore
                super(SlotItem, self).mouseReleaseEvent(event)
                return

            if target.accepts(self):
                self.newConnection.target = target #type:ignore
                self.newConnection.source = self #type:ignore
                self.newConnection.target_point = target.center() #type:ignore
                self.newConnection.source_point = self.center() #type:ignore

                # Perform the ConnectionItem.
                self.connect(target, self.newConnection) #type:ignore
                target.connect(self, self.newConnection) #type:ignore

                self.newConnection.updatePath() #type:ignore
            else:
                self.newConnection._remove() #type:ignore
        else:
            super(SlotItem, self).mouseReleaseEvent(event)

        nodzInst.currentHoveredNode = None

    def shape(self):
        """
        The shape of the Slot is a circle.

        """
        path = QtGui.QPainterPath()
        path.addRect(self.boundingRect())
        return path

    def paint(self, painter, option, widget):
        """
        Paint the Slot.

        """
        painter.setBrush(self.brush)
        painter.setPen(self.pen)

        nodzInst = self.scene().views()[0]
        config = nodzInst.config
        if nodzInst.drawingConnection:
            if self.parentItem() == nodzInst.currentHoveredNode:
                painter.setBrush(utils._convertDataToColor(config['non_connectable_color']))
                if (self.slotType == nodzInst.sourceSlot.slotType or (self.slotType != nodzInst.sourceSlot.slotType and self.dataType != nodzInst.sourceSlot.dataType)):
                    painter.setBrush(utils._convertDataToColor(config['non_connectable_color']))
                else:
                    _penValid = QtGui.QPen()
                    _penValid.setStyle(QtCore.Qt.SolidLine) #type:ignore
                    _penValid.setWidth(2)
                    _penValid.setColor(QtGui.QColor(255, 255, 255, 255))
                    painter.setPen(_penValid)
                    painter.setBrush(self.brush)

        painter.drawEllipse(self.boundingRect())

    def center(self):
        """
        Return The center of the Slot.

        """
        rect = self.boundingRect()
        center = QtCore.QPointF(rect.x() + rect.width() * 0.5,
                                rect.y() + rect.height() * 0.5)

        return self.mapToScene(center)


class PlugItem(SlotItem):

    """
    A graphics item representing an attribute out hook.

    """

    def __init__(self, parent, attribute, index, preset, dataType, maxConnections):
        """
        Initialize the class.

        :param parent: The parent item of the slot.
        :type  parent: QtWidgets.QGraphicsItem instance.

        :param attribute: The attribute associated to the slot.
        :type  attribute: String.

        :param index: int.
        :type  index: The index of the attribute in the node.

        :type  preset: str.
        :param preset: The name of graphical preset in the config file.

        :param dataType: The data type associated to the attribute.
        :type  dataType: Type.

        """
        super(PlugItem, self).__init__(parent, attribute, preset, index, dataType, maxConnections)

        # Storage.
        self.attributte = attribute
        self.preset = preset
        self.slotType = 'plug'

        # Methods.
        self._createStyle(parent)

    def _createStyle(self, parent):
        """
        Read the attribute style from the configuration file.

        """
        config = parent.scene().views()[0].config
        self.brush = QtGui.QBrush()
        self.brush.setStyle(QtCore.Qt.SolidPattern) #type:ignore
        self.brush.setColor(utils._convertDataToColor(config[self.preset]['plug']))

    def boundingRect(self):
        """
        The bounding rect based on the width and height variables.

        """
        width = height = self.parentItem().attrHeight / 2.0 #type:ignore

        nodzInst = self.scene().views()[0]
        config = nodzInst.config

        #Find how many attributes the parentItem has that are plugs before this index:
        nrPlugsParentBeforeThis = 0
        for attr in self.parentItem().attrs: #type:ignore
            if self.parentItem().attrs.index(attr)<self.parentItem().attrs.index(self.attribute): #type:ignore
                if self.parentItem().attrsData[attr]['plug']: #type:ignore
                    nrPlugsParentBeforeThis += 1


        x = self.parentItem().baseWidth - (width / 2.0) #type:ignore
        y = (self.parentItem().baseHeight - config['node_radius'] + #type:ignore
            #self.parentItem().attrHeight / 4 + #type:ignore
            (nrPlugsParentBeforeThis+0.5) * self.parentItem().attrHeight +  #type:ignore
            self.parentItem().textbox_exists*(self.parentItem().textboxheight+self.parentItem().textboxborder*2)) #type:ignore

        rect = QtCore.QRectF(QtCore.QRect(int(x), int(y), int(width), int(height)))
        return rect

    def connect(self, socket_item, connection,skipSignalEmit=False):
        """
        Connect to the given socket_item.

        """
        if self.maxConnections>0 and len(self.connected_slots) >= self.maxConnections:
            # Already connected.
            self.connections[self.maxConnections-1]._remove()


        nodzInst = self.scene().views()[0]
        if not skipSignalEmit:
            nodzInst.signal_PlugConnectedStartConnection.emit(connection.plugNode, connection.plugAttr, connection.socketNode, connection.socketAttr)

        # Populate connection.
        connection.socketItem = socket_item
        connection.plugNode = self.parentItem().name #type:ignore
        connection.plugAttr = self.attribute

        # Add socket to connected slots.
        if socket_item in self.connected_slots:
            self.connected_slots.remove(socket_item)
        self.connected_slots.append(socket_item)

        # Add connection.
        if connection not in self.connections:
            self.connections.append(connection)

        # Emit signal.
        if not skipSignalEmit:
            nodzInst.signal_PlugConnected.emit(connection.plugNode, connection.plugAttr, connection.socketNode, connection.socketAttr)

    def disconnect(self, connection):
        """
        Disconnect the given connection from this plug item.

        """
        # Emit signal.
        nodzInst = self.scene().views()[0]
        nodzInst.signal_PlugDisconnected.emit(connection.plugNode, connection.plugAttr, connection.socketNode, connection.socketAttr)

        # Remove connected socket from plug
        if connection.socketItem in self.connected_slots:
            self.connected_slots.remove(connection.socketItem)
        # Remove connection
        self.connections.remove(connection)

class SocketItem(SlotItem):

    """
    A graphics item representing an attribute in hook.

    """

    def __init__(self, parent, attribute, index, preset, dataType, maxConnections):
        """
        Initialize the socket.

        :param parent: The parent item of the slot.
        :type  parent: QtWidgets.QGraphicsItem instance.

        :param attribute: The attribute associated to the slot.
        :type  attribute: String.

        :param index: int.
        :type  index: The index of the attribute in the node.

        :type  preset: str.
        :param preset: The name of graphical preset in the config file.

        :param dataType: The data type associated to the attribute.
        :type  dataType: Type.

        """
        super(SocketItem, self).__init__(parent, attribute, preset, index, dataType, maxConnections)

        # Storage.
        self.attributte = attribute
        self.preset = preset
        self.slotType = 'socket'

        # Methods.
        self._createStyle(parent)

    def _createStyle(self, parent):
        """
        Read the attribute style from the configuration file.

        """
        config = parent.scene().views()[0].config
        self.brush = QtGui.QBrush()
        self.brush.setStyle(QtCore.Qt.SolidPattern) #type:ignore
        self.brush.setColor(utils._convertDataToColor(config[self.preset]['socket']))

    def boundingRect(self):
        """
        The bounding rect based on the width and height variables.

        """
        width = height = self.parentItem().attrHeight / 2.0 #type:ignore

        nodzInst = self.scene().views()[0]
        config = nodzInst.config
        
        
        #Find how many attributes the parentItem has that are sockets before this index:
        nrSocketsParentBeforeThis = 0
        for attr in self.parentItem().attrs: #type:ignore
            if self.parentItem().attrs.index(attr)<self.parentItem().attrs.index(self.attribute): #type:ignore
                if self.parentItem().attrsData[attr]['socket']: #type:ignore
                    nrSocketsParentBeforeThis += 1

        x = - width / 2.0
        y = (self.parentItem().baseHeight - config['node_radius'] + #type:ignore
            #(self.parentItem().attrHeight/4) + #type:ignore
            (nrSocketsParentBeforeThis+0.5) * self.parentItem().attrHeight +  #type:ignore
            self.parentItem().textbox_exists*(self.parentItem().textboxheight+self.parentItem().textboxborder*2)) #type:ignore

        rect = QtCore.QRectF(QtCore.QRect(int(x), int(y), int(width), int(height)))
        return rect

    def connect(self, plug_item, connection, skipSignalEmit=False):
        """
        Connect to the given plug item.

        """
        if self.maxConnections>0 and len(self.connected_slots) >= self.maxConnections:
            # Already connected.
            self.connections[self.maxConnections-1]._remove()

        nodzInst = self.scene().views()[0]
        if not skipSignalEmit:
            nodzInst.signal_SocketConnectedStartConnection.emit(connection.plugNode, connection.plugAttr, connection.socketNode, connection.socketAttr)

        # Populate connection.
        connection.plugItem = plug_item
        connection.socketNode = self.parentItem().name #type:ignore
        connection.socketAttr = self.attribute

        # Add plug to connected slots.
        self.connected_slots.append(plug_item)

        # Add connection.
        if connection not in self.connections:
            self.connections.append(connection)

        # Emit signal.
        if not skipSignalEmit:
            nodzInst.signal_SocketConnected.emit(connection.plugNode, connection.plugAttr, connection.socketNode, connection.socketAttr)

    def disconnect(self, connection):
        """
        Disconnect the given connection from this socket item.

        """
        # Emit signal.
        nodzInst = self.scene().views()[0]
        nodzInst.signal_SocketDisconnected.emit(connection.plugNode, connection.plugAttr, connection.socketNode, connection.socketAttr)

        # Remove connected plugs
        if connection.plugItem in self.connected_slots:
            self.connected_slots.remove(connection.plugItem)
        # Remove connections
        self.connections.remove(connection)

class BottomAttrItem(PlugItem):
    def __init__(self, parent, attribute, index, preset, dataType, maxConnections):
        super(BottomAttrItem, self).__init__(parent, attribute, index, preset, dataType, maxConnections)
        print('bottom attr created')
        self.attributte = attribute
        self.preset = preset
        self.slotType = 'bottomAttr'
    
    def boundingRect(self):
        """
        The bounding rect based on the width and height variables.

        """
        width = height = self.parentItem().attrHeight / 2.0 #type:ignore

        nodzInst = self.scene().views()[0]
        config = nodzInst.config

        #Find how many attributes the parentItem has that are BottomAttr before this index:
        nrBottomAttrParentBeforeThis = 0
        for attr in self.parentItem().attrs: #type:ignore
            if self.parentItem().attrs.index(attr)<self.parentItem().attrs.index(self.attribute): #type:ignore
                if self.parentItem().attrsData[attr]['bottomAttr']: #type:ignore
                    nrBottomAttrParentBeforeThis += 1

        totalnrBottomAttrs = len(self.parentItem().bottomAttrs) #type:ignore
        distanceFromLeft = nrBottomAttrParentBeforeThis/totalnrBottomAttrs+(1/totalnrBottomAttrs)/2

        x = distanceFromLeft*self.parentItem().baseWidth-2*self.parentItem().border #type:ignore
        y = (self.parentItem().boundingRect().height()-config['node_radius']) #type:ignore

        rect = QtCore.QRectF(QtCore.QRect(int(x), int(y), int(width), int(height)))
        return rect

class TopAttrItem(SocketItem):
    def __init__(self, parent, attribute, index, preset, dataType, maxConnections):
        super().__init__(parent, attribute, index, preset, dataType, maxConnections)
        print('top attr created')
        self.slotType = 'topAttr'
        
    def boundingRect(self):
        """
        The bounding rect based on the width and height variables.

        """
        width = height = self.parentItem().attrHeight / 2.0 #type:ignore

        nodzInst = self.scene().views()[0]
        config = nodzInst.config

        #Find how many attributes the parentItem has that are TopAttr before this index:
        nrTopAttrParentBeforeThis = 0
        for attr in self.parentItem().attrs: #type:ignore
            if self.parentItem().attrs.index(attr)<self.parentItem().attrs.index(self.attribute): #type:ignore
                if self.parentItem().attrsData[attr]['topAttr']: #type:ignore
                    nrTopAttrParentBeforeThis += 1

        totalnrTopAttrs = len(self.parentItem().topAttrs) #type:ignore
        distanceFromLeft = nrTopAttrParentBeforeThis/totalnrTopAttrs+(1/totalnrTopAttrs)/2

        x = distanceFromLeft*self.parentItem().baseWidth-2*self.parentItem().border #type:ignore
        y = -config['node_radius']#(self.parentItem().boundingRect().height()-self.parentItem().radius/2) #type:ignore

        rect = QtCore.QRectF(QtCore.QRect(int(x), int(y), int(width), int(height)))
        return rect
        
class ConnectionItem(QtWidgets.QGraphicsPathItem):

    """
    A graphics path representing a connection between two attributes.

    """

    def __init__(self, source_point, target_point, source, target):
        """
        Initialize the class.

        :param sourcePoint: Source position of the connection.
        :type  sourcePoint: QPoint.

        :param targetPoint: Target position of the connection
        :type  targetPoint: QPoint.

        :param source: Source item (plug or socket).
        :type  source: class.

        :param target: Target item (plug or socket).
        :type  target: class.

        """
        super(ConnectionItem, self).__init__()

        self.setZValue(1)

        # Storage.
        self.socketNode = None
        self.socketAttr = None
        self.plugNode = None
        self.plugAttr = None

        self.source_point = source_point
        self.target_point = target_point
        self.source = source
        self.target = target

        self.plugItem = None
        self.socketItem = None

        self.movable_point = None

        self.data = tuple() #type:ignore

        # Methods.
        self._createStyle()

    def _createStyle(self):
        """
        Read the connection style from the configuration file.

        """
        config = self.source.scene().views()[0].config #type:ignore
        self.setAcceptHoverEvents(True)
        self.setZValue(-1)

        self._pen = QtGui.QPen(utils._convertDataToColor(config['connection_color']))
        self._pen.setWidth(config['connection_width'])

    def _outputConnectionData(self):
        """
        .

        """
        return ("{0}.{1}".format(self.plugNode, self.plugAttr),
                "{0}.{1}".format(self.socketNode, self.socketAttr))

    def mousePressEvent(self, event):
        """
        Snap the Connection to the mouse.

        """
        nodzInst = self.scene().views()[0]

        for item in nodzInst.scene().items():
            if isinstance(item, ConnectionItem):
                item.setZValue(0)

        nodzInst.drawingConnection = True

        d_to_target = (event.pos() - self.target_point).manhattanLength()
        d_to_source = (event.pos() - self.source_point).manhattanLength()
        if d_to_target < d_to_source:
            self.target_point = event.pos()
            self.movable_point = 'target_point'
            self.target.disconnect(self) #type:ignore
            self.target = None
            nodzInst.sourceSlot = self.source
        else:
            self.source_point = event.pos()
            self.movable_point = 'source_point'
            self.source.disconnect(self) #type:ignore
            self.source = None
            nodzInst.sourceSlot = self.target

        self.updatePath()

    def mouseMoveEvent(self, event):
        """
        Move the Connection with the mouse.

        """
        nodzInst = self.scene().views()[0]
        config = nodzInst.config

        mbb = utils._createPointerBoundingBox(pointerPos=event.scenePos().toPoint(),
                                            bbSize=config['mouse_bounding_box'])

        # Get nodes in pointer's bounding box.
        targets = self.scene().items(mbb)

        if any(isinstance(target, NodeItem) for target in targets):

            if nodzInst.sourceSlot.parentItem() not in targets:
                for target in targets:
                    if isinstance(target, NodeItem):
                        nodzInst.currentHoveredNode = target
        else:
            nodzInst.currentHoveredNode = None

        if self.movable_point == 'target_point':
            self.target_point = event.pos()
        else:
            self.source_point = event.pos()

        self.updatePath()

    def mouseReleaseEvent(self, event):
        """
        Create a Connection if possible, otherwise delete it.

        """
        nodzInst = self.scene().views()[0]
        nodzInst.drawingConnection = False

        slot = self.scene().itemAt(event.scenePos().toPoint(), QtGui.QTransform())

        if not isinstance(slot, SlotItem):
            self._remove()
            self.updatePath()
            super(ConnectionItem, self).mouseReleaseEvent(event)
            return

        if self.movable_point == 'target_point':
            if slot.accepts(self.source):
                # Plug reconnection.
                self.target = slot
                self.target_point = slot.center()
                plug = self.source
                socket = self.target

                # Reconnect.
                socket.connect(plug, self) #type:ignore

                self.updatePath()
            else:
                self._remove()

        else:
            if slot.accepts(self.target):
                # Socket Reconnection
                self.source = slot
                self.source_point = slot.center()
                socket = self.target
                plug = self.source

                # Reconnect.
                plug.connect(socket, self) #type:ignore

                self.updatePath()
            else:
                self._remove()

    def _remove(self):
        """
        Remove this Connection from the scene.

        """
        if self.source is not None:
            self.source.disconnect(self) #type:ignore
        if self.target is not None:
            self.target.disconnect(self) #type:ignore

        scene = self.scene()
        scene.removeItem(self)
        scene.update()

    def updatePath(self):
        """
        Update the path.

        """
        self.setPen(self._pen)

        path = QtGui.QPainterPath()
        path.moveTo(self.source_point)
        if self.source.slotType != 'bottomAttr' and self.source.slotType != 'topAttr': #type:ignore
            dx = (self.target_point.x() - self.source_point.x()) * 0.5
            dy = self.target_point.y() - self.source_point.y()
            ctrl1 = QtCore.QPointF(self.source_point.x() + dx, self.source_point.y() + dy * 0)
            ctrl2 = QtCore.QPointF(self.source_point.x() + dx, self.source_point.y() + dy * 1)
        else:
            dx = (self.target_point.x() - self.source_point.x())
            dy = (self.target_point.y() - self.source_point.y()) * 0.5
            ctrl1 = QtCore.QPointF(self.source_point.x() + dx * 0, self.source_point.y() + dy)
            ctrl2 = QtCore.QPointF(self.source_point.x() + dx * 1, self.source_point.y() + dy)
        path.cubicTo(ctrl1, ctrl2, self.target_point)

        self.setPath(path)

