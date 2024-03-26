import numpy as np
from PyQt5.QtCore import pyqtSignal
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
from MMcontrols import microManagerControlsUI, MDAGlados
from AnalysisClass import *
from Analysis_dockWidgets import *
from FlowChart_dockWidgets import *
from napariHelperFunctions import getLayerIdFromName, InitateNapariUI
from utils import cleanUpTemporaryFiles

# Define a flag to control the continuous task
stop_continuous_task = False
# empty queue for (live) image data
img_queue = queue.Queue()
# Create a queue to pass image data between threads
image_queue_analysis = queue.Queue()
# Create a signal to communicate between threads
analysis_done_signal = pyqtSignal(object)

#Sleep time to keep responsiveness
sleep_time = 0.05


"""
Live update definitions for napari
"""

def napariUpdateLive(liveImage):
    """ 
    Function that finally shows the live image in napari
    
    Inputs: liveImage: current live image (array)
    """
    if liveImage is None:
        return
    global livestate
    if livestate == False:
        return
    logging.debug('NapariUpdateLive Ran at time {}'.format(time.time()))
    liveImageLayer = getLayerIdFromName('liveImage',napariViewer)

    #If it's the first liveImageLayer
    if not liveImageLayer:
        nrLayersBefore = len(napariViewer.layers)
        layer = napariViewer.add_image(liveImage, rendering='attenuated_mip')
        #Set correct scale - in nm
        layer.scale = [core.get_pixel_size_um(),core.get_pixel_size_um()] #type:ignore
        layer._keep_auto_contrast = True #type:ignore
        napariViewer.layers.move_multiple([nrLayersBefore,0])
        napariViewer.reset_view()
    #Else if the layer already exists, replace it!
    else:
        # layer is present, replace its data
        layer = napariViewer.layers[liveImageLayer[0]]
        layer.data = liveImage
    
    # Do analysis on this live image
    # Check if the queue is empty
    if image_queue_analysis.empty():
        image_queue_analysis.put(liveImage)
        #Start all analysisthreads
        for analysisThread in shared_data.analysisThreads:
            if not analysisThread.isRunning():
                analysisThread.start()
        # # Start the analysis thread if it's not already running
        # if not analysis_thread.isRunning():
        #     analysis_thread.start()
        # # Start the analysis thread if it's not already running
        # if not analysis_thread2.isRunning():
        #     analysis_thread2.start()  

def grab_image_livemode(image, metadata, event_queue):
    """ 
    Function that runs on every frame obtained in live mode and putis in the image queue
    
    Inputs: array image: image from micromanager
            metadata: metadata from micromanager
    """
    # print(event_queue.get())
    global livestate
    if livestate:
        logging.info('grab_image within livemode')
        if img_queue.qsize() < 3:
            img_queue.put((image))
            #Loop over all queues in shared_data.liveImageQueues and also append the image there:
            for queue in shared_data.liveImageQueues:
                if queue.qsize() < 2:
                    queue.put((image))
        
    else:
        logging.info('Broke off live mode')
        event_queue.put(None)
        try:
            acq.abort()
            logging.info('aborted acquisition')
        except:
            logging.info('attemped to abort acq')
    
    return image, metadata

@thread_worker
def run_live_mode_worker(img_queue):
    """ 
    Worker which handles live mode on/off turning etc
    
    Inputs: img_queue (unused, but required)
    """
    #The idea of live mode is that we do a very very long acquisition (10k frames), and real-time show the images, and then abort the acquisition when we stop life.
    #The abortion is handled in grab_image_livemode
    global livestate
    global acq
    while livestate:
        #JavaBackendAcquisition is an acquisition on a different thread to not block napari I believe
        with JavaBackendAcquisition(directory='./temp', name='LiveAcqShouldBeRemoved', show_display=False, image_process_fn = grab_image_livemode) as acq: #type:ignore
            events = multi_d_acquisition_events(num_time_points=9999, time_interval_s=0)
            acq.acquire(events)

    #Now we're after the livestate
    #We clean up, removing all LiveAcqShouldBeRemoved folders in /Temp:
    cleanUpTemporaryFiles()
    import shutil
    for folder in os.listdir('./temp'):
        if 'LiveAcqShouldBeRemoved' in folder:
            try:
                shutil.rmtree(os.path.join('./temp', folder))
            except:
                pass

@thread_worker(connect={'yielded': napariUpdateLive})
def visualise_live_mode_worker(img_queue):
    """
    Worker which handles the visualisation of the live mode queue
    Connected to display_napari function to update display 
    """
    global livestate

    while livestate:
        time.sleep(sleep_time)
        # get elements from queue while there is more than one element
        # playing it safe: I'm always leaving one element in the queue
        while img_queue.qsize() > 1:
            yield img_queue.get(block = False)

    # read out last remaining elements after end of acquisition
    while img_queue.qsize() > 0:
        yield img_queue.get(block = False)
    logging.debug("acquisition done")


