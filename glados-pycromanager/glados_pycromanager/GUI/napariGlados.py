import numpy as np
import tempfile
import zarr
from PyQt5.QtCore import pyqtSignal, QObject
import napari
import math
from napari.qt import thread_worker
import time
import queue
from PyQt5.QtWidgets import QMainWindow
from pycromanager import Core
from magicgui import magicgui
from qtpy.QtWidgets import QMainWindow, QVBoxLayout, QWidget, QScrollArea
import sys
import logging
import os, appdirs
from collections import deque


def is_pip_installed():
    return 'site-packages' in __file__ or 'dist-packages' in __file__

if is_pip_installed():
    from glados_pycromanager.GUI.LaserControlScripts import *
    import glados_pycromanager.GUI.napariGlados as napariGlados
    from glados_pycromanager.GUI.MMcontrols import microManagerControlsUI
    from glados_pycromanager.GUI.AnalysisClass import *
    from glados_pycromanager.GUI.Analysis_dockWidgets import *
    from glados_pycromanager.GUI.FlowChart_dockWidgets import *
    from glados_pycromanager.GUI.napariHelperFunctions import getLayerIdFromName, InitateNapariUI
    from glados_pycromanager.GUI.utils import cleanUpTemporaryFiles
    import glados_pycromanager.GUI.utils as utils
    from glados_pycromanager.GUI.custom_widget_ui import Ui_CustomDockWidget  # Import the generated UI module
    from glados_pycromanager.GUI.MDAGlados import MDAGlados
else:
    from custom_widget_ui import Ui_CustomDockWidget  # Import the generated UI module
    from LaserControlScripts import *
    from MMcontrols import microManagerControlsUI
    from AnalysisClass import *
    from Analysis_dockWidgets import *
    from FlowChart_dockWidgets import *
    from napariHelperFunctions import getLayerIdFromName, InitateNapariUI
    from utils import cleanUpTemporaryFiles
    import utils as utils
    from MDAGlados import MDAGlados

def napariUpdateLive_3(DataStruct):
    print('napariupdate live3')
    napariViewer = DataStruct['napariViewer']
    layerName = 'LiveT'
    liveImage = DataStruct['image']
    liveImageLayer = getLayerIdFromName(layerName,napariViewer)

    #If it's the first liveImageLayer
    if not liveImageLayer:
        print('live layer not found - creating')
        nrLayersBefore = len(napariViewer.layers)
        # Create a dask array with random noise
        layer = napariViewer.add_image(liveImage[-1,:,:], rendering='attenuated_mip', name = layerName) #TODO: reimplement colormap, get multi-D testing, get accurate all frames etc
        # layer.scale = [core.get_pixel_size_um(),core.get_pixel_size_um()] #type:ignore
        # layer._keep_auto_contrast = True #type:ignore
        # #Move to the front of the layers
        # # napariViewer.layers.move_multiple([liveImageLayer[0]],len(napariViewer.layers))
        # napariViewer.reset_view()
    #Else if the layer already exists, replace it!
    else:
        # print('live layer found')
        # layer is present, replace its data
        # layer = napariViewer.layers[layerName]
        #Also move to top
        # napariViewer.layers.move_multiple([liveImageLayer[0]],len(napariViewer.layers))
        napariViewer.layers[layerName].data = liveImage[-1,:,:]
        # print(liveImage)
        logging.debug(f'Would Put liveImage in the live layer with sizes: {liveImage.shape} and {napariViewer.layers[layerName].data.shape}')

