
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
            "display_name": "RT counter",
            "run_delay": 0,
            "visualise_delay": 500,
            "input":[
            ],
            "output":[
            ],
        }
    }


#-------------------------------------------------------------------------------------------------------------------------------
#Callable functions
#-------------------------------------------------------------------------------------------------------------------------------
class RT_counterV():
    def __init__(self,core,**kwargs):
        print(core)
        #Check if we have the required kwargs
        class_name = inspect.currentframe().f_locals.get('self', None).__class__.__name__ #type:ignore
        [provided_optional_args, missing_optional_args] = FunctionHandling.argumentChecking(__function_metadata__(),class_name,kwargs) #type:ignore

        print('in RT_counter at time '+str(time.time()))
        return None

    def run(self,image,metadata,core,**kwargs):
        if 'ImageNumber' in metadata:
            print("At frame: "+metadata['ImageNumber'])
        else:
            print("At axis-time: "+str(metadata['Axes']['time']))
        print(kwargs)
    
    def end(self,core,**kwargs):
        print('end of RTcounter')
        return
    
    def visualise_init(self): 
        layerName = 'RT counter'
        layerType = 'points' #layerType has to be from image|labels|points|shapes|surface|tracks|vectors
        return layerName,layerType
    
    def visualise(self,image,metadata,core,napariLayer,**kwargs):
        print('VISUALISING!')
        print(metadata['ImageNumber'])
        print(type(metadata['ImageNumber']))
            
        # create features for each point
        features = {
            'outputval': int(metadata['ImageNumber'])
        }
        textv = {
            'string': 'Current Frame: {outputval:.2f}',
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