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
# Define a flag to control the continuous task
stop_continuous_task = False
total_th1 = 0;
lock = threading.Lock()

# Create a queue to pass image data between threads
image_queue = queue.Queue()

# Create a signal to communicate between threads
analysis_done_signal = pyqtSignal(object)

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

    #Do analysis on this live image
    # Check if the queue is empty
    if image_queue.empty():
        image_queue.put(liveImage)
        # Start the analysis thread if it's not already running
        if not analysis_thread.isRunning():
            analysis_thread.start()
    
    liveImageLayer = getLayerIdFromName('liveImage')

    #If it's the first liveImageLayer
    if not liveImageLayer:
        nrLayersBefore = len(napariViewer.layers)
        print(nrLayersBefore)
        layer = napariViewer.add_image(liveImage, rendering='attenuated_mip')
        #Set correct scale - in nm
        layer.scale = [core.get_pixel_size_um(),core.get_pixel_size_um()]
        layer._keep_auto_contrast = True
        napariViewer.reset_view()
        napariViewer.layers.move_multiple([nrLayersBefore,0])
    #Else if the layer already exists, replace it!
    else:
        # layer is present, replace its data
        layer = napariViewer.layers[liveImageLayer[0]]
        layer.data = liveImage
    
@thread_worker(connect={'yielded': napariUpdateLive})
def buttonPressliveStateToggle():
    global livestate, stop_continuous_task
    print(livestate)
    if livestate:
        livestate = False
        stop_continuous_task = True
    else:
        livestate = True
        stop_continuous_task = False

    while livestate == True:
        core.snap_image()
        tagged_image = core.get_tagged_image()
        # get the pixels in numpy array and reshape it according to its height and width
        image_array = np.reshape(
            tagged_image.pix,
            newshape=[-1, tagged_image.tags["Height"], tagged_image.tags["Width"]],
        )
        
        #When image is arrived from MM, we yield it to napariUpdateLive
        yield image_array[0,:,:]
 
#This code gets some image and does some analysis on this
class AnalysisThread(QThread):
    # Create a signal to communicate between threads
    analysis_done_signal = pyqtSignal(object)
    
    def run(self):
        while True:
            liveImage = image_queue.get()
            time.sleep(1)
            print('Some analysis done after sleeping?')
            analysis_result = 10
            self.analysis_done_signal.emit(analysis_result)

def Visualise_Analysis_results(analysis_result):
    print(analysis_result)
    drawRandomOverlay('live_overlay')

# Start a separate analysis thread
# analysis_thread = threading.Thread(target=analysis_thread)
# analysis_thread.daemon = True
# analysis_thread.start()
analysis_thread = AnalysisThread()
analysis_thread.analysis_done_signal.connect(Visualise_Analysis_results)

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

    