#These need to be functions outside of any class due to Yield-calling
def napariUpdateLive(DataStructure):
    """ 
    Function that finally shows the  image in napari
    
    Basically the core visualisation method
    """
    
    #The min_delay_time is here to prevent 2 frames updating 1ms after one another if they arrive like this. Ideally, we wait exactly the frame-time between frames.
    min_delay_time = np.min(((50/1000),(float(shared_data.core.get_exposure())*0.99)/1000)) #Never more than 50 ms! This is on the main thread, so we don't want to unnecessarily wait.
    
    #TODO: Make this an advanced variable or so. 
    #JAVA is way slower so needs this longer update time of the display
    if shared_data.backend == 'JAVA':
        display_update_time = 1/float(shared_data.globalData['VISUALISATION-FPS']['value']) #0.05
    elif shared_data.backend == 'Python':
        display_update_time = 1/float(shared_data.globalData['VISUALISATION-FPS']['value'])#0.05
    
    if time.time() - shared_data.last_display_update_time < display_update_time: #less than a 50-100ms ago already update live mode? wait a bit before displaying live then.
        logging.debug('Updated live preview Hindered (due to display update time) at time {}'.format(time.time()))
        #Sleep for the remainder, then continue
        # time.sleep(display_update_time)
        return
    
    if time.time()-shared_data.last_display_update_time<min_delay_time and time.time()-shared_data.last_display_update_time>1/1000:
        logging.debug('Updated live preview Delayed (due to display update time) val found {}'.format(time.time()-shared_data.last_display_update_time))
        logging.debug('Updated live preview Delayed (due to display update time) by {}'.format(min_delay_time-(time.time()-shared_data.last_display_update_time)))
        #Sleep for the remainder, then continue
        time.sleep(min_delay_time-(time.time()-shared_data.last_display_update_time))
        
    shared_data.debugImageDisplayTimes.append(time.time())
    napariViewer = DataStructure['napariViewer']
    acqstate = DataStructure['acqState']
    core = DataStructure['core']
    image_queue_analysisA = DataStructure['image_queue_analysis']
    analysisThreads = DataStructure['analysisThreads']
    layerName = DataStructure['layer_name']
    
    
    # Check if the update is in progress
    if shared_data.liveModeUpdateOngoing:
        return
    
    shared_data.liveModeUpdateOngoing = True
    
    #Visualise the MDA data on a frame-by-frame method - i.e. not a 'stack', but simply a single image which is replaced every frame update
    if shared_data.globalData['MDAVISMETHOD']['value'] == 'frameByFrame' or DataStructure['layer_name']=='Live':
        liveImage = DataStructure['data'][0]
        metadata = DataStructure['data'][1]
        if liveImage is None:
            return
        if acqstate == False:
            return
        liveImageLayer = getLayerIdFromName(layerName,napariViewer)

        #If it's the first liveImageLayer
        if not liveImageLayer:
            nrLayersBefore = len(napariViewer.layers)
            layer = napariViewer.add_image(liveImage, rendering='attenuated_mip', colormap=DataStructure['layer_color_map'],name = layerName)
            #Set correct scale - in nm
            layer.scale = [core.get_pixel_size_um(),core.get_pixel_size_um()] #type:ignore
            layer._keep_auto_contrast = True #type:ignore
            #Move to the front of the layers
            # napariViewer.layers.move_multiple([liveImageLayer[0]],len(napariViewer.layers))
            napariViewer.reset_view()
        #Else if the layer already exists, replace it!
        else:
            # layer is present, replace its data
            layer = napariViewer.layers[liveImageLayer[0]]
            #Also move to top
            # napariViewer.layers.move_multiple([liveImageLayer[0]],len(napariViewer.layers))
            layer.data = liveImage
            logging.debug('Put liveImage in the live layer')
    
    #Visualise the MDA data via a 'stack' - i.e. a multiD method where the user can (later) scroll through the frames
    elif shared_data.globalData['MDAVISMETHOD']['value'] == 'multiDstack':
        if DataStructure['finalisationProcedure'] == False:
            liveImage = DataStructure['data'][0]
            metadata = DataStructure['data'][1]
            latestImage = DataStructure['data'][0]
            metadata = DataStructure['data'][1]
            if latestImage is None:
                return
            if acqstate == False:
                return
            liveImageLayer = getLayerIdFromName(layerName,napariViewer)
        
        
            if layerName != 'Live':
                #In case MDA is done repeatedly, the layer already exists, but the dimensions might be wrong. If this is the case, we reshape the MDA layer
                if liveImageLayer:
                    dimensionOrder, n_entries_in_dims, uniqueEntriesAllDims = utils.getDimensionsFromAcqData(shared_data._mdaModeParams)
                    
                    #Assume the dimensions are correct
                    correctDimensions = True
                    
                    #Then check if anywhere the dimensions of the layer are wrong
                    #Check if we have the correct nr of dimensions
                    CurrentLayer = napariViewer.layers[liveImageLayer[0]]
                    if CurrentLayer.ndim != len(uniqueEntriesAllDims)+2: #Note: +2 for image xy
                        correctDimensions = False
                    else:
                        layerData = CurrentLayer.data
                        #Check each dimension as follows:
                        for dim_id in range(0,len(uniqueEntriesAllDims)):
                            #Check if it has the correct label
                            # logging.debug(f'axis_labels: {napariViewer.dims.axis_labels[dim_id]} vs {dimensionOrder[dim_id]}')
                            # if napariViewer.dims.axis_labels[dim_id] != dimensionOrder[dim_id]:
                            #     correctDimensions = False
                            #     break
                            #Check it has the correct length:
                            logging.debug(f'range: {layerData.shape[dim_id]} vs {n_entries_in_dims[dim_id]}')
                            if int(layerData.shape[dim_id]) != n_entries_in_dims[dim_id]:
                                correctDimensions = False
                                break
                            
                    #Remove the layer if the dimensions are wrong
                    if correctDimensions == False:
                        logging.debug('removing mdaZarrData - looping over layers')
                        #Remove the mdaZarrData array and ensure that we create a new layer
                        for tLayerIndex in range(0,len(napariViewer.layers)):
                            tLayer = napariViewer.layers[tLayerIndex]
                            logging.debug(f'layer: {tLayer}, comparing with {napariViewer.layers[liveImageLayer[0]].name}, boolTest {str(tLayer) == str(napariViewer.layers[liveImageLayer[0]].name)}')
                            if str(tLayer) == str(napariViewer.layers[liveImageLayer[0]].name):
                                #If we found the layer, delete it, and ensure we create a new one
                                logging.debug(f'found layer to remove: {tLayer} at {tLayerIndex}')
                                napariViewer.layers.pop(tLayerIndex)
                                shared_data.mdaZarrData[layerName] = None
                                liveImageLayer = False
                                break
        
            #If it's the first layer
            if not liveImageLayer:
                if layerName != 'Live':
                    logging.debug(f'creating layer with name {layerName} via multiDstack method')
                    dimensionOrder, n_entries_in_dims, uniqueEntriesAllDims = utils.getDimensionsFromAcqData(shared_data._mdaModeParams)
                    logging.debug(f"obtained dimensions: {dimensionOrder} and n_entries_in_dims: {n_entries_in_dims}")
                    
                    shape = n_entries_in_dims
                    shared_data.mdaZarrData[layerName] = zarr.open(
                            str(tempfile.TemporaryDirectory().name),
                            shape = shape+[latestImage.shape[0],latestImage.shape[1]],
                            chunks = tuple([1] * len(shape) + [latestImage.shape[0],liveImage.shape[1]]),
                            )
                    #Changing the first image to the latest acquired image
                    shared_data.mdaZarrData[layerName][(0,) * len(shape) + (slice(None),slice(None))] = latestImage
                    shared_data.allMDAslicesRendered = {}
                    
                    layer = napariViewer.add_image(shared_data.mdaZarrData[layerName], colormap=DataStructure['layer_color_map'],name = layerName)
                    #Set correct scale - in nm
                    layer.scale = [core.get_pixel_size_um(),core.get_pixel_size_um()] #type:ignore
                    layer._keep_auto_contrast = True #type:ignore
                    
                    for dim_id in range(len(n_entries_in_dims)):
                        napariViewer.dims.set_axis_label(dim_id, dimensionOrder[dim_id])
                    #Move to the front of the layers
                    # napariViewer.layers.move_multiple([liveImageLayer[0]],len(napariViewer.layers))
                    napariViewer.reset_view()
                    
                    #set the napariViewer to the correct slices:
                    for dim_id in range(len(n_entries_in_dims)):
                        napariViewer.dims.set_current_step(dim_id,0)
                else:
                    nrLayersBefore = len(napariViewer.layers)
                    layer = napariViewer.add_image(latestImage, colormap=DataStructure['layer_color_map'],name = layerName)
                    #Set correct scale - in nm
                    layer.scale = [core.get_pixel_size_um(),core.get_pixel_size_um()] #type:ignore
                    layer._keep_auto_contrast = True #type:ignore
                    #Move to the front of the layers
                    # napariViewer.layers.move_multiple([liveImageLayer[0]],len(napariViewer.layers))
                    napariViewer.reset_view()
            #Else if the layer already exists, replace it!
            else:
                if layerName != 'Live':
                    # logging.debug(f'updating layer with name {layerName} via multiDstack method')
                    dimensionOrder, n_entries_in_dims, uniqueEntriesAllDims = utils.getDimensionsFromAcqData(shared_data._mdaModeParams)
                    
                    #Determine in which multi-D slice the image should be added:
                    sliceTuple = ()
                    for dim_id in range(len(n_entries_in_dims)):
                        currentSlice = metadata['Axes'][dimensionOrder[dim_id]]
                        currentSliceID = uniqueEntriesAllDims[dimensionOrder[dim_id]].tolist().index(currentSlice)
                        logging.debug(f"currentSlice[{dim_id}]: {currentSliceID}")
                        sliceTuple += (int(currentSliceID),)
                        
                    shared_data.mdaZarrData[layerName][sliceTuple + (slice(None),slice(None))] = liveImage #type:ignore
                    
                    #set the napariViewer to the correct slice:
                    for dim_id in range(len(n_entries_in_dims)):
                        currentSlice = metadata['Axes'][dimensionOrder[dim_id]]
                        currentSliceID = uniqueEntriesAllDims[dimensionOrder[dim_id]].tolist().index(currentSlice)
                        napariViewer.dims.set_current_step(dim_id,int(currentSliceID))
                    
                    #Store exactly which axes is rendered
                    shared_data.allMDAslicesRendered[len(shared_data.allMDAslicesRendered)] = metadata['Axes']
                else:
                    # layer is present, replace its data
                    layer = napariViewer.layers[liveImageLayer[0]]
                    #Also move to top
                    napariViewer.layers.move_multiple([liveImageLayer[0]],len(napariViewer.layers))
                    layer.data = liveImage
                    
        elif DataStructure['finalisationProcedure'] == True:
            #Render the missing images in the MDA acquisition
            shared_data._busy = True
            renderedSlices = shared_data.allMDAslicesRendered
            dimensionOrder, n_entries_in_dims, uniqueEntriesAllDims = utils.getDimensionsFromAcqData(shared_data._mdaModeParams)
            for expectedEntry in shared_data._mdaModeParams:
                #check in the rendered sclies if this is in there:
                entry_found = any(expectedEntry['axes'].items() <= item.items() for item in renderedSlices.values())
                if not entry_found:
                    time.sleep(0.001) #Can't explain why, but a sleep of 1 ms is super important for stability
                    
                    #Figure out which slice to read
                    readChannel = None
                    readZ = None
                    readTime = None
                    readPosition = None
                    readRow = None
                    readColumn = None
                    for key, value in expectedEntry['axes'].items():
                        if key == 'channel':
                            readChannel = value
                        if key == 'z':
                            readZ = value
                        if key == 'time':
                            readTime = value
                        if key == 'position':
                            readPosition = value
                        if key == 'row':
                            readRow = value
                        if key == 'column':
                            readColumn = value
                    #Read this slice from the NDDataset:
                    try:
                        # logging.debug(shared_data._mdaModeAcqData._dataset)
                        # logging.debug(f"Attempting reading slice at: {readChannel}, {readZ}, {readTime}, {readPosition}, {readRow}, {readColumn}")
                        sliceImage = shared_data._mdaModeAcqData._dataset.read_image(channel=readChannel,z=readZ,time=readTime,position=readPosition,row=readRow,column=readColumn)
                        # logging.debug(f"sliceImage: {sliceImage}")
                        
                        #Find the correct slice to slot it in
                        sliceTuple = ()
                        for dim_id in range(len(n_entries_in_dims)):
                            currentSlice = expectedEntry['axes'][dimensionOrder[dim_id]]
                            currentSliceID = uniqueEntriesAllDims[dimensionOrder[dim_id]].tolist().index(currentSlice)
                            sliceTuple += (int(currentSliceID),)
                        #Put it in
                        shared_data.mdaZarrData[layerName][sliceTuple + (slice(None),slice(None))] = sliceImage 
                        logging.debug(f"Added entry {expectedEntry} not rendered in the MDA acquisition")
                    except:
                        logging.debug(f'Entry {expectedEntry} tried, but not acquired')
            
            logging.debug('Finalised up visualisation...')
            #Move to the end
            # napariViewer.dims.set_point(0,timeslice)
            shared_data._busy = False
    
    shared_data.last_display_update_time = time.time()
    shared_data.liveModeUpdateOngoing = False
    
