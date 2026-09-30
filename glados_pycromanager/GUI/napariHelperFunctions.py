import importlib.util
import logging
import os

import numpy as np
from PyQt5.QtGui import QIcon

""" 
General napari functions
"""

def getLayerIdFromName(layer_name,napariViewer,shared_data=None):
    """
    Get the layer ID from the layer name in napari.

    When `shared_data` is passed, a per-viewer name->index cache is kept on it
    so repeated lookups for the same layer name (the live/MDA per-frame hot
    path calls this once or more per frame) don't need a full linear rescan
    of every layer. The cached index is validated with an O(1) name check
    before being trusted; a mismatch (layer removed/reordered/recreated)
    falls back to the full scan and refreshes the cache. Callers that don't
    pass shared_data get the previous unconditional-scan behavior.
    """
    if shared_data is not None:
        cache = getattr(shared_data, '_layer_id_cache', None)
        if cache is None:
            cache = {}
            shared_data._layer_id_cache = cache
        cached_idx = cache.get(layer_name)
        if cached_idx is not None and 0 <= cached_idx < len(napariViewer.layers):
            layer = napariViewer.layers[cached_idx]
            if getattr(layer, '_name', None) == layer_name:
                return [cached_idx]

    ImageLayer = [i for i, layer in enumerate(napariViewer.layers) if hasattr(layer, '_name') and layer._name == layer_name]
    if shared_data is not None and ImageLayer:
        cache[layer_name] = ImageLayer[0]
    return ImageLayer

def showScaleBar(napariViewer):
    """
    Shows the scale bar in napari
    """
    napariViewer.scale_bar.visible = True
    napariViewer.scale_bar.unit = "um"

def checkIfLayerExistsOrCreate(napariViewer,layer_name,layer_type='image',shared_data_throughput = None, required_size = (256,256)):
    """
    Check if a layer with specific name exists. If it does, return this layer. If not, create the layer and return it.
    """ 
    if shared_data_throughput == None:
        shared_dataF = shared_data #assumed to be global #type:ignore
    else:
        shared_dataF = shared_data_throughput
    layerId = getLayerIdFromName(layer_name,napariViewer)
    
    if len(layerId) > 0:
        layer = napariViewer.layers[layerId[0]]
        return layer
    else: #create the layer
        layer = napariViewer.add_image(np.zeros(required_size),name = layer_name)
        #Set correct scale - in nm
        if shared_dataF.MILcore.get_pixel_size_um() != 0:
            layer.scale = [shared_dataF.MILcore.get_pixel_size_um(),shared_dataF.MILcore.get_pixel_size_um()] #type:ignore
        else:
            logging.error('Pixel size in MM set to 1, probably not set properly in MicroManager, please set this!')
            layer.scale = [1,1] #type:ignore
        layer._keep_auto_contrast = True #type:ignore
        napariViewer.reset_view()
        return layer

#: Where the album stack's backing buffer and fill count live. `layer.data` is a
#: view onto the first `count` frames of that buffer, so the buffer itself has to
#: be reachable from the layer to be grown; `layer.metadata` is napari's own
#: place for exactly this.
ALBUM_BUFFER_KEY = '_glados_album_buffer'
ALBUM_COUNT_KEY = '_glados_album_count'

#: Frames the album buffer starts at, and the factor it grows by when full.
#: Geometric growth makes the total copying over a session O(N) amortized
#: instead of the O(N^2) `np.append` used to pay (T-E4).
ALBUM_INITIAL_CAPACITY = 4
ALBUM_GROWTH_FACTOR = 2


def _album_buffer_for(layer, image_data):
    """The album buffer and fill count backing `layer`, rebuilt if unusable.

    Returns `(buffer, count)` where `buffer[:count]` is exactly the stack the
    layer currently shows. Rebuilds (copying whatever frames the layer already
    holds into a fresh buffer) when there is no buffer yet -- the first append
    onto a 2-D layer made by the create branch below -- or when the bookkeeping
    no longer describes the layer, e.g. because the incoming frame changed shape
    or dtype, or something outside this function assigned `layer.data`.
    """
    existing = layer.data
    buffer = layer.metadata.get(ALBUM_BUFFER_KEY)
    count = layer.metadata.get(ALBUM_COUNT_KEY, 0)

    usable = (
        buffer is not None
        and buffer.ndim == 3
        and buffer.shape[1:] == image_data.shape
        and buffer.dtype == image_data.dtype
        and 0 < count <= buffer.shape[0]
        and existing.ndim == 3
        and existing.shape[0] == count
    )
    if usable:
        return buffer, count

    frames = existing if existing.ndim == 3 else existing[np.newaxis, :, :]
    if frames.shape[1:] != image_data.shape:
        # The frame geometry changed under us -- a ROI or binning change part-way
        # through an album. The frames already in the layer cannot be stacked
        # with this one at all, so start a fresh stack rather than raise, which
        # is what `np.append` did here before.
        logging.info('Album frame shape changed from %s to %s; starting a new stack',
                     frames.shape[1:], image_data.shape)
        frames = np.empty((0,) + image_data.shape, dtype=image_data.dtype)
    capacity = max(ALBUM_INITIAL_CAPACITY, frames.shape[0])
    # Explicit dtype, from the frame being added (T-E4). The old two-frame path
    # used a bare `np.zeros(...)`, which is float64 -- so a uint16 camera stack
    # was silently upcast to 4x its size on the second snap, and every
    # `np.append` after that inherited the promotion.
    buffer = np.zeros((capacity,) + image_data.shape, dtype=image_data.dtype)
    buffer[:frames.shape[0]] = frames
    return buffer, frames.shape[0]


