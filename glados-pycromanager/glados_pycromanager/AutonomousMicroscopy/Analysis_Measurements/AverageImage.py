
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
            "display_name": "Average image (time)"
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


def AvgGrayValue_visualise(datastruct,core,**kwargs):
    #This is how datastruct is organised...
    output,pointsLayer,mdaDataobject = datastruct
    
    
    # create features for each point
    features = {
        'outputval': output
    }
    # textv = {'string': 'Hi!','size':20,'color':'green','translation':np.array([-30,0])}
    textv = {
        'string': 'GrayValue {outputval:.2f}',
        'size': 15,
        'color': 'red',
        'translation': np.array([0, 0]),
        'anchor': 'upper_left',
    }
    pointsLayer.data = [0,0]
    pointsLayer.features = features
    pointsLayer.text = textv
    pointsLayer.size = 0