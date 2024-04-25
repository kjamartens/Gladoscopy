from MainScripts import FunctionHandling
from shapely import Polygon, affinity
import math
import numpy as np
import inspect
import dask.array as da
import time

# Required function __function_metadata__
# Should have an entry for every function in this file
def __function_metadata__():
    return {
        "RT_counterV": {
            "required_kwargs": [
                {"name": "ReqKwarg1", "description": "First required kwarg", "default": 'DefaultKwarg', "type": str}
            ],
            "optional_kwargs": [
                {"name": "OptBool2", "description": "OptBool", "default": False, "type": bool}
            ],
            "help_string": "RT counter.",
            "display_name": "RT counter"
        }
    }


#-------------------------------------------------------------------------------------------------------------------------------
#Callable functions
#-------------------------------------------------------------------------------------------------------------------------------
class RT_counterV():
    def __init__(self,**kwargs):
        #Check if we have the required kwargs
        class_name = inspect.currentframe().f_locals.get('self', None).__class__.__name__ #type:ignore
        [provided_optional_args, missing_optional_args] = FunctionHandling.argumentChecking(__function_metadata__(),class_name,kwargs) #type:ignore

        print('in RT_counter at time '+str(time.time()))
        return None

    def run(self,image,metadata,core,**kwargs):
        print('running every time this is called! now at time '+str(time.time()))
        print(image)
        print(metadata)
        print(core)
        print(kwargs)
    
    def visualise(self,image,metadata,core,**kwargs):
        print('optional visualising every time this is called!')