def liveModeChanged():
    """
    General function which is called if live mode is changed or not. Generally called from sharedFunction - when self._liveMode is altered
    
    Is called, and shared_data.liveMode should be changed seperately from running this funciton
    """
    global livestate, stop_continuous_task
    #Hook the live mode into the scripts here
    if shared_data.liveMode == False:
        livestate = False
        stop_continuous_task = True
        #Clear the image queue
        img_queue.queue.clear()
        logging.info("Live mode stopped")
    else:
        livestate = True
        stop_continuous_task = False
        #Start the two workers, one to run it, one to visualise it.
        worker1 = run_live_mode_worker(img_queue)
        worker2 = visualise_live_mode_worker(img_queue) #type:ignore
        worker1.start() #type:ignore
        logging.info("Live mode started")












def napariUpdateMda(mdaImage):
    """ 
    Function that finally shows the live image in napari
    
    Inputs: liveImage: current live image (array)
    """
    if mdaImage is None:
        return
    global mdastate
    if mdastate == False:
        return
    logging.debug('NapariUpdatemda Ran at time {}'.format(time.time()))
    mdaImageLayer = getLayerIdFromName('mdaImage',napariViewer)

    #If it's the first liveImageLayer
    if not mdaImageLayer:
        nrLayersBefore = len(napariViewer.layers)
        layer = napariViewer.add_image(mdaImage, rendering='attenuated_mip')
        #Set correct scale - in nm
        layer.scale = [core.get_pixel_size_um(),core.get_pixel_size_um()] #type:ignore
        layer._keep_auto_contrast = True #type:ignore
        napariViewer.layers.move_multiple([nrLayersBefore,0])
        napariViewer.reset_view()
    #Else if the layer already exists, replace it!
    else:
        # layer is present, replace its data
        layer = napariViewer.layers[mdaImageLayer[0]]
        layer.data = mdaImage
    
    # Do analysis on this live image
    # Check if the queue is empty
    if image_queue_analysis.empty():
        image_queue_analysis.put(mdaImage)
        #Start all analysisthreads
        for analysisThread in shared_data.analysisThreads:
            if not analysisThread.isRunning():
                analysisThread.start()
        # # Start the analysis thread if it's not already running
        # if not analysis_thread.isRunning():
        #     analysis_thread.start()
        # # Start the analysis thread if it's not already running
        # if not analysis_thread2.isRunning():
        #     analysis_thread2.start()  

def grab_image_mdamode(image, metadata, event_queue):
    """ 
    Function that runs on every frame obtained in live mode and putis in the image queue
    
    Inputs: array image: image from micromanager
            metadata: metadata from micromanager
    """
    # print(event_queue.get())
    global mdastate
    if mdastate:
        logging.info('grab_image within mdamode')
        if img_queue.qsize() < 3:
            img_queue.put((image))
            #Loop over all queues in shared_data.liveImageQueues and also append the image there:
            for queue in shared_data.mdaImageQueues:
                if queue.qsize() < 2:
                    queue.put((image))
        
    else:
        logging.info('Broke off mda mode')
        event_queue.put(None)
        try:
            acq.abort()
            logging.info('aborted acquisition')
        except:
            logging.info('attemped to abort acq')
    
    return image, metadata


@thread_worker
def run_mda_mode_worker(img_queue):
    """ 
    Worker which handles mda mode on/off turning etc
    
    Inputs: img_queue (unused, but required)
    """
    print('MDA mode worker run started')
    #The idea of live mode is that we do a very very long acquisition (10k frames), and real-time show the images, and then abort the acquisition when we stop life.
    #The abortion is handled in grab_image_livemode
    global mdastate
    global acq
    while mdastate:
        print("attempting to acquire")
        print(f"found mdaparams: {shared_data._mdaModeParams}")
        #JavaBackendAcquisition is an acquisition on a different thread to not block napari I believe
        savefolder = './temp'
        savename = 'MdaAcq'
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
        with JavaBackendAcquisition(directory=savefolder, name=savename, show_display=showdisplay, image_process_fn = grab_image_mdamode,napari_viewer=napariViewer) as acq: #type:ignore
            events = shared_data._mdaModeParams
            acq.acquire(events)
        mdastate = False

    #Now we're after the livestate
    #We clean up, removing all LiveAcqShouldBeRemoved folders in /Temp:
    cleanUpTemporaryFiles()

