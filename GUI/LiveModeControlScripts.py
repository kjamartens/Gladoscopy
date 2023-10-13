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
from pycromanager import *
# Define a flag to control the continuous task
stop_continuous_task = False
total_th1 = 0;
lock = threading.Lock()

# Create a queue to pass image data between threads
image_queue_analysis = queue.Queue()
# Create a signal to communicate between threads
analysis_done_signal = pyqtSignal(object)

image_queue_liveObtain = queue.Queue()
liveObtain_done_signal = pyqtSignal(object)

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
    shapes_layer.add(
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

            
def getLayerIdFromName(layer_name):
    ImageLayer = [i for i, layer in enumerate(napariViewer.layers) if hasattr(layer, '_name') and layer._name == layer_name]
    return ImageLayer

def InitateNapariUI(napariViewer):
    #Turn on scalebar
    napariViewer.scale_bar.visible = True
    napariViewer.scale_bar.unit = "um"

def napariUpdateLive(liveImage):
    if liveImage is None:
        return
    print('NapariUpdateLive Ran')
    liveImageLayer = getLayerIdFromName('liveImage')

    #If it's the first liveImageLayer
    if not liveImageLayer:
        nrLayersBefore = len(napariViewer.layers)
        print(nrLayersBefore)
        layer = napariViewer.add_image(liveImage, rendering='attenuated_mip')
        #Set correct scale - in nm
        layer.scale = [core.get_pixel_size_um(),core.get_pixel_size_um()]
        layer._keep_auto_contrast = True
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

class liveObtainThread(QThread):
    liveObtain_done_signal = pyqtSignal(object)
    
    def run(self):
        while True:
            tagged_image = image_queue_liveObtain.get()
            if isinstance(tagged_image, str):
                print('STR')
            else:
                # get the pixels in numpy array and reshape it according to its height and width
                image_array = np.reshape(
                    tagged_image.pix,
                    newshape=[-1, tagged_image.tags["Height"], tagged_image.tags["Width"]],
                )

                #When image is arrived from MM, we yield it to napariUpdateLive
                self.liveObtain_done_signal.emit(image_array[0,:,:])
                # yield image_array[0,:,:]
        

def updateNapariLiveView(liveImage):
    napariUpdateLive(liveImage)
    
def dummyPrintSomething(im):
    print('dummyPrintSomething')
    
@thread_worker(connect={'yielded': dummyPrintSomething})
# @thread_worker()
def buttonPressliveStateToggle():
    print('buttonPressliveStateToggle run')
    global livestate, stop_continuous_task
    if livestate:
        livestate = False
        stop_continuous_task = True
    else:
        livestate = True
        stop_continuous_task = False
    print('livestate now ', livestate)
    # if livestate == True:
        # #Do analysis on this live image
        # # Check if the queue is empty
        
    # Start the live obtain thread if it's not already running
    if not liveObtain_thread.isRunning():
        liveObtain_thread.start()
    
    # if livestate == True:
        #Try to reset pycromanager somehow
        # core.initialize_circular_buffer()
        # core.wait_for_system()
        # core = None
        # core = Core()
        #reset layer napari
        # liveImageLayer = getLayerIdFromName('liveImage')
        # print(liveImageLayer)
        # if not liveImageLayer:
        #     napariViewer.reset_view()
        # else:
        #     napariViewer.layers.remove(napariViewer.layers[liveImageLayer[0]])
    
    while livestate == True:
        core.snap_image()
        tagged_image = core.get_tagged_image()
        if image_queue_liveObtain.qsize()<10:
            image_queue_liveObtain.put(tagged_image)
            yield np.zeros((1))
        else:
            yield np.zeros((1))
    
    if livestate == False:
        #Reset queues and exit threads
        image_queue_liveObtain.queue.clear()
        yield np.zeros((1))

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
    print(analysis_result)
    drawTextOverlay('Text_overlay',analysis_result)
    # drawRandomOverlay('live_overlay')

# Start a separate analysis thread
analysis_thread = AnalysisThread()
analysis_thread.analysis_done_signal.connect(Visualise_Analysis_results)

liveObtain_thread = liveObtainThread()
liveObtain_thread.liveObtain_done_signal.connect(updateNapariLiveView)

def runLiveModeUI(score,sMM_JSON,sform,sapp):
    #Go from self to global variables
    global core, MM_JSON, form, app, livestate, napariViewer, livetextupdater
    core = score
    MM_JSON = sMM_JSON
    form = sform
    app = sapp
    livestate = False

    #Napari start
    napariViewer = napari.Viewer()
    
    # Connect the button's clicked signal to start the async function
    form.liveview_PushButton.clicked.connect(lambda: buttonPressliveStateToggle())

    #Set some common things for the UI (scale bar on and such)
    InitateNapariUI(napariViewer)

    breakpoint

    