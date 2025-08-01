"""
Handles the GUI display of Glados-pycromanager, as well as the structure for analysis (normal and real-time) to run on secondary threads.
"""

import sys
import time
import time
import numpy as np
import logging
from collections import deque
from typing import Union, Tuple, List
from PyQt5.QtCore import pyqtSignal, QThread
from threading import Event
from threading import Event

def is_pip_installed():
    return 'site-packages' in __file__ or 'dist-packages' in __file__

if is_pip_installed():
    from glados_pycromanager.GUI.custom_widget_ui import Ui_CustomDockWidget  # Import the generated UI module
    import glados_pycromanager.GUI.utils as utils
    import glados_pycromanager.GUI.microscopeInterfaceLayer as MIL
    from glados_pycromanager.AutonomousMicroscopy.Analysis_Measurements import * #type: ignore
    from glados_pycromanager.AutonomousMicroscopy.CustomFunctions import * #type: ignore
    from glados_pycromanager.AutonomousMicroscopy.Real_Time_Analysis import * #type: ignore
else:
    from custom_widget_ui import Ui_CustomDockWidget  # Import the generated UI module
    import utils
    import microscopeInterfaceLayer as MIL
    sys.path.append('AutonomousMicroscopy')
    sys.path.append('AutonomousMicroscopy/MainScripts')
    #Import all scripts in the custom script folders
    from Analysis_Measurements import * #type: ignore
    from CustomFunctions import * #type: ignore
    from Real_Time_Analysis import * #type: ignore

#Class for overlays and their update and such
class napariOverlay():
    def __init__(self,napariViewer,layer_name:Union[str,None]='new Layer',colormap='gray',opacity=1,visible=True,blending='translucent',layerType = None,RT_analysisObject=None):
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
        self.RT_analysisObject = RT_analysisObject
        self.layerType = layerType
        try:
            self.layer_scale = napariViewer.layers[0].scale
        except:
            self.layer_scale = [1,1]
        
        #Get info from a RT analysis object (i.e. outside-based-analysis)
        if self.RT_analysisObject is not None:
            self.layer_name, self.layerType = self.RT_analysisObject.visualise_init()
            logging.debug(f"#nO - Initialised napariOverlay with layer_name: {self.layer_name}, layerType: {self.layerType}")
            
        #Create the layer if layer_name is not none
        #layer_name is None if we only want to instantialise the napariOverlay but not get any shape
        if self.layer_name is not None:
            if self.layerType is not None:
                
                #check if a layer with this name already exists:
                if self.layer_name in napariViewer.layers:
                    self.layer = napariViewer.layers[self.layer_name]
                        
                else: #else create the layer
                    if self.layerType == 'image':
                        self.layer = napariViewer.add_image(np.zeros((32,32)),name=self.layer_name,scale=self.layer_scale)
                    elif self.layerType == 'labels':
                        self.layer = napariViewer.add_labels([],name=self.layer_name,scale=self.layer_scale)
                    elif self.layerType == 'points':
                        self.layer = napariViewer.add_points(name=self.layer_name,scale=self.layer_scale)
                    elif self.layerType == 'shapes':
                        self.layer = napariViewer.add_shapes(name=self.layer_name,scale=self.layer_scale)
                    elif self.layerType == 'surface':
                        self.layer = napariViewer.add_surface([],name=self.layer_name,scale=self.layer_scale)
                    elif self.layerType == 'tracks':
                        self.layer = napariViewer.add_tracks([],name=self.layer_name,scale=self.layer_scale)
                    elif self.layerType == 'vectors':
                        self.layer = napariViewer.add_vectors(name=self.layer_name,scale=self.layer_scale)
            else: #Fallback if no layer type is specified at all
                self.layer = napariViewer.add_shapes(name=self.layer_name,scale=self.layer_scale)
        
            logging.debug(f"Using layer {self.layer}")
        
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