def addToExistingOrNewLayer(napariViewer,layer_name,image_data,layer_type='image',shared_data_throughput = None):
    """
    If a layer exist, add an image to it (i.e. album-mode). If it doesn't exist yet, create it.
    """
    if shared_data_throughput == None:
        shared_dataF = shared_data #assumed to be global #type:ignore
    else:
        shared_dataF = shared_data_throughput
    layerId = getLayerIdFromName(layer_name,napariViewer)
    if len(layerId) > 0:
        logging.debug('updating layer')
        layer = napariViewer.layers[layerId[0]]

        # Append into a geometrically grown buffer, and hand napari a view of the
        # filled part (T-E4). This used to `np.append` -- which copies the whole
        # stack on every snap, O(N^2) bytes over a session -- and then destroy
        # the layer and rebuild it with `add_image`, copying a dozen display
        # properties across and forcing a full texture re-upload, per frame.
        # There is no known extent here: album mode is user-driven, one snap at a
        # time, so doubling is the right growth policy rather than preallocating.
        buffer, count = _album_buffer_for(layer, image_data)
        if count >= buffer.shape[0]:
            grown = np.zeros((buffer.shape[0] * ALBUM_GROWTH_FACTOR,) + buffer.shape[1:],
                             dtype=buffer.dtype)
            grown[:count] = buffer[:count]
            buffer = grown
        buffer[count] = image_data
        count += 1

        layer.metadata[ALBUM_BUFFER_KEY] = buffer
        layer.metadata[ALBUM_COUNT_KEY] = count
        # A view, not a copy -- O(1) regardless of stack size. The assignment
        # (rather than an in-place mutation plus `layer.refresh()`) is what tells
        # napari the stack got one frame longer, so the dims slider and the
        # layer's extent track it; napari's data setter refreshes for us.
        layer.data = buffer[:count]

        # The newest frame is at index count-1. The old code passed `count`,
        # one past the end, and relied on napari clamping it.
        napariViewer.dims.set_current_step(0, count - 1)

        #Move the layer to top
        moveLayerToTop(napariViewer,layer_name)

    else: #create the layer
        logging.debug('creating layer')
        layer = napariViewer.add_image(image_data,name = layer_name)
        #Set correct scale - in nm
        if shared_dataF.MILcore.get_pixel_size_um() != 0:
            layer.scale = [shared_dataF.MILcore.get_pixel_size_um(),shared_dataF.MILcore.get_pixel_size_um()] #type:ignore
        else:
            logging.error('Pixel size in MM set to 1, probably not set properly in MicroManager, please set this!')
            layer.scale = [1,1]
        layer._keep_auto_contrast = True #type:ignore
        napariViewer.reset_view()

def moveLayerToTop(napariViewer,layerName,selectLayer=True):
    """
    Move a layer to the top of the layer stack in the napari viewer.
    
    Args:
        napariViewer (napari.Viewer): The napari viewer object.
        layerName (str): The name of the layer to move to the top.
        selectLayer (bool, optional): Whether to select the layer after moving it to the top. Defaults to True.
    
    Returns:
        None
    """
    #check if the layer exist:
    layerExists = False
    if len(napariViewer.layers) > 0:
        for layer in napariViewer.layers:
            if layer.name == layerName:
                layerExists = True
                #Layers are ordered bottom-to-top:
                layerPosition = napariViewer.layers.index(layer)
                break
    if layerExists:
        #Moving to top is moving to the last position in the layer list
        napariViewer.layers.move(layerPosition,len(napariViewer.layers))
        if selectLayer:
            napariViewer.layers.selection.select_only(layer)


# @thread_worker
def InitateNapariUI(napariViewer):
    """
    Initiates the napari UI.

    Args:
        napariViewer (napari.Viewer): The napari viewer object.

    Returns:
        None
    """
    logging.debug("Napari UI initiated")
    #Set title, icon
    napariViewer.title="GladOS - napari"
    # Set the window icon
    if importlib.util.find_spec('glados_pycromanager') is not None:
        import glados_pycromanager
        # Get the installation path of the package
        package_path = os.path.dirname(glados_pycromanager.__file__)
        # Construct the path to the Icons folder
        iconFolder = os.path.join(package_path, 'GUI', 'Icons')

        if not os.path.exists(iconFolder):
            #Find the iconPath folder
            if os.path.exists('./glados_pycromanager/GUI/Icons/General_Start.png'):
                iconFolder = './glados_pycromanager/GUI/Icons/'
            elif os.path.exists('./glados-pycromanager/glados_pycromanager/GUI/Icons/General_Start.png'):
                iconFolder = './glados-pycromanager/glados_pycromanager/GUI/Icons/'
            else:
                iconFolder = ''
                
        icon_path = iconFolder+os.sep+'GladosIcon.ico'
        icon = QIcon(icon_path)
        napariViewer.window._qt_window.setWindowIcon(icon)
    else:
        try:
            import utils
            iconFolder = utils.findIconFolder()
            icon_path = iconFolder+os.sep+'GladosIcon.ico'
            icon = QIcon(icon_path)
            napariViewer.window._qt_window.setWindowIcon(icon)
        except (ImportError, AttributeError, OSError) as exc:
            logging.error('Tried and failed to set napari window icon: %s', exc)
        
    
    #Turn on scalebar
    showScaleBar(napariViewer)