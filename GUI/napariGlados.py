import numpy as np
from PyQt5.QtCore import QThread, pyqtSignal
import asyncio
import napari
from napari.qt import thread_worker
import random
import threading
import time
import queue
from PyQt5.QtWidgets import QMainWindow
from pycromanager import core
from magicgui import magicgui
from qtpy.QtWidgets import QMainWindow, QPushButton, QVBoxLayout, QWidget
import sys
from custom_widget_ui import Ui_CustomDockWidget  # Import the generated UI module

from LaserControlScripts import *
from AutonomousMicroscopyScripts import *
from MMcontrols import *

# Define a flag to control the continuous task
stop_continuous_task = False
# empty queue for (live) image data
img_queue = queue.Queue()
# Create a queue to pass image data between threads
image_queue_analysis = queue.Queue()
# Create a signal to communicate between threads
analysis_done_signal = pyqtSignal(object)

#Sleep time to keep responsiveness
sleep_time = 0.1


"""
Live update definitions for napari
"""

def napariUpdateLive(liveImage):
    if liveImage is None:
        return
    global livestate
    if livestate == False:
        return
    # print('NapariUpdateLive Ran at time {}'.format(time.time()))
    liveImageLayer = getLayerIdFromName('liveImage')

    #If it's the first liveImageLayer
    if not liveImageLayer:
        nrLayersBefore = len(napariViewer.layers)
        print(nrLayersBefore)
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
        # Start the analysis thread if it's not already running
        if not analysis_thread.isRunning():
            analysis_thread.start()
            
        
def grab_image(image, metadata,event_queue):
    """ image_process_fnc to grab image from uManager, clip it to central part
        and call the fnc that will put it into the queue.
        Inputs: array image: image from micromanager
                metadata from micromanager
        """
    # size = np.shape(image)
    # image_clipped = image[(size[0]-clip[0])//2:(size[0]+clip[0])//2,
    #                   (size[1]-clip[1])//2:(size[1]+clip[1])//2]
    global livestate
    if img_queue.qsize() < 2:
        img_queue.put((image))
    if livestate == False:
        event_queue.put(None)
    return image, metadata

@thread_worker
def append_img(img_queue):
    """ Worker thread that adds images to a list.
        Calls either micro-manager data acquisition or functions for simulating data.
        Inputs: img_queue """
    # start microscope data acquisition
    global livestate
    while livestate:
        with Acquisition(directory=None, name=None, show_display=False, image_process_fn = grab_image) as acq: #type:ignore
            events = multi_d_acquisition_events(num_time_points=99, time_interval_s=0.0)
            acq.acquire(events) #type:ignore
        # time.sleep(sleep_time)
        print('Acq done, to following')

@thread_worker(connect={'yielded': napariUpdateLive})
def yield_img(img_queue):
    """ Worker thread that checks whether there are elements in the
        queue, reads them out.
        Connected to display_napari function to update display """
    global livestate

    while livestate:
        time.sleep(sleep_time)
        # get elements from queue while there is more than one element
        # playing it safe: I'm always leaving one element in the queue
        while img_queue.qsize() > 1:
            #print("reading from queue ", img_queue.qsize())
            yield img_queue.get(block = False)

    # read out last remaining elements after end of acquisition
    while img_queue.qsize() > 0:
        yield img_queue.get(block = False)
    print("acquisition done")


def liveModeChanged():
    global livestate, stop_continuous_task
    #Hook the live mode into the scripts here
    if shared_data.liveMode == False:
        livestate = False
        stop_continuous_task = True
        #Clear the image queue
        img_queue.queue.clear()
    else:
        livestate = True
        stop_continuous_task = False
        worker1 = append_img(img_queue)
        worker2 = yield_img(img_queue) #type:ignore
        worker1.start() #type:ignore

"""
Live overlay definitions - maybe switch to other file later
"""

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
    # Create a signal to communicate between threads
    analysis_done_signal = pyqtSignal(object)
    
    def run(self):
        while True:
            liveImage = image_queue_analysis.get()
            analysis_result = np.mean(np.mean(liveImage))
            self.analysis_done_signal.emit(analysis_result)