def napariUpdateAnalysisThreads(DataStructure):
    """ 
    Function that finally shows the  image in napari
    """
    napariViewer = DataStructure['napariViewer']
    acqstate = DataStructure['acqState']
    core = DataStructure['core']
    image_queue_analysisA = DataStructure['image_queue_analysis']
    analysisThreads = DataStructure['analysisThreads']
    logging.debug('NapariUpdateLive Ran at time {}'.format(time.time()))
    liveImage = DataStructure['data'][0]
    metadata = DataStructure['data'][1]
    layerName = DataStructure['layer_name']
    if liveImage is None:
        return
    if acqstate == False:
        return
    liveImageLayer = getLayerIdFromName(layerName,napariViewer)

    # Check if the queue is empty
    # if image_queue_analysisA.empty():
    if len(image_queue_analysisA) < 3:
        image_queue_analysisA.append([liveImage,metadata,shared_data])
        #Start all analysisthreads
        for analysisThread in analysisThreads:
            if not analysisThread.isRunning():
                logging.debug(f'starting analysis thread: {analysisThread}')
                analysisThread.start()


# def start_napari_signalling(viewer, dataset):
    """
    Start up a threadworker, which will check for new images arrived in the dataset
    and then signal to napari to update or refresh as needed
    :param viewer: the napari Viewer
    :param dataset: the Datatset being acquired
    :return:
    """

    # def update_layer(image):
    #     """
    #     update the napari layer with the new image
    #     """
    #     print('in updatelayer')
    #     if image is not None:
    #         try:
    #             viewer.layers['pycromanager acquisition'].data = image
    #         except KeyError:
    #             viewer.add_image(image, name='pycromanager acquisition')

    # def printvv(image):
    #     print('asdf')
    # @thread_worker(connect={'yielded': printvv})
    # def napari_signaller():
    #     """
    #     Monitor for signals that Acquisition has a new image ready, and when that happens
    #     update napari appropriately
    #     """
    #     print('AAAAAAAAAAAAAAAAAHUPDATELAYER')
    #     # don't update faster than the display can handle
    #     min_update_time = 1 / 30
    #     last_update_time = time.time()
    #     while True:
    #         print('attempting this new method')
    #         dataset_writing_complete = dataset.is_finished()
    #         new_image_ready = dataset.await_new_image(timeout=.25)
    #         if not new_image_ready:
    #             continue
    #         print('attempting this new method - image found')
    #         image = dataset.as_array()
    #         update_time = time.time()
    #         yield image
    #         if dataset_writing_complete:
    #             break
    #         if update_time - last_update_time < min_update_time:
    #             time.sleep(min_update_time - (update_time - last_update_time))
    #         last_update_time = time.time()

    # napari_signaller()
