import numpy as np
from PyQt5.QtCore import pyqtSignal, QThread
import random
import napari
from napari.qt import thread_worker
import time
import queue
from PyQt5.QtWidgets import QMainWindow
from pycromanager import Core
from magicgui import magicgui
from qtpy.QtWidgets import QMainWindow, QVBoxLayout, QWidget
import sys
from custom_widget_ui import Ui_CustomDockWidget  # Import the generated UI module
from napari.layers import Shapes
from typing import Union, Tuple, List
from stardist.models import StarDist2D
from PIL import Image, ImageDraw

sys.path.append('AutonomousMicroscopy')
sys.path.append('AutonomousMicroscopy/MainScripts')
#Import all scripts in the custom script folders
from CellSegmentScripts import * #type: ignore
from CellScoringScripts import * #type: ignore
from ROICalcScripts import * #type: ignore
from ScoringMetrics import * #type: ignore
#Obtain the helperfunctions
import HelperFunctions  #type: ignore

#Class for overlays and their update and such
class napariOverlay():
    def __init__(self,napariViewer,layer_name:Union[str,None]='new Layer',colormap='gray',opacity=1,visible=True,blending='translucent',):
        """
        Initializes an instance of the class with the specified `napariViewer` and `layer_name`.

        Args:
            napariViewer (napari.Viewer): The napari viewer object.
            layer_name (Union[str, None], optional): The name of the layer. Defaults to 'new Layer'.
            colormap (str, optional): The colormap to use. Defaults to 'gray'.
            opacity (float, optional): The opacity of the layer. Defaults to 1.
            visible (bool, optional): Whether the layer is visible. Defaults to True.
            blending (str, optional): The blending mode. Defaults to 'opaque', options are {'opaque', 'translucent', and 'additive'}

        Returns:
            None
        """
        self.napariViewer = napariViewer
        self.layer_name = layer_name
        self.colormap = colormap
        self.opacity = opacity
        self.visible = visible
        self.blending = blending
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
        """
        Change the name of the napariOverlay

        Args:
            new_name (str): The new name for the napariOverlay.

        Returns:
            None
        """
        self.layer_name = new_name
        self.layer.name = self.layer_name
        #Return the layer
        
    def getLayer(self):
        """
        Returns the layer attribute of the object.

        Args:
            None

        Returns:
            layer (object or None): The layer attribute of the object if it exists, None otherwise.
        """
        if hasattr(self, 'layer'):
            return self.layer
        else:
            return None
        
    #Initialise drawing a text overly (single string of text)
    def drawTextOverlay_init(self):
        """
        Initializes the text overlay for drawing text on the napari viewer.

        Args:
            None
        
        Returns:
            None
        """
        polygons = [np.array([[0, 0], [0, 1], [1, 1], [1, 0]])]
        # create properties
        properties = {'value': [0]}
        text_properties = {'text': '{value:0.1f}','anchor': 'upper_left','translation': [-5, 0],'size': 8,'color': 'green',}
        #Remove old layer
        napariViewer.layers.remove(self.layer)
        # new layer with polygons and text
        self.layer = napariViewer.add_shapes(polygons,properties=properties,shape_type='polygon',edge_color='transparent',face_color='transparent',text=text_properties,name=self.layer_name,scale=self.layer_scale,opacity = self.opacity,visible=self.visible)
    
    #Update routine for drawing a text overly (single string of text)
    def drawTextOverlay(self,text='',pos=[0,0],textCol='red',textSize=8):
        """
        Running loop to draw/update the text overlay. Requires drawTextOverlay_init to be ran beforehand

        Args:
            text (str): The text to be displayed on the overlay. Defaults to an empty string.
            pos ([int of size (2,1)]): The position of the overlay on the image. Defaults to [0, 0].
            textCol (str): The color of the text. Defaults to 'red'.
            textSize (int): The size of the text. Defaults to 8.

        Returns:
            None
        """
        # Update the properties - this contains the text
        new_properties = {'text': np.array([text]).astype(object)}
        self.layer.properties = new_properties
        #update the polygon - this contains the position
        pseudo_size = 0.1
        polygons = [np.array([[pos[0], pos[1]], [pos[0]+pseudo_size, pos[1]], [pos[0]+pseudo_size, pos[1]+pseudo_size], [pos[0], pos[1]+pseudo_size]])]
        #Remove the old polygon
        self.layer.data = []
        # add the new polygon
        self.layer.add(polygons,shape_type='polygon',edge_color='transparent',face_color='transparent')
        #Update the text surrounding the invisible shape
        text_properties = {'text': '{text}','anchor': 'upper_left','translation': [0, 0],'size': textSize,'color': textCol}
        self.layer.text = text_properties
        
    #Initialise an overlay that only has shapes
    def shapesOverlay_init(self):
        """
        Initialise an overlay that only draws shapes.

        Args:
            None

        Returns:
            None
        """
        #Initialise an overlay that only has shapes
        #Create a single shape (polygon) and show it
        polygons = [np.array([[225, 146], [283, 146], [283, 211], [225, 211]])]
        #Remove old layer
        self.napariViewer.layers.remove(self.layer)
        # new layer with polygons and text
        self.layer = self.napariViewer.add_shapes(polygons,shape_type='polygon',edge_color='transparent',face_color='transparent',name=self.layer_name,scale=self.layer_scale,opacity = self.opacity,visible=self.visible)
    
    #Update routine for an overlay that only has shapes
    def drawSquaresOverlay(self,shapePosList = [[0,0,10,10]],shapeCol: List[Union[str, Tuple[float, float, float]]] = ['black']):
        """
        Running loop to draw/update and overlay with one or multiple rectangles. Requires shapesOverlay_init to be ran beforehand

        Args:
            shapePosList (List[List[int]]): A list of shape positions in the format [[x, y, w, h], [x, y, w, h], ...].
                Default is [[0, 0, 10, 10]].
            shapeCol (List[Union[str, Tuple[float, float, float]]]): A single entry or an array with the same size as shapePosList.
                Default is ['black'].

        Returns:
            None
        """        
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
        """
        Running loop to draw arbitrary-shaped polygon shapes. Requires shapesOverlay_init to be ran beforehand

        Args:
            shapePosList (List[List[float]]): A list of shape positions. A [[x1-1,y1-1],[x1-2,y1-2],...],[[x2-1,y2-1],[x2-2,y2-2],...] array of size [n,2,m], drawing m shapes with n points each. Default is [[0,0],[0,10],[10,10],[10,0]].
            shapeCol (List[Union[str, Tuple[float, float, float]]]): A list of shape colors. Default is ['black'].

        Returns:
            None
        """
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
    
    #Initialise an overlay that only shows an image
    def imageOverlay_init(self,opacity=None,visible=None,blending=None,colormap=None):
        """
        Initialize a napari overlay that only draws an image

        Args:
            opacity (float, optional): The opacity of the layer. If None, the value will be taken from self.opacity.
            visible (bool, optional): Whether the layer is visible. If None, the value will be taken from self.visible.
            blending (str, optional): The blending mode. If None, the value will be taken from self.blending.
            colormap (str, optional): The colormap to use. If None, the value will be taken from self.colormap.
        
        Returns:
            None
        """
        # Assign values from self if the corresponding argument is None
        self.opacity = self.opacity if opacity is None else opacity
        self.visible = self.visible if visible is None else visible
        self.blending = self.blending if blending is None else blending
        self.colormap = self.colormap if colormap is None else colormap
        #Load image
        im = np.random.random((300, 300))
        #Remove old layer
        self.napariViewer.layers.remove(self.layer)
        # new layer with polygons and text
        self.layer = self.napariViewer.add_image(im,scale=self.layer_scale,opacity = self.opacity,visible=self.visible,blending=self.blending,colormap=self.colormap)
        
    #Update an overlay that shows an image
    def drawImageOverlay(self,im=np.zeros((300,300))):
        """
        Running loop to draw an image as napari overlay. Requires imageOverlay_init to be ran beforehand

        Parameters:
            im (numpy.ndarray): The image to be overlaid. Default is np.zeros((300, 300)).

        Returns:
            None
        """
        #Remove the old image
        self.layer.data = np.ones(np.shape(self.layer.data))
        #Update the image
        self.layer.data = im
        
    def destroy(self):
        """
        Deletes the instance of the class.
        """
        del self
        
