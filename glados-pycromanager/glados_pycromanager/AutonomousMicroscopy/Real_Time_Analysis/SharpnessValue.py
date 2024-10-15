
def is_pip_installed():
    return 'site-packages' in __file__ or 'dist-packages' in __file__

if is_pip_installed():
    from glados_pycromanager.AutonomousMicroscopy.MainScripts import FunctionHandling
else:
    from MainScripts import FunctionHandling
from shapely import Polygon, affinity
import math
import numpy as np
import inspect
import dask.array as da
import time
from scipy import signal

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
            "run_delay": 50,
            "visualise_delay": 100,
            "visualisation_type": "points", #'image', 'points', 'value', or 'shapes'
            "input":[
            ],
            "output":[
            ],
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
class SharpnessValue():
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
            print('FilterType not recognized')
            self.currentValue = 0
    
    def end(self,core,**kwargs):
        return
    
    def visualise_init(self): 
        layerName = 'SharpnessMetric'
        layerType = 'points' #layerType has to be from image|labels|points|shapes|surface|tracks|vectors
        return layerName,layerType
    
    def visualise(self,image,metadata,core,napariLayer,**kwargs):
        # create features for each point
        features = {
            'outputval': self.currentValue
        }
        textv = {
            'string': 'Current sharpness: {outputval:.3f}',
            'size': 15,
            'color': 'red',
            'translation': np.array([0, 0]),
            'anchor': 'upper_left',
        }
        napariLayer.data = [0,0]
        napariLayer.features = features
        napariLayer.text = textv
        # napariLayer.size = 0
        
        # napariLayer.data = np.array([[100,100]])
        # napariLayer.text = text
        napariLayer.symbol = 'disc'
        napariLayer.size = 10
        napariLayer.edge_color='red'
        napariLayer.face_color = 'blue'
        napariLayer.selected_data = []