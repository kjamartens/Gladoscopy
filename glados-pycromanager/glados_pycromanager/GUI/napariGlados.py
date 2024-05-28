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
from custom_widget_ui import Ui_CustomDockWidget  # Import the generated UI module
import logging
import os

from LaserControlScripts import *
from AutonomousMicroscopyScripts import *
from MMcontrols import microManagerControlsUI
from MDAGlados import MDAGlados
from AnalysisClass import *
from Analysis_dockWidgets import *
from mdaAnalysisScoringVisualisation import *
from FlowChart_dockWidgets import *
from napariHelperFunctions import getLayerIdFromName, InitateNapariUI
from utils import cleanUpTemporaryFiles


# # Define a flag to control the continuous task
# stop_continuous_task = False
# # empty queue for (live) image data
# img_queue = queue.Queue()
# # Create a queue to pass image data between threads
# image_queue_analysis = queue.Queue()
# # Create a signal to communicate between threads
# analysis_done_signal = pyqtSignal(object)

# #Sleep time to keep responsiveness
# sleep_time = 0.05


#This needs to be a function outside of any class due to Yield-calling
def napariUpdateLive(DataStructure):
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

    #If it's the first layer
    if not liveImageLayer:
        if layerName == 'MDA':
            #Testing a few things
            shape = [len(shared_data._mdaModeParams)]
            shared_data.mdaZarrData = zarr.open(
                    str(tempfile.TemporaryDirectory().name),
                    shape = shape+[liveImage.shape[0],liveImage.shape[1]],
                    chunks = tuple([1] * len(shape) + [liveImage.shape[0],liveImage.shape[1]]),
                    )
            # dataArray = np.zeros((liveImage.shape[0],liveImage.shape[1],len(shared_data._mdaModeParams)))
            shared_data.mdaZarrData[0,:,:] = liveImage
            
            layer = napariViewer.add_image(shared_data.mdaZarrData, rendering='attenuated_mip', colormap=DataStructure['layer_color_map'],name = layerName)
            #Set correct scale - in nm
            layer.scale = [core.get_pixel_size_um(),core.get_pixel_size_um()] #type:ignore
            layer._keep_auto_contrast = True #type:ignore
            #Move to the front of the layers
            napariViewer.layers.move_multiple([liveImageLayer[0]],len(napariViewer.layers))
            napariViewer.reset_view()
            
            #Also put in the first image
            #set to correct slice
            napariViewer.dims.set_point(0,0)
        else:
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
        if layerName == 'MDA':
            shared_data.mdaZarrData[metadata['Axes']['time'],:,:] = liveImage
            #set to correct slice
            napariViewer.dims.set_point(0,metadata['Axes']['time'])
        else:
            # layer is present, replace its data
            layer = napariViewer.layers[liveImageLayer[0]]
            #Also move to top
            napariViewer.layers.move_multiple([liveImageLayer[0]],len(napariViewer.layers))
            layer.data = liveImage
    
    
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
    if image_queue_analysisA.empty():
        image_queue_analysisA.put_nowait([liveImage,metadata])
        #Start all analysisthreads
        for analysisThread in analysisThreads:
            if not analysisThread.isRunning():
                print(f'starting analysis thread: {analysisThread}')
                analysisThread.start()


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
        self.img_queue = queue.Queue()
        # Create a queue to pass image data between threads
        self.image_queue_analysis = queue.Queue()
        # Create a signal to communicate between threads
        self.mda_acq_done_signal = pyqtSignal(bool)

        #Sleep time to keep responsiveness
        self.sleep_time = 0.1
        self.layerName = 'newLayer'

    def mdaacqdonefunction(self):
        self.shared_data.mdaacqdonefunction()
        
    def grab_image(self,image, metadata, event_queue):
        """ 
        Function that runs on every frame obtained in live mode and putis in the image queue
        
        Inputs: array image: image from micromanager
                metadata: metadata from micromanager
        """
        # print(event_queue.get())
        if self.acqstate:
            if self.img_queue.qsize() < 20:
                self.img_queue.put_nowait([image,metadata])
                
            #Loop over all queues in shared_data.liveImageQueues and also append the image there:
            for queue in self.shared_data.liveImageQueues:
                if queue.qsize() < 20:
                    queue.put_nowait([image,metadata])
                        
            if self.image_queue_analysis.qsize() < 3:
                self.image_queue_analysis.put_nowait([image,metadata])
            
        else:
            logging.info('Broke off live mode')
            event_queue.put_nowait(None)
            try:
                acq.abort()
                logging.info('aborted acquisition')
            except:
                logging.info('attemped to abort acq')
        
        return image, metadata

    @thread_worker
    def run_pycroManagerAcquisition_worker(self,parent):
        """ 
        Worker which handles live mode on/off turning etc
        
        Inputs: img_queue (unused, but required)
        """
        img_queue = parent.img_queue
        global acq
        #The idea of live mode is that we do a very very long acquisition (10k frames), and real-time show the images, and then abort the acquisition when we stop life.
        #The abortion is handled in grab_image_livemode
        if self.liveOrMda == 'live':
            while self.acqstate:
                if self.shared_data.mdaMode:
                    print('LIVE NOT STARTED! MDA IS RUNNING')
                    self.shared_data.liveMode = False
                else:        
                    #JavaBackendAcquisition is an acquisition on a different thread to not block napari I believe
                    logging.debug('starting acq')
                    with JavaBackendAcquisition(directory='./temp', name='LiveAcqShouldBeRemoved', show_display=False, image_process_fn = self.grab_image) as acq: #type:ignore
                        events = multi_d_acquisition_events(num_time_points=9999, time_interval_s=0)
                        acq.acquire(events)

            #Now we're after the livestate
            self.shared_data.core.stop_sequence_acquisition()
            self.shared_data.liveMode = False
            #We clean up, removing all LiveAcqShouldBeRemoved folders in /Temp:
            cleanUpTemporaryFiles()
        elif self.liveOrMda == 'mda':
            while self.acqstate:
                if self.shared_data.liveMode:
                    self.shared_data.liveMode = False
                    time.sleep(1)
                    
                #JavaBackendAcquisition is an acquisition on a different thread to not block napari I believe
                logging.debug('starting MDA acq')
                savefolder = './temp'
                savename = 'MdaAcqShouldBeRemoved'
                if shared_data._mdaModeSaveLoc[0] != '':
                    savefolder = shared_data._mdaModeSaveLoc[0]
                if shared_data._mdaModeSaveLoc[1] != '':
                    savename = shared_data._mdaModeSaveLoc[1]
                if shared_data._mdaModeNapariViewer != None:
                    napariViewer = shared_data._mdaModeNapariViewer
                    showdisplay = True
                else:
                    napariViewer = None
                    showdisplay = False
                with JavaBackendAcquisition(directory=savefolder, name=savename, show_display=False, image_process_fn = self.grab_image,napari_viewer=None) as acq: #type:ignore
                    events = shared_data._mdaModeParams
                    acq.acquire(events)
                
                self.acqstate = False #End the MDA acq state
                self.shared_data.appendNewMDAdataset(acq.get_dataset())

            #Now we're after the acquisition
            self.shared_data.core.stop_sequence_acquisition()
            self.shared_data.mdaMode = False
            
            #Signal to all parents that the MDA acquisition is done - in the Nodz MDA, now we would trigger the MDA-based analysis for scoring or so
            parent.mdaacqdonefunction()
            
            #We clean up, removing all LiveAcqShouldBeRemoved folders in /Temp:
            cleanUpTemporaryFiles()
    
    
    @thread_worker(connect={'yielded': napariUpdateAnalysisThreads})
    def run_analysis_worker(self,parent,layerName='Layer',layerColorMap='gray'):
        """
        Worker which handles the visualisation of the live mode queue
        Connected to display_napari function to update display 
        """
        img_queue = parent.image_queue_analysis
        while self.acqstate:
            time.sleep(0)
            # get elements from queue while there is more than one element
            while img_queue.qsize() > 0:
                DataStructure = {}
                DataStructure['data'] = img_queue.get_nowait()
                DataStructure['napariViewer'] = self.shared_data.napariViewer
                DataStructure['acqState'] = self.acqstate
                DataStructure['core'] = self.shared_data.core
                DataStructure['image_queue_analysis'] = self.image_queue_analysis
                DataStructure['analysisThreads'] = self.shared_data.analysisThreads
                DataStructure['layer_name'] = layerName
                DataStructure['layer_color_map'] = layerColorMap
                yield DataStructure

    
    @thread_worker(connect={'yielded': napariUpdateLive})
    def run_napariVisualisation_worker(self,parent,layerName='Layer',layerColorMap='gray'):
        """
        Worker which handles the visualisation of the live mode queue
        Connected to display_napari function to update display 
        """
        img_queue = parent.img_queue
        while self.acqstate:
            time.sleep(self.sleep_time)
            logging.debug('in while-loop in visualise_live_mode_worker, len of img_queue: '+str(img_queue.qsize()))
            # get elements from queue while there is more than one element
            # playing it safe: I'm always leaving one element in the queue
            while img_queue.qsize() > 0:
                DataStructure = {}
                DataStructure['data'] = img_queue.get_nowait()
                DataStructure['napariViewer'] = self.shared_data.napariViewer
                DataStructure['acqState'] = self.acqstate
                DataStructure['core'] = self.shared_data.core
                DataStructure['image_queue_analysis'] = self.image_queue_analysis
                DataStructure['analysisThreads'] = self.shared_data.analysisThreads
                DataStructure['layer_name'] = layerName
                DataStructure['layer_color_map'] = layerColorMap
                yield DataStructure
                # self.napariUpdateLive(img_queue.get(block=False))

        # read out last remaining element(s) after end of acquisition
        while img_queue.qsize() > 0:
            DataStructure = {}
            DataStructure['data'] = img_queue.get_nowait()
            DataStructure['napariViewer'] = self.shared_data.napariViewer
            DataStructure['acqState'] = self.acqstate
            DataStructure['core'] = self.shared_data.core
            DataStructure['image_queue_analysis'] = self.image_queue_analysis
            DataStructure['analysisThreads'] = self.shared_data.analysisThreads
            DataStructure['layer_name'] = layerName
            DataStructure['layer_color_map'] = layerColorMap
            yield DataStructure#img_queue.get(block = False)
            # self.napariUpdateLive(img_queue.get(block=False))
        logging.debug("acquisition done")

    def acqModeChanged(self, newSharedData = None):
        """
        General function which is called if live mode is changed or not. Generally called from sharedFunction - when self._liveMode is altered
        
        Is called, and shared_data.liveMode should be changed seperately from running this funciton
        """
        if newSharedData is not None:
            self.shared_data = newSharedData
        if self.liveOrMda == 'live':
            #Hook the live mode into the scripts here
            if self.shared_data.liveMode == False:
                self.acqstate = False
                self.stop_continuous_task = True
                #Clear the image queue
                self.img_queue.queue.clear()
                logging.info("Live mode stopped")
            else:
                logging.debug('liveMode changed to TRUE')
                self.acqstate = True
                self.stop_continuous_task = False
                #Always start live-mode visualisation:
                napariGlados.startLiveModeVisualisation(self.shared_data)
                
                #Start the worker to run the pycromanager acquisition
                worker1 = self.run_pycroManagerAcquisition_worker(self) #type:ignore
                worker1.start() #type:ignore
                worker2 = self.run_analysis_worker(self) #type:ignore
                
                logging.info("Live mode started")
                
        elif self.liveOrMda == 'mda':
            #Hook the live mode into the scripts here
            if self.shared_data.mdaMode == False:
                self.acqstate = False
                self.stop_continuous_task = True
                #Clear the image queue
                self.img_queue.queue.clear()
                logging.debug("MDA mode stopped from acqModeChanged")
            else:
                logging.debug('mdaMode changed to TRUE')
                
                #Create the layer:
                #Testing a few things
                layerName = 'MDA'
                liveImageLayer = getLayerIdFromName(layerName,napariViewer)
                shape = [len(shared_data._mdaModeParams)]
                shared_data.mdaZarrData = zarr.open(
                        str(tempfile.TemporaryDirectory().name),
                        shape = shape+[shared_data.core.get_roi().width,shared_data.core.get_roi().height],
                        chunks = tuple([1] * len(shape) + [shared_data.core.get_roi().width,shared_data.core.get_roi().height]),
                        )
                layer = napariViewer.add_image(shared_data.mdaZarrData, rendering='attenuated_mip',name = layerName)
                #Set correct scale - in nm
                layer.scale = [core.get_pixel_size_um(),core.get_pixel_size_um()] #type:ignore
                layer._keep_auto_contrast = True #type:ignore
                #Move to the front of the layers
                napariViewer.reset_view()
                
                
                
                self.acqstate = True
                self.stop_continuous_task = False
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
        
        if os.path.exists('glados_state.json'):
            #Load the mda state
            with open('glados_state.json', 'r') as file:
                gladosInfo = json.load(file)
                mdaInfo = gladosInfo['MDA']
            
            #Add the full micro manager controls UI
            self.dockWidget = MDAGlados(core,MM_JSON,self.layout,shared_data,
                        hasGUI=True,
                        num_time_points = mdaInfo['num_time_points'], 
                        time_interval_s = mdaInfo['time_interval_s'], 
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
class dockWidget_mdaAnalysisScoringTest(dockWidgets):
    def __init__(self): 
        logging.debug("dockwidgetMDAANALYSISSCORINGTEST started")
        super().__init__()
        
        #Add the full micro manager controls UI
        self.dockWidget = mdaAnalysisScoringTest_dockWidget(core,MM_JSON,self.layout,shared_data)

# class dockWidget_analysisThreads(dockWidgets):
#     def __init__(self): 
#         logging.debug("dockWidget_analysisThreads started")
#         super().__init__()
#         print("Hello!")
#         #Add the full micro manager controls UI
#         self.dockWidget = analysis_dockWidget(MM_JSON,self.layout,shared_data)

class dockWidget_fullGladosUI(QMainWindow):
    def __init__(self): 
        logging.info("dockWidget_fullGladosUI started")
        super().__init__()
        self.ui = Ui_CustomDockWidget()
        self.ui.setupUi(self)
        #Open JSON file with MM settings
        with open(os.path.join(sys.path[0], 'MM_PycroManager_JSON.json'), 'r') as f:
            MM_JSON = json.load(f)
        #Run the laserController UI
        runlaserControllerUI(core,MM_JSON,self.ui,shared_data)
        # runAutonomousMicroscopyUI(core,MM_JSON,self.ui)

def startLiveModeVisualisation(shared_data,layerName='Live'):
    create_analysis_thread(shared_data,analysisInfo='LiveModeVisualisation',createNewThread=False,throughputThread=shared_data._livemodeNapariHandler.image_queue_analysis)
    
    shared_data._livemodeNapariHandler.run_napariVisualisation_worker(shared_data._livemodeNapariHandler,layerName = layerName)

def startMDAVisualisation(shared_data,layerName='MDA',layerColorMap='gray'):
    create_analysis_thread(shared_data,analysisInfo='mdaVisualisation',createNewThread=False,throughputThread=shared_data._mdamodeNapariHandler.image_queue_analysis)
    
    
    shared_data._mdamodeNapariHandler.run_napariVisualisation_worker(shared_data._mdamodeNapariHandler,layerName = layerName,layerColorMap=layerColorMap)

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
    logging.info(f"Default focus device set to {shared_data._defaultFocusDevice}")

    #Napari start
    napariViewer = napari.Viewer()
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
    
    custom_widget_MMcontrols = dockWidget_MMcontrol()
    napariViewer.window.add_dock_widget(custom_widget_MMcontrols, area="top", name="Controls",tabify=True)
    
    custom_widget_MDA = dockWidget_MDA()
    napariViewer.window.add_dock_widget(custom_widget_MDA, area="top", name="Multi-D acquisition",tabify=True)
    
    if include_flowChart_automatedMicroscopy:
        custom_widget_flowChart = dockWidget_flowChart()
        napariViewer.window.add_dock_widget(custom_widget_flowChart, area="top", name="Autonomous microscopy",tabify=True)
        custom_widget_flowChart.dockWidget.focus()
    
    if includecustomUI:
        custom_widget_gladosUI = dockWidget_fullGladosUI()
        napariViewer.window.add_dock_widget(custom_widget_gladosUI, area="right", name="GladosUI")

    returnInfo = {}
    returnInfo['napariViewer'] = napariViewer
    returnInfo['MMcontrolWidget'] = custom_widget_MMcontrols.getDockWidget()
    
    # breakpoint
    return returnInfo