class AnalysisThread_customFunction_Visualisation(QThread):
    finished = pyqtSignal()# signal to indicate that the thread has finished
    def __init__(self,analysisObject,shared_data,analysisInfo: Union[str, None] = 'Random',delay=None):
        super().__init__()
        #Initiate some variables
        if delay==None:
            #Get the delay of the function from the realTimeAnalysis module,
            #ensure that it's never faster than the visualisation rate
            min_delay_visualisation = int(1000/(float(shared_data.globalData['VISUALISATION-FPS']['value'])))
            delay = max(min_delay_visualisation,utils.realTimeAnalysis_getDelay(analysisInfo,runOrVis='visualise'))
        
        logging.debug('#aC - init analysisThread_customFunction_Visualisation')
        self.is_running = True
        self.analysis_ongoing = False
        self.shared_data = shared_data
        self.analysisInfo = analysisInfo
        self.napariViewer = shared_data.napariViewer
        self.sleepTimeMs = delay
        self.napariOverlay = napariOverlay(self.napariViewer,RT_analysisObject=analysisObject,layer_name='TestLayer_VIS')
        self.visualisation_queue = deque(maxlen=10)#queue.Queue()
        self.shared_data = shared_data
        
        #And start  the thread
        self.running = True
        self._new_image = Event() #Event when a new image is put in the queue
        self._new_image = Event() #Event when a new image is put in the queue
        # self.process_queue()
    
    def new_image(self):
        self._new_image.set()
        
    
    def new_image(self):
        self._new_image.set()
        
    def run(self):
        while self.running:
            # tic = time.time()
            # #Only check the vis queue if live or mda is ongoing
            # if self.shared_data.liveMode or self.shared_data.mdaMode:
            #     logging.debug(f'#aC - running analysisThread_customFunction_Visualisation, liveMode:{self.shared_data.liveMode}, mdaMode: {self.shared_data.mdaMode}')
            #     if self.visualisation_queue:
            self._new_image.wait()#Wait for a new image
            self._new_image.clear()
            
            data = self.visualisation_queue.popleft()
            RT_analysis_object,analysisInfo,image,metadata,shared_data,core = data
            self.updateVisualisation(RT_analysis_object,analysisInfo,image,metadata,core)
                    # self.visualisation_queue.task_done()
            #Always sleep while running
            self.msleep(max(1,self.sleepTimeMs))
            
            # print(f'Time spend in analysisclass-run; {time.time()-tic}')
            
    def updateVisualisation(self,RT_analysis_object,analysisInfo,image,metadata=None,core=None):
        # logging.info('visualisation should be updated here :)')
        # tic = time.time()
        res = utils.realTimeAnalysis_visualisation(RT_analysis_object,analysisInfo,image,metadata,core,self.napariOverlay.layer)
        # print(f'Time spend in updateVisualisation; {time.time()-tic}')

#This code gets some image and does some analysis on this - does NOT do the visualisation - see AnalysisThread_customFunction_Visualisation specifically for a second thread which does the RT visualisation based on this output

