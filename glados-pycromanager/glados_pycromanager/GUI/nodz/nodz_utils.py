import os
import json
import re
from PyQt5 import QtCore, QtGui


def _convertDataToColor(data=None, alternate=False, av=20):
    """
    Convert a list of 3 (rgb) or 4(rgba) values from the configuration
    file into a QColor.

    :param data: Input color.
    :type  data: List.

    :param alternate: Whether or not this is an alternate color.
    :type  alternate: Bool.

    :param av: Alternate value.
    :type  av: Int.

    """
    # rgb
    if len(data) == 3: #type:ignore
        color = QtGui.QColor(data[0], data[1], data[2]) #type:ignore
        if alternate:
            mult = _generateAlternateColorMultiplier(color, av)


            color = QtGui.QColor(max(0, data[0]-(av*mult)), max(0, data[1]-(av*mult)), max(0, data[2]-(av*mult))) #type:ignore
        return color

    # rgba
    elif len(data) == 4: #type:ignore
        color = QtGui.QColor(data[0], data[1], data[2], data[3]) #type:ignore
        if alternate:
            mult = _generateAlternateColorMultiplier(color, av)
            color = QtGui.QColor(int(max(0, data[0]-(av*mult))), int(max(0, data[1]-(av*mult))), int(max(0, data[2]-(av*mult))), int(data[3])) #type:ignore
        return color

    # wrong
    else:
        print('Color from configuration is not recognized : ', data)
        print('Can only be [R, G, B] or [R, G, B, A]')
        print('Using default color !')
        color = QtGui.QColor(120, 120, 120)
        if alternate:
            color = QtGui.QColor(120-av, 120-av, 120-av)
        return color

def _generateAlternateColorMultiplier(color, av):
    """
    Generate a multiplier based on the input color lighness to increase
    the alternate value for dark color or reduce it for bright colors.

    :param color: Input color.
    :type  color: QColor.

    :param av: Alternate value.
    :type  av: Int.

    """
    lightness = color.lightness()
    mult = float(lightness)/255

    return mult

def _createPointerBoundingBox(pointerPos, bbSize):
    """
    generate a bounding box around the pointer.

    :param pointerPos: Pointer position.
    :type  pointerPos: QPoint.

    :param bbSize: Width and Height of the bounding box.
    :type  bbSize: Int.

    """
    # Create pointer's bounding box.
    point = pointerPos

    mbbPos = point
    point.setX(int(point.x() - bbSize / 2))
    point.setY(int(point.y() - bbSize / 2))

    size = QtCore.QSize(bbSize, bbSize)
    bb = QtCore.QRect(mbbPos, size)
    bb = QtCore.QRectF(bb)

    return bb

def _swapListIndices(inputList, oldIndex, newIndex):
    """
    Simply swap 2 indices in a the specified list.

    :param inputList: List that contains the elements to swap.
    :type  inputList: List.

    :param oldIndex: Index of the element to move.
    :type  oldIndex: Int.

    :param newIndex: Destination index of the element.
    :type  newIndex: Int.

    """
    if oldIndex == -1:
        oldIndex = len(inputList)-1


    if newIndex == -1:
        newIndex = len(inputList)

    value = inputList[oldIndex]
    inputList.pop(oldIndex)
    inputList.insert(newIndex, value)

# IO
def _loadConfig(filePath):
    """
    Read the configuration file and strips out comments.

    :param filePath: File path.
    :type  filePath: Str.

    """
    with open(filePath, 'r') as myfile:
        fileString = myfile.read()

        # remove comments
        cleanString = re.sub('//.*?\n|/\*.*?\*/', '', fileString, re.S)

        data = json.loads(cleanString)

    return data

def _saveData(filePath, data):
    """
    save data as a .json file

    :param filePath: Path of the .json file.
    :type  filePath: Str.

    :param data: Data you want to save.
    :type  data: Dict or List.

    """
    f = open(filePath, "w")
    f.write(json.dumps(data,
                       sort_keys = True,
                       indent = 4,
                       ensure_ascii=False))
    f.close()

    print("Data successfully saved !")

def _loadData(filePath):
    """
    load data from a .json file.

    :param filePath: Path of the .json file.
    :type  filePath: Str.

    """
    with open(filePath) as json_file:
        j_data = json.load(json_file)

    json_file.close()

    print("Data successfully loaded !")
    return j_data



def findConnectedToNode(graphInfo,nodeName,fullNodeList,upstream=True,downstream=True):
    """
    Recursively search the connections of a node in a graph
    Example: NodeListConnections = findConnectedToNode(self.parent().evaluateGraph(),'scoringStart',[])

    :param graphInfo: List of connection info (.evaluateGraph()). Each connection is a tuple with
        the format (origin node name, destination node name)
    :type  graphInfo: List of tuples.

    :param nodeName: Name of the node to find the connected nodes from.
    :type  nodeName: Str.

    :param fullNodeList: List of nodes already found and their connected nodes.
    :type  fullNodeList: List of Str.

    :return: List of nodes connected to the given nodeName.
    :rtype:  List of Str.
    """

    for connection in graphInfo:
        if upstream:
            if nodeName in connection[0]:
                if connection[1].split('.')[0] not in fullNodeList:
                    fullNodeList.append(connection[1].split('.')[0])
                    fullNodeList = findConnectedToNode(graphInfo,connection[1].split('.')[0],fullNodeList,upstream=upstream,downstream=downstream)
        if downstream:
            if nodeName in connection[1]:
                if connection[0].split('.')[0] not in fullNodeList:
                    fullNodeList.append(connection[0].split('.')[0])
                    fullNodeList = findConnectedToNode(graphInfo,connection[0].split('.')[0],fullNodeList,upstream=upstream,downstream=downstream)
    
    return fullNodeList

def findNodeByName(flowchart,nodeName):
    for nodes in flowchart.nodes:
        if nodes.name == nodeName:
            return nodes

def getConnectedNodes(node, connectiontype):
    connectedNodes = []
    if connectiontype == 'topAttr':
        for attr in node.topAttrs:
            if len(node.topAttrs[attr].connections)>0:
                for connection in node.topAttrs[attr].connections:
                    connectedNodeName = connection.plugNode
                    connectedNode = findNodeByName(node.flowChart,connectedNodeName)
                    connectedNodes.append(connectedNode)
    elif connectiontype == 'bottomAttr':
        for attr in node.bottomAttrs:
            if len(node.bottomAttrs[attr].connections)>0:
                for connection in node.bottomAttrs[attr].connections:
                    connectedNodeName = connection.socketNode
                    connectedNode = findNodeByName(node.flowChart,connectedNodeName)
                    connectedNodes.append(connectedNode)
    return connectedNodes
                    