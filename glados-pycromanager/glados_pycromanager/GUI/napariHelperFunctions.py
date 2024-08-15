
from PyQt5.QtGui import QIcon
import logging
from napari.qt import thread_worker
import numpy as np

""" 
General napari functions
"""

def getLayerIdFromName(layer_name,napariViewer):
    """ 
    Get the layer ID from the layer name in napari.
    """
    ImageLayer = [i for i, layer in enumerate(napariViewer.layers) if hasattr(layer, '_name') and layer._name == layer_name]
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
        layer.scale = [shared_dataF.core.get_pixel_size_um(),shared_dataF.core.get_pixel_size_um()] #type:ignore
        layer._keep_auto_contrast = True #type:ignore
        napariViewer.reset_view()
        return layer

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
        if layer.data.ndim == 2:
            layer.data = np.expand_dims(layer.data, axis=0)
        if image_data.ndim == 2:
            image_data = np.expand_dims(image_data, axis=0)
        layer.data = np.append(layer.data,image_data,axis=0)
        current_slice = layer.data.shape[0]
        napariViewer.dims.set_current_step(0,current_slice)
        
        #Move the layer to top
        moveLayerToTop(napariViewer,layer_name)
            
    else: #create the layer
        logging.debug('creating layer')
        layer = napariViewer.add_image(image_data,name = layer_name)
        #Set correct scale - in nm
        layer.scale = [shared_dataF.core.get_pixel_size_um(),shared_dataF.core.get_pixel_size_um()] #type:ignore
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
    icon_path = 'glados-pycromanager/glados_pycromanager/GUI/Icons/GladosIcon.ico'
    icon = QIcon(icon_path)
    napariViewer.window._qt_window.setWindowIcon(icon)
    
    #Turn on scalebar
    showScaleBar(napariViewer)