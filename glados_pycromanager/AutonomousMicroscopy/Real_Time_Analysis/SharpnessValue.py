import os
import sys

#Sys insert to allow for proper importing from module via debug
if 'glados_pycromanager' not in sys.modules and 'site-packages' not in __file__:
    sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..')))

import inspect
import logging

# from shapely import Polygon, affinity
import math
import time

import dask.array as da
import numpy as np
from scipy import signal

from glados_pycromanager.AutonomousMicroscopy.MainScripts import FunctionHandling
from glados_pycromanager.autonomous.registry import register


# Required function __function_metadata__
# Should have an entry for every function in this file
def __function_metadata__():
    return {
        "SharpnessValue": {
            "required_kwargs": [
                {"name": "FilterType", "description": "Filter Type ([Laplacian, Redondo])", "default": 'Laplacian', "type": str}
            ],
            "optional_kwargs": [
            ],
            "help_string": "Sharpness value.",
            "display_name": "Sharpness value",
            "run_delay": 200,
            "visualise_delay": 200,
            "visualisation_type": "points", #'image', 'points', 'value', or 'shapes'
            "input":[
            ],
            "output":[
            ],
            # run() touches nothing but the frame and its own kwargs (a
            # convolution per frame, in numpy/cv2, holding the GIL), so it is
            # isolated in its own process - see
            # utils.realTimeAnalysis_runInSubprocess.
            "__runInSubprocess__": True,
            # What visualise() reads that run() produces. `firstLayerInit` is
            # set by visualise_init() on the main-process shadow instance and
            # must not be mirrored from the child.
            "__snapshot_attrs__": ["currentValue"],
        }
    }



def laplace_filter(image):
    """Applies a sort-of Laplace filter to an image.

    Args:
    image: A NumPy array representing the image.

    Returns:
    A NumPy array representing the filtered image.
    """
    
    #Note that this kernel is not a typo - this is how it should be.
    kernel = np.array([[0, 1, 0],
                    [1, 0, 1],
                    [0, -3, 0]])
    filtered_image = signal.convolve2d(image, kernel)
    return filtered_image

def blur_laplace(image):
    import cv2
    blurrad = 3
    blurim = cv2.GaussianBlur(image, (blurrad,blurrad), 1)
    edgemap = cv2.Laplacian(blurim,  cv2.CV_64F)
    return edgemap

#-------------------------------------------------------------------------------------------------------------------------------
#Callable functions
#-------------------------------------------------------------------------------------------------------------------------------
@register("SharpnessValue.SharpnessValue")
class SharpnessValue:
    def __init__(self,core,**kwargs):
        #Check if we have the required kwargs
        class_name = inspect.currentframe().f_locals.get('self', None).__class__.__name__ #type:ignore
        [provided_optional_args, missing_optional_args] = FunctionHandling.argumentChecking(__function_metadata__(),class_name,kwargs) #type:ignore

        self.currentValue = 0
        return None

    def run(self,image,metadata,shared_data,core,**kwargs):
        if kwargs['FilterType'] == 'Redondo':
            self.currentValue = (np.mean(laplace_filter(image)**2))*1e-6
        elif kwargs['FilterType'] == 'Laplacian':
            self.currentValue = (np.mean(blur_laplace(image)**2))
        else:
            logging.warning("FilterType not recognized")
            self.currentValue = 0
    
    def end(self,core,**kwargs):
        return
    
    def visualise_init(self):
        layerName = 'SharpnessMetric'
        layerType = 'points' #layerType has to be from image|labels|points|shapes|surface|tracks|vectors
        self.firstLayerInit = True
        return layerName,layerType

    def visualise(self,image,metadata,core,napariLayer,**kwargs):
        # Only the feature value changes each frame
        features = {
            'outputval': self.currentValue
        }
        napariLayer.features = features
        if self.firstLayerInit:
            napariLayer.data = np.array([[0, 0]])
            textv = {
                'string': 'Current sharpness: {outputval:.3f}',
                'size': 15,
                'color': 'red',
                'translation': np.array([0, 0]),
                'anchor': 'upper_left',
            }
            napariLayer.text = textv
            napariLayer.symbol = 'disc'
            napariLayer.size = 10
            napariLayer.edge_color = 'red'
            napariLayer.face_color = 'blue'
            napariLayer.selected_data = []
            self.firstLayerInit = False