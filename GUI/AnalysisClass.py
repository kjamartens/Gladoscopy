import numpy as np
from PyQt5.QtCore import pyqtSignal, QThread
import random
import napari
from napari.qt import thread_worker
import time
import queue
from PyQt5.QtWidgets import QMainWindow
from pycromanager import core
from magicgui import magicgui
from qtpy.QtWidgets import QMainWindow, QVBoxLayout, QWidget
import sys
from custom_widget_ui import Ui_CustomDockWidget  # Import the generated UI module

def drawRandomOverlay(layer_name):
    # create a list of polygons
    p = [(random.randint(0, 1024), random.randint(0, 1024)) for _ in range(4)]

    polygons = [np.array([[p[0][0], p[1][1]], [p[1][0], p[1][1]], [p[1][0], p[0][1]], [p[0][0], p[0][1]]])]
    
    #See if layer exists
    shapeLayer = getLayerIdFromName(layer_name)
    if not shapeLayer:
        print('First ever shapelayer')
        shapes_layer = napariViewer.add_shapes(
            name=layer_name,
        )
    else:
        #delete shapelayer
        napariViewer.layers[shapeLayer[0]].data = []
        shapes_layer = napariViewer.layers[shapeLayer[0]]

    # add polygons
    shapes_layer.add( #type:ignore
        polygons,
        shape_type='polygon',
        edge_width=5,
        edge_color='yellow',
        face_color='red',
    )
def getLayerIdFromName(layer_name):
    ImageLayer = [i for i, layer in enumerate(napariViewer.layers) if hasattr(layer, '_name') and layer._name == layer_name]
    return ImageLayer
  
def drawTextOverlay(layer_name,textv):
    polygons = [np.array([[0, 0], [10, 10], [20, 20], [30, 30]])]
    #See if layer exists
    shapeLayer = getLayerIdFromName(layer_name)

    textstring = {
        'string': 'TEST',
        'anchor': 'upper_left',
        'translation': [0, 0],
        'size': 100,
        'color': 'red',
    }
    
    #Add a layer if it doesn't exist yet
    if not shapeLayer:
        shapes_layer = napariViewer.add_shapes(
            polygons,
            shape_type='polygon',
            edge_width=5,
            edge_color='yellow',
            face_color='red',
            name = layer_name,
            text = textstring
        )
    else:
        #delete info in the layer and go from there
        napariViewer.layers[shapeLayer[0]].data = []
        shapes_layer = napariViewer.layers[shapeLayer[0]]
        # shapes_layer.text.values[0] = str(textv)

 
#This code gets some image and does some analysis on this
class AnalysisThread(QThread):
    # Define analysis_done_signal as a class attribute, shared among all instances of AnalysisThread class
    # Create a signal to communicate between threads
    analysis_done_signal = pyqtSignal(object)
    
    def __init__(self,overlayInfo='RandomOverlay'):
        super().__init__()	
        self.overlayInfo=overlayInfo
    
    def run(self):
        while True:
            #Run analysis on the image from the queue
            self.analysis_result = self.runAnalysis(image_queue_analysis.get(),self.overlayInfo)
            self.analysis_done_signal.emit(self.analysis_result)
    
    def runAnalysis(self,image,overlayInfo):
        #Do analysis here - the info in analysisResult will be passed to Visualise_Analysis_results
        if overlayInfo == 'RandomOverlay':
            analysisResult = 1
        else:
            analysisResult = 2
        return analysisResult

    def Visualise_Analysis_results(self,analysis_result):
        # print(analysis_result)
        if analysis_result == 1:
            print('RandomOverlay')
        else:
            print('Other overlay')
        # drawTextOverlay('Text_overlay',analysis_result)
        # drawRandomOverlay('live_overlay')
    

def create_analysis_thread(image_queue_transfer,shared_data,overlayInfo = 'RandomOverlay'):
    global image_queue_analysis, napariViewer
    napariViewer = shared_data.napariViewer
    image_queue_analysis = image_queue_transfer
    #Instantiate an analysis thread and add a signal
    analysis_thread = AnalysisThread(overlayInfo=overlayInfo)
    analysis_thread.analysis_done_signal.connect(analysis_thread.Visualise_Analysis_results)
    
    #Append it to the list of analysisThreads
    shared_data.analysisThreads.append(analysis_thread)
    
    return analysis_thread