class napariHandler():
    def __init__(self, shared_data,liveOrMda='live') -> None:
        self.shared_data = shared_data
        self.napariViewer = shared_data.napariViewer
        if liveOrMda == 'live':
            self.liveOrMda = 'live'
            self.acqstate = shared_data.liveMode
        elif liveOrMda == 'mda':
            self.liveOrMda = 'mda'
            self.acqstate = shared_data.mdaMode
        # Define a flag to control the continuous task
        self.stop_continuous_task = False
        # empty queue for (live) image data
        self.img_queue = deque()#queue.Queue() #Testing
        # Create a queue to pass image data between threads
        self.image_queue_analysis = deque()
        # Create a signal to communicate between threads
        self.mda_acq_done_signal = pyqtSignal(bool)

        #Sleep time to keep responsiveness
        self.sleep_time = 1/shared_data.globalData['VISUALISATION-FPS']['value'] #in sec
        self.layerName = 'newLayer'

        #Start this shit
        # self.stuurman_napari_implementation()

    def mdaacqdonefunction(self):
        logging.debug('mdaacqdonefunction called in napariHandler')
        self.shared_data.mdaacqdonefunction()
        
    def grab_image_liveVisualisation_and_liveAnalysis(self,image,metadata, event_queue):
        """ 
        Function that runs on every frame obtained in live mode and puts it in the image queue(s)
        
        Inputs: array image: image from micromanager
                metadata: metadata from micromanager
        """
        logging.debug('Updated live preview requesting grab_image_liveVisualisation_and_liveAnalysis at time {}'.format(time.time()))
        if self.acqstate:
            if len(self.img_queue) < 2:
                logging.debug('Updated live preview put in self.img_queue -lvla')
                self.img_queue.append([image,metadata]) #Don't use put_nowait
                
            #Loop over all queues in shared_data.liveImageQueues and also append the image there:
            for queue in self.shared_data.liveImageQueues:
                if len(queue) < 2:
                    # logging.debug('Updated live preview put in self.liveImageQueue: {} -lvla'.format(queue))
                    queue.append([image,metadata]) #Don't use put_nowait
                        
            # if len(self.image_queue_analysis) < 3:
            #     logging.debug('Updated live preview put in self.image_queue_analysis -lvla')
            #     self.image_queue_analysis.append([image,metadata]) #Don't use put_nowait
            
        else:
            logging.info('Broke off live mode')
            event_queue.clear()
            try:
                acq.abort()
                logging.debug('aborted acquisition')
            except:
                logging.debug('attemped to abort acq')
        
        # return image, metadata
        
    def grab_image_liveVisualisation_and_liveAnalysis_savedFn(self,axes,dataset, event_queue):
        """ 
        Function that runs on every frame obtained in live mode and putis in the image queue
        
        Inputs: array image: image from micromanager
                metadata: metadata from micromanager
        """
        logging.debug('Updated preview requesting grab_image_liveVisualisation_and_liveAnalysis_savedFn at time {}'.format(time.time()))
        shared_data.debugImageArrivalTimes.append(time.time())
        if self.acqstate:
            #Check if there is any reason to read the image:
            reasonToReadImage = False
            if len(self.img_queue) < 2:
                reasonToReadImage = True
            for queue in self.shared_data.liveImageQueues:
                if len(queue) < 2:
                    reasonToReadImage = True
            if len(self.image_queue_analysis) < 2:
                reasonToReadImage = True
                
            if reasonToReadImage:
                image = dataset.read_image(**axes)
                metadata = {}
                metadata['Axes']=axes
                logging.debug(f'grab_image_liveVisualisation_and_liveAnalysis_savedFn called in napariHandler read image: {dataset}, axes: {axes}, metadata: {metadata}')
                if len(self.img_queue) < 2:
                    self.img_queue.append([image,metadata])
                    
                #Loop over all queues in shared_data.liveImageQueues and also append the image there:
                for queue in self.shared_data.liveImageQueues:
                    if len(queue) < 2:
                        queue.append([image,metadata])
                            
                # if len(self.image_queue_analysis) < 2:
                #     self.image_queue_analysis.append([image,metadata])
            
        else:
            logging.info('Broke off live mode')
            event_queue.clear()
            try:
                acq.abort()
                logging.debug('aborted acquisition')
            except:
                logging.debug('attemped to abort acq')
        
        # return image, metadata


    

    @thread_worker
    def run_pycroManagerAcquisition_worker(self,parent):
        """ 
        Worker which handles live mode on/off turning etc
        
        Inputs: img_queue (unused, but required)
        """
        img_queue = parent.img_queue
        shared_data.debugImageArrivalTimes=[]
        shared_data.debugImageDisplayTimes=[]
        global acq
        # shared_data = self.shared_data
        logging.debug('in run_pycroManagerAcquisition_worker')
        #The idea of live mode is that we do a very very long acquisition (10k frames), and real-time show the images, and then abort the acquisition when we stop life.
        #The abortion is handled in grab_image_liveVisualisation_and_liveAnalysis
        if self.liveOrMda == 'live':
            while self.acqstate:
                if self.shared_data.mdaMode:
                    logging.error('LIVE NOT STARTED! MDA IS RUNNING')
                    self.shared_data.liveMode = False
                else:        
                    #JavaBackendAcquisition is an acquisition on a different thread to not block napari I believe
                    logging.debug('starting acq')
                    self.shared_data.allMDAslicesRendered = {}
                    #Already move the live layer to top
                    logging.debug('BMoved layer to top')
                    # moveLayerToTop(self.shared_data.napariViewer,"Live")
                    #
                    
                    #Acquisitions are slightly tricky. If run Headlessly, we take images directly from image_process_fn. However, if we run with a MM instance running, we use the image_saved_fn
                    if shared_data._headless and shared_data.backend == 'Python':
                        with Acquisition(directory=None, name=None, show_display=False, image_process_fn = self.grab_image_liveVisualisation_and_liveAnalysis ) as acq: #type:ignore
                            self.shared_data._mdaModeAcqData = acq
                            events = multi_d_acquisition_events(num_time_points=9999, time_interval_s=0)
                            acq.acquire(events)
                    else:
                        with Acquisition(directory=None, name=None, show_display=False, image_saved_fn = self.grab_image_liveVisualisation_and_liveAnalysis_savedFn ) as acq: #type:ignore
                            self.shared_data._mdaModeAcqData = acq
                            events = multi_d_acquisition_events(num_time_points=9999, time_interval_s=0)
                            acq.acquire(events)

                    logging.debug('After Acq Live')
            #Now we're after the livestate
            self.shared_data.core.stop_sequence_acquisition()
            self.shared_data.liveMode = False
            #We clean up, removing all LiveAcqShouldBeRemoved folders in /Temp:
            cleanUpTemporaryFiles(shared_data=self.shared_data)
        elif self.liveOrMda == 'mda':
            while self.acqstate:
                if self.shared_data.liveMode:
                    self.shared_data.liveMode = False
                    time.sleep(0.2)
                    
                #JavaBackendAcquisition is an acquisition on a different thread to not block napari I believe
                logging.debug('starting MDA acq - before JavaBackendAcquisition')
                savefolder = None#'./temp'
                savename = None#'MdaAcqShouldBeRemoved'
                if self.shared_data._mdaModeSaveLoc[0] != '':
                    savefolder = self.shared_data._mdaModeSaveLoc[0]
                    
                    savefolderAdv = utils.nodz_evaluateAdv(savefolder,self.shared_data.nodzInstance)
                    if savefolderAdv != None:
                        savefolder = savefolderAdv
                    logging.debug(savefolder)
                    
                if self.shared_data._mdaModeSaveLoc[1] != '':
                    savename = self.shared_data._mdaModeSaveLoc[1]
                    savenameAdv = utils.nodz_evaluateAdv(savename,self.shared_data.nodzInstance)
                    if savenameAdv != None:
                        savename = savenameAdv
                    logging.debug(savename)
                if self.shared_data._mdaModeNapariViewer != None:
                    napariViewer = self.shared_data._mdaModeNapariViewer
                    showdisplay = True
                else:
                    napariViewer = None
                    showdisplay = False
                    
                napariViewer = None
                showdisplay = False
                self.shared_data.allMDAslicesRendered = {}
                #Already move the layer to top
                # if self.shared_data.newestLayerName != '':
                #     moveLayerToTop(self.shared_data.napariViewer,self.shared_data.newestLayerName)
                
                
                if shared_data._headless and shared_data.backend == 'Python':
                    with Acquisition(directory=savefolder, name=savename, show_display=showdisplay, image_process_fn = self.grab_image_liveVisualisation_and_liveAnalysis,napari_viewer=napariViewer) as acq: #type:ignore
                        self.shared_data._mdaModeAcqData = acq
                        events = self.shared_data._mdaModeParams
                        acq.acquire(events)
                else:
                    with Acquisition(directory=savefolder, name=savename, show_display=showdisplay,napari_viewer=napariViewer, image_saved_fn = self.grab_image_liveVisualisation_and_liveAnalysis_savedFn ) as acq: #type:ignore
                        self.shared_data._mdaModeAcqData = acq
                        events = self.shared_data._mdaModeParams
                        acq.acquire(events)
                
                self.shared_data.mdaMode = False
                self.acqstate = False #End the MDA acq state
                self.shared_data.appendNewMDAdataset(acq.get_dataset())

            logging.debug('Stopping the acquisition from napariHandler')
            #Now we're after the acquisition
            self.shared_data.core.stop_sequence_acquisition()
            self.shared_data.mdaMode = False
            
            #Signal to all parents that the MDA acquisition is done - in the Nodz MDA, now we would trigger the MDA-based analysis for scoring or so
            parent.mdaacqdonefunction()
            
            #We clean up, removing all LiveAcqShouldBeRemoved folders in /Temp:
            cleanUpTemporaryFiles(shared_data=self.shared_data)
    
    @thread_worker(connect={'yielded': napariUpdateAnalysisThreads})
    def run_analysis_worker(self,parent,layerName='Layer',layerColorMap='gray'):
        """
        Worker which handles the visualisation of the real-time analyses
        Connected to display_napari function to update display 
        """
        img_queue = parent.image_queue_analysis
        while self.acqstate:
            time.sleep(0)
            # get elements from queue while there is more than one element
            # playing it safe: I'm always leaving one element in the queue
            while len(img_queue) > 1:
                DataStructure = {}
                DataStructure['data'] = img_queue.popleft()
                DataStructure['napariViewer'] = self.shared_data.napariViewer
                DataStructure['acqState'] = self.acqstate
                DataStructure['core'] = self.shared_data.core
                DataStructure['image_queue_analysis'] = self.image_queue_analysis
                DataStructure['analysisThreads'] = self.shared_data.analysisThreads
                logging.info('adding analysisThread in run_analysis_worker 1')
                DataStructure['layer_name'] = layerName
                DataStructure['layer_color_map'] = layerColorMap
                DataStructure['finalisationProcedure'] = False
                yield DataStructure

    @thread_worker(connect={'yielded': napariUpdateLive})
    def run_napariVisualisation_worker(self,parent,layerName='Layer',layerColorMap='gray'):
        """
        Worker which handles the visualisation of the live mode queue
        Connected to display_napari function to update display 
        """
        img_queue = parent.img_queue
        while self.acqstate:
            
            # get elements from queue while there is more than one element
            if img_queue:
                logging.debug('napariVisualisationWorkerLoop')
                if img_queue:
                    DataStructure = {}
                    DataStructure['data'] = img_queue.popleft()
                    DataStructure['napariViewer'] = self.shared_data.napariViewer
                    DataStructure['acqState'] = self.acqstate
                    DataStructure['core'] = self.shared_data.core
                    DataStructure['image_queue_analysis'] = self.image_queue_analysis
                    DataStructure['analysisThreads'] = self.shared_data.analysisThreads
                    logging.info('adding analysisThread in run_napariVisualisation_worker 1')
                    logging.info(str(self.shared_data.analysisThreads))
                    DataStructure['layer_name'] = layerName
                    DataStructure['layer_color_map'] = layerColorMap
                    DataStructure['finalisationProcedure'] = False
                    logging.debug('live mode worker - yield DataStructure')
                    yield DataStructure
            
            time.sleep(self.sleep_time) #This sleep time is based on the visualisation FPS in the adv. settings
            # time.sleep(1/240) #Sleep briefly to retain responsiveness on this thread
            
            # time.sleep(min(0.1,time.time() - shared_data.last_display_update_time))
            
            # 
                # self.napariUpdateLive(img_queue.get(block=False))

        # read out last remaining element(s) after end of acquisition
        while img_queue:
            DataStructure = {}
            DataStructure['data'] = img_queue.popleft()
            DataStructure['napariViewer'] = self.shared_data.napariViewer
            DataStructure['acqState'] = self.acqstate
            DataStructure['core'] = self.shared_data.core
            DataStructure['image_queue_analysis'] = self.image_queue_analysis
            DataStructure['analysisThreads'] = self.shared_data.analysisThreads
            logging.info('adding analysisThread in run_napariVisualisation_worker 2')
            DataStructure['layer_name'] = layerName
            DataStructure['layer_color_map'] = layerColorMap
            DataStructure['finalisationProcedure'] = False
            yield DataStructure#img_queue.get(block = False)
            
        #Do the final N images
        if self.shared_data.globalData['MDAVISMETHOD']['value'] == 'multiDstack':
            if layerName == 'MDA':
                logging.debug('Finalising MDA visualisation...')
                DataStructure = {}
                DataStructure['data'] = None
                DataStructure['napariViewer'] = self.shared_data.napariViewer
                DataStructure['acqState'] = self.acqstate
                DataStructure['core'] = self.shared_data.core
                DataStructure['image_queue_analysis'] = self.image_queue_analysis
                DataStructure['analysisThreads'] = self.shared_data.analysisThreads
                logging.info('adding analysisThread in run_napariVisualisation_worker 3')
                DataStructure['layer_name'] = layerName
                DataStructure['layer_color_map'] = layerColorMap
                DataStructure['finalisationProcedure'] = True
                napariUpdateLive(DataStructure)
        
        # shared_data.analysisThreads.remove(shared_data.lastMDAThread)
        # shared_data.lastMDAThread.destroy()
        # shared_data.lastMDAThread = None
        logging.debug("acquisition done")
        self.shared_data.liveModeUpdateOngoing = False

    def acqModeChanged(self, newSharedData = None):
        """
        General function which is called if live mode is changed or not. Generally called from sharedFunction - when self._liveMode is altered
        
        Is called, and shared_data.liveMode should be changed seperately from running this funciton
        """
        logging.debug('acqModeChanged called from napariHandler')
        if newSharedData is not None:
            global napariViewer, shared_data, Core
            self.shared_data = newSharedData
            shared_data = self.shared_data
            napariViewer = self.shared_data.napariViewer
            core = self.shared_data.core
            
        if self.liveOrMda == 'live':
            #Hook the live mode into the scripts here
            if self.shared_data.liveMode == False:
                self.acqstate = False
                self.stop_continuous_task = True
                #Clear the image queue
                self.img_queue.clear()
                logging.info("Live mode stopped")
            else:
                logging.debug('liveMode changed to TRUE')
                self.acqstate = True
                self.stop_continuous_task = False
                #Always start live-mode visualisation:
                napariGlados.startLiveModeVisualisation(self.shared_data)
                #Move layer to top - if it isn't created yet, it will fail
                moveLayerToTop(self.shared_data.napariViewer,"Live")
                
                #Start the worker to run the pycromanager acquisition
                worker1 = self.run_pycroManagerAcquisition_worker(self) #type:ignore
                worker1.start() #type:ignore
                # worker2 = self.run_analysis_worker(self) #type:ignore
                
                logging.info("Live mode started")
        elif self.liveOrMda == 'mda':
            #Hook the live mode into the scripts here
            if self.shared_data.mdaMode == False:
                self.acqstate = False
                self.stop_continuous_task = True
                #Clear the image queue
                self.img_queue.clear()
                logging.info("MDA mode stopped from acqModeChanged")
                # self.mdaacqdonefunction()
            else:
                logging.debug('mdaMode changed to TRUE')
                self.acqstate = True
                self.stop_continuous_task = False
                #Move layer to top - if it isn't created yet, it will fail
                if self.shared_data.newestLayerName != '':
                    moveLayerToTop(self.shared_data.napariViewer,self.shared_data.newestLayerName)
                #Start the two workers, one to run it, one to visualise it.
                worker1 = self.run_pycroManagerAcquisition_worker(self) #type:ignore
                # worker2 = self.run_napariVisualisation_worker(self) #type:ignore
                worker1.start() #type:ignore
                # worker2.start()
                logging.debug("MDA mode started from acqModeChanged")