#This code gets some image and does some analysis on this
class AnalysisThread(QThread):
    # Define analysis_done_signal as a class attribute, shared among all instances of AnalysisThread class
    # Create a signal to communicate between threads
    analysis_done_signal = pyqtSignal(object)
    finished = pyqtSignal()# signal to indicate that the thread has finished
    def __init__(self,shared_data,analysisInfo: Union[str, None] = 'Random',visualisationInfo: Union[str, None] = 'Random',analysisQueue=None,sleepTimeMs=500):
        """
        Initializes the AnalysisThread object.

        Args:
            shared_data: The shared data object. See Shared_data class for more information
            analysisInfo (Union[str, None]): Optional. The analysis 'title/method'. Default is 'Random'.
            visualisationInfo (Union[str, None]): Optional. The visualisation 'title/method'. Default is 'Random'.

        Returns:
        None
        """
        super().__init__()	
        self.is_running = True
        self.analysis_ongoing = False
        self.shared_data = shared_data
        self.analysisInfo = analysisInfo
        self.visualisationInfo = visualisationInfo
        self.napariViewer = shared_data.napariViewer
        self.image_queue_analysis = analysisQueue
        self.sleepTimeMs = sleepTimeMs
        if self.analysisInfo == 'CellSegmentOverlay':
            storageloc = './AutonomousMicroscopy/ExampleData/StarDistModel'
            # storageloc = './AutonomousMicroscopy/ExampleData/StarDist_hfx_20220823'
            modelDirectory = storageloc.rsplit('/', 1)
            #Load the model - better to do this out of the loop for time reasons
            self.stardistModel = StarDist2D(None,name=modelDirectory[1],basedir=modelDirectory[0]+"/") #type:ignore
        if analysisInfo == None:
            self.napariOverlay = napariOverlay(self.napariViewer,layer_name=None)
        elif analysisInfo == 'LiveModeVisualisation':
            self.napariOverlay = napariOverlay(self.napariViewer,layer_name=None)
        else:
            self.napariOverlay = napariOverlay(self.napariViewer,layer_name=analysisInfo)
            #Create an empty overlay
            if visualisationInfo != None:
                #Activate layer
                self.initialise_napariLayer()
    
    def run(self):
        """
        Runs the function in a loop as long as `self.is_running` is True.

        Args:
            None

        Returns:
            None
        """
        while not self.isInterruptionRequested():
            #Run analysis on the image from the queue
            self.analysis_result = self.runAnalysis(self.image_queue_analysis.get()) #type:ignore
            self.analysis_done_signal.emit(self.analysis_result)
            # self.finished.emit()
            if self.is_running == False:
                # self.finished.emit()
                return
        
        # Thread has finished, emit the finished signal
        self.finished.emit()
    
    def stop(self):
        """
        Stops the execution of the function
        """
        self.is_running = False
        #Also remove the image queue requestion from live mode
        self.shared_data.liveImageQueues.remove(self.image_queue_analysis)
    
    def destroy(self):
        """
        Destroy the object.

        Args:
            None

        Returns:
            None
        """
        try:
            print('Destroying '+str(self.analysisInfo))
        except:
            print('Destroying some analysis thread')
        #Wait for the thread to be finished
        self.stop()
        self.requestInterruption()
        self.quit()
        #Officially we'd need to wait here, but that seems to start an infinite loop somewhere
        # self.wait()
        # self.deleteLater()
    
    #Get corresponding layer of napariOverlay
    def getLayer(self):
        """
        Obtain the napari overlay layer (napariOverlay class) associated with this analysisThread
        
        Args:
            None

        Returns:
            napari.layers.Layer: The layer associated with the napari overlay.
        """
        return self.napariOverlay.getLayer()
    
    #Analysis is split into two parts: obtaining the analysis result and displaying this.
    #Here, we calculate the analysis result based on the analysisInfo
    def runAnalysis(self,image): 
        """
        Runs the analysis on the given image based on the analysis information provided.

        Args:
            image (Image): The image on which the analysis needs to be performed.

        Returns:
            analysisResult (Any): The result of the analysis. The analysis result will be passed to Visualise_Analysis_results.

        Notes:
            - The layer should be open before running the analysis.
            - The analysisInfo parameter should be set before calling this function.
            - If analysisInfo is 'AvgGrayValueText', the analysisResult will be the result of calcAnalysisAvgGrayValue.
            - If analysisInfo is 'GrayValueOverlay', the analysisResult will be the result of calcGrayValueOverlay.
            - If analysisInfo is 'CellSegmentOverlay', the analysisResult will be the result of calcCellSegmentOverlay.
            - If analysisInfo is not set or is invalid, the analysisResult will be None.
        """
        if self.analysisInfo is not None and self.analysisInfo != 'LiveModeVisualisation':
            self.msleep(self.sleepTimeMs)
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
        elif self.analysisInfo == 'LiveModeVisualisation':
            self.setPriority(self.HighestPriority) #type:ignore
            return None
        else:
            return None

    #And here we perform the visualisation - can be fully separate from performing the analysis
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
        if self.analysisInfo is not None and self.analysisInfo != 'LiveModeVisualisation':
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
        self.napariOverlay.drawImageOverlay(im=analysis_result) #type:ignore
    
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
        self.napariOverlay.drawImageOverlay(im=analysis_result) #type:ignore
        
    def initCellSegmentOverlay(self):
        # self.napariOverlay.shapesOverlay_init()
        self.napariOverlay.imageOverlay_init(blending='additive',opacity=0.5,colormap='red')
        self.napariOverlay.changeName('Cell Segment Overlay')
        
def create_analysis_thread(shared_data,analysisInfo = None,visualisationInfo = None,createNewThread = True,throughputThread=None):
    global image_queue_analysis, napariViewer
    napariViewer = shared_data.napariViewer
    if createNewThread == False:
        image_queue_analysis = throughputThread
    else:
        #Create a new analysis thread
        print('starting new image queue analysis')
        image_queue_analysis = queue.Queue() #This now needs to be linked to pycromanager so that pycromanager pushes images to all image queues and not just one
        shared_data.liveImageQueues.append(image_queue_analysis)
        
    # image_queue_analysis = image_queue_transfer
    #Instantiate an analysis thread and add a signal
    analysis_thread = AnalysisThread(shared_data,analysisInfo=analysisInfo,visualisationInfo=analysisInfo,analysisQueue=image_queue_analysis)
    analysis_thread.analysis_done_signal.connect(analysis_thread.update_napariLayer)
    analysis_thread.finished.connect(analysis_thread.deleteLater)
    analysis_thread.start()
    
    #Append it to the list of analysisThreads
    shared_data.analysisThreads.append(analysis_thread)
     
    return analysis_thread 