@thread_worker(connect={'yielded': napariUpdateMda})
def visualise_mda_mode_worker(img_queue):
    """
    Worker which handles the visualisation of the live mode queue
    Connected to display_napari function to update display 
    """
    global mdastate
    print('MDA mode worker visualisation started')

    while mdastate:
        time.sleep(sleep_time)
        # get elements from queue while there is more than one element
        # playing it safe: I'm always leaving one element in the queue
        while img_queue.qsize() > 1:
            yield img_queue.get(block = False)

    # read out last remaining elements after end of acquisition
    while img_queue.qsize() > 0:
        yield img_queue.get(block = False)
    logging.debug("acquisition done")


def mdaModeChanged():
    """
    General function which is called if mda mode is changed or not. Generally called from sharedFunction - when self._mdaMode is altered
    
    Is called, and shared_data.mdaMode should be changed seperately from running this funciton
    """
    print('mdamodechanged called')
    global mdastate, stop_continuous_task
    #Hook the live mode into the scripts here
    if shared_data.mdaMode == False:
        mdastate = False
        stop_continuous_task = True
        #Clear the image queue
        img_queue.queue.clear()
        logging.info("MDA mode stopped")
    else:
        mdastate = True
        stop_continuous_task = False
        #Start the two workers, one to run it, one to visualise it.
        worker1 = run_mda_mode_worker(img_queue)
        worker2 = visualise_mda_mode_worker(img_queue) #type:ignore
        worker1.start() #type:ignore
        logging.info("MDA display mode started")


""" 
Napari widgets
"""

class dockWidgets(QMainWindow):
    def __init__(self):
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
        
class dockWidget_MMcontrol(dockWidgets):
    def __init__(self): 
        logging.debug("dockWidget_MMcontrol started")
        super().__init__()
        #Add the full micro manager controls UI
        self.dockWidget = microManagerControlsUI(core,MM_JSON,self.layout,shared_data)
    
class dockWidget_analysisThreads(dockWidgets):
    def __init__(self): 
        logging.debug("dockWidget_analysisThreads started")
        super().__init__()
        
        #Add the full micro manager controls UI
        self.dockWidget = analysis_dockWidget(MM_JSON,self.layout,shared_data)

class dockWidget_flowChart(dockWidgets):
    def __init__(self): 
        logging.debug("dockWidget_flowchart started")
        super().__init__()
        
        #Add the full micro manager controls UI
        self.dockWidget = flowChart_dockWidgets(core,MM_JSON,self.layout,shared_data)

class dockWidget_MDA(dockWidgets):
    def __init__(self): 
        logging.debug("dockWidget_MDA started")
        super().__init__()
        
        #Add the full micro manager controls UI
        self.dockWidget = MDAGlados(core,MM_JSON,self.layout,shared_data,hasGUI=True).getGui()

def layer_removed_event_callback(event, shared_data):
    #The name of the layer that is being removed:
    layerRemoved = shared_data.napariViewer.layers[event.index].name
    #Find this layer in the analysis threads
    for l in shared_data.analysisThreads:
        if l.getLayer() is not None:
            if l.getLayer().name == layerRemoved:
                #Destroy the analysis thread
                l.destroy()
                shared_data.analysisThreads.remove(l)

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
    
    create_analysis_thread(shared_data,analysisInfo='LiveModeVisualisation',createNewThread=False,throughputThread=image_queue_analysis)
    create_analysis_thread(shared_data,analysisInfo='mdaVisualisation',createNewThread=False,throughputThread=image_queue_analysis)
    logging.debug("Live mode pseudo-analysis thread created")
    
    #Set some common things for the UI (scale bar on and such)
    InitateNapariUI(napariViewer)
    
    # Start separate analysis threads
    # create_analysis_thread(image_queue_analysis,shared_data,analysisInfo='AvgGrayValueText')
    
    #Add widgets as wanted
    custom_widget_analysisThreads = dockWidget_analysisThreads()
    napariViewer.window.add_dock_widget(custom_widget_analysisThreads, area="top", name="analysisThreads",tabify=True)
    
    custom_widget_MMcontrols = dockWidget_MMcontrol()
    napariViewer.window.add_dock_widget(custom_widget_MMcontrols, area="top", name="MMcontrols",tabify=True)
    
    custom_widget_MDA = dockWidget_MDA()
    napariViewer.window.add_dock_widget(custom_widget_MDA, area="top", name="MDA",tabify=True)
    
    if include_flowChart_automatedMicroscopy:
        custom_widget_flowChart = dockWidget_flowChart()
        napariViewer.window.add_dock_widget(custom_widget_flowChart, area="top", name="flowChart",tabify=True)
        custom_widget_flowChart.dockWidget.focus()
    
    if includecustomUI:
        custom_widget_gladosUI = dockWidget_fullGladosUI()
        napariViewer.window.add_dock_widget(custom_widget_gladosUI, area="right", name="GladosUI")

    returnInfo = {}
    returnInfo['napariViewer'] = napariViewer
    returnInfo['MMcontrolWidget'] = custom_widget_MMcontrols.getDockWidget()
    
    # breakpoint
    return returnInfo