class napariHandler_liveMode(napariHandler):
    def __init__(self, shared_data) -> None:
        super().__init__(shared_data, liveOrMda='live')

class napariHandler_mdaMode(napariHandler):
    def __init__(self, shared_data) -> None:
        super().__init__(shared_data, liveOrMda='mda')
""" 
Napari widgets
"""

class dockWidgets(QMainWindow):
    sizeChanged = pyqtSignal(QSize)
    
    def resizeEvent(self, event):
        super().resizeEvent(event)
        self.sizeChanged.emit(event.size())
        
    def __init__(self):
        logging.debug('dockwidget started')
        super().__init__()
        #Create all the widgets/layouts:
        self.central_widget = QWidget(self)
        self.central_layout = QVBoxLayout()
        self.scroll_area = QScrollArea()
        self.scroll_area.setWidgetResizable(True)
        self.content_widget = QWidget()
        self.layout = QGridLayout() #type:ignore
        
        #Order them logically:
        self.content_widget.setLayout(self.layout)
        self.scroll_area.setWidget(self.content_widget)
        self.central_layout.addWidget(self.scroll_area)
        self.central_widget.setLayout(self.central_layout)
        self.setCentralWidget(self.central_widget)
        
        self.dockWidget = None

        #we end up with self.layout() that's changed by every indiv dockwidget
        
    def getDockWidget(self):
        return self.dockWidget