#Has to be a QThread and not e.g. multiprocessing because we rely on pickyyable objects - mostly the pycromanager core that we send around to influence the run during RT analysis
class AnalysisThread_customFunction(QThread):
    # Define analysis_done_signal as a class attribute, shared among all instances of AnalysisThread class
    # Create a signal to communicate between threads
    analysis_done_signal = pyqtSignal(object)
    finished = pyqtSignal()# signal to indicate that the thread has finished
    def __init__(self,shared_data,analysisInfo: Union[str, None] = 'Random',analysisQueue=None,sleepTimeMs=1,nodzInfo=None):
        """
        Initializes the AnalysisThread object.

        Args:
            shared_data: The shared data object. See Shared_data class for more information
            analysisInfo (Union[str, None]): Optional. The analysis 'title/method'. Default is 'Random'.
            visualisationInfo (Union[str, None]): Optional. The visualisation 'title/method'. Default is 'Random'.

        Returns:
        None
        """
        logging.debug('#aC - started AnalysisThread_customFunction')
        super().__init__()
        #Initiate some variables
        self.is_running = True
        self.analysis_ongoing = False
        self.shared_data = shared_data
        self.analysisInfo = analysisInfo
        self.napariViewer = shared_data.napariViewer
        self.image_queue_analysis = analysisQueue
        self.sleepTimeMs = sleepTimeMs
        self.napariOverlay = None
        self.nodzInfo=nodzInfo
        # self.napariOverlay = napariOverlay(self.napariViewer,layer_name='TestLayer')
        self.initAnalysis()
        self.running = True
        self._activity_event = Event() #Event when MDA/LIVE is started/stopped.
        self._new_image = Event() #Event when a new image is put in the queue
        self._activity_event = Event() #Event when MDA/LIVE is started/stopped.
        self._new_image = Event() #Event when a new image is put in the queue
    
    def run(self):
        """
        Runs the function in a loop as long as `self.is_running` is True.

        Args:
            None

        Returns:
            None
        """
        
        while self.is_running:
            # # tic = time.time()
            # # Wait until liveMode or mdaMode is active
            # self._activity_event.wait()
            
            # #Only check the vis queue if live or mda is ongoing
            # if self.shared_data.liveMode or self.shared_data.mdaMode:
            #     # logging.debug(f'#aC - running analysisThread_customFunction, liveMode:{self.shared_data.liveMode}, mdaMode: {self.shared_data.mdaMode}')
            #     #Run analysis on the image from the queue
            
            self._new_image.wait()#Wait for a new image
            self._new_image.clear()
            #Analyse it.
            if self.image_queue_analysis:
                self.analysis_result = self.runAnalysis(self.image_queue_analysis.popleft()) #type:ignore
                self.analysis_done_signal.emit(self.analysis_result)
                # self.image_queue_analysis.task_done() #type:ignore
            #Always sleep while running - at least 1 ms
            self.msleep(max(1,self.sleepTimeMs))
            # print(f'Time spend in analysisclass-run; {time.time()-tic}')
            
            # # tic = time.time()
            # # Wait until liveMode or mdaMode is active
            # self._activity_event.wait()
            
            # #Only check the vis queue if live or mda is ongoing
            # if self.shared_data.liveMode or self.shared_data.mdaMode:
            #     # logging.debug(f'#aC - running analysisThread_customFunction, liveMode:{self.shared_data.liveMode}, mdaMode: {self.shared_data.mdaMode}')
            #     #Run analysis on the image from the queue
            
            self._new_image.wait()#Wait for a new image
            self._new_image.clear()
            #Analyse it.
            if self.image_queue_analysis:
                self.analysis_result = self.runAnalysis(self.image_queue_analysis.popleft()) #type:ignore
                self.analysis_done_signal.emit(self.analysis_result)
                # self.image_queue_analysis.task_done() #type:ignore
            #Always sleep while running - at least 1 ms
            self.msleep(max(1,self.sleepTimeMs))
            # print(f'Time spend in analysisclass-run; {time.time()-tic}')
            
        # Thread has finished, emit the finished signal
        self.finished.emit()
    
        
        # while self.running:
        #     if not self.image_queue_analysis.empty():
        #         data = self.image_queue_analysis.get_nowait()
        #         self.runAnalysis(data)
        #         self.image_queue_analysis.task_done()
        #     time.sleep(self.sleepTimeMs/1000.0)
    
    def stop(self):
        """
        Stops the execution of the function
        """
        self.endAnalysis(self.analysisInfo,core=self.shared_data.core)
        self.is_running = False
        self._activity_event.set()
        self._activity_event.set()
        #Also remove the image queue requestion from live mode
        # if self.image_queue_analysis in self.shared_data.RTAnalysisQueues:
        #     self.shared_data.RTAnalysisQueues.remove(self.image_queue_analysis)
        # if self.image_queue_analysis in self.shared_data.mdaImageQueues:
        #     self.shared_data.mdaImageQueues.remove(self.image_queue_analysis)
    
        try:
            #check if there's a layer associated with this...
            # layer = self.getLayer()
            #and remove it
            self.shared_data.skipAnalysisThreadDeletion = True
            # self.shared_data.napariViewer.layers.remove(layer)
        except:
            pass
        
    def destroy(self):
        """
        Destroy the object.

        Args:
            None

        Returns:
            None
        """
        self.endAnalysis(self.analysisInfo,core=self.shared_data.core)
        try:
            logging.debug('Destroying '+str(self.analysisInfo))
        except:
            logging.debug('Destroying some analysis thread')
        #Wait for the thread to be finished
        self.stop()
        self.requestInterruption()
        self.quit()
        #Officially we'd need to wait here, but that seems to start an infinite loop somewhere
        # self.wait()
        # self.deleteLater()
    
    def set_activity(self, is_active):
        if is_active:
            self._activity_event.set()
            # print('setting self._activity_event')
        else:
            self._activity_event.clear()
            # print('clearing self._activity_event')
    
    def new_image(self):
        self._new_image.set()
        # print('setting self.new_image')
            
    
    def set_activity(self, is_active):
        if is_active:
            self._activity_event.set()
            # print('setting self._activity_event')
        else:
            self._activity_event.clear()
            # print('clearing self._activity_event')
    
    def new_image(self):
        self._new_image.set()
        # print('setting self.new_image')
            
    #Get corresponding layer of napariOverlay
    def getLayer(self):
        """
        Obtain the napari overlay layer (napariOverlay class) associated with this analysisThread
        
        Args:
            None

        Returns:
            napari.layers.Layer: The layer associated with the napari overlay.
        """
        if self.napariOverlay is not None:
            return self.napariOverlay.getLayer()
        else:
            return None
    
    #Analysis is split into two parts: obtaining the analysis result and displaying this.
    #Here, we calculate the analysis result based on the analysisInfo
    def runAnalysis(self,data): 
        """
        Runs the analysis on the given image based on the analysis information provided.

        Args:
            data, containing:
            image (Image): The image on which the analysis needs to be performed.
            metadata: corresponding metadata

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
        if data is not None:
            image = data[0]
            metadata = data[1]
            if self.analysisInfo is not None and self.analysisInfo != 'LiveModeVisualisation' and self.analysisInfo != 'mdaVisualisation':
                # self.msleep(self.sleepTimeMs)
                # self.msleep(self.sleepTimeMs)
                #Do analysis here - the info in analysisResult will be passed to Visualise_Analysis_results
                analysisResult = self.runAnalysisThisImage(self.analysisInfo,image,metadata=metadata,shared_data=self.shared_data,core=self.shared_data.core)
                # if self.analysisInfo == 'ChangeStageAtFrame':
                #     analysisResult = self.changeStageAtFrame(image,metadata=metadata,core=self.shared_data.core,frame=500)
                    
                return [analysisResult,metadata]
            elif self.analysisInfo == 'LiveModeVisualisation' or self.analysisInfo == 'mdaVisualisation':
                self.setPriority(self.TimeCriticalPriority) #type:ignore
                return None
            else:
                return None
        else:
            return None

    def initAnalysis(self):
        self.RT_analysis_object = utils.realTimeAnalysis_init(self.analysisInfo,core=self.shared_data.core,nodzInfo=self.nodzInfo)
        logging.debug('run initAnalysis')
        #Make a rtVis thread if required
        #Make a rtVis thread if required
        if '__realTimeVisualisation__' in self.analysisInfo and self.analysisInfo['__realTimeVisualisation__']: #type:ignore
            self.queue_visualisation = deque(maxlen=10)
            self.visualisationObject=AnalysisThread_customFunction_Visualisation(self.RT_analysis_object,self.shared_data,analysisInfo=self.analysisInfo)
            self.visualisationObject.start()
    
    def runAnalysisThisImage(self,analysisInfo,image,metadata=None,shared_data=None,core=None):
        # self.msleep(self.sleepTimeMs)
        # self.msleep(self.sleepTimeMs)
        
        #We are absolutely not allowed to access the core during the real-time analysis running.
        result = utils.realTimeAnalysis_run(self.RT_analysis_object,analysisInfo,image,metadata,shared_data,None,nodzInfo=self.nodzInfo)
        
        logging.info(f"Analysis on Image done with result: {result}")
        
        if '__realTimeVisualisation__' in self.analysisInfo and self.analysisInfo['__realTimeVisualisation__']:#type:ignore
            logging.debug('Attempting RT visualisation!')
            # self.update_napariLayer(analysisInfo,image,metadata=metadata,core=core)
            # if self.visualisationObject.visualisation_queue.empty():
            # print(f'#ac537 -- len of queue: {len(self.visualisationObject.visualisation_queue)}')
            if len(self.visualisationObject.visualisation_queue) < 1:
                # data = (self.RT_analysis_object,analysisInfo,image,metadata,shared_data,core)
                data = (self.RT_analysis_object,analysisInfo,image,metadata,shared_data,core)
                self.visualisationObject.visualisation_queue.append(data)
                self.visualisationObject.new_image() #Signal that we have a new image in the visualisation object
                logging.debug('Put data in visualisation_queue!')
        
        return result
    
    def endAnalysis(self,analysisInfo,core=None):
        self.msleep(self.sleepTimeMs)
        result = utils.realTimeAnalysis_end(self.RT_analysis_object,analysisInfo,core,nodzInfo=self.nodzInfo)
        
        if '__realTimeVisualisation__' in self.analysisInfo and self.analysisInfo['__realTimeVisualisation__']:#type:ignore
            #End the visualisation
            self.visualisationObject.running=False
        return result


def create_real_time_analysis_thread(shared_data,analysisInfo = None,createNewThread = True,throughputThread=None,delay: float|None = None,nodzInfo=None):
    """
    Function that creates separate threads for real-time analysis. 
    """    
    global image_queue_analysis, napariViewer
    napariViewer = shared_data.napariViewer
    if createNewThread == False:
        image_queue_analysis = throughputThread
    else:
        #Create a new analysis thread
        image_queue_analysis = deque(maxlen=10)#queue.Queue() #This now needs to be linked to pycromanager so that pycromanager pushes images to all image queues and not just one
            
    if delay==None:
        #Get the delay of the function from the realTimeAnalysis module
        delay = utils.realTimeAnalysis_getDelay(analysisInfo,runOrVis='run')
    
    # image_queue_analysis = image_queue_transfer
    #Instantiate an analysis thread and add a signal
    analysis_thread = AnalysisThread_customFunction(shared_data,analysisInfo=analysisInfo, analysisQueue=image_queue_analysis,sleepTimeMs = delay,nodzInfo=nodzInfo) #type:ignore
    
    
    analysis_thread.start()
    analysis_thread.finished.connect(analysis_thread.deleteLater)
    
    #Append it to the list of analysisThreads
    shared_data.RTAnalysisQueuesThreads.append({'Queue':image_queue_analysis,'Thread':analysis_thread})
    shared_data.RTAnalysisQueuesThreads.append({'Queue':image_queue_analysis,'Thread':analysis_thread})
    
    return analysis_thread






# #PRETTY SURE THIS IS DEPRECATED
# #Maybe done for MDA visualisation ONLY
# #This code gets some image and does some analysis on this
# class AnalysisThread(QThread):
#     """
#     Obtained streamed data, and perform rt analysis and/or rt visualisation on this.
#     """
#     # Define analysis_done_signal as a class attribute, shared among all instances of AnalysisThread class
#     # Create a signal to communicate between threads
#     analysis_done_signal = pyqtSignal(object)
#     finished = pyqtSignal()# signal to indicate that the thread has finished
#     def __init__(self,shared_data,analysisInfo: Union[str, None] = 'Random',visualisationInfo: Union[str, None] = 'Random',analysisQueue=None,sleepTimeMs=500):
#         """
#         Initializes the AnalysisThread object.

