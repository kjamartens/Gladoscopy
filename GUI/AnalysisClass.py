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
from typing import Union, Tuple, List
from stardist.models import StarDist2D
from PIL import Image, ImageDraw

sys.path.append('AutonomousMicroscopy')
#Import all scripts in the custom script folders
from CellSegmentScripts import * #type: ignore
from CellScoringScripts import * #type: ignore
from ROICalcScripts import * #type: ignore
from ScoringMetrics import * #type: ignore
#Obtain the helperfunctions
import HelperFunctions  #type: ignore

#Class for overlays and their update and such
class napariOverlay():
    def __init__(self,napariViewer,layer_name:Union[str,None]='new Layer'):
        self.napariViewer = napariViewer
        self.layer_name = layer_name
        try:
            self.layer_scale = napariViewer.layers[0].scale
        except:
            self.layer_scale = [1,1]
        #Create the layer if layer_name is not none
        #layer_name is None if we only want to instantialise the napariOverlay but not get any shape
        if layer_name is not None:
            self.layer = napariViewer.add_shapes(name=self.layer_name,scale=self.layer_scale)
        
    #Update the name of the overlay
    def changeName(self,new_name):
        self.layer_name = new_name
        self.layer.name = self.layer_name
    
    #Initialise drawing a text overly (single string of text)
    def drawTextOverlay_init(self):
        polygons = [np.array([[0, 0], [0, 1], [1, 1], [1, 0]])]
        # create properties
        properties = {'value': [0]}
        text_properties = {'text': '{value:0.1f}','anchor': 'upper_left','translation': [-5, 0],'size': 8,'color': 'green',}
        #Remove old layer
        napariViewer.layers.remove(self.layer)
        # new layer with polygons and text
        self.layer = napariViewer.add_shapes(polygons,properties=properties,shape_type='polygon',edge_color='transparent',face_color='transparent',text=text_properties,name=self.layer_name,scale=self.layer_scale,)
        # change some properties of the layer
        self.layer.opacity = 1
    
    #Update routine for drawing a text overly (single string of text)
    def drawTextOverlay(self,text='',pos=[0,0],textCol='red',textSize=8):
        # Update the properties - this contains the text
        new_properties = {'text': [text]}
        self.layer.properties = new_properties
        #update the polygon - this contains the position
        pseudo_size = 0.1
        polygons = [np.array([[pos[0], pos[1]], [pos[0]+pseudo_size, pos[1]], [pos[0]+pseudo_size, pos[1]+pseudo_size], [pos[0], pos[1]+pseudo_size]])]
        #Remove the old polygon
        self.layer.data = []
        # add the new polygon
        self.layer.add(polygons,shape_type='polygon',edge_color='transparent',face_color='transparent',)
        #Update the text surrounding the invisible shape
        text_properties = {'text': '{text}','anchor': 'upper_left','translation': [0, 0],'size': textSize,'color': textCol}
        self.layer.text = text_properties
        
    #Initialise an overlay that only has shapes
    def shapesOverlay_init(self):
        #Initialise an overlay that only has shapes
        #Create a single shape (polygon) and show it
        polygons = [np.array([[225, 146], [283, 146], [283, 211], [225, 211]])]
        #Remove old layer
        self.napariViewer.layers.remove(self.layer)
        # new layer with polygons and text
        self.layer = self.napariViewer.add_shapes(polygons,shape_type='polygon',edge_color='transparent',face_color='transparent',name=self.layer_name,scale=self.layer_scale)
    
    #Update routine for an overlay that only has shapes
    def drawSquaresOverlay(self,shapePosList = [[0,0,10,10]],shapeCol: List[Union[str, Tuple[float, float, float]]] = ['black']):
        #ShapePosList should be a [[x,y,w,h],[x,y,w,h],...] array
        #ShapeCol should be a single entry or an array with same size as shapeposlist
        
        #Update the shapes
        polygons = []
        for p in range(len(shapePosList)):
            polygons.append(np.array([[shapePosList[p][0], shapePosList[p][1]], [shapePosList[p][0]+shapePosList[p][2], shapePosList[p][1]], [shapePosList[p][0]+shapePosList[p][2], shapePosList[p][1]+shapePosList[p][3]], [shapePosList[p][0], shapePosList[p][1]+shapePosList[p][3]]]))
        #Remove the old polygon
        self.layer.data = []
        # add the new polygon
        if len(shapeCol) == 1:
            self.layer.add(polygons,shape_type='polygon',edge_color='transparent',face_color=shapeCol[0])
        else:
            self.layer.add(polygons,shape_type='polygon',edge_color='transparent',face_color=shapeCol)
    
    
    #Update routine for an overlay that only has shapes
    def drawShapesOverlay(self,shapePosList = [[0,0],[0,10],[10,10],[10,0]],shapeCol: List[Union[str, Tuple[float, float, float]]] = ['black']):
        #Draw true polygon shapes
        #Expected input shapePosList: a [[x1-1,y1-1],[x1-2,y1-2],...],[[x2-1,y2-1],[x2-2,y2-2],...] array of size [n,2,m], drawing m shapes with n points each
        
        #Update the shapes
        polygons = []
        for p in range((shapePosList.shape[2])):
            polygons.append(shapePosList[:,:,p])
        #Remove the old polygon
        self.layer.data = []
        # add the new polygon
        if len(shapeCol) == 1:
            self.layer.add(polygons,shape_type='polygon',edge_color='transparent',face_color=shapeCol[0])
        else:
            self.layer.add(polygons,shape_type='polygon',edge_color='transparent',face_color=shapeCol)
    
    #Return the layer
    def getLayer(self):
        if hasattr(self, 'layer'):
            return self.layer
        else:
            return None
    
    #Initialise an overlay that only shows an image
    def imageOverlay_init(self):
        #Initialise an overlay that only has shapes
        #Load image
        im = np.random.random((300, 300))
        #Remove old layer
        self.napariViewer.layers.remove(self.layer)
        # new layer with polygons and text
        self.layer = self.napariViewer.add_image(im,scale=self.layer_scale)
        
    #Update an overlay that shows an image
    def drawImageOverlay(self,im):
        #Remove the old image
        self.layer.data = np.ones(np.shape(self.layer.data))
        #Update the image
        self.layer.data = im
        
    def destroy(self):
        del self
        
