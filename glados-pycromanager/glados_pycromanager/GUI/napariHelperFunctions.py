
from PyQt5.QtGui import QIcon
import logging
from napari.qt import thread_worker

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