#         Args:
#             shared_data: The shared data object. See Shared_data class for more information
#             analysisInfo (Union[str, None]): Optional. The analysis 'title/method'. Default is 'Random'.
#             visualisationInfo (Union[str, None]): Optional. The visualisation 'title/method'. Default is 'Random'.

#         Returns:
#         None
#         """
#         super().__init__()	
#         logging.debug('#aC - init AnalysisThread')
#         self.is_running = True
#         self.running = self.is_running
#         self.analysis_ongoing = False
#         self.shared_data = shared_data
#         self.analysisInfo = analysisInfo
#         self.visualisationInfo = visualisationInfo
#         self.napariViewer = shared_data.napariViewer
#         self.image_queue_analysis = analysisQueue
#         self.sleepTimeMs = sleepTimeMs
#         if analysisInfo == None:
#             self.napariOverlay = napariOverlay(self.napariViewer,layer_name=None)
#         elif analysisInfo == 'LiveModeVisualisation':
#             self.napariOverlay = napariOverlay(self.napariViewer,layer_name=None)
#             self.sleepTimeMs = 1000/float(self.shared_data.globalData['VISUALISATION-FPS']['value'])
#         elif analysisInfo == 'mdaVisualisation':
#             self.napariOverlay = napariOverlay(self.napariViewer,layer_name=None)
#             self.sleepTimeMs = 1000/float(self.shared_data.globalData['VISUALISATION-FPS']['value'])
#         else:
#             self.napariOverlay = napariOverlay(self.napariViewer,layer_name=analysisInfo)
#             #Create an empty overlay
#             if visualisationInfo != None:
#                 #Activate layer
#                 self.initialise_napariLayer()
    
