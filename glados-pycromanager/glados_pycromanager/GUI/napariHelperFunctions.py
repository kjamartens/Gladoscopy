from PyQt5.QtGui import QIcon
import logging
import numpy as np
import os
import importlib.util

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
        if shared_dataF.MILcore.get_pixel_size_um() != 0:
            layer.scale = [shared_dataF.MILcore.get_pixel_size_um(),shared_dataF.MILcore.get_pixel_size_um()] #type:ignore
        else:
            logging.error('Pixel size in MM set to 1, probably not set properly in MicroManager, please set this!')
            layer.scale = [1,1] #type:ignore
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
            new_data = np.zeros((2,layer.data.shape[0],layer.data.shape[1]))
            new_data[0,:,:] = layer.data
            new_data[1,:,:] = image_data
        else:
            new_data = np.append(layer.data,image_data[np.newaxis, :, :],axis=0)
        layer_old = layer
        layer_name = layer.name
        
        #Remove the current layer:
        #And add a new one with the old name etc:
        layer = napariViewer.add_image(new_data)
        layer.opacity = layer_old.opacity
        layer.contrast_limits = layer_old.contrast_limits
        layer._keep_auto_contrast = layer_old._keep_auto_contrast
        layer.rendering = layer_old.rendering
        layer.colormap = layer_old.colormap
        layer.scale = layer_old.scale
        layer.scale_factor = layer_old.scale_factor
        layer.translate = layer_old.translate
        layer.gamma = layer_old.gamma
        layer.iso_threshold = layer_old.iso_threshold
        layer.blending = layer_old.blending
        layer.attenuation = layer_old.attenuation
        
        #remove old on
        napariViewer.layers.remove(layer_old)
        
        #Give the new one the old one's name
        layer.name = layer_name
            
        current_slice = layer.data.shape[0]
        napariViewer.dims.set_current_step(0,current_slice)
        
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
        except:
            logging.error("Tried and failed to import glados_pycromanager.")
            pass
        
    
    #Turn on scalebar
    showScaleBar(napariViewer)