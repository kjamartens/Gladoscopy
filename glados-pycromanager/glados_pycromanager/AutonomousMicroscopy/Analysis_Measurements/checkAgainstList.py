import sys,os
#Sys insert to allow for proper importing from module via debug
if 'glados_pycromanager' not in sys.modules and 'site-packages' not in __file__:
    sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..')))

from glados_pycromanager.AutonomousMicroscopy.MainScripts import FunctionHandling
# from shapely import Polygon, affinity
import math
import numpy as np
import inspect
import dask.array as da
import ndtiff

# Required function __function_metadata__
# Should have an entry for every function in this file
def __function_metadata__():
    return {
        "CheckVsList": {
            "input":[
                {"name": "Position", "type": [np.ndarray,list]}
            ],
            "output":[
                {"name": "within_range", "type": [bool], "importance": "Default"}
            ],
            "required_kwargs": [
                {"name": "List", "description": "List", "default": [], "type": [np.ndarray,list]},
                {"name": "Distance", "description": "List", "default": 10, "type": [int, float]}
            ],
            "optional_kwargs": [
            ],
            "help_string": "Check whether Position is closer than Distance to any entry in List.",
            "display_name": "Check Position for closeness to List",
            "visualisation_type" : "value" #'Image', 'points', 'value', or 'shapes'
        }
    }


#-------------------------------------------------------------------------------------------------------------------------------
#Callable functions
#-------------------------------------------------------------------------------------------------------------------------------
def CheckVsList(core,**kwargs):
    
    #Check if we have the required kwargs
    [provided_optional_args, missing_optional_args] = FunctionHandling.argumentChecking(__function_metadata__(),inspect.currentframe().f_code.co_name,kwargs) #type:ignore

    output = {}
    output['within_range'] = False
    
    try:
        listInfo = eval(kwargs['List'])
    except:
        listInfo = kwargs['List']
        
    if len(listInfo)>0:
        for entry in listInfo:
            if len(entry) == 2:
                try:
                    totalEuclidianDist = math.sqrt((eval(kwargs['Position'])[0]-entry[0])**2 + (eval(kwargs['Position'])[1]-entry[1])**2)
                except:
                    totalEuclidianDist = math.sqrt(((kwargs['Position'])[0]-entry[0])**2 + ((kwargs['Position'])[1]-entry[1])**2)
                if totalEuclidianDist < float(kwargs['Distance']):
                    output['within_range'] = True
                    break
    
    
    return output