class dockWidget_MMcontrol(dockWidgets):
    def __init__(self): 
        logging.debug("dockWidget_MMcontrol started")
        super().__init__()
        #Add the full micro manager controls UI
        self.dockWidget = microManagerControlsUI(core,MM_JSON,self.layout,shared_data)

class dockWidget_MDA(dockWidgets):
    def __init__(self): 
        logging.debug("dockWidget_MDA started")
        super().__init__()
        
        #load from appdata
        appdata_folder = appdirs.user_data_dir()#os.getenv('APPDATA')
        if appdata_folder is None:
            raise EnvironmentError("APPDATA environment variable not found")
        app_specific_folder = os.path.join(appdata_folder, 'Glados-PycroManager')
        os.makedirs(app_specific_folder, exist_ok=True)
        if os.path.exists(os.path.join(app_specific_folder, 'glados_state.json')):
            #Load the mda state
            with open(os.path.join(app_specific_folder, 'glados_state.json'), 'r') as file:
                gladosInfo = json.load(file)
                mdaInfo = gladosInfo['MDA']
            
            try:
                #Add the full micro manager controls UI
                self.dockWidget = MDAGlados(core,MM_JSON,self.layout,shared_data,
                            hasGUI=True,
                            num_time_points = mdaInfo['num_time_points'], 
                            time_interval_s = mdaInfo['time_interval_s'], 
                            time_interval_s_or_ms = mdaInfo['time_interval_s_or_ms'],
                            z_start = mdaInfo['z_start'],
                            z_end = mdaInfo['z_end'],
                            z_step = mdaInfo['z_step'],
                            z_stage_sel = mdaInfo['z_stage_sel'],
                            z_nr_steps = mdaInfo['z_nr_steps'],
                            z_step_distance = mdaInfo['z_step_distance'],
                            z_nrsteps_radio_sel = mdaInfo['z_nrsteps_radio_sel'],
                            z_stepdistance_radio_sel = mdaInfo['z_stepdistance_radio_sel'],
                            channel_group = mdaInfo['channel_group'],
                            channels = mdaInfo['channels'],
                            channel_exposures_ms = mdaInfo['channel_exposures_ms'],
                            xy_positions = mdaInfo['xy_positions'],
                            xyz_positions = mdaInfo['xyz_positions'],
                            position_labels = mdaInfo['position_labels'],
                            exposure_ms = mdaInfo['exposure_ms'],
                            exposure_s_or_ms = mdaInfo['exposure_s_or_ms'],
                            storage_folder = mdaInfo['storage_folder'],
                            storage_file_name = mdaInfo['storage_file_name'],
                            order = mdaInfo['order'],
                            GUI_show_exposure = mdaInfo['GUI_show_exposure'], 
                            GUI_show_xy = mdaInfo['GUI_show_xy'], 
                            GUI_show_z = mdaInfo['GUI_show_z'], 
                            GUI_show_channel = mdaInfo['GUI_show_channel'], 
                            GUI_show_time = mdaInfo['GUI_show_time'], 
                            GUI_show_order = mdaInfo['GUI_show_order'], 
                            GUI_show_storage = mdaInfo['GUI_show_storage'], 
                            GUI_xy_pos_fullInfo = mdaInfo['xy_positions_saveInfo'],
                            GUI_acquire_button = True,
                            autoSaveLoad=True).getGui()
            except KeyError:
                #Add the full micro manager controls UI
                self.dockWidget = MDAGlados(core,MM_JSON,self.layout,shared_data,
                            hasGUI=True,
                            GUI_acquire_button = True,
                            autoSaveLoad=True).getGui()
        else: #If no MDA state is yet saved, open a new MDAGlados from scratch
            #Add the full micro manager controls UI
            self.dockWidget = MDAGlados(core,MM_JSON,self.layout,shared_data,
                        hasGUI=True,
                        GUI_acquire_button = True,
                        autoSaveLoad=True).getGui()
            
        self.sizeChanged.connect(self.dockWidget.handleSizeChange)

