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
        "auto_focus_iter_rel_bf": {
            "input":[
            ],
            "output":[
            ],
            "required_kwargs": [
                {"name": "StageName", "description": "Name of the stage",  "default": 'TIPFSOffset', "type": str},
                {"name": "startPosition", "description": "Starting position, relative from current", "default": -75, "type": float},
                {"name": "endPosition", "description": "Ending position, relative from current", "default": 75, "type": float},
                {"name": "n_positions", "description": "Number of z steps per iteration", "default": 6, "type": int},
                {"name":"aggressiveness", "description": "Higher = more aggressive jumping. 1 would mean no jumping, 10 means zoom in to center 1/10th, etc.", "default": 5, "type": int},
                {"name":"wantedResolution", "description": "Final resolution - i.e. stopping criteria", "default": 0.5, "type": float}
            ],
            "optional_kwargs": [
            ],
            "help_string": "",
            "display_name": "Iterative Auto-focus BF [Relative Position]"
        },
        "auto_focus_iter_abs_bf": {
            "input":[
            ],
            "output":[
            ],
            "required_kwargs": [
                {"name": "StageName", "description": "Name of the stage",  "default": 'TIPFSOffset', "type": str},
                {"name": "startPosition", "description": "Starting position, absolute", "default": 0, "type": float},
                {"name": "endPosition", "description": "Ending position, absolute", "default": 400, "type": float},
                {"name": "n_positions", "description": "Number of z steps per iteration", "default": 6, "type": int},
                {"name":"aggressiveness", "description": "Higher = more aggressive jumping. 1 would mean no jumping, 10 means zoom in to center 1/10th, etc.", "default": 5, "type": int},
                {"name":"wantedResolution", "description": "Final resolution - i.e. stopping criteria", "default": 0.5, "type": float}
            ],
            "optional_kwargs": [
            ],
            "help_string": "",
            "display_name": "Iterative Auto-focus BF [Absolute Position]"
        }
    }


#-------------------------------------------------------------------------------------------------------------------------------
#Callable functions
#-------------------------------------------------------------------------------------------------------------------------------

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

def testArray_report_redondo(core,position_array_test,zmovestage):
    res_arr = []
    for n in range(len(position_array_test)):
        print(f"n: {n}, abs_pos_arr[n]: {position_array_test[n]}")
        core.set_position(zmovestage,position_array_test[n]) #type:ignore
        core.wait_for_system()
        core.snap_image()
        im = core.get_tagged_image()
        im_ndarr = im.pix.reshape((im.tags["Height"],im.tags["Width"]))
        res_arr.append(np.mean(laplace_filter(im_ndarr)**2))
    return res_arr

def single_redondo(core,position,zmovestage):
    core.set_position(zmovestage,position) #type:ignore
    core.wait_for_system()
    core.snap_image()
    im = core.get_tagged_image()
    im_ndarr = im.pix.reshape((im.tags["Height"],im.tags["Width"]))
    return (np.mean(laplace_filter(im_ndarr)**2))


def auto_focus_iter_rel_bf(core,**kwargs):
    
    #Check if we have the required kwargs
    [provided_optional_args, missing_optional_args] = FunctionHandling.argumentChecking(__function_metadata__(),inspect.currentframe().f_code.co_name,kwargs) #type:ignore

    
    #General idea: take images throughout z-stack of BF images, compuate the value/deriv, find the best, set position to that
    import time
    zmovestage = kwargs['StageName']#"TIPFSOffset"
    startp = float(kwargs['startPosition'])#-75 #relative wrt current position
    endp = float(kwargs['endPosition'])#75 #relative wrt current position
    final_offset = 0
    n_per_zoom = int(kwargs['n_positions']) #6
    aggressiveness = int(kwargs['aggressiveness']) # 5 - #higher = more aggressive jumping. 1 would mean no jumping, 10 means zoom in to center 1/10th, etc.
    aggressiveness = 1/aggressiveness
    wantedResolution = float(kwargs['wantedResolution']) #0.5
    
    #These two are hardcoded now.
    maxmaxiter = 10
    max_n_appending = 3
    
    #Get the current absolute position
    start_abs_pos = core.get_position(zmovestage)
    
    #Initialise some variables
    totalIter = 0
    resolutionTest = np.inf
    
    #Get the array of positions to test the resolution
    position_array_test = start_abs_pos+np.linspace(startp,endp,num=n_per_zoom)
    
    #Continue doing all of this untill we're done or maxiter is hit
    import logging
    while resolutionTest > wantedResolution and totalIter < maxmaxiter:
        logging.debug(f"New full redondo test with {(position_array_test)} positions, iter {totalIter}")
        #We test all of these positions
        redondo_arr = testArray_report_redondo(core,position_array_test,zmovestage)
        
        #see if the argmax is at 0 or end and do up to 3 more:
        max_index = np.argmax(redondo_arr)
        while max_index == 0 or max_index == len(redondo_arr)-1:
            logging.debug(f"max index found at {max_index} for array {redondo_arr} with position array {position_array_test}")
            n_appending = 0
            if n_appending < max_n_appending:
                #If we are at the start, we measure another position at the start
                if max_index == 0:
                    additional_position = position_array_test[0]-(position_array_test[1]-position_array_test[0])
                    logging.debug('Doing new position at start at '+str(additional_position))
                    newEntry = single_redondo(core,additional_position,zmovestage)
                    redondo_arr = np.insert(redondo_arr,0,newEntry)
                    position_array_test = np.insert(position_array_test,0,additional_position)
                    max_index = np.argmax(redondo_arr)
                #If we are at the end, we measure another position at the end
                elif max_index == len(redondo_arr)-1:
                    logging.debug('Doing new position at end at '+str(additional_position))
                    additional_position = position_array_test[-1]+(position_array_test[-1]-position_array_test[-2])
                    newEntry = single_redondo(core,additional_position,zmovestage)
                    redondo_arr = np.insert(redondo_arr,len(redondo_arr),newEntry)
                    position_array_test = np.insert(position_array_test,len(position_array_test),additional_position)
                    max_index = np.argmax(redondo_arr)
                n_appending += 1
            else:
                break
        
        #So now we have a good array
        #normalize
        redondo_arr_nrom = redondo_arr/np.max(redondo_arr)
        max_index = np.argmax(redondo_arr_nrom)
        logging.debug(f"final redondo_arr_nrom: {redondo_arr_nrom} at pos {position_array_test}")
        
        #determine the current resolution
        resolutionTest = position_array_test[1]-position_array_test[0]
        
        #Choose the new array:
        splitdiff = aggressiveness*(position_array_test[-1]-position_array_test[0])
        
        new_redondo_arr = np.linspace(position_array_test[max_index]-splitdiff,position_array_test[max_index]+splitdiff,num=n_per_zoom)
        position_array_test = new_redondo_arr
        
        totalIter += 1
    
    #Output nothing.
    output = {}
    
    return output