#     def run(self):
#         """
#         Runs the function in a loop as long as `self.is_running` is True.

#         Args:
#             None

#         Returns:
#             None
#         """
#         while not self.isInterruptionRequested():
#             #Run analysis on the image from the queue
#             # logging.debug(self.image_queue_analysis.get())
#             # if self.image_queue_analysis.qsize() > 0:
#             logging.debug('#aC - runAnalysis is running')
#             if self.image_queue_analysis:
#                 #Get_nowait is not allowed in the following line:
#                 data = self.image_queue_analysis.popleft()
#                 self.analysis_result = self.runAnalysis(data) #type:ignore
#                 self.analysis_done_signal.emit(self.analysis_result)
#                 if self.is_running == False:
#                     # self.finished.emit()
#                     return
#             #Always sleep between frames
#             self.msleep(self.sleepTimeMs)
        
#         # Thread has finished, emit the finished signal
#         self.finished.emit()
        
        
#         # while self.running:
#         #     if not self.image_queue_analysis.empty():
#         #         data = self.image_queue_analysis.get_nowait()
#         #         self.runAnalysis(data)
#         #         self.image_queue_analysis.task_done()
#         #     time.sleep(self.sleepTimeMs/1000.0)
    
#     def stop(self):
#         """
#         Stops the execution of the function
#         """
#         self.is_running = False
#         #Also remove the image queue requestion from live mode
#         # if self.image_queue_analysis in self.shared_data.RTAnalysisQueues:
#         #     self.shared_data.RTAnalysisQueues.remove(self.image_queue_analysis)
#         # if self.image_queue_analysis in self.shared_data.mdaImageQueues:
#         #     self.shared_data.mdaImageQueues.remove(self.image_queue_analysis)
    
