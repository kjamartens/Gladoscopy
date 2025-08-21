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
        "laser_adjustment": {
            "required_kwargs": [
                {"name": "Laser_id", "description": "LaserID", "default": "TS_DAC02_488Laser", "type": str},
                {"name": "maxFrame", "description": "Max frames", "default": 100, "type": int}
            ],
            "optional_kwargs": [
            ],
            "help_string": ".",
            "display_name": "LaserAdj",
            "run_delay": 0,
            "visualise_delay": 500
        },
        "laser_adjustment_advanced": {
            "required_kwargs": [
                {"name": "Laser_id", "description": "LaserID", "default": "TS_DAC02_488Laser", "type": str},
                {"name": "Laser_power", "description": "Laser power information", "default": "{1:0.01, 2:0.05, 10:1.00}", "type": str}
            ],
            "optional_kwargs": [
            ],
            "help_string": ".",
            "display_name": "Advanced laser adjustment",
            "run_delay": 0,
            "visualise_delay": 500
        }
    }


#-------------------------------------------------------------------------------------------------------------------------------
#Callable functions
#-------------------------------------------------------------------------------------------------------------------------------
class laser_adjustment():
    def __init__(self,core,**kwargs):
        print(core)
        #Check if we have the required kwargs
        class_name = inspect.currentframe().f_locals.get('self', None).__class__.__name__ #type:ignore
        [provided_optional_args, missing_optional_args] = FunctionHandling.argumentChecking(__function_metadata__(),class_name,kwargs) #type:ignore

        propertyname = kwargs['Laser_id']
        MMprop_intensity_name = "Volts"
        ValIntMM = 0
        core.set_property(propertyname, MMprop_intensity_name, str(ValIntMM))
        print('INIT laser_adjustment')
        return None

    def run(self,image,metadata,shared_data,core,**kwargs):
        print("At frame: "+metadata['ImageNumber'])
        propertyname = kwargs['Laser_id']
        MMprop_intensity_name = "Volts"
        frame = int(metadata['ImageNumber'])
        ValIntMM = min(5,frame/float(kwargs['maxFrame'])*5)
        core.set_property(propertyname, MMprop_intensity_name, str(ValIntMM))
        
            
        # propertyname = MM_JSON["lasers"]["Laser"+str(laserID)]["MM_Property_Name"]
        # MMprop_intensity_name = MM_JSON["lasers"]["MM_Property_Intensity_Name"]

        # #Translate the value to 0-5
        # ValIntMM = ValIntPerc*float(MM_JSON["lasers"]["Laser"+str(laserID)]["Intensity_slope"])-float(MM_JSON["lasers"]["Laser"+str(laserID)]["Intensity_offset"])
        # #Set value in Micromanager
    
    
    def end(self,core,**kwargs):
        print('end of laserAdj')
        return
    
    def visualise(self,image,metadata,core,**kwargs):
        print('optional visualising every time this is called!')



class laser_adjustment_advanced():
    def __init__(self,core,**kwargs):
        print(core)
        #Check if we have the required kwargs
        class_name = inspect.currentframe().f_locals.get('self', None).__class__.__name__ #type:ignore
        [provided_optional_args, missing_optional_args] = FunctionHandling.argumentChecking(__function_metadata__(),class_name,kwargs) #type:ignore


        #Set the laser to 0
        propertyname = kwargs['Laser_id']
        MMprop_intensity_name = "Volts"
        ValIntMM = 0
        core.set_property(propertyname, MMprop_intensity_name, str(ValIntMM))
        print('INIT laser_adjustment')
        
        
        self.LaserKeys = list(eval(kwargs['Laser_power']+".keys()"))
        print(self.LaserKeys)

    def run(self,image,metadata,core,**kwargs):
        print("At frame: "+metadata['ImageNumber'])
        propertyname = kwargs['Laser_id']
        MMprop_intensity_name = "Volts"
        frame = int(metadata['ImageNumber'])
        
        ""
        laserPower = eval(kwargs['Laser_power'])
        
        currentLaserPower=0
        for i in reversed(range(len(laserPower))):
            if frame+1 >= self.LaserKeys[i]:
                currentLaserPower = laserPower[self.LaserKeys[i]]
                print(currentLaserPower)
                break
        
        ValIntMM = max(0,min(5,currentLaserPower*5))
        core.set_property(propertyname, MMprop_intensity_name, str(ValIntMM))
    
    def end(self,core,**kwargs):
        print('end of laserAdj')
        return
    
    def visualise(self,image,metadata,core,**kwargs):
        print('optional visualising every time this is called!')