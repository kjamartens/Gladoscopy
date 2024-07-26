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
                {"name": "OptBool2", "description": "OptBool", "default": False, "type": bool}
            ],
            "help_string": "Sharpness value.",
            "display_name": "Sharpness value",
            "run_delay": 0,
            "visualise_delay": 500,
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

# def testArray_report_redondo(core,position_array_test,zmovestage):
#     res_arr = []
#     for n in range(len(position_array_test)):
#         print(f"n: {n}, abs_pos_arr[n]: {position_array_test[n]}")
#         core.set_position(zmovestage,position_array_test[n]) #type:ignore
#         core.wait_for_system()
#         core.snap_image()
#         im = core.get_tagged_image()
#         im_ndarr = im.pix.reshape((im.tags["Height"],im.tags["Width"]))
#         res_arr.append(np.mean(laplace_filter(im_ndarr)**2))
#     return res_arr

# def single_redondo(core,position,zmovestage):
#     core.set_position(zmovestage,position) #type:ignore
#     core.wait_for_system()
#     core.snap_image()
#     im = core.get_tagged_image()
#     im_ndarr = im.pix.reshape((im.tags["Height"],im.tags["Width"]))
#     return 


#-------------------------------------------------------------------------------------------------------------------------------
#Callable functions
#-------------------------------------------------------------------------------------------------------------------------------
class SharpnessValue():
    def __init__(self,core,**kwargs):
        print(core)
        #Check if we have the required kwargs
        class_name = inspect.currentframe().f_locals.get('self', None).__class__.__name__ #type:ignore
        [provided_optional_args, missing_optional_args] = FunctionHandling.argumentChecking(__function_metadata__(),class_name,kwargs) #type:ignore

        self.currentValue = 0
        return None

    def run(self,image,metadata,core,**kwargs):
        if kwargs['FilterType'] == 'Redondo':
            self.currentValue = (np.mean(laplace_filter(image)**2))
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
        print('VISUALISING!')
            
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