#     def destroy(self):
#         """
#         Destroy the object.

#         Args:
#             None

#         Returns:
#             None
#         """
#         try:
#             logging.debug('Destroying '+str(self.analysisInfo))
#         except:
#             logging.debug('Destroying some analysis thread')
#         #Wait for the thread to be finished
#         self.stop()
#         self.requestInterruption()
#         self.quit()
#         #Officially we'd need to wait here, but that seems to start an infinite loop somewhere
#         # self.wait()
#         # self.deleteLater()
    
#     #Get corresponding layer of napariOverlay
#     def getLayer(self):
#         """
#         Obtain the napari overlay layer (napariOverlay class) associated with this analysisThread
        
#         Args:
#             None

#         Returns:
#             napari.layers.Layer: The layer associated with the napari overlay.
#         """
#         return self.napariOverlay.getLayer()
    
#     #Analysis is split into two parts: obtaining the analysis result and displaying this.
#     #Here, we calculate the analysis result based on the analysisInfo
#     def runAnalysis(self,data): 
#         """
#         Runs the analysis on the given image based on the analysis information provided.

#         Args:
#             data, containing:
#             image (Image): The image on which the analysis needs to be performed.
#             metadata: corresponding metadata

#         Returns:
#             analysisResult (Any): The result of the analysis. The analysis result will be passed to Visualise_Analysis_results.

#         Notes:
#             - The layer should be open before running the analysis.
#             - The analysisInfo parameter should be set before calling this function.
#             - If analysisInfo is not set or is invalid, the analysisResult will be None.
#         """
#         if data is not None:
#             if self.analysisInfo == 'LiveModeVisualisation' or self.analysisInfo == 'mdaVisualisation':
#                 self.setPriority(self.TimeCriticalPriority) #type:ignore
#                 return None
#             else:
#                 return None
#         else:
#             return None

#     #And here we perform the visualisation - can be fully separate from performing the analysis
#     #Initialisation is called upon creation
#     def initialise_napariLayer(self):
#         if self.visualisationInfo == 'AvgGrayValueText':
#             self.initAvgGrayValueText()
#         elif self.analysisInfo == 'GrayValueOverlay':
#             self.initGrayScaleImageOverlay()
#         elif self.analysisInfo == 'ChangeStageAtFrame':
#             self.initChangeStageAtFrame()
#         else:
#             self.initRandomOverlay()
            
