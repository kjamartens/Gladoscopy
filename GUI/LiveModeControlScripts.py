import numpy as np
from PyQt5.QtCore import QThread, pyqtSignal
import asyncio
import napari
from napari.qt import thread_worker
import random

#Old method for live in PyQT
# async def snap_image_async():
#     # acquire an image and display it
#     print(core.get_exposure())
#     core.snap_image()
#     tagged_image = core.get_tagged_image()
#     # get the pixels in numpy array and reshape it according to its height and width
#     image_array = np.reshape(
#         tagged_image.pix,
#         newshape=[-1, tagged_image.tags["Height"], tagged_image.tags["Width"]],
#     )
#     # for display, we can scale the image into the range of 0~255
#     image_array = (image_array / image_array.max() * 255).astype("uint8")
#     # return the first channel if multiple exists
#     return image_array[0, :, :]


# # async def ButtonTest(val):
# def update_image(im):
#     # Convert your NumPy ndarray (im) to a QImage
#     qimage = qimage2ndarray.array2qimage(im)

#     # Convert your image (im) to a QPixmap
#     # pixmap = QPixmap(100,100)
#     pixmap = QPixmap.fromImage(qimage)

#     # Create a QGraphicsPixmapItem and set it as the background for your QGraphicsView
#     item = QGraphicsPixmapItem(pixmap)
#     # form.liveview_GraphicsView.setScene(QGraphicsScene())
#     scene = QGraphicsScene()

#     # Calculate the scaling factor to fit the QGraphicsScene
#     desired_scene_width = form.liveview_GraphicsView.width()*.95  # Width of the QGraphicsView
#     desired_scene_height = form.liveview_GraphicsView.height()*.95  # Height of the QGraphicsView

#     # Calculate the scaling factors for both width and height
#     scale_width = desired_scene_width / pixmap.width()
#     scale_height = desired_scene_height / pixmap.height()

#     # Use the minimum of the two scaling factors to maintain the aspect ratio
#     scale_factor = min(scale_width, scale_height)
    
#     # Set the scaling factor for the QGraphicsPixmapItem
#     item.setScale(scale_factor)
#     scene.addItem(item)

#     form.liveview_GraphicsView.setScene(scene)

#     # Process pending events to update the GUI asynchronously
#     QCoreApplication.processEvents()

# def buttonPress(async_worker,core):
#     global livestate
#     if livestate:
#         livestate = False
#     else:
#         livestate = True
    
#     while livestate:
#         start = time.time()

#         core.snap_image()
#         tagged_image = core.get_tagged_image()
#         # get the pixels in numpy array and reshape it according to its height and width
#         image_array = np.reshape(
#             tagged_image.pix,
#             newshape=[-1, tagged_image.tags["Height"], tagged_image.tags["Width"]],
#         )
#         # for display, we can scale the image into the range of 0~255
#         image_array = (image_array / image_array.max() * 255).astype("uint8")
#         mid = time.time()
#         update_image(image_array[0,:,:])

#         end = time.time()
#         print('{}\t\t{}'.format(end - mid, mid - start))
#         # async_worker.run()

#     # if livestate == False:
#     #     core.stop_sequence_acquisition()

# # Worker thread to run the async function
# class AsyncWorker(QThread):
#     def run(self):
#         loop = asyncio.new_event_loop()
#         asyncio.set_event_loop(loop)
#         image_data = loop.run_until_complete(snap_image_async())
#         self.dataReady.emit(image_data)

#     dataReady = pyqtSignal(np.ndarray)

def getLayerIdFromName(layer_name):
    ImageLayer = [i for i, layer in enumerate(napariViewer.layers) if hasattr(layer, '_name') and layer._name == layer_name]
    return ImageLayer

def napariUpdateLive(liveImage):
    if liveImage is None:
        return

    liveImageLayer = getLayerIdFromName('liveImage')

    #If it's the first liveImageLayer
    if not liveImageLayer:
        layer = napariViewer.add_image(liveImage, rendering='attenuated_mip')
        #Set correct scale - in nm
        layer.scale = [core.get_pixel_size_um(),core.get_pixel_size_um()]
        layer._keep_auto_contrast = True
        napariViewer.reset_view()
    #Else if the layer already exists, replace it!
    else:
        # layer is present, replace its data
        layer = napariViewer.layers[liveImageLayer[0]]
        # image_shape = layer.data.shape[1:]
        # image_dtype = layer.data.dtype
        layer.data = liveImage#da.concatenate((layer.data, delayed_image), axis=2)

    # we want to show the last file added in the viewer to do so we want to
    # put the slider at the very end. But, sometimes when user is scrolling
    # through the previous slide then it is annoying to jump to last
    # stack as it gets added. To avoid that jump we 1st check where
    # the scroll is and if its not at the last slide then don't move the slider.
    # if napariViewer.dims.point[0] >= layer.data.shape[0] - 2:
    #     napariViewer.dims.set_point(0, layer.data.shape[0] - 1)

@thread_worker(connect={'yielded': napariUpdateLive})
def buttonPressliveStateToggle():
    global livestate
    print(livestate)
    if livestate:
        livestate = False
    else:
        livestate = True

    while livestate == True:
        core.snap_image()
        tagged_image = core.get_tagged_image()
        # get the pixels in numpy array and reshape it according to its height and width
        image_array = np.reshape(
            tagged_image.pix,
            newshape=[-1, tagged_image.tags["Height"], tagged_image.tags["Width"]],
        )
        # for display, we can scale the image into the range of 0~255
        # image_array = (image_array / image_array.max() * 255).astype("uint8")
        yield image_array[0,:,:]

def InitateNapariUI(napariViewer):
    #Turn on scalebar
    napariViewer.scale_bar.visible = True
    napariViewer.scale_bar.unit = "um"

#Testing of a live overlay. Not sure what what but eh
def TestLiveOverlay(layer_name):
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
        edge_color='class',
        face_color='transparent',
    )

def runLiveModeUI(score,sMM_JSON,sform,sapp):
    #Go from self to global variables
    global core, MM_JSON, form, app, livestate, napariViewer
    core = score
    MM_JSON = sMM_JSON
    form = sform
    app = sapp
    livestate = False

    #Napari start
    napariViewer = napari.Viewer()
    
    # async_worker.run_async
    # Connect the button's clicked signal to start the async function
    form.liveview_PushButton.clicked.connect(lambda: buttonPressliveStateToggle())

    #Set some common things for the UI (scale bar on and such)
    InitateNapariUI(napariViewer)

    TestLiveOverlay('liverOverlay')

    breakpoint

    