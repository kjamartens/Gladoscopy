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
        "auto_focus_bf": {
            "input":[
            ],
            "output":[
            ],
            "required_kwargs": [
                {"name": "StageName", "description": "Name of the stage",  "default": 'TIPFSOffset', "type": str},
                {"name": "startPosition", "description": "Starting position, relative from current", "default": -75, "type": float},
                {"name": "endPosition", "description": "Ending position, relative from current", "default": 75, "type": float},
                {"name": "numsteps", "description": "Number of z steps", "default": 2, "type": int}
            ],
            "optional_kwargs": [
                {"name": "final_offset", "description": "Final offset from 'perfect' position", "default": 6, "type": float}
            ],
            "help_string": "",
            "display_name": "Auto-focus BF"
        }
    }


#-------------------------------------------------------------------------------------------------------------------------------
#Callable functions
#-------------------------------------------------------------------------------------------------------------------------------
def auto_focus_bf(core,**kwargs):
    
    #Check if we have the required kwargs
    [provided_optional_args, missing_optional_args] = FunctionHandling.argumentChecking(__function_metadata__(),inspect.currentframe().f_code.co_name,kwargs) #type:ignore

    print(kwargs)
    
    #General idea: take images throughout z-stack of BF images, compuate the value/deriv, find the best, set position to that
    import time
    zmovestage = kwargs['StageName']#"TIPFSOffset"
    startp = float(kwargs['startPosition'])#-75
    endp = float(kwargs['endPosition'])#75
    numsteps = int(kwargs['numsteps'])#50
    final_offset = float(kwargs['final_offset'])#6
    
    minval = startp
    valstep = (endp-startp)/numsteps
    
    from scipy import signal
    def laplace_filter(image):
        """Applies a sort-of Laplace filter to an image.

        Args:
        image: A NumPy array representing the image.

        Returns:
        A NumPy array representing the filtered image.
        """
        
        #Note that this kernel is not a typo - this is how it should be.
        kernel = np.array([[0, 1, 0],
                        [1, 0, 1],
                        [0, -3, 0]])
        filtered_image = signal.convolve2d(image, kernel)
        return filtered_image
    
    redondo_arr = []

    core.set_relative_position(zmovestage,minval) #type:ignore
    core.wait_for_system()
    for n in range(numsteps):
        print(n)
        core.set_relative_position(zmovestage,valstep) #type:ignore
        core.wait_for_system()
        core.snap_image()
        # core.wait_for_system()
        im = core.get_tagged_image()
        im_ndarr = im.pix.reshape((im.tags["Height"],im.tags["Width"]))
        
        redondo_arr.append(np.mean(laplace_filter(im_ndarr)**2))
    
    from scipy.signal import savgol_filter
    derivRedondo = np.gradient(savgol_filter(redondo_arr, window_length=int(numsteps/20)+1, polyorder=1))
    #make the top and bottom 5% of points 0:
    derivRedondo[:int(len(derivRedondo)*0.05)] = np.mean(derivRedondo)
    derivRedondo[int(len(derivRedondo)*0.95):] = np.mean(derivRedondo)
    #check if the peak is negative or positive:
    if sum(derivRedondo) < 0:
        derivRedondo *= -1
    derivRedondo_smoothed = savgol_filter(derivRedondo, window_length=int(numsteps/20)+1, polyorder=1)
    #Find the max of the deriv:
    derivRedondo_max_index = np.argmax(derivRedondo_smoothed)
    print(f"derivRedondo_max_index max: {derivRedondo_max_index}")
    
    #Currently, we're at the max pos, so we move to the final position:
    #Factually, we're moving to the start (endp*-1 + startp), then move the derivRedondo offset, then add a final_offset
    core.set_relative_position(zmovestage,endp*-1+startp+valstep*derivRedondo_max_index+final_offset) #type:ignore
    
    
    output = {}
    
    return output


def auto_focus_bf_visualise(datastruct,core,**kwargs):
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