#     #Update ir called every time the analysis is done
#     def update_napariLayer(self,analysis_data):
#         if analysis_data is not None:
#             analysis_result = analysis_data[0]
#             metadata = analysis_data[1]
#             # logging.debug(analysis_result)
#             if self.analysisInfo is not None and self.analysisInfo != 'LiveModeVisualisation' and self.analysisInfo != 'mdaVisualisation':
#                 if self.visualisationInfo == 'AvgGrayValueText':
#                     self.visualiseAvgGrayValueText(analysis_result=analysis_result,metadata=metadata)
#                 elif self.analysisInfo == 'GrayValueOverlay':
#                     self.visualiseGrayScaleImageOverlay(analysis_result=analysis_result,metadata=metadata)
#                 # else:
#                 #     self.visualiseRandomOverlay()
    
#     def outlineCoordinatesToImage(self,coords):
#     # Create a blank grayscale image with a white background
#         image = Image.new("L", (self.shared_data.core.get_roi().width,self.shared_data.core.get_roi().height), "black")
#         draw = ImageDraw.Draw(image)

#         # Iterate over each n in N
#         for n in range(coords.shape[0]):
#             # Get the x and y coordinates for the current n
#             x = coords[n, 0, :]
#             y = coords[n, 1, :]

#             # Create a list of (x, y) tuples for drawing the lines
#             points = [(x[i], y[i]) for i in range(len(x))]

#             # Draw the lines on the image
#             draw.line(points, fill="white",width=2)  # Use black for the lines

#         # Convert the image to grayscale mode (L)
#         grayscale_image = image.convert("L")
#         return np.fliplr(np.rot90(np.array(grayscale_image),k=3))
    
#     """
#     Testing updating a stage during acq
#     """
    
#     def changeStageAtFrame(self,image,metadata=None,core=None,frame=100):
#         logging.debug(float(metadata['ImageNumber'])) #type:ignore
        
#         if float(metadata['ImageNumber'])>frame and self.notyetchanged == True: #type:ignore
#             core.set_relative_position('Z',100.0) #type:ignore
#             self.notyetchanged = False
#             logging.debug('Z position changed!')
        
#     def initChangeStageAtFrame(self):
#         logging.debug('Initted changestageatframe')
#         self.notyetchanged = True
    
#     """
#     Average gray value calculation and display
#     """
#     #Calculating average gray value of an image
#     def calcAnalysisAvgGrayValue(self,image,metadata=None):
#         return np.mean(np.mean(image))
    
#     def visualiseAvgGrayValueText(self,analysis_result='Random',metadata={}):
#         self.napariOverlay.drawTextOverlay(text='Mean gray value: {:.0f}, at frame: {:.0f}'.format(analysis_result,float(metadata['ImageNumber'])),pos=[0,0],textCol='white',textSize=12)
        
#     def initAvgGrayValueText(self):
#         self.napariOverlay.changeName('Average Gray Value')
#         self.napariOverlay.drawTextOverlay_init()
    
#     """
#     Random overlay display
#     """   
#     def visualiseRandomOverlay(self,analysis_result=None,metadata={}):
#         self.napariOverlay.drawSquaresOverlay(shapePosList=[[random.random()*100,random.random()*100,50,50],[100+random.random()*100,random.random()*100,100,100]],shapeCol=[(random.random(),random.random(),random.random()),(random.random(),random.random(),random.random())])
        
#     def initRandomOverlay(self):
#         self.napariOverlay.changeName('RandomOverlay')
#         self.napariOverlay.shapesOverlay_init()    
    
#     """
#     Testing overlay of image - based on grayscale value
#     """
#     def calcGrayValueOverlay(self,image,metadata=None):
#         #Get an image that simply provides a Boolean based on percentile:
#         image2 = np.where(image<np.percentile(image,25),1,0)
#         return image2
    
#     def visualiseGrayScaleImageOverlay(self,analysis_result=None,metadata={}):
#         #Expected analysis_result is a boolean image.
#         #Create an image overlay from napari
#         self.napariOverlay.drawImageOverlay(im=analysis_result) #type:ignore
    
#     def initGrayScaleImageOverlay(self):
#         self.napariOverlay.imageOverlay_init()
#         self.napariOverlay.changeName('Grayscale Image Overlay')
