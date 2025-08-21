import sys,os
#Sys insert to allow for proper importing from module via debug
if 'glados_pycromanager' not in sys.modules and 'site-packages' not in __file__:
    sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..')))

from glados_pycromanager.AutonomousMicroscopy.MainScripts import FunctionHandling
import math
import numpy as np
import inspect
import dask.array as da
import ndtiff

# Required function __function_metadata__
# Should have an entry for every function in this file
def __function_metadata__():
    return {
        "AvgImage": {
            "input":[
                {"name": "Image", "type": [ndtiff.NDTiffDataset]}
            ],
            "output":[
                {"name": "average_image", "type": [np.array], "importance": "Default"}
            ],
            "required_kwargs": [
            ],
            "optional_kwargs": [
            ],
            "help_string": "Create an average image over time-axis.",
            "display_name": "Average image (time)",
            "visualisation_type" : "image" #'image', 'points', 'value', or 'shapes'
        }
    }


#-------------------------------------------------------------------------------------------------------------------------------
#Callable functions
#-------------------------------------------------------------------------------------------------------------------------------
def AvgImage(core,**kwargs):
    
    #Check if we have the required kwargs
    [provided_optional_args, missing_optional_args] = FunctionHandling.argumentChecking(__function_metadata__(),inspect.currentframe().f_code.co_name,kwargs) #type:ignore

    # print(NDTIFFStack._summary_metadata)
    # print(NDTIFFStack.as_array())
    print(kwargs)
    NDTIFFStack = kwargs['Image']
    
    # Compute the average image
    average_image = da.mean(NDTIFFStack.as_array(), axis=(0)) #type:ignore

    #change dask array to np array:
    average_image_np = average_image.compute()

    output = {}
    output['average_image'] = average_image_np
    
    return output


def AvgImage_visualise(datastruct,core,**kwargs):
    # This is how datastruct is organised...
    output,imageLayer = datastruct
    # Set the layer data
    imageLayer.data = output['average_image']
    # Reset the contrast limits so we can nicely view
    imageLayer.reset_contrast_limits()
    imageLayer.reset_contrast_limits_range()