class dockWidget_flowChart(dockWidgets):
    def __init__(self): 
        logging.debug("dockWidget_flowchart started")
        super().__init__()
        
        #Add the full micro manager controls UI
        self.dockWidget = flowChart_dockWidgets(core,MM_JSON,self.layout,shared_data)

#--- below here not fully necessary---
# class dockWidget_mdaAnalysisScoringTest(dockWidgets):
#     def __init__(self): 
#         logging.debug("dockwidgetMDAANALYSISSCORINGTEST started")
#         super().__init__()
        
#         #Add the full micro manager controls UI
#         self.dockWidget = mdaAnalysisScoringTest_dockWidget(core,MM_JSON,self.layout,shared_data)

# class dockWidget_analysisThreads(dockWidgets):
#     def __init__(self): 
#         logging.debug("dockWidget_analysisThreads started")
#         super().__init__()
        
#         #Add the full micro manager controls UI
#         self.dockWidget = analysis_dockWidget(MM_JSON,self.layout,shared_data)

class dockWidget_fullGladosUI(dockWidgets):
    def __init__(self): 
        logging.debug("dockWidget_fullGladosUI started")
        super().__init__()
        # #new QWidget:
        tempWidget = QMainWindow()
        
        
        
    
    
        
        
        ui = Ui_CustomDockWidget()
        ui.setupUi(tempWidget)
        #Open JSON file with MM settings
        MM_JSON_path = os.path.join(sys.path[0], 'MM_PycroManager_JSON.json')
        # with open(os.path.join(sys.path[0], 'MM_PycroManager_JSON.json'), 'r') as f:
        with open(MM_JSON_path) as f:
            MM_JSON = json.load(f)
            
        form, self.criticalErrors = runlaserControllerUI(core,MM_JSON,ui,shared_data)
        #Run the laserController UI        
        #
        #Create a Vertical+horizontal layout:
        self.dockwidgetLayout = QGridLayout()
        #Create a layout for the configs:
        self.analysisLayout = QGridLayout()
        #Add this to the mainLayout:
        self.dockwidgetLayout.addLayout(self.analysisLayout,0,0)
        
        self.analysisLayout.addWidget(ui.centralwidget.children()[1].children()[0],1,1)
        
        self.dockWidget = self.layout.addLayout(self.dockwidgetLayout,0,0)
        

        

def startLiveModeVisualisation(shared_data,layerName='Live'):
    # create_analysis_thread(shared_data,analysisInfo='LiveModeVisualisation',createNewThread=False,throughputThread=shared_data._livemodeNapariHandler.image_queue_analysis)
    
    
    #Check for running liveVisualisation threads and remove those
    for thread in shared_data.analysisThreads:
        if thread.analysisInfo == 'LiveModeVisualisation':
            shared_data.analysisThreads.remove(thread)
            logging.debug('removed old LiveModeVisualisation thread')
    
    
    shared_data.newestLayerName = layerName
    create_analysis_thread(shared_data,analysisInfo='LiveModeVisualisation',createNewThread=False,throughputThread=shared_data._livemodeNapariHandler.image_queue_analysis)
    shared_data._livemodeNapariHandler.run_napariVisualisation_worker(shared_data._livemodeNapariHandler,layerName = layerName)

def startMDAVisualisation(shared_data,layerName='MDA',layerColorMap='gray'):
    #Check for running mdaVisualisation threads and remove those
    
    for thread in shared_data.analysisThreads:
        if thread.analysisInfo == 'mdaVisualisation':
            shared_data.analysisThreads.remove(thread)
            logging.debug('removed old mdaVisualisation thread')
    
    #Set the latest layer name to be the layer name
    shared_data.newestLayerName = layerName
    #Create an analysis thread which runs this MDA visualisation
    create_analysis_thread(shared_data,analysisInfo='mdaVisualisation',createNewThread=False,throughputThread=shared_data._mdamodeNapariHandler.image_queue_analysis)
    shared_data._mdamodeNapariHandler.run_napariVisualisation_worker(shared_data._mdamodeNapariHandler,layerName = layerName,layerColorMap=layerColorMap)
    
    # shared_data._mdamodeNapariHandler.stuurman_napari_implementation()


def layer_removed_event_callback(event, shared_data):
    #The name of the layer that is being removed:
    layerRemoved = shared_data.napariViewer.layers[event.index].name
    #Find this layer in the analysis threads
    for l in shared_data.analysisThreads:
        if l.getLayer() is not None:
            if l.getLayer().name == layerRemoved:
                #Destroy the analysis thread
                shared_data.analysisThreads.remove(l)
                
                if 'skipAnalysisThreadDeletion' in vars(shared_data):
                    if not shared_data.skipAnalysisThreadDeletion:
                        l.destroy()
                    else:
                        shared_data.skipAnalysisThreadDeletion = False
                else:
                    l.destroy()

