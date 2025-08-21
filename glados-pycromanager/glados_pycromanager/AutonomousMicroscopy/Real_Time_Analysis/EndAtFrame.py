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
import time

# Required function __function_metadata__
# Should have an entry for every function in this file
def __function_metadata__():
    return { 
        "EndAtFrame": {
            "required_kwargs": [
                {"name": "LastFrame", "description": "Last frame after which it should be cut off", "default": 50, "type": int}
            ],
            "optional_kwargs": [
            ],
            "help_string": "Examplary method to influence the run",
            "display_name": "Example - influence the run by stopping it at a set frame",
            "run_delay": 0,
            "visualise_delay": 10,
            "visualisation_type": "points", #'image', 'points', 'value', or 'shapes'
            "input":[
            ],
            "output":[
            ],
        }
    }


#-------------------------------------------------------------------------------------------------------------------------------
#Callable functions
#-------------------------------------------------------------------------------------------------------------------------------
class EndAtFrame():
    def __init__(self,core,**kwargs):
        print(core)
        self.initDone = 'Yea'
        #Check if we have the required kwargs
        class_name = inspect.currentframe().f_locals.get('self', None).__class__.__name__ #type:ignore
        [provided_optional_args, missing_optional_args] = FunctionHandling.argumentChecking(__function_metadata__(),class_name,kwargs) #type:ignore

        return None

    def run(self,image,metadata,shared_data,core,**kwargs):
        self.image = image
        self.metadata = metadata
        self.shared_data = shared_data
        self.kwargs = kwargs
        if self.metadata['Axes']['time'] >= int(self.kwargs['LastFrame']):
            #Abort and mark-finished the pycromanager acquisition
            shared_data._mdaModeAcqData.abort()
            shared_data._mdaModeAcqData.mark_finished()
            #Print a statement
            print(f"Ended at frame {self.metadata['Axes']['time']}")
    
    def end(self,core,**kwargs):
        return
    
    def visualise_init(self): 
        #No visualisation implemented
        layerName = 'None'
        layerType = 'points' #layerType has to be from image|labels|points|shapes|surface|tracks|vectors
        return layerName,layerType
    
    def visualise(self,image,metadata,core,napariLayer,**kwargs):
        #No visualisation implemented
        return
    