#This code gets some image and does some analysis on this
class AnalysisThread(QThread):
    # Define analysis_done_signal as a class attribute, shared among all instances of AnalysisThread class
    # Create a signal to communicate between threads
    analysis_done_signal = pyqtSignal(object)
    
    def __init__(self,shared_data,analysisInfo: Union[str, None] = 'Random',visualisationInfo: Union[str, None] = 'Random'):
        super().__init__()	
        self.is_running = True
        self.analysis_ongoing = False
        self.shared_data = shared_data
        self.analysisInfo=analysisInfo
        self.visualisationInfo = visualisationInfo
        self.napariViewer = shared_data.napariViewer
        if self.analysisInfo == 'CellSegmentOverlay':
            storageloc = './AutonomousMicroscopy/ExampleData/StarDistModel'
            modelDirectory = storageloc.rsplit('/', 1)
            #Load the model - better to do this out of the loop for time reasons
            self.stardistModel = StarDist2D(None,name=modelDirectory[1],basedir=modelDirectory[0]+"/") #type:ignore
        if analysisInfo == None:
            self.napariOverlay = napariOverlay(self.napariViewer,layer_name=None)
        else:
            self.napariOverlay = napariOverlay(self.napariViewer,layer_name=analysisInfo)
            #Create an empty overlay
            if visualisationInfo != None:
                #Activate layer
                self.initialise_napariLayer()
    
    def run(self):
        while self.is_running:
            #Run analysis on the image from the queue
            self.analysis_result = self.runAnalysis(image_queue_analysis.get())
            self.analysis_done_signal.emit(self.analysis_result)
            self.finished.emit()
    
    def stop(self):
        self.is_running = False
    
    def destroy(self):
        try:
            print('Destroying '+str(self.analysisInfo))
        except:
            print('Destroying some analysis thread')
        self.stop()
        # self.analysis_done_signal.disconnect(self.update_napariLayer)
        # self.analysisInfo = None
        #Wait for the thread to be finished
        # self.napariOverlay.destroy()
        self.quit()
        self.wait()
        self.deleteLater()
    
    #Get corresponding layer of napariOverlay
    def getLayer(self):
        return self.napariOverlay.getLayer()
    
    #Analysis is split into two parts: obtaining the analysis result and displaying this.
    #Here, we calculate the analysis result based on the analysisInfo
    def runAnalysis(self,image): 
        #Maybe add here that the layer should also be open?
        if self.analysisInfo is not None:
            print('layer running analysis')
            #Do analysis here - the info in analysisResult will be passed to Visualise_Analysis_results
            if self.analysisInfo == 'AvgGrayValueText':
                analysisResult = self.calcAnalysisAvgGrayValue(image)
            elif self.analysisInfo == 'GrayValueOverlay':
                analysisResult = self.calcGrayValueOverlay(image)
            elif self.analysisInfo == 'CellSegmentOverlay':
                analysisResult = self.calcCellSegmentOverlay(image)
            else:
                analysisResult = None
            return analysisResult
        else:
            return None

    #And here we perform the visualisation - can be fully separate from performing tha analysis
    #Initialisation is called upon creation
    def initialise_napariLayer(self):
        if self.visualisationInfo == 'AvgGrayValueText':
            self.initAvgGrayValueText()
        elif self.analysisInfo == 'GrayValueOverlay':
            self.initGrayScaleImageOverlay()
        elif self.analysisInfo == 'CellSegmentOverlay':
            self.initCellSegmentOverlay()
        else:
            self.initRandomOverlay()
            
    #Update ir called every time the analysis is done
    def update_napariLayer(self,analysis_result):
        # print(analysis_result)
        if self.analysisInfo is not None:
            if self.visualisationInfo == 'AvgGrayValueText':
                self.visualiseAvgGrayValueText(analysis_result)
            elif self.analysisInfo == 'GrayValueOverlay':
                self.visualiseGrayScaleImageOverlay(analysis_result)
            elif self.analysisInfo == 'CellSegmentOverlay':
                self.visualiseCellSegmentOverlay(analysis_result)
            else:
                self.visualiseRandomOverlay()
    
    def outlineCoordinatesToImage(self,coords):
    # Create a blank grayscale image with a white background
        image = Image.new("L", (self.shared_data.core.get_roi().width,self.shared_data.core.get_roi().height), "black")
        draw = ImageDraw.Draw(image)

        # Iterate over each n in N
        for n in range(coords.shape[0]):
            # Get the x and y coordinates for the current n
            x = coords[n, 0, :]
            y = coords[n, 1, :]

            # Create a list of (x, y) tuples for drawing the lines
            points = [(x[i], y[i]) for i in range(len(x))]

            # Draw the lines on the image
            draw.line(points, fill="white",width=2)  # Use black for the lines

        # Convert the image to grayscale mode (L)
        grayscale_image = image.convert("L")
        return np.fliplr(np.rot90(np.array(grayscale_image),k=3))
    
    """
    Average gray value calculation and display
    """
    #Calculating average gray value of an image
    def calcAnalysisAvgGrayValue(self,image):
        return np.mean(np.mean(image))
    
    def visualiseAvgGrayValueText(self,analysis_result='Random'):
        self.napariOverlay.drawTextOverlay(text='Mean gray value: {:.0f}'.format(analysis_result),pos=[0,0],textCol='white',textSize=12)
        
    def initAvgGrayValueText(self):
        self.napariOverlay.changeName('Average Gray Value')
        self.napariOverlay.drawTextOverlay_init()
    
    """
    Random overlay display
    """   
    def visualiseRandomOverlay(self,analysis_result=None):
        self.napariOverlay.drawSquaresOverlay(shapePosList=[[random.random()*100,random.random()*100,50,50],[100+random.random()*100,random.random()*100,100,100]],shapeCol=[(random.random(),random.random(),random.random()),(random.random(),random.random(),random.random())])
        
    def initRandomOverlay(self):
        self.napariOverlay.changeName('RandomOverlay')
        self.napariOverlay.shapesOverlay_init()    
    
    """
    Testing overlay of image - based on grayscale value
    """
    def calcGrayValueOverlay(self,image):
        #Get an image that simply provides a Boolean based on percentile:
        image2 = np.where(image<np.percentile(image,25),1,0)
        return image2
    
    def visualiseGrayScaleImageOverlay(self,analysis_result=None):
        #Expected analysis_result is a boolean image.
        #Create an image overlay from napari
        self.napariOverlay.drawImageOverlay(im=analysis_result)
    
    def initGrayScaleImageOverlay(self):
        self.napariOverlay.imageOverlay_init()
        self.napariOverlay.changeName('Grayscale Image Overlay')
        
    """
    Testing cell segmentation
    """
    
    def calcCellSegmentOverlay(self,image):
        coords = eval(HelperFunctions.createFunctionWithKwargs("StarDist.StarDistSegment_preloadedModel",image_data="image",model="self.stardistModel"))
        #Get image from this coords:
        outimage = self.outlineCoordinatesToImage(coords)
        return outimage
        
    def visualiseCellSegmentOverlay(self,analysis_result=None):
        # self.napariOverlay.drawShapesOverlay(shapePosList=analysis_result,shapeCol=['red'])
        self.napariOverlay.drawImageOverlay(im=analysis_result)
        
    def initCellSegmentOverlay(self):
        # self.napariOverlay.shapesOverlay_init()
        self.napariOverlay.imageOverlay_init()
        self.napariOverlay.changeName('Cell Segment Overlay')
        
def create_analysis_thread(image_queue_transfer,shared_data,analysisInfo = None,visualisationInfo = None):
    global image_queue_analysis, napariViewer
    napariViewer = shared_data.napariViewer
    image_queue_analysis = image_queue_transfer
    #Instantiate an analysis thread and add a signal
    analysis_thread = AnalysisThread(shared_data,analysisInfo=analysisInfo,visualisationInfo=analysisInfo)
    analysis_thread.analysis_done_signal.connect(analysis_thread.update_napariLayer)
    
    #Append it to the list of analysisThreads
    shared_data.analysisThreads.append(analysis_thread)
     
    return analysis_thread 