def runNapariPycroManager(score,sMM_JSON,sshared_data,includecustomUI = False,include_flowChart_automatedMicroscopy = True):
    #Go from self to global variables
    global core, MM_JSON, livestate, napariViewer, shared_data
    core = score
    MM_JSON = sMM_JSON
    livestate = False
    shared_data = sshared_data
    
    #Get some info from core to put in shared_data
    shared_data._defaultFocusDevice = core.get_focus_device()
    logging.debug(f"Default focus device set to {shared_data._defaultFocusDevice}")

    #Run the UI on a second thread (hopefully robustly)
    #Napari start
    napariViewer = napari.Viewer()
    
    #Set QT attributes here for some reason...
    from PyQt5.QtWidgets import QApplication
    from PyQt5.QtCore import Qt
    QApplication.setAttribute(Qt.AA_EnableHighDpiScaling)
    QApplication.setAttribute(Qt.AA_ShareOpenGLContexts)# type:ignore
    QApplication.setAttribute(Qt.AA_UseStyleSheetPropagationInWidgetStyles, True)# type:ignore
    
    # napariViewer._window._qt_viewer.canvas.view._transform.scale=[2,2,2,2]
    #Add a connect event if a layer is removed - to stop background processes
    napariViewer.layers.events.removing.connect(lambda event: layer_removed_event_callback(event,shared_data))
    shared_data.napariViewer = napariViewer
    
    # create_analysis_thread(shared_data,analysisInfo='LiveModeVisualisation',createNewThread=False,throughputThread=shared_data._livemodeNapariHandler.image_queue_analysis)
    # create_analysis_thread(shared_data,analysisInfo='mdaVisualisation',createNewThread=False,throughputThread=shared_data._mdamodeNapariHandler.image_queue_analysis)
    logging.debug("Live mode pseudo-analysis thread created")
    
    #Set some common things for the UI (scale bar on and such)
    InitateNapariUI(napariViewer)
    
    #Add widgets as wanted
    # custom_widget_analysisThreads = dockWidget_analysisThreads()
    # napariViewer.window.add_dock_widget(custom_widget_analysisThreads, area="top", name="Real-time analysis",tabify=True)
    
    #Do something funky for stylesheet re-scaling of pyqt5
    from PyQt5.QtWidgets import QStyle
    defaultFontSize = 14#QWidget().font().pointSize()
    defaultPadding = 1#QWidget().style().pixelMetric(QStyle.PM_DefaultFrameWidth)
    defaultSpacingH = QWidget().style().pixelMetric(QStyle.PM_LayoutHorizontalSpacing)
    defaultSpacingV = QWidget().style().pixelMetric(QStyle.PM_LayoutVerticalSpacing)
    
    
    defaultLeftMargin = QWidget().style().pixelMetric(QStyle.PM_LayoutLeftMargin)
    defaultRightMargin = QWidget().style().pixelMetric(QStyle.PM_LayoutRightMargin)
    defaultTopMargin = QWidget().style().pixelMetric(QStyle.PM_LayoutTopMargin)
    defaultBottomMargin = QWidget().style().pixelMetric(QStyle.PM_LayoutBottomMargin)
    
    
    
    defaultSpacing=defaultSpacingH
    # Create a custom stylesheet with a scaling factor
    
    scaleFactor = 0.75
    shared_data.GUIscaleFactor = scaleFactor
    useStyleSheet = True
    ScaledStylesheetOld = f"""
    QWidget {{
        font-size: {int(defaultFontSize*scaleFactor)}px;
        padding: {int(defaultSpacingH*scaleFactor)}px {int(defaultSpacingV*scaleFactor)}px;
    }}
    
    QPushButton {{
        padding: {int(defaultPadding * scaleFactor)}px {int(defaultPadding * scaleFactor)}px;
        min-height: {int(20 * scaleFactor)}px; 
        min-width: {int(20 * scaleFactor)}px; 
    }}
    QLineEdit {{
        border-width: {int(0*scaleFactor)}px {int(0*scaleFactor)}px;
        padding: {int(defaultPadding*scaleFactor)}px {int(defaultPadding*scaleFactor)}px;
        margin: {int(0*scaleFactor)}px {int(0*scaleFactor)}px;min-height: {int(20 * scaleFactor)}px; 
    }}
    QCheckBox::indicator {{
        width: {int(12 * scaleFactor)}px; 
        height: {int(12 * scaleFactor)}px; 
    }}
    QAbstractButton::icon {{
        width: {int(16 * scaleFactor)}px; 
        height: {int(16 * scaleFactor)}px; 
    }}
    QComboBox {{
        padding: {int(defaultPadding*scaleFactor)}px {int(defaultSpacing*scaleFactor)}px;
        min-height: {int(20 * scaleFactor)}px;
        min-width: {int(20 * scaleFactor)}px; 
    }}
    QComboBox::down-arrow {{
        width: {int(12 * scaleFactor)}px; 
        height: {int(12 * scaleFactor)}px; 
    }}
    """

    # padding: {int(defaultSpacingH/2*scaleFactor)}px {int(defaultSpacingV/2*scaleFactor)}px;
    ScaledStylesheet = f"""
    QWidget {{
        font-size: {int(defaultFontSize*scaleFactor)}px;
        padding: {int(defaultSpacingH*scaleFactor)}px {int(defaultSpacingV*scaleFactor)}px;
        margin: {int(defaultTopMargin/4*scaleFactor)}px {int(defaultRightMargin/4*scaleFactor)}px {int(defaultBottomMargin/4*scaleFactor)}px {int(defaultLeftMargin/4*scaleFactor)}px;
    }}
    QLineEdit {{
        border-width: {int(4*scaleFactor)}px {int(4*scaleFactor)}px;
        min-height: {int(25 * scaleFactor)}px; 
        min-width: {int(25 * scaleFactor)}px; 
    }}
    QCheckBox::indicator {{
        width: {int(12 * scaleFactor)}px; 
        height: {int(12 * scaleFactor)}px; 
    }}
    QAbstractButton::icon {{
        width: {int(12 * scaleFactor)}px; 
        height: {int(12 * scaleFactor)}px; 
    }}
    QComboBox::down-arrow {{
        width: {int(12 * scaleFactor)}px; 
        height: {int(12 * scaleFactor)}px; 
    }}
    QComboBox{{
        min-height: {int(25 * scaleFactor)}px; 
        min-width: {int(25 * scaleFactor)}px; 
    }}
    QCheckBox{{
        min-height: {int(25 * scaleFactor)}px; 
        min-width: {int(25 * scaleFactor)}px; 
    }}
    QGroupBox {{
        margin: 0px;
        padding: 0px;
        spacing: 0px;
    }}
    QVBoxLayout {{
        spacing: 0px;
    }}
    """

    
    
    logging.debug('In runNapariPycroManager')
    
    custom_widget_MMcontrols = dockWidget_MMcontrol()
    # Apply the stylesheet
    if useStyleSheet:
        custom_widget_MMcontrols.setStyleSheet(ScaledStylesheet)
    #Add to napari
    napariViewer.window.add_dock_widget(custom_widget_MMcontrols, area="top", name="Controls",tabify=True)
    
    custom_widget_MDA = dockWidget_MDA()
    if useStyleSheet:
        custom_widget_MDA.setStyleSheet(ScaledStylesheet)
    napariViewer.window.add_dock_widget(custom_widget_MDA, area="top", name="Multi-D acquisition",tabify=True)
    
    if include_flowChart_automatedMicroscopy:
        custom_widget_flowChart = dockWidget_flowChart()
        if useStyleSheet:
            custom_widget_flowChart.setStyleSheet(ScaledStylesheet)
        napariViewer.window.add_dock_widget(custom_widget_flowChart, area="top", name="Autonomous microscopy",tabify=True)
        custom_widget_flowChart.dockWidget.focus()
    
    if includecustomUI:
        gladosLaserInfo = dockWidget_fullGladosUI()
        if not gladosLaserInfo.criticalErrors:
            napariViewer.window.add_dock_widget(gladosLaserInfo, area="right", name="GladosUI")
        else:
            logging.warning("GladosUI (specific for Endesfelder lab) not added due to critical errors")

    returnInfo = {}
    returnInfo['napariViewer'] = napariViewer
    returnInfo['MMcontrolWidget'] = custom_widget_MMcontrols.getDockWidget()
    
    # breakpoint
    return returnInfo