def auto_focus_iter_abs_bf(core,**kwargs):
    
    #Check if we have the required kwargs
    [provided_optional_args, missing_optional_args] = FunctionHandling.argumentChecking(__function_metadata__(),inspect.currentframe().f_code.co_name,kwargs) #type:ignore

    
    #General idea: take images throughout z-stack of BF images, compuate the value/deriv, find the best, set position to that
    import time
    zmovestage = kwargs['StageName']#"TIPFSOffset"
    startp = float(kwargs['startPosition'])#-75 #ABSOLUTE
    endp = float(kwargs['endPosition'])#75 #ABSOLUTE
    final_offset = 0
    n_per_zoom = int(kwargs['n_positions']) #6
    aggressiveness = int(kwargs['aggressiveness']) # 5 - #higher = more aggressive jumping. 1 would mean no jumping, 10 means zoom in to center 1/10th, etc.
    aggressiveness = 1/aggressiveness
    wantedResolution = float(kwargs['wantedResolution']) #0.5
    
    #These two are hardcoded now.
    maxmaxiter = 10
    max_n_appending = 3
    
    #Get the current absolute position
    start_abs_pos = core.get_position(zmovestage)
    
    #Initialise some variables
    totalIter = 0
    resolutionTest = np.inf
    
    #Get the array of positions to test the resolution
    position_array_test = np.linspace(startp,endp,num=n_per_zoom)
    
    #Continue doing all of this untill we're done or maxiter is hit
    import logging
    while resolutionTest > wantedResolution and totalIter < maxmaxiter:
        logging.debug(f"New full redondo test with {(position_array_test)} positions, iter {totalIter}")
        #We test all of these positions
        redondo_arr = testArray_report_redondo(core,position_array_test,zmovestage)
        
        #see if the argmax is at 0 or end and do up to 3 more:
        max_index = np.argmax(redondo_arr)
        while max_index == 0 or max_index == len(redondo_arr)-1:
            logging.debug(f"max index found at {max_index} for array {redondo_arr} with position array {position_array_test}")
            n_appending = 0
            if n_appending < max_n_appending:
                #If we are at the start, we measure another position at the start
                if max_index == 0:
                    additional_position = position_array_test[0]-(position_array_test[1]-position_array_test[0])
                    logging.debug('Doing new position at start at '+str(additional_position))
                    newEntry = single_redondo(core,additional_position,zmovestage)
                    redondo_arr = np.insert(redondo_arr,0,newEntry)
                    position_array_test = np.insert(position_array_test,0,additional_position)
                    max_index = np.argmax(redondo_arr)
                #If we are at the end, we measure another position at the end
                elif max_index == len(redondo_arr)-1:
                    logging.debug('Doing new position at end at '+str(additional_position))
                    additional_position = position_array_test[-1]+(position_array_test[-1]-position_array_test[-2])
                    newEntry = single_redondo(core,additional_position,zmovestage)
                    redondo_arr = np.insert(redondo_arr,len(redondo_arr),newEntry)
                    position_array_test = np.insert(position_array_test,len(position_array_test),additional_position)
                    max_index = np.argmax(redondo_arr)
                n_appending += 1
            else:
                break
        
        #So now we have a good array
        #normalize
        redondo_arr_nrom = redondo_arr/np.max(redondo_arr)
        max_index = np.argmax(redondo_arr_nrom)
        logging.debug(f"final redondo_arr_nrom: {redondo_arr_nrom} at pos {position_array_test}")
        
        #determine the current resolution
        resolutionTest = position_array_test[1]-position_array_test[0]
        
        #Choose the new array:
        splitdiff = aggressiveness*(position_array_test[-1]-position_array_test[0])
        
        new_redondo_arr = np.linspace(position_array_test[max_index]-splitdiff,position_array_test[max_index]+splitdiff,num=n_per_zoom)
        position_array_test = new_redondo_arr
        
        totalIter += 1
    
    #Output nothing.
    output = {}
    
    return output
