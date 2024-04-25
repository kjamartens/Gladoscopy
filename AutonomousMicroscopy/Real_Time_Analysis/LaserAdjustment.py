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
        "laser_adjustment": {
            "required_kwargs": [
                {"name": "Laser_id", "description": "LaserID", "default": 2, "type": int},
                {"name": "maxFrame", "description": "Max frames", "default": 100, "type": int}
            ],
            "optional_kwargs": [
            ],
            "help_string": ".",
            "display_name": "LaserAdj",
            "run_delay": 0,
            "visualise_delay": 500
        }
    }


#-------------------------------------------------------------------------------------------------------------------------------
#Callable functions
#-------------------------------------------------------------------------------------------------------------------------------
class laser_adjustment():
    def __init__(self,**kwargs):
        #Check if we have the required kwargs
        class_name = inspect.currentframe().f_locals.get('self', None).__class__.__name__ #type:ignore
        [provided_optional_args, missing_optional_args] = FunctionHandling.argumentChecking(__function_metadata__(),class_name,kwargs) #type:ignore

        propertyname = "TS_DAC02_488Laser"
        MMprop_intensity_name = "Volts"
        ValIntMM = 0
        core.set_property(propertyname, MMprop_intensity_name, str(ValIntMM))
        print('INIT laser_adjustment')
        return None

    def run(self,image,metadata,core,**kwargs):
        print("At frame: "+metadata['ImageNumber'])
        propertyname = "TS_DAC02_488Laser"
        MMprop_intensity_name = "Volts"
        frame = int(metadata['ImageNumber'])
        ValIntMM = min(5,frame/float(kwargs['maxFrame'])*5)
        core.set_property(propertyname, MMprop_intensity_name, str(ValIntMM))
        
            
        # propertyname = MM_JSON["lasers"]["Laser"+str(laserID)]["MM_Property_Name"]
        # MMprop_intensity_name = MM_JSON["lasers"]["MM_Property_Intensity_Name"]

        # #Translate the value to 0-5
        # ValIntMM = ValIntPerc*float(MM_JSON["lasers"]["Laser"+str(laserID)]["Intensity_slope"])-float(MM_JSON["lasers"]["Laser"+str(laserID)]["Intensity_offset"])
        # #Set value in Micromanager
    
    
    def visualise(self,image,metadata,core,**kwargs):
        print('optional visualising every time this is called!')