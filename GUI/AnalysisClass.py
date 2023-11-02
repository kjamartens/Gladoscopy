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
from napari.layers import Shapes

#Class for overlays and their update and such
class napariOverlay():
    def __init__(self,layer_name='new Layer'):
        self.layer_name = layer_name
        self.layer = napariViewer.add_shapes(
                name=self.layer_name,
            )
    
    #Update the name of the overlay
    def changeName(self,new_name):
        self.layer_name = new_name
        self.layer.name = self.layer_name
    
    def drawRandomOverlay(self):
        # create a list of polygons
        p = [(random.randint(0, 1024), random.randint(0, 1024)) for _ in range(4)]

        polygons = [np.array([[p[0][0], p[1][1]], [p[1][0], p[1][1]], [p[1][0], p[0][1]], [p[0][0], p[0][1]]])]
        
        #See if layer exists
        if not self.layer:
            print('First ever shapelayer')
            self.layer = napariViewer.add_shapes(
                name=self.layer_name,
            )
        else:
            #delete shapelayer
            self.layer.data = []

        # add polygons
        self.layer.add( #type:ignore
            polygons,
            shape_type='polygon',
            edge_width=5,
            edge_color='yellow',
            face_color='red',
        )
    
    
    def drawTextOverlay_init(self):
        polygons = [
            np.array([[225, 146], [283, 146], [283, 211], [225, 211]])
        ]
        # create properties
        properties = {'value': [0]}

        text_properties = {
            'text': '{value:0.1f}%',
            # 'text': 'Test',
            'anchor': 'upper_left',
            'translation': [-5, 0],
            'size': 8,
            'color': 'green',
        }
        #Remove old layer
        napariViewer.layers.remove(self.layer)
        # new layer with polygons and text
        self.layer = napariViewer.add_shapes(
            polygons,
            properties=properties,
            shape_type='polygon',
            edge_color='transparent',
            face_color='transparent',
            text=text_properties,
            name=self.layer_name,
        )
        # change some properties of the layer
        self.layer.opacity = 1
    
    
    def drawTextOverlay(self,text='',pos=[0,0],textCol='red',textSize=8):
        # Update the properties - this contains the text
        new_properties = {
            'text': [text]
        }
        self.layer.properties = new_properties
        #update the polygon - this contains the position
        pseudo_size = 0.1
        polygons = [np.array([[pos[0], pos[1]], [pos[0]+pseudo_size, pos[1]], [pos[0]+pseudo_size, pos[1]+pseudo_size], [pos[0], pos[1]+pseudo_size]])]
        #Remove the old polygon
        self.layer.data = []
        # add the new polygon
        self.layer.add(
            polygons,
            shape_type='polygon',
            edge_color='transparent',
            face_color='transparent',
        )
        #Update the text surrounding the invisible shape
        text_properties = {
            'text': '{text}',
            'anchor': 'upper_left',
            'translation': [0, 0],
            'size': textSize,
            'color': textCol,
        }
        self.layer.text = text_properties
        

#This code gets some image and does some analysis on this
class AnalysisThread(QThread):
    # Define analysis_done_signal as a class attribute, shared among all instances of AnalysisThread class
    # Create a signal to communicate between threads
    analysis_done_signal = pyqtSignal(object)
    
    def __init__(self,analysisInfo='Random',visualisationInfo='Random'):
        super().__init__()	
        self.analysisInfo=analysisInfo
        self.visualisationInfo = visualisationInfo
        #Create an empty overlay
        if visualisationInfo != None:
            self.napariOverlay = napariOverlay()
            self.initialise_napariLayer()
            # self.napariOverlay.changeName('RandomOverlay')
    
    def run(self):
        while True:
            #Run analysis on the image from the queue
            self.analysis_result = self.runAnalysis(image_queue_analysis.get())
            self.analysis_done_signal.emit(self.analysis_result)
    
    #Analysis is split into two parts: obtaining the analysis result and displaying this.
    #Here, we calculate the analysis result based on the analysisInfo
    def runAnalysis(self,image):
        #Do analysis here - the info in analysisResult will be passed to Visualise_Analysis_results
        if self.analysisInfo == 'AvgGrayValueText':
            time.sleep(0.5)
            analysisResult = self.calcAnalysisAvgGrayValue(image)
        else:
            analysisResult = None
        return analysisResult

    #And here we perform the visualisation - can be fully separate from performing tha analysis
    #Initialisation is called upon creation
    def initialise_napariLayer(self):
        if self.visualisationInfo == 'AvgGrayValueText':
            self.initAvgGrayValueText()
    #Update ir called every time the analysis is done
    def update_napariLayer(self,analysis_result):
        # print(analysis_result)
        if self.visualisationInfo == 'AvgGrayValueText':
            self.visualiseAvgGrayValueText(analysis_result)
        # drawTextOverlay('Text_overlay',analysis_result)
        # drawRandomOverlay('live_overlay')
    
    
    """
    Average gray value calculation and display
    """
    #Calculating average gray value of an image
    def calcAnalysisAvgGrayValue(self,image):
        return np.mean(np.mean(image))
    
    def visualiseAvgGrayValueText(self,analysis_result):
        self.napariOverlay.drawTextOverlay(text='Mean gray value: {:.0f}'.format(analysis_result),pos=[0,0],textCol='white',textSize=12)
        
    def initAvgGrayValueText(self):
        self.napariOverlay.changeName('Average Gray Value')
        self.napariOverlay.drawTextOverlay_init()
        
        
        
        
        
def create_analysis_thread(image_queue_transfer,shared_data,analysisInfo = 'Random',visualisationInfo = None):
    global image_queue_analysis, napariViewer
    napariViewer = shared_data.napariViewer
    image_queue_analysis = image_queue_transfer
    #Instantiate an analysis thread and add a signal
    analysis_thread = AnalysisThread(analysisInfo=analysisInfo,visualisationInfo=analysisInfo)
    analysis_thread.analysis_done_signal.connect(analysis_thread.update_napariLayer)
    
    #Append it to the list of analysisThreads
    shared_data.analysisThreads.append(analysis_thread)
    
    return analysis_thread