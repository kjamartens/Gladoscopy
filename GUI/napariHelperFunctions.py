
from PyQt5.QtGui import QIcon
import logging

""" 
General napari functions
"""

def getLayerIdFromName(layer_name,napariViewer):
    ImageLayer = [i for i, layer in enumerate(napariViewer.layers) if hasattr(layer, '_name') and layer._name == layer_name]
    return ImageLayer

def InitateNapariUI(napariViewer):
    logging.debug("Napari UI initiated")
    #Set title, icon
    napariViewer.title="GladOS - napari"
    # Set the window icon
    icon_path = './GUI/Icons/GladosIcon.ico'
    icon = QIcon(icon_path)
    napariViewer.window._qt_window.setWindowIcon(icon)
    
    #Turn on scalebar
    napariViewer.scale_bar.visible = True
    napariViewer.scale_bar.unit = "um"
    