def Visualise_Analysis_results(analysis_result):
    # print(analysis_result)
    drawTextOverlay('Text_overlay',analysis_result)
    # drawRandomOverlay('live_overlay')
           
""" 
General napari functions
"""

def getLayerIdFromName(layer_name):
    ImageLayer = [i for i, layer in enumerate(napariViewer.layers) if hasattr(layer, '_name') and layer._name == layer_name]
    return ImageLayer

def InitateNapariUI(napariViewer):
    #Set title, icon
    napariViewer.title="GladOS - napari"
    # Set the window icon
    icon_path = './GUI/Icons/GladosIcon.ico'
    icon = QIcon(icon_path)
    napariViewer.window._qt_window.setWindowIcon(icon)
    
    #Turn on scalebar
    napariViewer.scale_bar.visible = True
    napariViewer.scale_bar.unit = "um"
    
""" 
Napari widgets
"""
class dockWidget_liveMode(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Combined Functions")
        self.central_widget = QWidget(self)
        self.setCentralWidget(self.central_widget)
        self.layout = QVBoxLayout(self.central_widget) #type:ignore
        self.button_one = QPushButton("Startstoplive", self)
        self.button_one.clicked.connect(lambda: self.run_function(1))
        self.layout.addWidget(self.button_one)
        
    def change_button_label(self, new_label):
        # Update the label of the button
        self.button_one.setText(new_label)
    
    def run_function(self,button_number):
        global livestate,shared_data
        if shared_data.liveMode == False:
            shared_data.liveMode = True
        else:
            shared_data.liveMode = False
   
class dockWidget_fullGladosUI(QMainWindow):
    def __init__(self): 
        super().__init__()
        self.ui = Ui_CustomDockWidget()
        self.ui.setupUi(self)
        #Open JSON file with MM settings
        with open(os.path.join(sys.path[0], 'MM_PycroManager_JSON.json'), 'r') as f:
            MM_JSON = json.load(f)
        #Run the laserController UI
        runlaserControllerUI(core,MM_JSON,self.ui,shared_data)
        # runAutonomousMicroscopyUI(core,MM_JSON,self.ui)
        
class dockWidget_MMcontrol(QMainWindow):
    def __init__(self): 
        super().__init__()
        #Add a central widget in napari
        self.central_widget = QWidget(self)
        self.setCentralWidget(self.central_widget)
        #add a layout in this central widget
        self.layout = QVBoxLayout(self.central_widget) #type:ignore
        
        #Add the full micro manager controls UI
        self.dockWidget = microManagerControlsUI(core,MM_JSON,self.layout)
    
    def getDockWidget(self):
        return self.dockWidget
    
# Start a separate analysis thread
analysis_thread = AnalysisThread()
analysis_thread.analysis_done_signal.connect(Visualise_Analysis_results)


def runNapariMicroManager(score,sMM_JSON,sshared_data):
    #Go from self to global variables
    global core, MM_JSON, livestate, napariViewer, shared_data
    core = score
    MM_JSON = sMM_JSON
    livestate = False
    shared_data = sshared_data

    #Napari start
    napariViewer = napari.Viewer()
    
    #Set some common things for the UI (scale bar on and such)
    InitateNapariUI(napariViewer)
    
    #Add widgets as wanted
    custom_widget_MMcontrols = dockWidget_MMcontrol()
    napariViewer.window.add_dock_widget(custom_widget_MMcontrols, area="top", name="MMcontrols")
    custom_widget_liveMode = dockWidget_liveMode()
    napariViewer.window.add_dock_widget(custom_widget_liveMode, area="right", name="Live Mode")
    custom_widget_gladosUI = dockWidget_fullGladosUI()
    napariViewer.window.add_dock_widget(custom_widget_gladosUI, area="right", name="GladosUI")

    # breakpoint
    return napariViewer, custom_widget_MMcontrols.getDockWidget()

    