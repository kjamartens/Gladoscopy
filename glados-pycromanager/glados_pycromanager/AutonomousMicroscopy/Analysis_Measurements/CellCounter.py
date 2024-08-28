
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
        "CellCounter": {
            "input":[
                {"name": "Image", "type": [da.Array, np.ndarray, ndtiff.NDTiffDataset]}
            ],
            "output":[
                {"name": "n_cells", "type": int, "importance": "Default"},
            ],
            "required_kwargs": [
            ],
            "optional_kwargs": [
            ],
            "help_string": "Counts shapes.",
            "display_name": "Cell Counter"
        }
    }


#-------------------------------------------------------------------------------------------------------------------------------
#Callable functions
#-------------------------------------------------------------------------------------------------------------------------------
def CellCounter(dataobject,core,**kwargs):
    
    #Check if we have the required kwargs
    [provided_optional_args, missing_optional_args] = FunctionHandling.argumentChecking(__function_metadata__(),inspect.currentframe().f_code.co_name,kwargs) #type:ignore

    # print(NDTIFFStack._summary_metadata)
    # print(NDTIFFStack.as_array())
    
    
    n_cells = np.max(np.max(dataobject['labels']))
    
    # Print the average intensity of each slice
    # print("Average intensity of each slice:")
    # print(slice_avg_intensity.compute())

    # # Print the overall average intensity
    # print("Overall average intensity:", overall_avg_intensity)
    
    return n_cells


def AvgGrayValue_visualise(datastruct,core,**kwargs):
    #This is how datastruct is organised...
    output,pointsLayer,mdaDataobject = datastruct
    
    
    # create features for each point
    features = {
        'outputval': output
    }
    textv = {
        'string': 'Nr cells: {outputval:.0f}',
        'size': 15,
        'color': 'red',
        'translation': np.array([0, 0]),
        'anchor': 'upper_left',
    }
    pointsLayer.data = [0,0]
    pointsLayer.features = features
    pointsLayer.text = textv
    pointsLayer.size = 0