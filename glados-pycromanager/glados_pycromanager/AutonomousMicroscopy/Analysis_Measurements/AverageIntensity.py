
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
import ndtiff

# Required function __function_metadata__
# Should have an entry for every function in this file
def __function_metadata__():
    return {
        "AvgGrayValue": {
            "input":[
                {"name": "Image", "type": [ndtiff.NDTiffDataset]}
            ],
            "output":[
                {"name": "overall_avg_intensity", "type": float, "importance": "Default"},
                {"name": "slice_avg_intensity", "type": [np.array]}
            ],
            "required_kwargs": [
                {"name": "ReqKwarg1", "description": "First required kwarg", "default": 'DefaultKwarg', "type": str},
                {"name": "ReqKwarg2", "description": "Second required kwarg", "default": 0, "type": int}
            ],
            "optional_kwargs": [
                {"name": "OptBool2", "description": "OptBool", "default": 20}
            ],
            "help_string": "Average gray value.",
            "display_name": "Average gray value",
            "visualisation_type" : "value" #'Image', 'points', 'value', or 'shapes'
        }
    }


#-------------------------------------------------------------------------------------------------------------------------------
#Callable functions
#-------------------------------------------------------------------------------------------------------------------------------
def AvgGrayValue(core,**kwargs):
    #Check if we have the required kwargs
    [provided_optional_args, missing_optional_args] = FunctionHandling.argumentChecking(__function_metadata__(),inspect.currentframe().f_code.co_name,kwargs) #type:ignore

    # print(NDTIFFStack._summary_metadata)
    # print(NDTIFFStack.as_array())
    print(kwargs)
    NDTIFFStack = kwargs['Image']
    
    # Compute the average intensity of each slice
    slice_avg_intensity = da.mean(NDTIFFStack.as_array(), axis=(1, 2)) #type:ignore

    #change dask array to np array:
    slice_avg_intensity_np = slice_avg_intensity.compute()

    # Compute the overall average intensity
    overall_avg_intensity = slice_avg_intensity.mean().compute()

    # Print the average intensity of each slice
    # print("Average intensity of each slice:")
    # print(slice_avg_intensity.compute())

    # # Print the overall average intensity
    # print("Overall average intensity:", overall_avg_intensity)
    output = {}
    output['slice_avg_intensity'] = slice_avg_intensity_np
    output['overall_avg_intensity'] = overall_avg_intensity
    
    return output


def AvgGrayValue_visualise(datastruct,core,**kwargs):
    #This is how datastruct is organised...
    output,pointsLayer = datastruct
    
    
    # create features for each point
    features = {
        'outputval': output['overall_avg_intensity']
    }
    textv = {
        'string': 'GrayValue {outputval:.2f}',
        'size': 10,
        'color': 'red',
        'translation': np.array([0, 0]),
        'anchor': 'upper_left',
    }
    pointsLayer.data = [0,0]
    pointsLayer.features = features
    pointsLayer.text = textv
    pointsLayer.size = 0